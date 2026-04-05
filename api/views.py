from rest_framework.decorators import api_view
from django.http import JsonResponse, HttpResponse
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from django.forms.models import model_to_dict
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook
import json
import datetime
import traceback
import secrets

from .models import read_users, billings, readings, users, Logs, Admin
from .serializers import NewUserSerializer, WaterUserSerializer


# =========================================
# 1. USER PROFILE (SAFE VERSION)
# =========================================
@api_view(["GET"])
def user_profile(request, user_id):
    try:
        user = read_users.objects.filter(id=user_id).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        user_readings = readings.objects.filter(user=user)
        user_billings = billings.objects.filter(user_id=user.id)

        latest_reading = user_readings.order_by("-id").first()

        total_units = user_readings.aggregate(Sum("units_used"))["units_used__sum"] or 0
        total_bill = user_billings.aggregate(Sum("bill"))["bill__sum"] or 0
        total_paid = user_billings.aggregate(Sum("paid"))["paid__sum"] or 0

        return Response({
            "personal_info": {
                "id": user.id,
                "name": user.fname,
                "phone": user.phone,
                "zone": user.zone,
                "metre": user.metre_num,
                "rate": user.rate,
            },
            "usage_summary": {
                "total_units_used": total_units,
                "number_of_readings": user_readings.count(),
                "prev": latest_reading.prev_user if latest_reading else 0,
                "cur": latest_reading.cur_user if latest_reading else 0,
            },
            "billing_summary": {
                "total_bill": total_bill,
                "total_paid": total_paid,
                "total_balance": total_bill - total_paid,
                "status": "Paid" if (total_bill - total_paid) <= 0 else "Unpaid",
            },
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# =========================================
# 2. GET ALL USERS
# =========================================
'''
def water_users(request):
    users_data = read_users.objects.values(
        'id', 'fname', 'phone', 'metre_num', 'zone', 'rate', 'created_on'
    )

    data = []
    for user in users_data:
        if isinstance(user['created_on'], (datetime.date, datetime.datetime)):
            user['created_on'] = user['created_on'].isoformat()
        data.append(user)

    return JsonResponse(data, safe=False)
'''
def water_users(request):
    users = read_users.objects.all()
    data = []
    for u in users:
        data.append({
            'id' : u.id,
            'fname' : u.fname,
            'phone' : u.phone,
            'metre_num' : u.metre_num,
            'zone' : u.zone,
            'rate' : u.rate,
            'created_on' : u.created_on
        })
    return JsonResponse(data, safe=False)

# =========================================
# 3. CRUD (VIEWSET)
# =========================================
class WaterUserViewSet(viewsets.ModelViewSet):
    queryset = read_users.objects.all()
    serializer_class = WaterUserSerializer


# =========================================
# 4. BILLINGS
# =========================================
def bill(request):
    bills = billings.objects.values(
        'id', 'user_id', 'name', 'phone', 'billed_on',
        'units_used', 'rate', 'bill', 'paid', 'bal'
    )
    return JsonResponse(list(bills), safe=False)


# =========================================
# 5. LOGS
# =========================================
def logs(request):
    try:
        return JsonResponse(list(Logs.objects.all().values()), safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)})


# =========================================
# 6. UPDATE PAYMENT
# =========================================
@api_view(["POST"])
def update_paid(request):
    try:
        billing = billings.objects.get(id=request.data.get("id"))

        from decimal import Decimal
        billing.paid = Decimal(request.data.get("paid"))
        billing.save()

        return Response({
            "message": "Updated",
            "paid": float(billing.paid),
            "bal": float(billing.bal),
            "status": billing.status
        })

    except billings.DoesNotExist:
        return Response({"error": "Not found"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=400)


# =========================================
# 7. READINGS (LATEST ONLY)
# =========================================
def read_data(request):
    readings_data = readings.objects.all().order_by("-id")

    data = []
    seen_users = set()

    for r in readings_data:
        if r.user_id in seen_users:
            continue

        obj = model_to_dict(r)

        for k, v in obj.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                obj[k] = v.isoformat()

        data.append(obj)
        seen_users.add(r.user_id)

    return JsonResponse(data, safe=False)


# =========================================
# 8. ANALYTICS
# =========================================
@api_view(["GET"])
def total_units(request):
    return Response({"total_units": readings.total_units()})


@api_view(["GET"])
def total_bill(request):
    return Response({"total_bill": billings.total_bill()})


@api_view(["GET"])
def total_paid(request):
    return Response({"total_paid": billings.total_paid()})


@api_view(["GET"])
def total_cust(request):
    return Response({"total_cust": read_users.total_cust()})


@api_view(["GET"])
def avg_units(request):
    return Response({"avg_units": readings.avg_units()})


# =========================================
# 9. CREATE USER
# =========================================
@api_view(['POST'])
def new_user(request):
    try:
        with transaction.atomic():
            serializer = NewUserSerializer(data=request.data)

            if serializer.is_valid():
                user = serializer.save()
                return Response({"message": "User created", "id": user.id})

            return Response(serializer.errors, status=400)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# =========================================
# 10. NEW READING + BILLING
# =========================================
@api_view(["POST"])
def submit_new_reading(request):
    try:
        user_id = request.data.get("user_id")

        last = readings.objects.filter(user_id=user_id).order_by("-id").first()
        if not last:
            return Response({"error": "No previous reading"}, status=400)

        new = readings.objects.create(
            user_id=user_id,
            name=last.name,
            phone=last.phone,
            prev_user=last.cur_user,
            prev_sup=last.cur_sup,
            prev_date=last.cur_date,
            cur_user=request.data.get("cur_user"),
            cur_sup=request.data.get("cur_sup"),
            cur_date=timezone.now().date(),
            rate=last.rate
        )

        units = new.cur_user - new.prev_user

        billings.objects.create(
            user_id=user_id,
            name=new.name,
            phone=new.phone,
            units_used=units,
            rate=new.rate,
            bill=units * new.rate,
            paid=0,
            bal=units * new.rate,
            status="Unpaid"
        )

        return Response({"message": "Reading + billing created"})

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# =========================================
# 11. EXPORT EXCEL
# =========================================
def export_readings_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "User", "Units"])

    for r in readings.objects.all():
        ws.append([r.id, r.user_id, r.units_used])

    response = HttpResponse(content_type="application/vnd.ms-excel")
    response['Content-Disposition'] = 'attachment; filename="readings.xlsx"'
    wb.save(response)
    return response


# =========================================
# 12. LOGIN (ADMIN)
# =========================================
@csrf_exempt
def login_user(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    data = json.loads(request.body)

    user = Admin.objects.filter(
        username=data.get("username"),
        password=data.get("password")
    ).first()

    if user:
        return JsonResponse({
            "token": secrets.token_hex(32),
            "username": user.username
        })

    return JsonResponse({"error": "Invalid credentials"}, status=401)


# =========================================
# 13. LOGIN (USERS)
# =========================================
@api_view(['POST'])
def login_users(request):
    user = users.objects.filter(
        username=request.data.get("username"),
        password=request.data.get("password")
    ).first()

    if user:
        return Response({
            "token": secrets.token_hex(32),
            "role": user.role,
            "username": user.username,
            "id": user.id
        })

    return Response({"error": "Invalid credentials"}, status=401)