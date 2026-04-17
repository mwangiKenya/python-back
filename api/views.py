
from django.http import JsonResponse, HttpResponse
from .models import read_users, readings, Admin, Billings, Logs, Users
from django.views.decorators.csrf import csrf_exempt
import json
import secrets
from django.db import transaction
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Avg, Count
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

# ============================================================
# HELPER FUNCTION → CREATE LOG (Avoid repeating code everywhere)
# ============================================================
def create_log(username, role, action, table, record_id, description,
               field_changed=None, old_val=None, new_val=None):

    Logs.objects.create(
        username=username,
        role=role,
        action=action,
        table_name=table,
        record_id=record_id,
        field_changed=field_changed,
        old_val=str(old_val) if old_val is not None else None,
        new_val=str(new_val) if new_val is not None else None,
        description=description
    )

# ============================================================
# FETCH ALL WATER USERS
# ============================================================
def water_users(request):
    users = read_users.objects.all()
    data = []

    for u in users:
        data.append({
            'id': u.id,
            'fname': u.fname,
            'phone': u.phone,
            'metre_num': u.metre_num,
            'zone': u.zone,
            'rate': u.rate,
            'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None
        })

    return JsonResponse(data, safe=False)

# ============================================================
# FETCH ALL BILLINGS
# ============================================================
def bill(request):
    bills = Billings.objects.all()
    data = []

    for b in bills:
        data.append({
            'id': b.id,
            'user_id': b.user_id,
            'name': b.name,
            'phone': b.phone,
            'units_used': b.units_used,
            'rate': b.rate,
            'bill': b.bill,
            'paid': b.paid,
            'bal': b.bal,
            'status': b.status
        })

    return JsonResponse(data, safe=False)

# ============================================================
# FETCH ALL LOGS (FOR ADMIN DASHBOARD)
# ============================================================
def logs(request):
    log = Logs.objects.all().order_by('-changed_at')
    data = []

    for l in log:
        data.append({
            'id': l.id,
            'username': l.username,
            'role': l.role,
            'action': l.action,
            'table_name': l.table_name,
            'record_id': l.record_id,
            'field_changed': l.field_changed,
            'old_val': l.old_val,
            'new_val': l.new_val,
            'description': l.description,
            'changed_at': l.changed_at.strftime('%Y-%m-%d %H:%M:%S') if l.changed_at else None
        })

    return JsonResponse(data, safe=False)

# ============================================================
# FETCH READINGS
# ============================================================
def read_data(request):
    read = readings.objects.all()
    data = []

    for r in read:
        data.append({
            'id': r.id,
            'user_id': r.user_id,
            'name': r.name,
            'phone': r.phone,
            'metre_num' : r.metre_num,
            'prev_user': r.prev_user,
            'prev_sup': r.prev_sup,
            'prev_date': r.prev_date.strftime('%Y-%m-%d') if r.prev_date else None,
            'cur_user': r.cur_user,
            'cur_sup': r.cur_sup,
            'cur_date' : r.cur_date.strftime('%Y-%m-%d') if r.cur_date else None,
            'rate': r.rate
        })

    return JsonResponse(data, safe=False)

