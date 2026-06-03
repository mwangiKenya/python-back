
from django.http import JsonResponse, HttpResponse
from .models import read_users, readings, Admin, Billings, Logs, Users, history
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
from .sms import send_sms
import calendar
from datetime import datetime, date, timedelta
import pandas as pd
from django.db import transaction
from django.http import JsonResponse
from datetime import date, datetime
from .models import read_users, readings, Billings, Logs

def update_reading_field(reading, field_name, new_value, username="system", role="system"):
    """
    Safely updates a field AND logs history automatically
    """

    #old_value = getattr(reading, field_name)
    #old_value = readings.objects.get(id=reading.id).__dict__.get(field_name)
    old_value = (
    readings.objects
    .filter(id=reading.id)
    .values_list(field_name, flat=True)
    .first()
    )

    # only log if something actually changes
    if old_value != new_value:
        history.objects.create(
            name=reading.name,
            field=field_name,
            old_val=old_value if old_value is not None else 0,
            new_val=new_value if new_value is not None else 0
        )

        create_log(
            username=username,
            role=role,
            action="UPDATE",
            table="readings",
            record_id=reading.id,
            field_changed=field_name,
            old_val=old_value,
            new_val=new_value,
            description=f"{field_name} updated for {reading.name}"
        )

    setattr(reading, field_name, new_value)


CYCLE_SCHEDULER = {
    "end_time": None
}

BILLING_STATE = {
    "start_month": None,   # e.g. "2026-05"
}
CYCLE_CONFIG = {
    "start_date": None,
    "delay_days": 30,
}


def last_day_of_month(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)



# ============================
# BILLING CYCLE CONFIG (NEW)
# ============================

BILLING_CYCLE = {
    "start_month": 5,   # May default
    "start_year": 2026,
    "shift_days": 0     # optional delay before shift
}

from datetime import datetime, timedelta
from django.utils import timezone

CYCLE_SCHEDULER = {
    "end_time": None
}

