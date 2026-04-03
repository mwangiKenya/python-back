from rest_framework.decorators import api_view
from django.http import JsonResponse
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status, viewsets
from .models import  read_users, billings, readings, users, Logs
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils import timezone
import traceback
from .serializers import NewUserSerializer, UpdateReadingsSerializer
import datetime
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from .serializers import WaterUserSerializer
from django.db.models import Sum


@api_view(["GET"])
def user_profile(request, user_id):
    try:
        user = read_users.objects.get(id=user_id)
        reading = readings.objects.get(id=user_id)
        billing = billings.objects.get(id=user_id)

        user_readings = readings.objects.filter(user=user)
        user_billings = billings.objects.filter(user_id=user.id)

        total_units = user_readings.aggregate(Sum("units_used"))["units_used__sum"] or 0
        total_bill = user_billings.aggregate(Sum("bill"))["bill__sum"] or 0
        total_paid = user_billings.aggregate(Sum("paid"))["paid__sum"] or 0
        total_balance = total_bill - total_paid

        data = {
            "personal_info": {
                "id": user.id,
                "name": f"{user.fname}",  # combine first and last
                "phone": user.phone,
                "zone": user.zone,
                "metre": user.metre_num,
                "rate": user.rate,
            },
            "usage_summary": {
                "total_units_used": total_units,
                "number_of_readings": user_readings.count(),
                "prev": reading.prev_user,
                "cur" : reading.cur_user,
            },
            "billing_summary": {
                "total_bill": total_bill,
                "total_paid": total_paid,
                "total_balance": total_balance,
                "status": "Paid" if total_balance <= 0 else "Unpaid",
            },
        }

        return Response(data)

    except read_users.DoesNotExist:
        return Response({"error": "User not found"}, status=404)
    except Exception as e:
        # Catch any other unexpected errors
        return Response({"error": str(e)}, status=500)








#FETCH THE WATER USERS DATA FROM THE DATABASE TO DISPLAY ON FRONTEND
#USE THE MODEL CLASS (READ_USERS) FROM MODELS
def water_users(request):
    # Fetch only the fields you need
    users = read_users.objects.values(
        'id', 'fname', 'phone', 'metre_num', 'zone', 'rate', 'created_on'
    )

    data_list = []
    for user in users:
        # Serialize date to ISO
        if isinstance(user['created_on'], (datetime.date, datetime.datetime)):
            user['created_on'] = user['created_on'].isoformat()
        data_list.append(user)

    return JsonResponse(data_list, safe=False)

#===============================================================
#Allow the update and deleting of the user data from the frontend
class WaterUserViewSet(viewsets.ModelViewSet):
    queryset = read_users.objects.all()
    serializer_class = WaterUserSerializer

#USE THE BILLINGS MODEL CLASS FROM MODELS
#FETCH THE BILLINGS DATA FROM DATABASE TO DISPLAY ON THE FRONTEND
def bill(request):
    bills = billings.objects.values(
        'id', 'user_id', 'name', 'phone', 'billed_on', 'units_used','rate', 'bill', 'paid', 'bal'
    )
    return JsonResponse(list(bills), safe=False)
#==================================================================================
#USE THE LOGS MODEL FROM THE MODELS
#FETCH THE LOGS DATA TO DISPLAY THEM ON FRONTEND
'''
def logs(request):
    log = Logs.objects.all()
    data = []

    for a in log:
        data.append({
            'id': a.id,
            'reading': a.reading_id,
            'field_changed': a.field_changed,
            'old_val': a.old_val,
            'new_val': a.new_val,
            'changed_at': a.changed_at.isoformat() if a.changed_at else None
        })

    return JsonResponse(data, safe=False)
'''
def logs(request):
    try:
        log = Logs.objects.all().values()
        return JsonResponse(list(log), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)})