# ============================================================
# ADMIN LOGIN
# ============================================================
@csrf_exempt
def login_user(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        admin = Admin.objects.filter(username=username, password=password).first()

        if admin:
            token = secrets.token_hex(32)

            # 🔥 LOG LOGIN
            create_log(
                username="admin",
                role="admin",
                action="LOGIN",
                table="admin",
                record_id=admin.id,
                description="Admin logged into system"
            )

            return JsonResponse({"token": token})

        return JsonResponse({"error": "Invalid login credentials"}, status=401)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# CREATE NEW CUSTOMER
# ============================================================
@csrf_exempt
def new_user(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        fname = data.get("fname")
        phone = data.get("phone")
        metre_num = data.get("metre_num")
        zone = data.get("zone")
        rate = data.get("rate")

        user_name = data.get("username")
        role = data.get("role")

        if not all([fname, phone, metre_num, zone, rate]):
            return JsonResponse({"error": "Missing fields"}, status=400)

        with transaction.atomic():
            user = read_users.objects.create(
                fname=fname,
                phone=phone,
                metre_num=metre_num,
                zone=zone,
                rate=rate
            )

            today = date.today()

            readings.objects.create(
                user=user,
                name=fname,
                phone=phone,
                prev_user=0,
                prev_sup=0,
                prev_date=today,
                cur_user=None,
                cur_sup=None,
                cur_date=today,
                units_used=0,
                rate=rate,
                metre_num=metre_num
            )

            # 🔥 LOG USER CREATION
            create_log(
                username=user_name,
                role=role,
                action="CREATE",
                table="waterusers",
                record_id=user.id,
                description=f"{user_name} created new customer {fname}"
            )

        return JsonResponse({"message": "User registered successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# SUBMIT NEW READINGS + BILLING + LOGGING
# ============================================================
@csrf_exempt
def submit_new_reading(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        updates = data if isinstance(data, list) else [data]

        with transaction.atomic():

            for item in updates:
                user_id = item.get("user_id")
                new_cur_user = int(item.get("cur_user", 0))
                new_cur_sup = int(item.get("cur_sup", 0))

                user_name = item.get("username")
                role = item.get("role")

                reading = readings.objects.get(user_id=user_id)

                prev_user = reading.prev_user
                prev_sup = reading.prev_sup

                # 🔥 LOG CHANGES
                if new_cur_user != 0:
                    create_log(
                        user_name, role, "UPDATE", "readings", reading.id,
                        f"{role} updated user reading from {prev_user} to {new_cur_user}",
                        "cur_user", prev_user, new_cur_user
                    )

                if new_cur_sup != 0:
                    create_log(
                        user_name, role, "UPDATE", "readings", reading.id,
                        f"{role} updated sup reading from {prev_sup} to {new_cur_sup}",
                        "cur_sup", prev_sup, new_cur_sup
                    )

                # CALCULATIONS
                units_used = new_cur_user - prev_user

                reading.prev_user = new_cur_user or prev_user
                reading.prev_sup = new_cur_sup or prev_sup
                reading.cur_user = None
                reading.cur_sup = None
                reading.units_used = units_used
                reading.cur_date = date.today()
                reading.save()

                # BILLING
                bill = units_used * reading.rate
                if units_used == 0:
                    bill = 300

                billing, created = Billings.objects.get_or_create(
                    user_id=user_id,
                    defaults={
                        "name": reading.name,
                        "phone": reading.phone,
                        "billed_on": date.today(),
                        "units_used": units_used,
                        "rate": reading.rate,
                        "bill": bill,
                        "paid": 0,
                        "bal": bill,
                        "status": "Unpaid"
                    }
                )

                if not created:
                    billing.units_used = units_used
                    billing.bill = bill
                    billing.bal = bill - billing.paid
                    billing.save()

                    # 🔥 LOG BILL UPDATE
                    create_log(
                        user_name, role, "UPDATE", "billings", billing.id,
                        f"{role} updated billing for {reading.name}"
                    )

        return JsonResponse({"message": "Saved successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# UPDATE PAYMENT
# ============================================================
@csrf_exempt
def update_paid(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        billing = Billings.objects.get(id=data.get("id"))
        old_paid = billing.paid

        new_paid = Decimal(str(data.get("paid", 0)))

        billing.paid = new_paid
        billing.bal = billing.bill - new_paid

        if new_paid == 0:
            billing.status = "Unpaid"
        elif new_paid < billing.bill:
            billing.status = "Partially Paid"
        else:
            billing.status = "Paid"

        billing.save()

        # 🔥 LOG PAYMENT
        create_log(
            data.get("username"),
            data.get("role"),
            "UPDATE",
            "billings",
            billing.id,
            f"{data.get('role')} updated payment from {old_paid} to {new_paid}",
            "paid",
            old_paid,
            new_paid
        )

        return JsonResponse({"message": "Payment updated"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# ANALYTICS (UNCHANGED)
# ============================================================
def total_bill(request):
    total = Billings.objects.aggregate(total_bill=Sum('bill'))['total_bill'] or 0
    return JsonResponse({"total_bill": round(float(total), 2)})

def total_paid(request):
    total = Billings.objects.aggregate(total_paid=Sum('paid'))['total_paid'] or 0
    return JsonResponse({"total_paid": round(float(total), 2)})

def avg_units(request):
    avg = Billings.objects.aggregate(avg_units=Avg('units_used'))['avg_units'] or 0
    return JsonResponse({"avg_units": round(float(avg), 2)})

def total_units(request):
    total = Billings.objects.aggregate(total_units=Sum('units_used'))['total_units'] or 0
    return JsonResponse({"total_units": round(float(total), 2)})

def total_cust(request):
    total = read_users.objects.aggregate(total_cust=Count('id'))['total_cust'] or 0
    return JsonResponse({"total_cust": total})

# ============================================================
# EMPLOYEE MANAGEMENT
# ============================================================
@api_view(['POST'])
def register_user(request):
    user = Users.objects.create(
        username=request.data.get('username'),
        password=request.data.get('password'),
        role=request.data.get('role')
    )

    # 🔥 LOG USER CREATION
    create_log(
        "Admin",
        "admin",
        "CREATE",
        "users",
        user.id,
        f"Admin created employee {user.username}"
    )

    return Response({"message": "User registered successfully"})

@api_view(['GET'])
def list_employees(request):
    return Response(list(Users.objects.all().values('id', 'username', 'role')))

# ============================================================
# USERS LOGIN (ROLE-BASED)
# ============================================================
@csrf_exempt
def users_login(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    try:
        data = json.loads(request.body)
        user = Users.objects.filter(
            username=data.get("username"),
            password=data.get("password")
        ).first()

        if not user:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

        token = secrets.token_hex(16)

        # 🔥 LOG LOGIN
        create_log(
            user.username,
            user.role,
            "LOGIN",
            "users",
            user.id,
            f"{user.username} logged into system"
        )

        return JsonResponse({
            "token": token,
            "username": user.username,
            "role": user.role
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def delete_user(request, user_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}

        user_name = data.get("username", "Unknown")
        role = data.get("role", "Unknown")

        with transaction.atomic():

            try:
                user = read_users.objects.get(id=user_id)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)

            fname = user.fname

            # ====================================================
            # 1. DELETE READINGS (SAFE)
            # ====================================================
            readings.objects.filter(user_id=user_id).delete()

            # ====================================================
            # 2. DELETE BILLINGS (TRY MULTIPLE MATCHES)
            # ====================================================
            Billings.objects.filter(user_id=user_id).delete()
            Billings.objects.filter(name=user.fname, phone=user.phone).delete()
            Billings.objects.filter(phone=user.phone).delete()

            # ====================================================
            # 3. DELETE USER
            # ====================================================
            user.delete()

            create_log(
                username=user_name,
                role=role,
                action="DELETE",
                table="waterusers",
                record_id=user_id,
                description=f"{user_name} deleted customer {fname}, readings, billings"
            )

        return JsonResponse({"message": "User fully deleted"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def delete_employee(request, emp_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        emp = Users.objects.get(id=emp_id)
        emp.delete()
        return JsonResponse({"message": "Employee deleted"})
    except Users.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    

@csrf_exempt
def update_employee(request, emp_id):
    if request.method != "PUT":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        emp = Users.objects.get(id=emp_id)

        emp.username = data.get("username", emp.username)
        emp.role = data.get("role", emp.role)

        emp.save()

        return JsonResponse({"message": "Employee updated"})
    except Users.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
#==============================================================================================
#=================================================================================
#===========================================================================================

def process_reading_update(user_id, new_cur_user, new_cur_sup, username=None, role=None):
    reading = readings.objects.get(user_id=user_id)

    prev_user = reading.prev_user
    prev_sup = reading.prev_sup

    # LOG USER READING
    if new_cur_user is not None:
        create_log(
            username, role, "UPDATE", "readings", reading.id,
            f"updated user reading {prev_user} → {new_cur_user}",
            "cur_user", prev_user, new_cur_user
        )

    if new_cur_sup is not None:
        create_log(
            username, role, "UPDATE", "readings", reading.id,
            f"updated sup reading {prev_sup} → {new_cur_sup}",
            "cur_sup", prev_sup, new_cur_sup
        )

    # CALCULATION
    units_used = new_cur_user - prev_user

    reading.prev_user = new_cur_user or prev_user
    reading.prev_sup = new_cur_sup or prev_sup
    reading.cur_user = None
    reading.cur_sup = None
    reading.units_used = units_used
    reading.cur_date = date.today()
    reading.save()

    # BILLING
    bill_amount = units_used * reading.rate if units_used > 0 else 300

    billing, created = Billings.objects.get_or_create(
        user_id=user_id,
        defaults={
            "name": reading.name,
            "phone": reading.phone,
            "billed_on": date.today(),
            "units_used": units_used,
            "rate": reading.rate,
            "bill": bill_amount,
            "paid": 0,
            "bal": bill_amount,
            "status": "Unpaid"
        }
    )

    if not created:
        billing.units_used = units_used
        billing.bill = bill_amount
        billing.bal = bill_amount - billing.paid
        billing.save()


import pandas as pd
from django.http import HttpResponse

def download_readings_template(request):
    data = readings.objects.all().values(
        "user_id", "name", "phone", "metre_num",
        "prev_user", "prev_sup"
    )

    df = pd.DataFrame(list(data))

    df["cur_user"] = ""
    df["cur_sup"] = ""

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=readings_template.xlsx'

    df.to_excel(response, index=False)

    return response


@csrf_exempt
def upload_readings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        file = request.FILES["file"]
        df = pd.read_excel(file)

        with transaction.atomic():
            for _, row in df.iterrows():

                user_id = row["user_id"]
                cur_user = row["cur_user"]
                cur_sup = row["cur_sup"]

                if pd.isna(cur_user) or pd.isna(cur_sup):
                    continue

                process_reading_update(
                    user_id=int(user_id),
                    new_cur_user=int(cur_user),
                    new_cur_sup=int(cur_sup),
                    username="excel_upload",
                    role="system"
                )

        return JsonResponse({"message": "Excel uploaded and processed successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)