@csrf_exempt
def set_cycle_duration(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        days = int(data.get("days", 0))
        hours = int(data.get("hours", 0))
        minutes = int(data.get("minutes", 0))
        seconds = int(data.get("seconds", 0))

        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

        end_time = timezone.now() + delta
        CYCLE_SCHEDULER["end_time"] = end_time

        return JsonResponse({
            "message": "Cycle timer started",
            "end_time": end_time.isoformat()
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
def cycle_timer_status(request):
    now = timezone.now()

    if not CYCLE_SCHEDULER["end_time"]:
        return JsonResponse({
            "running": False,
            "days": 0,
            "hours": 0,
            "minutes": 0,
            "seconds": 0
        })

    diff = CYCLE_SCHEDULER["end_time"] - now

    if diff.total_seconds() <= 0:
        return JsonResponse({
            "running": False,
            "expired": True
        })

    return JsonResponse({
        "running": True,
        "days": diff.days,
        "hours": diff.seconds // 3600,
        "minutes": (diff.seconds % 3600) // 60,
        "seconds": diff.seconds % 60
    })

@csrf_exempt
def auto_shift_if_due(request):
    """
    This is called repeatedly by frontend OR cron.
    If timer is 0 → shift readings automatically.
    """

    now = timezone.now()

    if not CYCLE_SCHEDULER["end_time"]:
        return JsonResponse({"message": "No cycle running"})

    if now < CYCLE_SCHEDULER["end_time"]:
        return JsonResponse({"message": "Not yet time"})

    # RESET TIMER
    CYCLE_SCHEDULER["end_time"] = None

    # SHIFT LOGIC (NO BILLING CALCULATION)
    with transaction.atomic():
        next_month = now.month + 1
        next_year = now.year

        if next_month > 12:
            next_month = 1
            next_year += 1

        next_last_day = calendar.monthrange(next_year, next_month)[1]
        next_cycle_date = date(next_year, next_month, next_last_day)

        for r in readings.objects.all():

            r.prev_user = r.cur_user if r.cur_user is not None else r.prev_user
            r.prev_sup = r.cur_sup if r.cur_sup is not None else r.prev_sup

            r.prev_date = r.cur_date or r.prev_date
            r.cur_date = next_cycle_date

            r.cur_user = None
            r.cur_sup = None

            # IMPORTANT: DO NOT TOUCH billing
            r.save()

    return JsonResponse({
        "message": "Auto shift completed",
        "next_cycle_date": str(next_cycle_date)
    })

# TEMP SNAPSHOT FOR RESTORE (NEW FEATURE)
LAST_STATE_SNAPSHOT = None
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

def create_hist(name, field, old_val, new_val):
    history.objects.create(
        name=name,
        field=field,
        old_val=old_val,
        new_val=new_val
    )

import copy

def snapshot_readings():
    global LAST_STATE_SNAPSHOT
    LAST_STATE_SNAPSHOT = list(readings.objects.values())

#SELECT THE BILLING MONTH TO START
@csrf_exempt
def start_billing_month(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        start_month = data.get("start_month")  # format: "2026-05"

        if not start_month:
            return JsonResponse({"error": "start_month required"}, status=400)

        year, month = map(int, start_month.split("-"))

        # last day of selected month
        last_day = calendar.monthrange(year, month)[1]
        prev_date = date(year, month, last_day)

        # next month end date
        next_month = month + 1
        next_year = year

        if next_month > 12:
            next_month = 1
            next_year += 1

        next_last_day = calendar.monthrange(next_year, next_month)[1]
        cur_date = date(next_year, next_month, next_last_day)

        with transaction.atomic():
            # update ALL readings
            readings.objects.all().update(
                prev_date=prev_date,
                cur_date=cur_date
            )

        BILLING_STATE["start_month"] = start_month

        return JsonResponse({
            "message": "Billing month started",
            "prev_date": str(prev_date),
            "cur_date": str(cur_date)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
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
            'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None,
            'grp' : u.grp,
            'parent' : u.parent
        })

    return JsonResponse(data, safe=False)
#==============================================================
#FETCH THE READING HISTORY DATA
def hist_data(request):
    name = request.GET.get("name")
    field = request.GET.get("field")

    hist = history.objects.all()

    if name:
        hist = hist.filter(name__icontains=name)

    if field:
        hist = hist.filter(field__icontains=field)

    data = []
    for h in hist:
        data.append({
            'id': h.id,
            'name': h.name,
            'field': h.field,
            'old_val': h.old_val,
            'new_val': h.new_val,
            'changes_on': h.changed_on.strftime('%Y-%m-%d') if h.changed_on else None
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
            'status': b.status,
            'b_cd' : b.b_cd,
            'prev_user' : b.prev_user,
            'cur_user' : b.cur_user,
            'sms_name' : b.sms_name,
            'grp' : b.grp,
            'parent' : b.parent
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
            'rate': r.rate,
            'mid_user':r.mid_user,
            'mid_sup': r.mid_sup,
            'grp': r.grp,
            'parent': r.parent
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
        grp = data.get("grp")
        parent = data.get("parent")

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
                rate=rate,
                grp = grp,
                parent = parent
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
                metre_num=metre_num,
                grp = grp,
                parent=parent
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

                user_name = item.get("username", "system")
                role = item.get("role", "system")

                reading = readings.objects.select_for_update().get(
                    user_id=item["user_id"]
                )
        with transaction.atomic():
            for item in updates:

                reading = readings.objects.select_for_update().get(user_id=item["user_id"])

                cur_user = item.get("cur_user")
                cur_sup = item.get("cur_sup")

                if cur_user is not None:
                    cur_user = int(cur_user)

                    # calculate usage WITHOUT shifting prev_user
                    reading.units_used = max(0, cur_user - (reading.prev_user or 0))

                    # keep current reading stored
                    #reading.cur_user = cur_user
                    update_reading_field(reading, "cur_user", cur_user, user_name, role)

                if cur_sup is not None:
                   #reading.cur_sup = int(cur_sup)
                   update_reading_field(reading, "cur_sup", cur_sup, user_name, role)

                reading.mid_user = item.get("mid_user", reading.mid_user)
                reading.mid_sup = item.get("mid_sup", reading.mid_sup)

                reading.save()

                # BILLING
                bill_amount = reading.units_used * reading.rate
                if reading.units_used == 0:
                    bill_amount = 300

                # GET OLD BILLING IF EXISTS
                old_billing = Billings.objects.filter(user_id=reading.user_id).first()

                #previous_balance = Decimal("0")
                previous_balance = old_billing.b_cd if old_billing else Decimal("0")
                previous_paid = Decimal("0")

                if old_billing:
                    previous_balance = old_billing.bal or Decimal("0")
                    previous_paid = old_billing.paid or Decimal("0")

                # CURRENT TOTAL DUE
                total_balance = previous_balance + Decimal(str(bill_amount))

                billing = Billings.objects.filter(user_id=reading.user_id).first()

                if billing:

                        billing.name = reading.name
                        billing.phone = reading.phone
                        billing.units_used = reading.units_used
                        billing.rate = reading.rate

                        # CURRENT MONTH BILL
                        billing.bill = bill_amount

                        # PREVIOUS BALANCE
                        billing.b_cd = previous_balance

                        # TOTAL BALANCE
                        billing.bal = total_balance

                        # RESET PAID
                        billing.paid = 0

                        billing.status = "Unpaid"
                        billing.prev_user = reading.prev_user
                        billing.cur_user = reading.cur_user
                        billing.sms_name
                        billing.grp
                        billing.parent

                        billing.save(update_fields=[
                            "name",
                            "phone",
                            "units_used",
                            "rate",
                            "bill",
                            "b_cd",
                            "bal",
                            "paid",
                            "status",
                            "prev_user",
                            "cur_user",
                            "sms_name",
                            "grp",
                            "parent"
                        ])

                else:

                        Billings.objects.create(
                            user_id=reading.user_id,
                            name=reading.name,
                            phone=reading.phone,
                            units_used=reading.units_used,
                            rate=reading.rate,
                            bill=bill_amount,
                            b_cd=previous_balance,
                            bal=total_balance,
                            paid=0,
                            status="Unpaid",
                            prev_user=reading.prev_user,
                            cur_user=reading.cur_user,
                            sms_name =reading.metre_num,
                            grp=reading.grp,
                            parent=reading.parent
                        )

            return JsonResponse({"message": "Saved successfully"})

    except Exception as e:
                         return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def finalize_month(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        today = datetime.now()

        # ==========================
        # STEP 1: CHECK IF CYCLE ENDED
        # ==========================
        last_day = calendar.monthrange(today.year, today.month)[1]
        cycle_end = datetime(today.year, today.month, last_day, 23, 59, 59)

        if today < cycle_end:
            return JsonResponse({
                "error": "Cycle not finished yet"
            }, status=400)

        # ==========================
        # STEP 2: CALCULATE NEXT CYCLE DATE
        # ==========================
        next_month = today.month + 1
        next_year = today.year

        if next_month > 12:
            next_month = 1
            next_year += 1

        next_last_day = calendar.monthrange(next_year, next_month)[1]
        next_cycle_date = date(next_year, next_month, next_last_day)

        # ==========================
        # STEP 3: SHIFT DATA SAFELY
        # ==========================
        with transaction.atomic():
            for r in readings.objects.all():

                # SHIFT previous readings ONLY if current exists
                if r.cur_user is not None:
                    r.prev_user = r.cur_user
                if r.cur_sup is not None:
                    r.prev_sup = r.cur_sup

                # RESET CURRENT
                r.cur_user = None
                r.cur_sup = None

                # RESET MID MONTH
                r.mid_user = 0
                r.mid_sup = 0

                # SHIFT DATES
                r.prev_date = r.cur_date or r.prev_date
                r.cur_date = next_cycle_date

                r.save()

        return JsonResponse({
            "message": "Cycle shifted successfully",
            "next_cycle_date": str(next_cycle_date)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
def billing_timer(request):
    today = datetime.now()

    next_month = today.month + 1
    next_year = today.year

    if next_month > 12:
        next_month = 1
        next_year += 1

    end_date = datetime(next_year, next_month, calendar.monthrange(next_year, next_month)[1], 23, 59, 59)

    diff = end_date - today

    return JsonResponse({
        "days": diff.days,
        "hours": diff.seconds // 3600,
        "minutes": (diff.seconds % 3600) // 60,
        "seconds": diff.seconds % 60
    })
# ============================================================
# UPDATE PAYMENT
# ============================================================
@csrf_exempt
def update_paid(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        # ===============================
        # CASE 1: BULK UPDATE (LIST)
        # ===============================
        if isinstance(data, list):
            updated = []

            with transaction.atomic():
                for item in data:
                    billing = Billings.objects.get(id=item.get("id"))
                    old_paid = billing.paid

                    new_paid = Decimal(str(item.get("paid", 0)))

                    billing.paid = new_paid
                    total_due = (billing.bill or 0) + (billing.b_cd or 0)
                    billing.bal = total_due - new_paid

                    if new_paid == 0:
                        billing.status = "Unpaid"
                    elif new_paid < billing.bal:
                        billing.status = "Partially Paid"
                    else:
                        billing.status = "Paid"

                    billing.save()

                    create_log(
                        item.get("username", "system"),
                        item.get("role", "system"),
                        "UPDATE",
                        "billings",
                        billing.id,
                        f"bulk update: {old_paid} → {new_paid}",
                        "paid",
                        old_paid,
                        new_paid
                    )

                    updated.append({
                        "id": billing.id,
                        "paid": billing.paid,
                        "bal": billing.bal,
                        "status": billing.status
                    })

            return JsonResponse({
                "message": "Bulk payment updated successfully",
                "updated": updated
            })

        # ===============================
        # CASE 2: SINGLE UPDATE 
        # ===============================
        billing = Billings.objects.get(id=data.get("id"))
        old_paid = billing.paid

        new_paid = Decimal(str(data.get("paid", 0)))

        billing.paid = new_paid
        total_due = (billing.bill or 0) + (billing.b_cd or 0)
        billing.bal = total_due - new_paid

        if new_paid == 0:
            billing.status = "Unpaid"
        elif new_paid < billing.bill:
            billing.status = "Partially Paid"
        else:
            billing.status = "Paid"

        billing.save()

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

        return JsonResponse({
            "message": "Payment updated",
            "id": billing.id,
            "paid": billing.paid,
            "bal": billing.bal,
            "status": billing.status
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# ANALYTICS (UNCHANGED)
# ============================================================
def total_bill(request):
    total = Billings.objects.aggregate(total_bill=Sum('bill'))['total_bill'] or 0
    return JsonResponse({"total_bill": round(float(total), 2)})

def total_bal(request):
    total = Billings.objects.aggregate(total_bal=Sum('b_cd'))['total_bal'] or 0
    return JsonResponse({"total_bal": round(float(total), 2)})

def total_paid(request):
    total = Billings.objects.aggregate(total_paid=Sum('paid'))['total_paid'] or 0
    return JsonResponse({"total_paid": round(float(total), 2)})


def total_units(request):
    total = Billings.objects.aggregate(total_units=Sum('units_used'))['total_units'] or 0
    return JsonResponse({"total_units": round(float(total), 2)})

def total_cust(request):
    total = read_users.objects.aggregate(total_cust=Count('id'))['total_cust'] or 0
    return JsonResponse({"total_cust": total})
def avg_units(request):
    avg = Billings.objects.aggregate(avg_units=Avg('units_used'))['avg_units'] or 0
    return JsonResponse({"avg_units": round(float(avg), 2)})


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
    
#====================================================================================
#DELETING THE CUSTOMER FROM THE SYSTEM
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
            Billings.objects.filter(name=user.fname).delete()
            #Billings.objects.filter(phone=user.phone).delete()

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

#DELETING AN EMPLOYEE FROM THE SYSTEM
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
    

#UPDATING THE EMPLOYEE DETAILS
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

def process_reading_update(
    user_id,
    new_cur_user=None,
    new_cur_sup=None,
    mid_user=None,
    mid_sup=None,
    username="system",
    role="system"
):
    try:
        reading = readings.objects.get(user_id=user_id)
    except readings.DoesNotExist:
        create_log(username, role, "ERROR", "readings", user_id,
                   "Reading record not found")
        return

    prev_user = reading.prev_user or 0
    prev_sup = reading.prev_sup or 0

    # =========================
    # MID READINGS
    # =========================
    if mid_user is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"mid_user {reading.mid_user} → {mid_user}",
                   "mid_user", reading.mid_user, mid_user)
        #reading.mid_user = mid_user
        update_reading_field(reading, "mid_user", mid_user, username, role)

    if mid_sup is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"mid_sup {reading.mid_sup} → {mid_sup}",
                   "mid_sup", reading.mid_sup, mid_sup)
        #reading.mid_sup = mid_sup
        update_reading_field(reading, "mid_sup", mid_sup, username, role)

    # =========================
    # IF NO CURRENT READING
    # =========================
    if new_cur_user is None and new_cur_sup is None:
        reading.save()
        return

    # =========================
    # SAFE UNIT CALCULATION
    # =========================
    units_used = reading.units_used or 0

    if new_cur_user is not None:
        try:
            units_used = int(new_cur_user) - int(prev_user)
        except Exception:
            create_log(username, role, "ERROR", "readings", reading.id,
                       "Invalid numeric reading input")
            return

        if units_used < 0:
            units_used = 0

    # =========================
    # LOG CHANGES
    # =========================
    if new_cur_user is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"user reading {prev_user} → {new_cur_user}",
                   "cur_user", prev_user, new_cur_user)

    if new_cur_sup is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"sup reading {prev_sup} → {new_cur_sup}",
                   "cur_sup", prev_sup, new_cur_sup)

    # =========================
    # UPDATE READING
    # =========================

    if new_cur_user is not None:
            #reading.cur_user = new_cur_user
            update_reading_field(reading, "cur_user", new_cur_user, username, role)

    if new_cur_sup is not None:
            #reading.cur_sup = new_cur_sup
            update_reading_field(reading, "cur_sup", new_cur_sup, username, role)

    reading.units_used = units_used

        # DO NOT SHIFT PREVIOUS VALUES
        # WAIT FOR TIMER / FINALIZE

    reading.save()

    # =========================
    # BILLING
    # =========================
    if new_cur_user is not None:
        rate = reading.rate or 0
        bill_amount = units_used * rate

        if units_used == 0:
            bill_amount = 300

        billing, created = Billings.objects.get_or_create(
            user_id=user_id,
            billed_on=date.today(),
            defaults={
                "name": reading.name,
                "phone": reading.phone,
                "units_used": units_used,
                "rate": rate,
                "bill": bill_amount,
                "paid": 0,
                "bal": bill_amount,
                "status": "Unpaid",
                "b_cd": billing.bal,
                "prev_user": reading.prev_user,
                "cur_user": reading.cur_user,
                "sms_name": reading.metre_num,
                "grp": reading.grp,
                "parent": reading.parent
            }
        )

        if not created:
            billing.units_used = units_used
            billing.bill = bill_amount
            billing.bal = bill_amount - billing.paid

            if billing.paid == 0:
                billing.status = "Unpaid"
            elif billing.paid < bill_amount:
                billing.status = "Partially Paid"
            else:
                billing.status = "Paid"

            billing.save()
#DOWNLOAD A FORMATED EXCEL SHEET OF THE READINGS TABLE TO FILL AND UPLOAD
def download_readings_template(request):
    data = readings.objects.all().values(
        "user_id", "name", "phone", "metre_num",
        "prev_user", "prev_sup"
    )

    df = pd.DataFrame(list(data))
    
    df["mid_user"] = ""
    df["mid_sup"] = ""
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
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        df = pd.read_excel(file)

        required_columns = ["user_id"]
        for col in required_columns:
            if col not in df.columns:
                return JsonResponse({"error": f"Missing required column: {col}"}, status=400)

        processed = 0
        skipped = 0

        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    user_id = row.get("user_id")

                    if pd.isna(user_id):
                        skipped += 1
                        continue

                    # -------- READ VALUES --------
                    cur_user = row.get("cur_user")
                    cur_sup = row.get("cur_sup")
                    mid_user = row.get("mid_user")
                    mid_sup = row.get("mid_sup")

                    # -------- CLEAN NaN --------
                    cur_user = None if pd.isna(cur_user) else int(cur_user)
                    cur_sup = None if pd.isna(cur_sup) else int(cur_sup)
                    mid_user = None if pd.isna(mid_user) else int(mid_user)
                    mid_sup = None if pd.isna(mid_sup) else int(mid_sup)

                    # -------- SKIP EMPTY ROW --------
                    if cur_user is None and cur_sup is None and mid_user is None and mid_sup is None:
                        skipped += 1
                        continue

                    # -------- PROCESS UPDATE --------
                    process_reading_update(
                        user_id=int(user_id),
                        new_cur_user=cur_user,
                        new_cur_sup=cur_sup,
                        mid_user=mid_user,
                        mid_sup=mid_sup,
                        username="excel_upload",
                        role="system"
                    )

                    processed += 1

                except Exception as row_error:
                    print(f"Row {index} skipped: {row_error}")
                    skipped += 1
                    continue

        return JsonResponse({
            "message": "Excel uploaded successfully",
            "processed_rows": processed,
            "skipped_rows": skipped
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

#UPDAE CUSTOMER DETAILS IN ALL TABLES THAT HE EXISTS
@csrf_exempt
def update_user(request, user_id):
    if request.method != "PUT":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        fname = data.get("fname")
        phone = data.get("phone")
        metre_num = data.get("metre_num")
        zone = data.get("zone")
        rate = data.get("rate")
        grp = data.get("grp")
        parent = data.get("parent")

        user_name = data.get("username", "Unknown")
        role = data.get("role", "Unknown")

        with transaction.atomic():

            # ===============================
            # 1. UPDATE WATERUSERS
            # ===============================
            try:
                user = read_users.objects.get(id=user_id)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)

            old_name = user.fname
            old_phone = user.phone

            user.fname = fname or user.fname
            user.phone = phone or user.phone
            user.metre_num = metre_num or user.metre_num
            user.zone = zone or user.zone
            user.rate = rate or user.rate
            user.grp = grp or user.grp
            user.parent = parent or user.parent
            user.save()

            # ===============================
            # 2. UPDATE READINGS (IF EXISTS)
            # ===============================
            readings.objects.filter(user_id=user_id).update(
                name=fname,
                phone=phone,
                metre_num=metre_num,
                rate=rate,
                grp = grp,
                parent = parent
            )

            # ===============================
            # 3. UPDATE BILLINGS (IF EXISTS)
            # ===============================
            Billings.objects.filter(user_id=user_id).update(
                name=fname,
                phone=phone,
                rate=rate,
                sms_name=metre_num,
                grp =grp,
                parent = parent
            )

            # ===============================
            # LOG
            # ===============================
            create_log(
                username=user_name,
                role=role,
                action="UPDATE",
                table="waterusers",
                record_id=user_id,
                description=f"{role} updated customer {old_name} → {fname}"
            )

        return JsonResponse({"message": "User updated successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

#SEND BILLING SMS
import requests
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

#ADVANTA CREDENTIALS
API_URL = "https://quicksms.advantasms.com/api/services/sendbulk"
PARTNER_ID = "16256"
API_KEY = "bc1bc562ccb7c72732e7fa0add447129"
SHORTCODE = "AdvantaSMS"


def send_bulk_sms(customers):
    payload = {
        "count": len(customers),
        "smslist": []
    }

    for i, customer in enumerate(customers):
        payload["smslist"].append({
            "partnerID": PARTNER_ID,
            "apikey": API_KEY,
            "pass_type": "plain",
            "clientsmsid": i + 1,
            "mobile": customer["phone"],
            "message": customer["message"],
            "shortcode": SHORTCODE
        })

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(API_URL, json=payload, headers=headers)

    return response.json()


@csrf_exempt
def send_sms_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            customers = data.get("customers", [])

            if not customers:
                return JsonResponse({"error": "No customers selected"}, status=400)

            result = send_bulk_sms(customers)

            return JsonResponse({
                "message": "SMS sent successfully",
                "data": result
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

#DOWNLOAD BILLINGS EXCEL, FILL AND UPLOAD IT
import pandas as pd

def download_billings_template(request):
    data = Billings.objects.all().values(
        "id", "name", "phone", "bill", "paid"
    )

    df = pd.DataFrame(list(data))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=billings_template.xlsx'

    df.to_excel(response, index=False)

    return response



@csrf_exempt
def upload_billings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        file = request.FILES["file"]
        df = pd.read_excel(file)

        updated = []

        with transaction.atomic():
            for _, row in df.iterrows():

                billing_id = row.get("id")
                paid = row.get("paid")

                if pd.isna(billing_id) or pd.isna(paid):
                    continue

                billing = Billings.objects.get(id=int(billing_id))

                old_paid = billing.paid
                new_paid = Decimal(str(paid))

                billing.paid = new_paid
                total_due = (billing.bill or 0) + (billing.b_cd or 0)
                billing.bal = total_due - new_paid

                if new_paid == 0:
                    billing.status = "Unpaid"
                elif new_paid < billing.bill:
                    billing.status = "Partially Paid"
                else:
                    billing.status = "Paid"

                billing.save()

                create_log(
                    "excel_upload",
                    "system",
                    "UPDATE",
                    "billings",
                    billing.id,
                    f"Excel update: {old_paid} → {new_paid}",
                    "paid",
                    old_paid,
                    new_paid
                )

                updated.append(billing.id)

        return JsonResponse({
            "message": "Excel uploaded successfully",
            "updated_count": len(updated)
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
#==============================================================
#RRESET THE MID-MONTH READINGS
@csrf_exempt
def reset_mid_month_readings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}

        username = data.get("username", "system")
        role = data.get("role", "system")

        with transaction.atomic():

            readings_qs = readings.objects.all()

            for r in readings_qs:
                old_mid_user = r.mid_user
                old_mid_sup = r.mid_sup

                r.mid_user = 0
                r.mid_sup = 0
                r.save()

                # LOG CHANGES
                create_log(
                    username=username,
                    role=role,
                    action="UPDATE",
                    table="readings",
                    record_id=r.id,
                    field_changed="mid_month_reset",
                    old_val=f"user:{old_mid_user}, sup:{old_mid_sup}",
                    new_val="user:0, sup:0",
                    description=f"Mid-month readings reset for {r.name}"
                )

        return JsonResponse({
            "message": "Mid-month readings reset successfully"
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def restore_readings(request):
    global LAST_STATE_SNAPSHOT

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    if not LAST_STATE_SNAPSHOT:
        return JsonResponse({"error": "No snapshot available"}, status=400)

    with transaction.atomic():
        readings.objects.all().delete()

        for r in LAST_STATE_SNAPSHOT:
            r.pop("id", None)
            readings.objects.create(**r)

    return JsonResponse({"message": "System restored successfully"})




def download_users_excel(request):
    users = read_users.objects.all().values(
        "id", "fname", "phone", "metre_num",
        "zone", "rate", "grp", "parent", "created_on"
    )

    df = pd.DataFrame(list(users))

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="water_users.xlsx"'

    df.to_excel(response, index=False)

    return response