#==================================================================================
#UPDATE THE PAID AMOUNT IN BILLINGS
@api_view(["POST"])
def update_paid(request):
    billing_id = request.data.get("id")
    paid = request.data.get("paid")

    try:
        billing = billings.objects.get(id=billing_id)
        # Convert paid to Decimal (or float)
        from decimal import Decimal
        billing.paid = Decimal(paid)
        billing.bal = float(billing.bill) - float(paid)
        billing.save()
        # Return the updated billing info
        return Response({
            "message": "Saved successfully",
            "id": billing.id,
            "paid": float(billing.paid),
            "bal": float(billing.bal),
            "status": billing.status
        })
    except billings.DoesNotExist:
        return Response({"error": "Billing not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


#FETCH THE READINGS DATA AND DISPLAY THEM ON THE FRONTEND

def read_data(request):
    data_list = []
    all_readings = readings.objects.all()  # fetch model instances

    for obj in all_readings:
        obj_dict = model_to_dict(obj)  # convert model to dict
        # Serialize dates to ISO format
        for key, value in obj_dict.items():
            if isinstance(value, (datetime.date, datetime.datetime)):
                obj_dict[key] = value.isoformat()
        data_list.append(obj_dict)

    return JsonResponse(data_list, safe=False)
#FETCH THE ANALYTICS SUMS AND DISPLAY THEM ON THE PAGE
@api_view(["GET"])
def total_units(request):
    return Response({
        "total_units": readings.total_units()
    })


#FETCH THE TOTAL AMOUNT OF BILLING AND DISPLAY IT ON THE FRONTEND
@api_view(["GET"])
def total_bill(request):
    return Response({
        "total_bill": billings.total_bill()
    })

#FETCH THE TOTAL AMOUNT BILLED FROM THE BILLINGS TABLE
@api_view(["GET"])
def total_paid(request):
    return Response({
        "total_paid" : billings.total_paid()
    })

#FETCH THE TOTAL NUMBER OF CUSTOMERS
#AND DISPLAY THEM ON THE FRONTEND
@api_view(["GET"])
def total_cust(request):
    return Response({
        "total_cust": read_users.total_cust()
    })

#READ THE AVERAGE OF UNITS_USED FROM THE READINGS TABLE
#AND DISPLAY THEM ON THE FRONTEND
@api_view(["GET"])
def avg_units(reauest):
    return Response({
        "avg_units": readings.avg_units()
    })


#INSERT WATER USERS DATA TO THE DATABASE
#USE THE WATER_USERS MODEL CLASS FROM THE MODELS


# views.py


@api_view(['POST'])
def new_user(request):
    try:
        with transaction.atomic():
            serializer = NewUserSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()  # handles both water_users and readings
                return Response({
                    "fname": user.fname,
                    #"sname": user.sname,
                    "phone": user.phone,
                    "metre_num": user.metre_num,
                    "zone": user.zone,
                    "rate": user.rate,
                    "created_on": user.created_on,
                    "message": "User added successfully and readings initialized"
                })
            else:
                return Response(serializer.errors, status=400)
    except Exception as e:
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)



# --- 2. update_readings view with serializer ---
@csrf_exempt
def update_readings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)

        with transaction.atomic():
            for item in data:
                reading_id = item.get("id")

                # Lock the readings row
                reading = readings.objects.select_for_update().get(id=reading_id)

                # Use serializer for safe update
                serializer = UpdateReadingsSerializer(instance=reading, data=item, partial=True)
                if serializer.is_valid():
                    serializer.save()  # handles both readings update and billings
                else:
                    return JsonResponse({"error": serializer.errors}, status=400)

        return JsonResponse({"message": "Readings and billings updated successfully"})

    except readings.DoesNotExist:
        return JsonResponse({"error": f"Reading with id {reading_id} not found"}, status=404)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
    


#===================================================================
#CREATE AN EXCEL FILES TO READ DATA TO DOWNLOAD IN THE FRONEND
# backend/api/views.py
from django.http import HttpResponse
from openpyxl import Workbook

def export_readings_excel(request):
    # 1️⃣ Create a workbook and sheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Readings"

    # 2️⃣ Write header row
    ws.append(["ID", "User", "Name", "Phone", "Prev User", "Cur User", "Units Used"])

    # 3️⃣ Write all data rows
    all_readings = readings.objects.all()
    for r in all_readings:
        ws.append([
            r.id,
            r.user.id,
            r.name,
            r.phone,
            r.prev_user,
            r.cur_user,
            r.units_used
        ])

    # 4️⃣ Prepare the response as an Excel file
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="readings.xlsx"'
    wb.save(response)
    return response


#===================================================
#DOWNLOAD THE BILLINGS FILE
def export_billings_excel(request):
    # 1️⃣ Create a workbook and sheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Billings"

    # 2️⃣ Write header row
    ws.append(["USER ID", "NAME", "PHONE", "DATE BILLED", "UNITS USED", "BILLED AMOUNT"])

    # 3️⃣ Write all data rows
    all_bills = billings.objects.all()
    for b in all_bills:
        ws.append([
            b.user_id,
            b.name,
            b.phone,
            b.billed_on,
            b.units_used,
            b.bill
        ])

    # 4️⃣ Prepare the response as an Excel file
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="billings.xlsx"'
    wb.save(response)
    return response




#===================================================
#DOWNLOAD THE WATER USERS FILE
def export_users_excel(request):
    # 1️⃣ Create a workbook and sheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"

    # 2️⃣ Write header row
    ws.append(["FIRST NAME", "PHONE", "EMAIL", "REG. DATE"])

    # 3️⃣ Write all data rows
    all_users = read_users.objects.all()
    for c in all_users:
        ws.append([
            c.fname,
            c.phone,
            c.email,
            c.created_on
        ])

    # 4️⃣ Prepare the response as an Excel file
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="billings.xlsx"'
    wb.save(response)
    return response


#===================================================================
#SENDING SMS


from .sms import send_sms  # your sandbox-safe send_sms function
from django.conf import settings

# Your sandbox number (no spaces!)
SANDBOX_NUMBER = "+254705973203"

@api_view(['POST'])
def send_billing_sms(request):
    """
    Send billing SMS to customers using the billings table.
    Sandbox-safe: all messages go to simulator number if username is 'sandbox'.
    """
    send_to_all = request.data.get('send_to_all', True)

    if send_to_all:
        bills = billings.objects.all()
    else:
        billing_id = request.data.get('billing_id')
        bills = billings.objects.filter(id=billing_id)

    sent = []
    failed = []

    # Detect if we're in sandbox mode once
    is_sandbox = getattr(settings, "AT_USERNAME", "").lower() == "sandbox"

    for bill in bills:
        try:
            message = (
                f"Hello {bill.name},\n"
                f"Prev readings: {bill.prev_user}\n"
                f"Current readings :{bill.cur_user}\n"
                f"Water units used: {bill.units_used}\n"
                f"Amount due: KES {bill.bill}\n"
                f"Thank you."
            )

            # Sandbox override: always send to simulator
            recipient = SANDBOX_NUMBER if is_sandbox else bill.phone

            response = send_sms(recipient, message)

            # Log info clearly
            sent.append({
                "original_phone": bill.phone,
                "sent_to": recipient,
                "message": message,
                "response": response
            })

        except Exception as e:
            failed.append({
                "original_phone": bill.phone,
                "error": str(e)
            })

    return Response({
        "total": bills.count(),
        "sent_count": len(sent),
        "failed_count": len(failed),
        "sent": sent,
        "failed": failed,
        "mode": "sandbox" if is_sandbox else "live"
    })


#========================================================================
#========================================================================
#ENABLE LOGINS

from .models import Admin
import secrets

@api_view(['POST'])
def login_user(request):
    username = request.data.get("username")
    password = request.data.get("password")

    admin = Admin.objects.filter(username=username, password=password).first()

    if admin:
        token = secrets.token_hex(32)
        return Response({
            "token": token,
            "message": "Login successful"
        })

    return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


#==========================================================================
#ALLOW THE USERS TO LOGIN
import secrets
from rest_framework import status
@api_view(['POST'])
def login_users(request):
    username = request.data.get("username")
    password = request.data.get("password")

    user = users.objects.filter(username=username, password=password).first()

    if user:
        token = secrets.token_hex(32)

        return Response({
            "token": token,
            "role": user.role,
            "username": user.username,
            "id": user.id,
            "message": "Login successful"
        })

    return Response(
        {"error": "Invalid credentials"},
        status=status.HTTP_401_UNAUTHORIZED
    )