from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Sum, Avg, Count, Q
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
import os
import calendar
import secrets
from io import BytesIO
from textwrap import wrap
from datetime import date, datetime, timedelta
from decimal import Decimal
import pandas as pd
import requests
from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from .models import (
    read_users, readings, Admin, Billings, Logs, Users, history,
    ReadingHistory, PaymentHistory, BillingHistory, AuditTrail,
    BillingCycleHistory, CustomerPaymentSummary
)

#======================================================================================
# LOGGING / HISTORY / AUDIT HELPERS
#======================================================================================

def create_log(username, role, action, table, record_id, description,
               field_changed=None, old_val=None, new_val=None):
    """Write a row to the lightweight Logs table."""
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


def create_audit_trail(username, role, action, table_name=None, record_id=None,
                        field_changed=None, old_value=None, new_value=None,
                        description=None, request=None):
    """Write a row to the AuditTrail table, capturing request metadata if given."""
    try:
        ip_address = None
        user_agent = None
        session_id = None

        if request:
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT')
            session_id = request.session.session_key

        AuditTrail.objects.create(
            username=username,
            role=role,
            action=action,
            table_name=table_name,
            record_id=record_id,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            description=description or f"{action} performed by {username}",
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id
        )
    except Exception as e:
        print(f"Error creating audit trail: {e}")


def create_reading_history(reading, recorded_by="system", role="system",
                            prev_user=None, prev_sup=None,
                            cur_user=None, cur_sup=None, units_used=None):
    """
    Create a historical snapshot of a reading, stamped with the current
    timestamp/cycle month.

    By default the reading's own current field values are recorded. Pass
    explicit prev_user/prev_sup/cur_user/cur_sup/units_used to override
    individual values (used by the Excel-upload flow, which needs to record
    the old "prev" values alongside brand-new "cur" values in one snapshot).
    """
    try:
        current_date = timezone.now().date()
        ReadingHistory.objects.create(
            reading_id=reading.id,
            user_id=reading.user_id,
            name=reading.name,
            phone=reading.phone,
            metre_num=reading.metre_num,
            grp=reading.grp,
            parent=reading.parent,
            prev_user=(reading.prev_user if prev_user is None else prev_user) or 0,
            prev_sup=(reading.prev_sup if prev_sup is None else prev_sup) or 0,
            cur_user=(reading.cur_user if cur_user is None else cur_user) or 0,
            cur_sup=(reading.cur_sup if cur_sup is None else cur_sup) or 0,
            mid_user=reading.mid_user,
            mid_sup=reading.mid_sup,
            units_used=(reading.units_used if units_used is None else units_used) or 0,
            rate=reading.rate or 0,
            reading_date=current_date,
            prev_date=reading.prev_date,
            cycle_month=current_date.strftime("%Y-%m"),
            recorded_by=recorded_by,
            role=role,
            version=getattr(reading, 'version', 1)
        )
    except Exception as e:
        print(f"Error creating reading history: {e}")


def create_payment_history(billing, amount, previous_balance,
                            payment_method='CASH', recorded_by="system",
                            role="system", notes=None):
    """Create a payment history record and return its generated receipt number."""
    try:
        receipt_number = f"RCP-{datetime.now().strftime('%Y%m%d')}-{billing.id}-{secrets.token_hex(4).upper()}"
        current_balance = previous_balance - amount
        payment_status = 'COMPLETED' if amount >= previous_balance else 'PARTIAL'

        PaymentHistory.objects.create(
            billing_id=billing.id,
            user_id=billing.user_id,
            name=billing.name,
            phone=billing.phone,
            grp=billing.grp,
            parent=billing.parent,
            amount_paid=amount,
            previous_balance=previous_balance,
            current_balance=current_balance,
            bill_amount=billing.bill,
            payment_method=payment_method,
            status=payment_status,
            receipt_number=receipt_number,
            notes=notes,
            recorded_by=recorded_by,
            role=role
        )
        return receipt_number
    except Exception as e:
        print(f"Error creating payment history: {e}")
        return None


def create_billing_history(billing, cycle_month, generated_by="system", role="system"):
    """Snapshot a Billings row into BillingHistory before it gets overwritten."""
    try:
        BillingHistory.objects.create(
            billing_id=billing.id,
            user_id=billing.user_id,
            name=billing.name,
            phone=billing.phone,
            metre_num=billing.sms_name,
            grp=billing.grp,
            parent=billing.parent,
            units_used=billing.units_used,
            rate=billing.rate,
            current_bill=billing.bill,
            previous_balance=billing.b_cd,
            total_due=billing.bill + billing.b_cd,
            amount_paid=billing.paid,
            remaining_balance=billing.bal,
            prev_reading=billing.prev_user,
            current_reading=billing.cur_user,
            cycle_month=cycle_month,
            billing_date=billing.billed_on or date.today(),
            due_date=(billing.billed_on or date.today()) + timedelta(days=30),
            status=billing.status,
            generated_by=generated_by,
            role=role
        )
    except Exception as e:
        print(f"Error creating billing history: {e}")


def update_customer_summary(user_id):
    """Recompute and persist the CustomerPaymentSummary row for a customer."""
    try:
        billing = Billings.objects.filter(user_id=user_id).first()
        if not billing:
            return

        summary, _ = CustomerPaymentSummary.objects.get_or_create(
            user_id=user_id,
            defaults={
                'name': billing.name,
                'phone': billing.phone,
                'metre_num': billing.sms_name,
                'grp': billing.grp,
                'parent': billing.parent,
            }
        )

        totals = Billings.objects.filter(user_id=user_id).aggregate(
            total_billed=Sum('bill'), total_paid=Sum('paid')
        )
        summary.total_billed = totals['total_billed'] or 0
        summary.total_paid = totals['total_paid'] or 0
        summary.current_balance = billing.bal

        last_payment = PaymentHistory.objects.filter(
            user_id=user_id, status='COMPLETED'
        ).order_by('-timestamp').first()

        if last_payment:
            summary.last_payment_date = last_payment.payment_date
            summary.last_payment_amount = last_payment.amount_paid
            summary.payment_count = PaymentHistory.objects.filter(
                user_id=user_id, status='COMPLETED'
            ).count()

        if billing.bal <= 0:
            summary.payment_status = 'PAID'
        elif billing.bal < 1000:
            summary.payment_status = 'CURRENT'
        elif billing.bal < 5000:
            summary.payment_status = 'OVERDUE'
        else:
            summary.payment_status = 'DELINQUENT'

        summary.save()
    except Exception as e:
        print(f"Error updating customer summary: {e}")


def update_reading_field(reading, field_name, new_value, username="system", role="system"):
    """Set a field on a (not-yet-saved) reading instance while logging the change."""
    old_value = (
        readings.objects
        .filter(id=reading.id)
        .values_list(field_name, flat=True)
        .first()
    )

    if old_value != new_value:
        history.objects.create(
            name=reading.name,
            field=field_name,
            old_val=old_value if old_value is not None else 0,
            new_val=new_value if new_value is not None else 0
        )
        create_log(
            username=username, role=role, action="UPDATE", table="readings",
            record_id=reading.id, field_changed=field_name,
            old_val=old_value, new_val=new_value,
            description=f"{field_name} updated for {reading.name}"
        )
        create_audit_trail(
            username=username, role=role, action="UPDATE", table_name="readings",
            record_id=reading.id, field_changed=field_name,
            old_value=old_value, new_value=new_value,
            description=f"{field_name} updated for {reading.name}"
        )

    setattr(reading, field_name, new_value)


#======================================================================================
# BILLING / PAYMENT HELPERS
#======================================================================================

def current_cycle_month():
    return timezone.now().strftime("%Y-%m")


def compute_billing_status(paid, total_due):
    """Shared Unpaid / Partially Paid / Paid classification."""
    if paid == 0:
        return "Unpaid"
    elif paid < total_due:
        return "Partially Paid"
    return "Paid"


def compute_bill_amount(units_used, rate, zero_threshold=2, flat_fee=300):
    """Metered bill (units * rate), or a flat fee when usage is at/below the threshold."""
    units_used = units_used or 0
    if units_used <= zero_threshold:
        return flat_fee
    return units_used * rate


def apply_new_billing_cycle(reading, bill_amount, recorded_by="system", role="system"):
    """
    Create or refresh the Billings record for a reading after a new reading
    has been recorded: brings down the previous balance, resets paid/penalty
    for the new cycle, snapshots BillingHistory, and refreshes the customer
    summary. Returns the saved Billings instance.
    """
    old_billing = Billings.objects.filter(user_id=reading.user_id).first()
    previous_balance = old_billing.bal if old_billing else Decimal("0")
    total_balance = previous_balance + Decimal(str(bill_amount))
    cycle_month = current_cycle_month()

    if old_billing:
        create_billing_history(old_billing, cycle_month, recorded_by, role)
        billing = old_billing
    else:
        billing = Billings(user_id=reading.user_id)

    billing.name = reading.name
    billing.phone = reading.phone
    billing.units_used = reading.units_used
    billing.rate = reading.rate
    billing.bill = bill_amount
    billing.b_cd = previous_balance
    billing.penalty = 0  # reset penalty/discount for the new cycle
    billing.bal = total_balance
    billing.paid = 0
    billing.status = "Unpaid"
    billing.prev_user = reading.prev_user
    billing.cur_user = reading.cur_user
    billing.sms_name = reading.metre_num
    billing.grp = reading.grp
    billing.parent = reading.parent
    billing.save()

    if not old_billing:
        create_billing_history(billing, cycle_month, recorded_by, role)

    update_customer_summary(reading.user_id)
    return billing


def apply_payment(billing, new_paid, previous_balance, payment_method,
                   username="system", role="system", notes=None):
    """
    Shared payment-processing logic: writes a PaymentHistory row for any
    increase in the amount paid, then recalculates paid/bal/status on the
    Billings record and refreshes the customer summary.

    Returns (receipt_number, old_paid, total_due).
    """
    old_paid = billing.paid
    amount = new_paid - old_paid
    receipt = None

    if amount > 0:
        receipt = create_payment_history(
            billing=billing,
            amount=amount,
            previous_balance=previous_balance,
            payment_method=payment_method,
            recorded_by=username,
            role=role,
            notes=notes
        )

    billing.paid = new_paid
    penalty = billing.penalty or Decimal("0")
    total_due = (billing.bill or 0) + (billing.b_cd or 0) + penalty
    billing.bal = total_due - new_paid
    billing.status = compute_billing_status(new_paid, total_due)
    billing.save()

    update_customer_summary(billing.user_id)
    return receipt, old_paid, total_due


#======================================================================================
# CYCLE / DATE HELPERS
#======================================================================================

def last_day_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def get_next_cycle_date(current_date):
    """Given any date, return the last day of the following month."""
    next_month = current_date.month + 1
    next_year = current_date.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    return last_day_of_month(next_year, next_month)


def snapshot_readings():
    global LAST_STATE_SNAPSHOT
    LAST_STATE_SNAPSHOT = list(readings.objects.values())


#======================================================================================
# GLOBAL STATE
#======================================================================================

CYCLE_SCHEDULER = {
    "end_time": None
}
BILLING_STATE = {
    "start_month": None,
}
LAST_STATE_SNAPSHOT = None


#======================================================================================
# CYCLE MANAGEMENT ENDPOINTS
#======================================================================================

@csrf_exempt
def set_cycle_duration(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        delta = timedelta(
            days=int(data.get("days", 0)),
            hours=int(data.get("hours", 0)),
            minutes=int(data.get("minutes", 0)),
            seconds=int(data.get("seconds", 0)),
        )
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
        return JsonResponse({"running": False, "days": 0, "hours": 0, "minutes": 0, "seconds": 0})

    diff = CYCLE_SCHEDULER["end_time"] - now
    if diff.total_seconds() <= 0:
        return JsonResponse({"running": False, "expired": True})

    return JsonResponse({
        "running": True,
        "days": diff.days,
        "hours": diff.seconds // 3600,
        "minutes": (diff.seconds % 3600) // 60,
        "seconds": diff.seconds % 60
    })


@csrf_exempt
def auto_shift_if_due(request):
    now = timezone.now()
    if not CYCLE_SCHEDULER["end_time"]:
        return JsonResponse({"message": "No cycle running"})
    if now < CYCLE_SCHEDULER["end_time"]:
        return JsonResponse({"message": "Not yet time"})

    CYCLE_SCHEDULER["end_time"] = None
    next_cycle_date = get_next_cycle_date(now.date())

    with transaction.atomic():
        for r in readings.objects.all():
            create_reading_history(r, "system", "system")

            r.prev_user = r.cur_user if r.cur_user is not None else r.prev_user
            r.prev_sup = r.cur_sup if r.cur_sup is not None else r.prev_sup
            r.prev_date = r.cur_date or r.prev_date
            r.cur_date = next_cycle_date
            r.cur_user = None
            r.cur_sup = None
            r.save()

    return JsonResponse({
        "message": "Auto shift completed",
        "next_cycle_date": str(next_cycle_date)
    })


@csrf_exempt
def start_billing_month(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        start_month = data.get("start_month")
        if not start_month:
            return JsonResponse({"error": "start_month required"}, status=400)

        year, month = map(int, start_month.split("-"))
        prev_date = last_day_of_month(year, month)
        cur_date = get_next_cycle_date(prev_date)

        with transaction.atomic():
            readings.objects.all().update(prev_date=prev_date, cur_date=cur_date)

            BillingCycleHistory.objects.create(
                cycle_month=start_month,
                start_date=prev_date,
                end_date=cur_date,
                next_cycle_date=cur_date + timedelta(days=30),
                status='IN_PROGRESS',
                started_by=data.get("username", "system")
            )

        BILLING_STATE["start_month"] = start_month
        return JsonResponse({
            "message": "Billing month started",
            "prev_date": str(prev_date),
            "cur_date": str(cur_date)
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# FETCH ENDPOINTS
#======================================================================================

def water_users(request):
    data = [{
        'id': u.id, 'fname': u.fname, 'phone': u.phone, 'metre_num': u.metre_num,
        'zone': u.zone, 'rate': u.rate,
        'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None,
        'grp': u.grp, 'parent': u.parent
    } for u in read_users.objects.all()]
    return JsonResponse(data, safe=False)


def hist_data(request):
    name = request.GET.get("name")
    field = request.GET.get("field")
    hist = history.objects.all()
    if name:
        hist = hist.filter(name__icontains=name)
    if field:
        hist = hist.filter(field__icontains=field)

    data = [{
        'id': h.id, 'name': h.name, 'field': h.field,
        'old_val': h.old_val, 'new_val': h.new_val,
        'changes_on': h.changed_on.strftime('%Y-%m-%d') if h.changed_on else None
    } for h in hist]
    return JsonResponse(data, safe=False)


def bill(request):
    data = [{
        'id': b.id, 'user_id': b.user_id, 'name': b.name, 'phone': b.phone,
        'units_used': b.units_used, 'rate': b.rate, 'bill': b.bill, 'paid': b.paid,
        'bal': b.bal, 'status': b.status, 'b_cd': b.b_cd,
        'penalty': float(b.penalty) if b.penalty is not None else 0,
        'prev_user': b.prev_user, 'cur_user': b.cur_user, 'sms_name': b.sms_name,
        'grp': b.grp, 'parent': b.parent
    } for b in Billings.objects.all()]
    return JsonResponse(data, safe=False)


def logs(request):
    data = [{
        'id': l.id, 'username': l.username, 'role': l.role, 'action': l.action,
        'table_name': l.table_name, 'record_id': l.record_id,
        'field_changed': l.field_changed, 'old_val': l.old_val, 'new_val': l.new_val,
        'description': l.description,
        'changed_at': l.changed_at.strftime('%Y-%m-%d %H:%M:%S') if l.changed_at else None
    } for l in Logs.objects.all().order_by('-changed_at')]
    return JsonResponse(data, safe=False)


def read_data(request):
    data = [{
        'id': r.id, 'user_id': r.user_id, 'name': r.name, 'phone': r.phone,
        'metre_num': r.metre_num, 'prev_user': r.prev_user, 'prev_sup': r.prev_sup,
        'prev_date': r.prev_date.strftime('%Y-%m-%d') if r.prev_date else None,
        'cur_user': r.cur_user, 'cur_sup': r.cur_sup,
        'cur_date': r.cur_date.strftime('%Y-%m-%d') if r.cur_date else None,
        'rate': r.rate, 'mid_user': r.mid_user, 'mid_sup': r.mid_sup,
        'grp': r.grp, 'parent': r.parent
    } for r in readings.objects.all()]
    return JsonResponse(data, safe=False)


#======================================================================================
# HISTORY FETCH ENDPOINTS (LIGHTWEIGHT / FILTERED)
#======================================================================================

@api_view(['GET'])
def get_reading_history(request):
    """Get reading history with filters (lightweight field set)."""
    user_id = request.GET.get('user_id')
    cycle_month = request.GET.get('cycle_month')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    history_qs = ReadingHistory.objects.all()
    if user_id:
        history_qs = history_qs.filter(user_id=user_id)
    if cycle_month:
        history_qs = history_qs.filter(cycle_month=cycle_month)
    if start_date:
        history_qs = history_qs.filter(timestamp__date__gte=start_date)
    if end_date:
        history_qs = history_qs.filter(timestamp__date__lte=end_date)

    data = list(history_qs.values(
        'id', 'name', 'phone', 'prev_user', 'cur_user',
        'units_used', 'cycle_month', 'timestamp', 'recorded_by', 'reading_date'
    ))
    return Response(data)


@api_view(['GET'])
def get_payment_history(request):
    """Get payment history with filters (lightweight field set)."""
    user_id = request.GET.get('user_id')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    history_qs = PaymentHistory.objects.all()
    if user_id:
        history_qs = history_qs.filter(user_id=user_id)
    if start_date:
        history_qs = history_qs.filter(payment_date__gte=start_date)
    if end_date:
        history_qs = history_qs.filter(payment_date__lte=end_date)

    data = list(history_qs.values(
        'id', 'name', 'phone', 'amount_paid', 'previous_balance',
        'current_balance', 'payment_method', 'receipt_number',
        'payment_date', 'recorded_by'
    ))
    return Response(data)


@api_view(['GET'])
def get_billing_history(request):
    """Get billing history with filters."""
    user_id = request.GET.get('user_id')
    cycle_month = request.GET.get('cycle_month')
    status_filter = request.GET.get('status')

    history_qs = BillingHistory.objects.all()
    if user_id:
        history_qs = history_qs.filter(user_id=user_id)
    if cycle_month:
        history_qs = history_qs.filter(cycle_month=cycle_month)
    if status_filter:
        history_qs = history_qs.filter(status=status_filter)

    data = list(history_qs.values(
        'id', 'name', 'phone', 'units_used', 'current_bill',
        'total_due', 'amount_paid', 'remaining_balance',
        'cycle_month', 'status', 'billing_date', 'due_date'
    ))
    return Response(data)


@api_view(['GET'])
def get_customer_history(request, user_id):
    """Get complete (reading + payment + billing) history for one customer."""
    try:
        reading_history = ReadingHistory.objects.filter(user_id=user_id).values(
            'timestamp', 'cur_user', 'prev_user', 'units_used',
            'cycle_month', 'recorded_by', 'reading_date'
        )
        payment_history = PaymentHistory.objects.filter(user_id=user_id).values(
            'timestamp', 'amount_paid', 'previous_balance',
            'current_balance', 'payment_method', 'receipt_number', 'payment_date'
        )
        billing_history = BillingHistory.objects.filter(user_id=user_id).values(
            'cycle_month', 'current_bill', 'total_due', 'amount_paid',
            'remaining_balance', 'status'
        )

        return Response({
            'user_id': user_id,
            'reading_history': reading_history,
            'payment_history': payment_history,
            'billing_history': billing_history
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#======================================================================================
# AUTHENTICATION
#======================================================================================

@csrf_exempt
def login_user(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        admin = Admin.objects.filter(
            username=data.get("username"), password=data.get("password")
        ).first()
        if not admin:
            return JsonResponse({"error": "Invalid login credentials"}, status=401)

        token = secrets.token_hex(32)
        create_log("admin", "admin", "LOGIN", "admin", admin.id, "Admin logged into system")
        create_audit_trail(
            username="admin", role="admin", action="LOGIN",
            description="Admin logged into system", request=request
        )
        return JsonResponse({"token": token})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def users_login(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
    try:
        data = json.loads(request.body)
        user = Users.objects.filter(
            username=data.get("username"), password=data.get("password")
        ).first()
        if not user:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

        token = secrets.token_hex(16)
        create_log(user.username, user.role, "LOGIN", "users", user.id,
                   f"{user.username} logged into system")
        create_audit_trail(
            username=user.username, role=user.role, action="LOGIN",
            description=f"{user.username} logged into system", request=request
        )
        return JsonResponse({"token": token, "username": user.username, "role": user.role})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# USER MANAGEMENT
#======================================================================================

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
                fname=fname, phone=phone, metre_num=metre_num,
                zone=zone, rate=rate, grp=grp, parent=parent
            )
            today = date.today()
            reading = readings.objects.create(
                user=user, name=fname, phone=phone,
                prev_user=0, prev_sup=0, prev_date=today,
                cur_user=None, cur_sup=None, cur_date=today,
                units_used=0, rate=rate, metre_num=metre_num,
                grp=grp, parent=parent
            )

            create_reading_history(reading, user_name, role)

            create_log(user_name, role, "CREATE", "waterusers", user.id,
                       f"{user_name} created new customer {fname}")
            create_audit_trail(
                username=user_name, role=role, action="CREATE",
                table_name="waterusers", record_id=user.id,
                description=f"{user_name} created new customer {fname}",
                request=request
            )

        return JsonResponse({"message": "User registered successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


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
            try:
                user = read_users.objects.get(id=user_id)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)

            old_name = user.fname
            old_data = {
                'fname': user.fname, 'phone': user.phone, 'metre_num': user.metre_num,
                'zone': user.zone, 'rate': user.rate, 'grp': user.grp, 'parent': user.parent
            }

            user.fname = fname or user.fname
            user.phone = phone or user.phone
            user.metre_num = metre_num or user.metre_num
            user.zone = zone or user.zone
            user.rate = rate or user.rate
            user.grp = grp or user.grp
            user.parent = parent or user.parent
            user.save()

            readings.objects.filter(user_id=user_id).update(
                name=fname, phone=phone, metre_num=metre_num,
                rate=rate, grp=grp, parent=parent
            )
            Billings.objects.filter(user_id=user_id).update(
                name=fname, phone=phone, rate=rate,
                sms_name=metre_num, grp=grp, parent=parent
            )

            update_customer_summary(user_id)

            create_log(user_name, role, "UPDATE", "waterusers", user_id,
                       f"{role} updated customer {old_name} → {fname}")
            create_audit_trail(
                username=user_name, role=role, action="UPDATE",
                table_name="waterusers", record_id=user_id,
                old_value=json.dumps(old_data),
                new_value=json.dumps({
                    'fname': user.fname, 'phone': user.phone, 'metre_num': user.metre_num,
                    'zone': user.zone, 'rate': user.rate, 'grp': user.grp, 'parent': user.parent
                }),
                description=f"{role} updated customer {old_name} → {fname}",
                request=request
            )

        return JsonResponse({"message": "User updated successfully"})
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

            for r in readings.objects.filter(user_id=user_id):
                create_reading_history(r, user_name, role)

            readings.objects.filter(user_id=user_id).delete()
            Billings.objects.filter(user_id=user_id).delete()
            Billings.objects.filter(name=user.fname).delete()
            CustomerPaymentSummary.objects.filter(user_id=user_id).delete()
            user.delete()

            create_log(user_name, role, "DELETE", "waterusers", user_id,
                       f"{user_name} deleted customer {fname}, readings, billings")
            create_audit_trail(
                username=user_name, role=role, action="DELETE",
                table_name="waterusers", record_id=user_id,
                description=f"{user_name} deleted customer {fname}",
                request=request
            )

        return JsonResponse({"message": "User fully deleted"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# SUBMIT READINGS AND BILLING
#======================================================================================

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
                reading = readings.objects.select_for_update().get(user_id=item["user_id"])

                cur_user = item.get("cur_user")
                cur_sup = item.get("cur_sup")

                if cur_user is not None:
                    cur_user = int(cur_user)
                    reading.units_used = max(0, cur_user - (reading.prev_user or 0))
                    update_reading_field(reading, "cur_user", cur_user, user_name, role)

                if cur_sup is not None:
                    update_reading_field(reading, "cur_sup", cur_sup, user_name, role)

                reading.mid_user = item.get("mid_user", reading.mid_user)
                reading.mid_sup = item.get("mid_sup", reading.mid_sup)
                reading.save()

                create_reading_history(reading, user_name, role)

                bill_amount = compute_bill_amount(reading.units_used, reading.rate, zero_threshold=2)
                apply_new_billing_cycle(reading, bill_amount, user_name, role)

                create_audit_trail(
                    username=user_name, role=role, action="UPDATE",
                    table_name="readings", record_id=reading.id,
                    description=f"Reading submitted for {reading.name}",
                    request=request
                )

        return JsonResponse({"message": "Saved successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# PAYMENT UPDATES
#======================================================================================

@csrf_exempt
def update_paid(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)

        if isinstance(data, list):
            updated = []
            with transaction.atomic():
                for item in data:
                    billing = Billings.objects.get(id=item.get("id"))
                    new_paid = Decimal(str(item.get("paid", 0)))
                    amount = new_paid - billing.paid
                    # bulk uploads record the pre-payment balance as bal + amount
                    previous_balance = billing.bal + amount if amount > 0 else billing.bal

                    receipt, old_paid, _ = apply_payment(
                        billing, new_paid, previous_balance, 'BULK',
                        item.get("username", "system"), item.get("role", "system")
                    )

                    create_log(
                        item.get("username", "system"), item.get("role", "system"),
                        "UPDATE", "billings", billing.id,
                        f"bulk update: {old_paid} → {new_paid}",
                        "paid", old_paid, new_paid
                    )

                    updated.append({
                        "id": billing.id, "paid": billing.paid,
                        "bal": billing.bal, "status": billing.status
                    })

            return JsonResponse({"message": "Bulk payment updated successfully", "updated": updated})

        else:
            billing = Billings.objects.get(id=data.get("id"))
            new_paid = Decimal(str(data.get("paid", 0)))
            previous_balance = billing.bal

            receipt, old_paid, _ = apply_payment(
                billing, new_paid, previous_balance,
                data.get("payment_method", 'CASH'),
                data.get("username", "system"), data.get("role", "system"),
                notes=data.get("notes")
            )

            create_log(
                data.get("username"), data.get("role"), "UPDATE", "billings", billing.id,
                f"{data.get('role')} updated payment from {old_paid} to {new_paid}",
                "paid", old_paid, new_paid
            )

            return JsonResponse({
                "message": "Payment updated",
                "id": billing.id,
                "paid": billing.paid,
                "bal": billing.bal,
                "status": billing.status,
                "receipt_number": receipt
            })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# PENALTY / DISCOUNT MANAGEMENT
#======================================================================================

@csrf_exempt
def update_billing_penalty(request):
    """
    Add, change, or clear a penalty/discount on a single billing record.

    Expected POST body:
        {
            "id": <billing id>,
            "type": "penalty" | "discount" | "reset",
            "amount": <positive number, ignored for "reset">,
            "username": "...",
            "role": "..."
        }

    Storage rule: penalty column holds a POSITIVE number for a penalty and a
    NEGATIVE number for a discount. "reset" sets it back to 0.
    bal (amount to pay) is always recalculated as: bal = bill + b_cd + penalty - paid
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        billing_id = data.get("id")
        action_type = (data.get("type") or "").lower()
        username = data.get("username", "system")
        role = data.get("role", "system")

        if not billing_id:
            return JsonResponse({"error": "Billing id is required"}, status=400)
        if action_type not in ("penalty", "discount", "reset"):
            return JsonResponse({"error": "type must be 'penalty', 'discount' or 'reset'"}, status=400)

        with transaction.atomic():
            try:
                billing = Billings.objects.select_for_update().get(id=billing_id)
            except Billings.DoesNotExist:
                return JsonResponse({"error": "Billing record not found"}, status=404)

            old_penalty = billing.penalty or Decimal("0")

            if action_type == "reset":
                new_penalty = Decimal("0")
                label = "Removed penalty/discount"
            else:
                try:
                    amount = Decimal(str(data.get("amount", 0)))
                except Exception:
                    return JsonResponse({"error": "Invalid amount"}, status=400)
                amount = abs(amount)  # amount is always entered as a positive number

                if action_type == "penalty":
                    new_penalty = amount
                    label = f"Added penalty of {amount}"
                else:  # discount
                    new_penalty = -amount
                    label = f"Added discount of {amount}"

            billing.penalty = new_penalty
            paid = billing.paid or Decimal("0")
            total_due = (billing.bill or 0) + (billing.b_cd or 0) + new_penalty
            billing.bal = total_due - paid
            billing.status = compute_billing_status(paid, total_due)
            billing.save()

            update_customer_summary(billing.user_id)

            create_log(
                username=username, role=role, action="UPDATE", table="billings",
                record_id=billing.id, field_changed="penalty",
                old_val=old_penalty, new_val=new_penalty,
                description=f"{label} for {billing.name}"
            )
            create_audit_trail(
                username=username, role=role, action="UPDATE", table_name="billings",
                record_id=billing.id, field_changed="penalty",
                old_value=str(old_penalty), new_value=str(new_penalty),
                description=f"{label} for {billing.name}", request=request
            )

        return JsonResponse({
            "message": "Penalty/discount updated successfully",
            "id": billing.id,
            "penalty": float(billing.penalty),
            "bill": billing.bill,
            "b_cd": billing.b_cd,
            "paid": billing.paid,
            "bal": billing.bal,
            "status": billing.status
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# MONTH FINALIZATION
#======================================================================================

@csrf_exempt
def finalize_month(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        username = data.get("username", "system")
        role = data.get("role", "system")

        today = datetime.now()
        last_day = calendar.monthrange(today.year, today.month)[1]
        cycle_end = datetime(today.year, today.month, last_day, 23, 59, 59)

        if today < cycle_end:
            return JsonResponse({"error": "Cycle not finished yet"}, status=400)

        next_cycle_date = get_next_cycle_date(today.date())

        with transaction.atomic():
            current_cycle = BillingCycleHistory.objects.filter(
                cycle_month=today.strftime("%Y-%m")
            ).first()

            if current_cycle:
                current_cycle.status = 'COMPLETED'
                current_cycle.completed_by = username
                current_cycle.completed_at = timezone.now()
                current_cycle.save()

            for r in readings.objects.all():
                create_reading_history(r, username, role)

                if r.cur_user is not None:
                    r.prev_user = r.cur_user
                if r.cur_sup is not None:
                    r.prev_sup = r.cur_sup

                r.cur_user = None
                r.cur_sup = None
                r.mid_user = 0
                r.mid_sup = 0
                r.prev_date = r.cur_date or r.prev_date
                r.cur_date = next_cycle_date
                r.save()

            BillingCycleHistory.objects.create(
                cycle_month=next_cycle_date.strftime("%Y-%m"),
                start_date=next_cycle_date,
                end_date=next_cycle_date + timedelta(days=30),
                next_cycle_date=next_cycle_date + timedelta(days=60),
                status='PENDING',
                started_by=username
            )

            create_audit_trail(
                username=username, role=role, action="SYSTEM", table_name="readings",
                description=f"Month finalized for {today.strftime('%Y-%m')}",
                request=request
            )

        return JsonResponse({"message": "Cycle shifted successfully", "next_cycle_date": str(next_cycle_date)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#======================================================================================
# EMPLOYEE MANAGEMENT
#======================================================================================

@api_view(['POST'])
def register_user(request):
    user = Users.objects.create(
        username=request.data.get('username'),
        password=request.data.get('password'),
        role=request.data.get('role')
    )
    create_log("Admin", "admin", "CREATE", "users", user.id,
               f"Admin created employee {user.username}")
    create_audit_trail(
        username="Admin", role="admin", action="CREATE", table_name="users",
        record_id=user.id, description=f"Admin created employee {user.username}",
        request=request
    )
    return Response({"message": "User registered successfully"})


@api_view(['GET'])
def list_employees(request):
    return Response(list(Users.objects.all().values('id', 'username', 'role')))


@csrf_exempt
def delete_employee(request, emp_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        Users.objects.get(id=emp_id).delete()
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


#======================================================================================
# ANALYTICS
#======================================================================================

def total_bill(request):
    total = Billings.objects.aggregate(v=Sum('bill'))['v'] or 0
    return JsonResponse({"total_bill": round(float(total), 2)})


def total_bal(request):
    total = Billings.objects.aggregate(v=Sum('b_cd'))['v'] or 0
    return JsonResponse({"total_bal": round(float(total), 2)})


def total_paid(request):
    total = Billings.objects.aggregate(v=Sum('paid'))['v'] or 0
    return JsonResponse({"total_paid": round(float(total), 2)})


def total_units(request):
    total = Billings.objects.aggregate(v=Sum('units_used'))['v'] or 0
    return JsonResponse({"total_units": round(float(total), 2)})


def total_cust(request):
    total = read_users.objects.aggregate(v=Count('id'))['v'] or 0
    return JsonResponse({"total_cust": total})


def avg_units(request):
    avg = Billings.objects.aggregate(v=Avg('units_used'))['v'] or 0
    return JsonResponse({"avg_units": round(float(avg), 2)})


#======================================================================================
# EXCEL UPLOAD/DOWNLOAD
#======================================================================================

def download_readings_template(request):
    template_path = os.path.join(settings.BASE_DIR, "templates", "readings_template.xlsx")
    wb = load_workbook(template_path)
    ws = wb.active

    readings_data = readings.objects.all().values(
        "user_id", "name", "phone", "metre_num", "prev_user", "prev_sup"
    )

    row = 2
    for r in readings_data:
        ws[f"A{row}"] = r["user_id"]
        ws[f"B{row}"] = r["name"]
        ws[f"C{row}"] = r["phone"]
        ws[f"D{row}"] = r["metre_num"]
        ws[f"E{row}"] = r["prev_user"]
        ws[f"F{row}"] = r["prev_sup"]
        for col in ["G", "H", "I", "J"]:
            ws[f"{col}{row}"] = None
        row += 1

    while row <= ws.max_row:
        for col in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
            ws[f"{col}{row}"] = None
        row += 1

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="readings_template.xlsx"'
    wb.save(response)
    return response


@csrf_exempt
def upload_readings_excel(request):
    """
    Automated Excel upload. For each row: records a ReadingHistory snapshot
    (old prev vs new cur), updates the readings table, refreshes billing,
    updates customer summaries, and writes an audit trail.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        df = pd.read_excel(file)
        if "user_id" not in df.columns:
            return JsonResponse({"error": "Excel must contain user_id column"}, status=400)

        processed = 0
        skipped = 0
        errors = []

        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    user_id = row.get("user_id")
                    if pd.isna(user_id):
                        skipped += 1
                        continue

                    reading = readings.objects.select_for_update().get(user_id=int(user_id))

                    old_prev_user = reading.prev_user or 0
                    old_prev_sup = reading.prev_sup or 0
                    old_cur_user = reading.cur_user or 0
                    old_cur_sup = reading.cur_sup or 0

                    cur_user = None if pd.isna(row.get("cur_user")) else int(row.get("cur_user"))
                    cur_sup = None if pd.isna(row.get("cur_sup")) else int(row.get("cur_sup"))
                    mid_user = None if pd.isna(row.get("mid_user")) else int(row.get("mid_user"))
                    mid_sup = None if pd.isna(row.get("mid_sup")) else int(row.get("mid_sup"))

                    if cur_user is None and cur_sup is None and mid_user is None and mid_sup is None:
                        skipped += 1
                        continue

                    units_used = reading.units_used or 0
                    if cur_user is not None:
                        units_used = max(0, cur_user - (reading.prev_user or 0))

                    # Snapshot BEFORE updating so both old "prev" and new "cur" are recorded
                    create_reading_history(
                        reading,
                        recorded_by="excel_upload", role="system",
                        prev_user=old_prev_user, prev_sup=old_prev_sup,
                        cur_user=cur_user if cur_user is not None else old_cur_user,
                        cur_sup=cur_sup if cur_sup is not None else old_cur_sup,
                        units_used=units_used
                    )

                    if cur_user is not None:
                        reading.cur_user = cur_user
                        reading.units_used = units_used
                    if cur_sup is not None:
                        reading.cur_sup = cur_sup
                    if mid_user is not None:
                        reading.mid_user = mid_user
                    if mid_sup is not None:
                        reading.mid_sup = mid_sup
                    reading.save()

                    bill_amount = compute_bill_amount(reading.units_used, reading.rate, zero_threshold=2)
                    apply_new_billing_cycle(reading, bill_amount, "excel_upload", "system")

                    create_log(
                        username="excel_upload", role="system", action="UPDATE",
                        table="readings", record_id=reading.id,
                        description=f"Excel upload: Prev={old_prev_user} → Curr={cur_user}, Units={units_used}"
                    )

                    processed += 1

                except readings.DoesNotExist:
                    errors.append(f"Row {index}: User ID {row.get('user_id')} not found")
                    skipped += 1
                except Exception as row_error:
                    errors.append(f"Row {index}: {str(row_error)}")
                    skipped += 1

            create_audit_trail(
                username="excel_upload", role="system", action="BULK_UPLOAD",
                table_name="readings",
                description=f"Excel upload: {processed} records processed, {skipped} skipped",
                request=request
            )

        return JsonResponse({
            "message": "Excel uploaded and processed successfully",
            "processed_rows": processed,
            "skipped_rows": skipped,
            "errors": errors[:10]
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)




def download_billings_template(request):
    template_path = os.path.join(
        settings.BASE_DIR,
        "templates",
        "Billings.xlsx"
    )
    # Load the existing Excel template
    wb = load_workbook(template_path)
    ws = wb.active
    # Get billing records from the database
    billings_data = Billings.objects.all().order_by("id")
    # Start inserting customer data from row 6
    row = 6
    #CALCULATE THE REQUIRED METRICS
    total_customers = Billings.objects.count()
    for billing in billings_data:
        #total customers
        ws.cell(row=2, column=9).value=total_customers
        ws.cell(row=2, column=3).value='Aug-2026'
        ws.cell(row=2, column=6).value='31-Aug-26'
        # A - ID
        ws.cell(row=row, column=1).value = billing.id
        # B - Name
        ws.cell(row=row, column=2).value = billing.name
        # C - Phone
        ws.cell(row=row, column=3).value = billing.phone
        # D - Units Used
        ws.cell(row=row, column=4).value = billing.units_used
        # E - Rate
        ws.cell(row=row, column=5).value = billing.rate
        # F - Bill
        ws.cell(row=row, column=6).value = billing.bill
        # G - B_CD / Previous Balance
        ws.cell(row=row, column=7).value = billing.b_cd
        # H - Penalty
        ws.cell(row=row, column=8).value = billing.penalty
        # I - Bill + B_CD + Penalty
        bill = billing.bill or Decimal("0")
        b_cd = billing.b_cd or Decimal("0")
        penalty = billing.penalty or Decimal("0")
        ws.cell(row=row, column=9).value = bill + b_cd + penalty
        # J - Amount Paid
        # Leave this blank for the user to enter payment
        ws.cell(row=row, column=10).value = None
        # K - Balance
        # I - J
        ws.cell(row=row, column=11).value = f"=I{row}-J{row}"
        row += 1
    # Tell Excel to recalculate formulas when the file is opened
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"
    # Create Excel response
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = (
        'attachment; filename="billings_template.xlsx"'
    )
    # Save workbook directly to response
    wb.save(response)
    return response


import uuid  # add to the top-level imports in views.py

# Folder where "pending" (not-yet-committed) billing uploads are stored.
PENDING_BILLINGS_UPLOAD_DIR = os.path.join(settings.BASE_DIR, "temp_uploads", "billings")
os.makedirs(PENDING_BILLINGS_UPLOAD_DIR, exist_ok=True)


def _pending_upload_path(token):
    # Guard against path traversal — token is always a uuid4 hex string.
    safe_token = "".join(ch for ch in str(token) if ch.isalnum())
    return os.path.join(PENDING_BILLINGS_UPLOAD_DIR, f"{safe_token}.xlsx")


def _read_pending_billing_rows(path, start_row=6, id_col=1, paid_col=10):
    
    wb = load_workbook(path, data_only=True)
    ws = wb.active

    rows = []
    for row_num in range(start_row, ws.max_row + 1):
        billing_id = ws.cell(row=row_num, column=id_col).value
        paid = ws.cell(row=row_num, column=paid_col).value

        if billing_id is None or paid is None:
            continue
        if isinstance(paid, str) and paid.strip() == "":
            continue

        rows.append((row_num, billing_id, paid))

    return rows


@csrf_exempt
def upload_billings_excel(request):
    
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        token = uuid.uuid4().hex
        saved_path = _pending_upload_path(token)

        with open(saved_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        return JsonResponse({
            "message": "Sheet uploaded successfully. Click \"Extract Data\" to preview the changes.",
            "token": token
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def extract_billings_excel(request):
    
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        if not token:
            return JsonResponse({"error": "Missing upload token"}, status=400)

        saved_path = _pending_upload_path(token)
        if not os.path.exists(saved_path):
            return JsonResponse(
                {"error": "Upload not found or already processed. Please upload the sheet again."},
                status=404
            )

        try:
            rows = _read_pending_billing_rows(saved_path)
        except Exception as read_error:
            return JsonResponse({"error": f"Could not read the Excel file: {read_error}"}, status=400)

        preview = []
        errors = []

        for row_num, billing_id, paid in rows:
            try:
                billing = Billings.objects.filter(id=int(billing_id)).first()
                if not billing:
                    errors.append(f"Row {row_num}: Billing ID {billing_id} not found")
                    continue

                new_paid = Decimal(str(paid))
                penalty = billing.penalty or Decimal("0")
                total_due = (billing.bill or 0) + (billing.b_cd or 0) + penalty
                new_bal = total_due - new_paid
                new_status = compute_billing_status(new_paid, total_due)

                preview.append({
                    "id": billing.id,
                    "paid": float(new_paid),
                    "bal": float(new_bal),
                    "status": new_status
                })
            except Exception as row_error:
                errors.append(f"Row {row_num}: {str(row_error)}")

        if not preview:
            return JsonResponse({
                "error": "No valid rows could be extracted from this sheet (expected data in rows 6+, ID in column A, Paid in column J). Please check it and try again.",
                "row_errors": errors[:10]
            }, status=400)

        return JsonResponse({
            "message": f"Data extracted successfully — {len(preview)} record(s) ready for review. Nothing has been saved yet.",
            "preview": preview,
            "errors": errors[:10],
            "token": token
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def commit_billings_excel(request):
    
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        if not token:
            return JsonResponse({"error": "Missing upload token"}, status=400)

        saved_path = _pending_upload_path(token)
        if not os.path.exists(saved_path):
            return JsonResponse(
                {"error": "Upload not found or already processed. Please upload the sheet again."},
                status=404
            )

        try:
            rows = _read_pending_billing_rows(saved_path)
        except Exception as read_error:
            return JsonResponse({"error": f"Could not read the Excel file: {read_error}"}, status=400)

        updated = []
        errors = []

        with transaction.atomic():
            for row_num, billing_id, paid in rows:
                try:
                    billing = Billings.objects.get(id=int(billing_id))
                    new_paid = Decimal(str(paid))
                    previous_balance = billing.bal

                    receipt, old_paid, _ = apply_payment(
                        billing, new_paid, previous_balance, 'EXCEL',
                        username=data.get("username", "excel_upload"),
                        role=data.get("role", "system")
                    )

                    create_log(
                        data.get("username", "excel_upload"), data.get("role", "system"),
                        "UPDATE", "billings", billing.id,
                        f"Excel update: {old_paid} → {new_paid}", "paid", old_paid, new_paid
                    )
                    updated.append({
                        "id": billing.id, "paid": billing.paid,
                        "bal": billing.bal, "status": billing.status
                    })
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")

            create_audit_trail(
                username=data.get("username", "excel_upload"), role=data.get("role", "system"),
                action="BULK_UPLOAD", table_name="billings",
                description=f"Excel billing upload committed: {len(updated)} record(s) updated",
                request=request
            )

        # Now that it's permanently saved, the pending file can go
        try:
            os.remove(saved_path)
        except OSError:
            pass

        return JsonResponse({
            "message": "Committed successfully — payments have been permanently saved to the database.",
            "updated": updated,
            "updated_count": len(updated),
            "errors": errors[:10]
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def rollback_billings_excel(request):
    
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")

        if token:
            saved_path = _pending_upload_path(token)
            if os.path.exists(saved_path):
                os.remove(saved_path)

        return JsonResponse({
            "message": "Rolled back — no changes were saved. The billing table has been restored."
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def download_users_excel(request):
    users = read_users.objects.all().values(
        "id", "fname", "phone", "metre_num", "zone", "rate", "grp", "parent", "created_on"
    )
    df = pd.DataFrame(list(users))
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="water_users.xlsx"'
    df.to_excel(response, index=False)
    return response


#======================================================================================
# OTHER UTILITY ENDPOINTS
#======================================================================================

def billing_timer(request):
    today = datetime.now()
    end_date_only = get_next_cycle_date(today.date())
    end_date = datetime(end_date_only.year, end_date_only.month, end_date_only.day, 23, 59, 59)

    diff = end_date - today
    return JsonResponse({
        "days": diff.days,
        "hours": diff.seconds // 3600,
        "minutes": (diff.seconds % 3600) // 60,
        "seconds": diff.seconds % 60
    })


@csrf_exempt
def reset_mid_month_readings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        username = data.get("username", "system")
        role = data.get("role", "system")

        with transaction.atomic():
            for r in readings.objects.all():
                old_mid_user = r.mid_user
                old_mid_sup = r.mid_sup

                create_reading_history(r, username, role)

                r.mid_user = 0
                r.mid_sup = 0
                r.save()

                create_log(
                    username=username, role=role, action="UPDATE", table="readings",
                    record_id=r.id, field_changed="mid_month_reset",
                    old_val=f"user:{old_mid_user}, sup:{old_mid_sup}",
                    new_val="user:0, sup:0",
                    description=f"Mid-month readings reset for {r.name}"
                )

        return JsonResponse({"message": "Mid-month readings reset successfully"})
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


@csrf_exempt
def update_all_users(request):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT request required"}, status=405)
    try:
        customers = json.loads(request.body)
        with transaction.atomic():
            for customer in customers:
                user = read_users.objects.get(id=customer["id"])

                user.fname = customer["fname"]
                user.phone = customer["phone"]
                user.metre_num = customer["metre_num"]
                user.rate = customer["rate"]
                user.grp = customer["grp"]
                user.parent = customer["parent"]
                user.save()

                readings.objects.filter(user_id=user.id).update(
                    name=user.fname, phone=user.phone, metre_num=user.metre_num,
                    rate=user.rate, grp=user.grp, parent=user.parent
                )
                Billings.objects.filter(user_id=user.id).update(
                    name=user.fname, phone=user.phone, rate=user.rate,
                    sms_name=user.metre_num, grp=user.grp, parent=user.parent
                )

                update_customer_summary(user.id)

        return JsonResponse({"success": True, "message": "All users updated successfully."})
    except read_users.DoesNotExist:
        return JsonResponse({"error": "One or more users do not exist."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def update_all_bill_phones(request):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT request required"}, status=405)
    try:
        data = json.loads(request.body)
        phone = data.get("phone")
        if not phone:
            return JsonResponse({"error": "Phone number is required"}, status=400)

        updated = Billings.objects.update(phone=phone)
        CustomerPaymentSummary.objects.update(phone=phone)

        return JsonResponse({"success": True, "updated": updated})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


#======================================================================================
# SMS FUNCTIONS
#======================================================================================

API_URL = "https://quicksms.advantasms.com/api/services/sendbulk"
PARTNER_ID = "16256"
API_KEY = "bc1bc562ccb7c72732e7fa0add447129"
SHORTCODE = "AdvantaSMS"


def send_bulk_sms(customers):
    payload = {
        "count": len(customers),
        "smslist": [
            {
                "partnerID": PARTNER_ID,
                "apikey": API_KEY,
                "pass_type": "plain",
                "clientsmsid": i + 1,
                "mobile": customer["phone"],
                "message": customer["message"],
                "shortcode": SHORTCODE
            }
            for i, customer in enumerate(customers)
        ]
    }
    response = requests.post(API_URL, json=payload, headers={"Content-Type": "application/json"})
    return response.json()


@csrf_exempt
def send_sms_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        customers = data.get("customers", [])
        if not customers:
            return JsonResponse({"error": "No customers selected"}, status=400)

        result = send_bulk_sms(customers)

        create_audit_trail(
            username=data.get("username", "system"), role=data.get("role", "system"),
            action="EXPORT", table_name="sms",
            description=f"SMS sent to {len(customers)} customers",
            request=request
        )

        return JsonResponse(result, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def process_reading_update(
    user_id, new_cur_user=None, new_cur_sup=None,
    mid_user=None, mid_sup=None, username="system", role="system"
):
    """
    Non-HTTP helper for applying a single reading update (used by internal
    automation / scheduled jobs rather than the HTTP endpoints above).
    """
    try:
        reading = readings.objects.get(user_id=user_id)
    except readings.DoesNotExist:
        create_log(username, role, "ERROR", "readings", user_id, "Reading record not found")
        return

    prev_user = reading.prev_user or 0
    prev_sup = reading.prev_sup or 0

    if mid_user is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"mid_user {reading.mid_user} → {mid_user}",
                   "mid_user", reading.mid_user, mid_user)
        update_reading_field(reading, "mid_user", mid_user, username, role)

    if mid_sup is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"mid_sup {reading.mid_sup} → {mid_sup}",
                   "mid_sup", reading.mid_sup, mid_sup)
        update_reading_field(reading, "mid_sup", mid_sup, username, role)

    if new_cur_user is None and new_cur_sup is None:
        reading.save()
        return

    units_used = reading.units_used or 0
    if new_cur_user is not None:
        try:
            units_used = max(0, int(new_cur_user) - int(prev_user))
        except Exception:
            create_log(username, role, "ERROR", "readings", reading.id, "Invalid numeric reading input")
            return

        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"user reading {prev_user} → {new_cur_user}",
                   "cur_user", prev_user, new_cur_user)
        update_reading_field(reading, "cur_user", new_cur_user, username, role)

    if new_cur_sup is not None:
        create_log(username, role, "UPDATE", "readings", reading.id,
                   f"sup reading {prev_sup} → {new_cur_sup}",
                   "cur_sup", prev_sup, new_cur_sup)
        update_reading_field(reading, "cur_sup", new_cur_sup, username, role)

    reading.units_used = units_used
    reading.save()

    create_reading_history(reading, username, role)

    if new_cur_user is not None:
        rate = reading.rate or 0
        bill_amount = compute_bill_amount(units_used, rate, zero_threshold=2)

        old_billing = Billings.objects.filter(user_id=user_id).first()
        previous_balance = old_billing.bal if old_billing else Decimal("0")

        billing, created = Billings.objects.get_or_create(
            user_id=user_id,
            billed_on=date.today(),
            defaults={
                "name": reading.name, "phone": reading.phone,
                "units_used": units_used, "rate": rate, "bill": bill_amount,
                "paid": 0, "penalty": 0, "bal": bill_amount, "status": "Unpaid",
                "b_cd": previous_balance, "prev_user": reading.prev_user,
                "cur_user": reading.cur_user, "sms_name": reading.metre_num,
                "grp": reading.grp, "parent": reading.parent
            }
        )

        if not created:
            create_billing_history(billing, current_cycle_month(), username, role)

            billing.units_used = units_used
            billing.bill = bill_amount
            billing.paid = 0
            billing.penalty = 0  # reset penalty/discount for the new cycle
            billing.b_cd = previous_balance
            billing.bal = previous_balance + Decimal(str(bill_amount))
            billing.status = compute_billing_status(billing.paid, bill_amount)
            billing.save()

        update_customer_summary(user_id)


#======================================================================================
# PAYMENT HISTORY SERIALIZATION + FETCH ENDPOINTS
#======================================================================================

def _payment_method_display(method):
    return dict(PaymentHistory.PAYMENT_METHODS).get(method, method)


def _payment_status_display(status_value):
    return dict(PaymentHistory.PAYMENT_STATUS).get(status_value, status_value)


def _serialize_payment(p):
    """Shared serializer for PaymentHistory rows, used across all payment-history endpoints."""
    return {
        'id': p.id,
        'billing_id': p.billing_id,
        'user_id': p.user_id,
        'name': p.name,
        'phone': p.phone,
        'grp': p.grp,
        'parent': p.parent,
        'amount_paid': float(p.amount_paid),
        'previous_balance': float(p.previous_balance),
        'current_balance': float(p.current_balance),
        'bill_amount': float(p.bill_amount),
        'payment_method': p.payment_method,
        'payment_method_display': _payment_method_display(p.payment_method),
        'status': p.status,
        'status_display': _payment_status_display(p.status),
        'receipt_number': p.receipt_number,
        'notes': p.notes,
        'payment_date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else None,
        'recorded_by': p.recorded_by,
        'role': p.role,
        'timestamp': p.timestamp.strftime('%Y-%m-%d %H:%M:%S') if p.timestamp else None
    }


@api_view(['GET'])
def get_all_payment_history(request):
    """Fetch all payment history records with optional filters."""
    try:
        user_id = request.GET.get('user_id')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        payment_method = request.GET.get('payment_method')
        status_filter = request.GET.get('status')
        search = request.GET.get('search')

        qs = PaymentHistory.objects.all()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if start_date:
            qs = qs.filter(payment_date__gte=start_date)
        if end_date:
            qs = qs.filter(payment_date__lte=end_date)
        if payment_method:
            qs = qs.filter(payment_method=payment_method)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))

        qs = qs.order_by('-timestamp')
        data = [_serialize_payment(p) for p in qs]

        total_amount = qs.aggregate(total=Sum('amount_paid'))['total'] or 0

        return Response({
            'success': True,
            'data': data,
            'summary': {
                'total_payments': qs.count(),
                'total_amount': float(total_amount),
                'filters_applied': {
                    'user_id': user_id, 'start_date': start_date, 'end_date': end_date,
                    'payment_method': payment_method, 'status': status_filter, 'search': search
                }
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_payment_history_by_user(request, user_id):
    """Fetch payment history for a specific user."""
    try:
        qs = PaymentHistory.objects.filter(user_id=user_id).order_by('-timestamp')
        if not qs.exists():
            return Response({'success': True, 'data': [], 'message': 'No payment history found for this user'})

        data = [_serialize_payment(p) for p in qs]
        user_summary = CustomerPaymentSummary.objects.filter(user_id=user_id).first()

        return Response({
            'success': True,
            'user_id': user_id,
            'payment_history': data,
            'summary': {
                'total_paid': float(user_summary.total_paid) if user_summary else 0,
                'current_balance': float(user_summary.current_balance) if user_summary else 0,
                'payment_count': len(data),
                'last_payment': data[0] if data else None
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_payment_summary(request):
    """Get summary statistics of all payments."""
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        qs = PaymentHistory.objects.all()
        if start_date:
            qs = qs.filter(payment_date__gte=start_date)
        if end_date:
            qs = qs.filter(payment_date__lte=end_date)

        total_payments = qs.count()
        total_amount = qs.aggregate(total=Sum('amount_paid'))['total'] or 0

        method_breakdown = qs.values('payment_method').annotate(
            count=Count('id'), total=Sum('amount_paid')
        ).order_by('-total')

        daily_trend = qs.values('payment_date').annotate(
            count=Count('id'), total=Sum('amount_paid')
        ).order_by('-payment_date')[:30]

        method_data = [{
            'method': m['payment_method'],
            'method_display': _payment_method_display(m['payment_method']),
            'count': m['count'],
            'total': float(m['total'])
        } for m in method_breakdown]

        return Response({
            'success': True,
            'summary': {
                'total_payments': total_payments,
                'total_amount': float(total_amount),
                'average_payment': float(total_amount / total_payments) if total_payments > 0 else 0
            },
            'method_breakdown': method_data,
            'daily_trend': list(daily_trend)
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_payment_receipt(request, receipt_number):
    """Get payment details by receipt number."""
    try:
        payment = PaymentHistory.objects.filter(receipt_number=receipt_number).first()
        if not payment:
            return Response({'success': False, 'error': 'Payment receipt not found'}, status=status.HTTP_404_NOT_FOUND)

        billing = Billings.objects.filter(id=payment.billing_id).first()
        data = _serialize_payment(payment)
        data['billing_details'] = {
            'units_used': billing.units_used if billing else None,
            'rate': billing.rate if billing else None,
            'bill_amount': billing.bill if billing else None,
            'status': billing.status if billing else None
        } if billing else None

        return Response({'success': True, 'data': data})
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_payment_history_json(request):
    """Simple JsonResponse (non-DRF) version of the full payment history."""
    try:
        payments = PaymentHistory.objects.all().order_by('-timestamp')
        data = [_serialize_payment(p) for p in payments]
        total_amount = PaymentHistory.objects.aggregate(total=Sum('amount_paid'))['total'] or 0

        return JsonResponse({
            'success': True,
            'data': data,
            'summary': {'total_payments': len(data), 'total_amount': float(total_amount)}
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


#======================================================================================
# PAYMENT RECEIPT PDF (modernized design)
#======================================================================================

NAVY = colors.HexColor('#0F172A')
SLATE = colors.HexColor('#475569')
LIGHT_SLATE = colors.HexColor('#94A3B8')
ACCENT = colors.HexColor('#0EA5E9')
BG_LIGHT = colors.HexColor('#F1F5F9')
GREEN = colors.HexColor('#16A34A')
RED = colors.HexColor('#DC2626')
AMBER = colors.HexColor('#D97706')
WHITE = colors.white
BORDER = colors.HexColor('#E2E8F0')

COMPANY_NAME = "KAMENGO AGENCIES"
COMPANY_SUBTITLE = "Water Utility Services"
COMPANY_ADDRESS = "+254 741 088 799"
COMPANY_INITIALS = "KA"


def _status_color(status_value):
    s = (status_value or "").strip().lower()
    if s in ("completed", "paid", "success"):
        return GREEN
    if s in ("pending", "processing"):
        return AMBER
    return RED


def _draw_receipt(c, payment, billing):
    """Draws one modern, professional receipt onto the given canvas."""
    page_w, page_h = A4

    # ===== Header band =====
    header_h = 42 * mm
    c.setFillColor(NAVY)
    c.rect(0, page_h - header_h, page_w, header_h, fill=1, stroke=0)

    c.setFillColor(ACCENT)
    c.rect(0, page_h - 3, page_w, 3, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, page_h - 20 * mm, COMPANY_NAME)
    c.setFont("Helvetica", 9.5)
    c.setFillColor(colors.HexColor('#CBD5E1'))
    c.drawString(20 * mm, page_h - 26 * mm, COMPANY_SUBTITLE)
    c.drawString(20 * mm, page_h - 31 * mm, COMPANY_ADDRESS)

    c.setFillColor(ACCENT)
    c.circle(page_w - 28 * mm, page_h - 20 * mm, 9 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w - 28 * mm, page_h - 22.3 * mm, COMPANY_INITIALS)

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(page_w - 20 * mm, page_h - 34 * mm, "PAYMENT RECEIPT")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#CBD5E1'))
    c.drawRightString(page_w - 20 * mm, page_h - 38.5 * mm, payment.receipt_number)

    y = page_h - header_h - 12 * mm

    # ===== Status badge + issue date =====
    status_text = payment.status or ""
    status_color = _status_color(status_text)
    badge_text = status_text.upper() if status_text else "N/A"
    c.setFont("Helvetica-Bold", 9)
    badge_w = c.stringWidth(badge_text, "Helvetica-Bold", 9) + 14
    c.setFillColor(status_color)
    c.roundRect(20 * mm, y - 4, badge_w, 16, 8, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawString(20 * mm + 7, y, badge_text)

    date_str = payment.payment_date.strftime('%d %b %Y, %I:%M %p') if payment.payment_date else 'N/A'
    c.setFont("Helvetica", 9.5)
    c.setFillColor(SLATE)
    c.drawRightString(page_w - 20 * mm, y, f"Issued: {date_str}")

    y -= 14 * mm

    # ===== Billed To / Receipt details =====
    col1_x = 20 * mm
    col2_x = page_w / 2 + 5 * mm

    def section_label(x, y_pos, text):
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(LIGHT_SLATE)
        c.drawString(x, y_pos, text.upper())

    section_label(col1_x, y, "Billed To")
    section_label(col2_x, y, "Receipt Details")
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NAVY)
    c.drawString(col1_x, y, payment.name or "N/A")
    c.drawString(col2_x, y, payment.receipt_number)
    y -= 5.5 * mm

    c.setFont("Helvetica", 9.5)
    c.setFillColor(SLATE)
    c.drawString(col1_x, y, payment.phone or "N/A")
    c.drawString(col2_x, y, f"Status: {status_text if status_text else 'N/A'}")
    y -= 12 * mm

    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.line(20 * mm, y, page_w - 20 * mm, y)
    y -= 10 * mm

    # ===== Billing details (if available) =====
    if billing:
        section_label(col1_x, y, "Billing Details")
        y -= 7 * mm

        rows = [
            ("Units Consumed", f"{billing.units_used or 0} m\u00b3"),
            ("Rate per Unit", f"KES {float(billing.rate or 0):,.2f}"),
            ("Bill Status", payment.status or "N/A"),
        ]
        row_h = 8 * mm
        table_x = 20 * mm
        table_w = page_w - 40 * mm

        c.setFillColor(BG_LIGHT)
        c.roundRect(table_x, y - row_h * len(rows) + 2 * mm, table_w, row_h * len(rows), 4, fill=1, stroke=0)

        ry = y - 5.5 * mm
        for label, value in rows:
            c.setFont("Helvetica", 9.5)
            c.setFillColor(SLATE)
            c.drawString(table_x + 6 * mm, ry, label)
            c.setFont("Helvetica-Bold", 9.5)
            c.setFillColor(NAVY)
            c.drawRightString(table_x + table_w - 6 * mm, ry, value)
            ry -= row_h
        y -= row_h * len(rows) + 6 * mm

    # ===== Payment summary (highlighted box) =====
    box_h = 34 * mm
    box_y = y - box_h
    c.setFillColor(NAVY)
    c.roundRect(20 * mm, box_y, page_w - 40 * mm, box_h, 5, fill=1, stroke=0)

    pad = 8 * mm
    inner_y = box_y + box_h - 9 * mm

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor('#94A3B8'))
    c.drawString(20 * mm + pad, inner_y, "BILL AMOUNT")
    c.drawString(20 * mm + pad + 55 * mm, inner_y, "AMOUNT PAID")

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(WHITE)
    c.drawString(20 * mm + pad, inner_y - 7 * mm, f"KES {float(payment.previous_balance):,.2f}")
    c.setFillColor(colors.HexColor('#7DD3FC'))
    c.drawString(20 * mm + pad + 55 * mm, inner_y - 7 * mm, f"KES {float(payment.amount_paid):,.2f}")

    c.setStrokeColor(colors.HexColor('#334155'))
    c.line(20 * mm + pad, box_y + 11 * mm, page_w - 20 * mm - pad, box_y + 11 * mm)

    bal = float(payment.current_balance)
    bal_color = colors.HexColor('#86EFAC') if bal <= 0 else colors.HexColor('#FCA5A5')
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#CBD5E1'))
    c.drawString(20 * mm + pad, box_y + 5 * mm, "CURRENT BALANCE")
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(bal_color)
    c.drawRightString(page_w - 20 * mm - pad, box_y + 4.5 * mm, f"KES {bal:,.2f}")

    y = box_y - 10 * mm

    # ===== Notes =====
    if getattr(payment, "notes", None):
        section_label(col1_x, y, "Notes")
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        c.setFillColor(SLATE)
        for line in wrap(payment.notes, 95):
            c.drawString(col1_x, y, line)
            y -= 5 * mm
        y -= 4 * mm

    # ===== Footer =====
    footer_y = 18 * mm
    c.setStrokeColor(BORDER)
    c.line(20 * mm, footer_y + 10 * mm, page_w - 20 * mm, footer_y + 10 * mm)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(NAVY)
    c.drawCentredString(page_w / 2, footer_y + 4 * mm, "Thank you for your payment!")
    c.setFont("Helvetica", 8)
    c.setFillColor(LIGHT_SLATE)
    c.drawCentredString(page_w / 2, footer_y - 1 * mm,
                         f"{COMPANY_NAME.title()}  \u2022  This is a system-generated receipt.")
    c.drawCentredString(page_w / 2, footer_y - 5.5 * mm,
                         f"Generated on {datetime.now().strftime('%d %b %Y, %I:%M %p')}")


def download_payment_receipt(request, receipt_number):
    """Download a single payment receipt as PDF."""
    try:
        payment = PaymentHistory.objects.filter(receipt_number=receipt_number).first()
        if not payment:
            return JsonResponse({'success': False, 'error': 'Payment receipt not found'}, status=404)

        billing = Billings.objects.filter(id=payment.billing_id).first()

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        _draw_receipt(c, payment, billing)
        c.showPage()
        c.save()

        pdf_data = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="receipt_{receipt_number}.pdf"'

        create_audit_trail(
            username=request.GET.get('username', 'system'), role=request.GET.get('role', 'system'),
            action="DOWNLOAD", table_name="payment_history", record_id=payment.id,
            description=f"Payment receipt downloaded: {receipt_number}", request=request
        )

        return response
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
def download_user_payment_history(request, user_id):
    """Download the complete payment history for a user as a multi-page PDF (one receipt per page)."""
    try:
        payments = PaymentHistory.objects.filter(user_id=user_id).order_by('-timestamp')
        if not payments.exists():
            return Response({'success': False, 'error': 'No payment history found for this user'},
                             status=status.HTTP_404_NOT_FOUND)

        first_payment = payments.first()
        user_name = first_payment.name

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        payment_count = payments.count()
        for idx, payment in enumerate(payments):
            billing = Billings.objects.filter(id=payment.billing_id).first()
            _draw_receipt(c, payment, billing)
            if idx < payment_count - 1:
                c.showPage()

        c.save()
        pdf_data = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_data, content_type='application/pdf')
        filename = f"payment_history_{user_name}_{user_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        create_audit_trail(
            username=request.GET.get('username', 'system'), role=request.GET.get('role', 'system'),
            action="DOWNLOAD", table_name="payment_history", record_id=None,
            description=f"User payment history downloaded for {user_name} (ID: {user_id}) - {payment_count} records",
            request=request
        )

        return response
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#======================================================================================
# READING HISTORY SERIALIZATION + FETCH ENDPOINTS
#======================================================================================

def _serialize_reading_history(h):
    """Shared serializer for ReadingHistory rows, used across reading-history endpoints."""
    return {
        'id': h.id,
        'reading_id': h.reading_id,
        'user_id': h.user_id,
        'name': h.name,
        'phone': h.phone,
        'metre_num': h.metre_num,
        'grp': h.grp,
        'parent': h.parent,
        'prev_user': h.prev_user or 0,
        'prev_sup': h.prev_sup or 0,
        'cur_user': h.cur_user or 0,
        'cur_sup': h.cur_sup or 0,
        'mid_user': h.mid_user or 0,
        'mid_sup': h.mid_sup or 0,
        'units_used': h.units_used or 0,
        'rate': h.rate or 0,
        'reading_date': h.reading_date.strftime('%Y-%m-%d') if h.reading_date else None,
        'prev_date': h.prev_date.strftime('%Y-%m-%d') if h.prev_date else None,
        'cycle_month': h.cycle_month,
        'recorded_by': h.recorded_by,
        'role': h.role,
        'version': h.version,
        'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S') if h.timestamp else None
    }


@api_view(['GET'])
def get_reading_history_list(request):
    """Fetch all reading history records with advanced filtering and pagination."""
    try:
        user_id = request.GET.get('user_id')
        cycle_month = request.GET.get('cycle_month')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        search = request.GET.get('search')
        recorded_by = request.GET.get('recorded_by')

        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        offset = (page - 1) * page_size

        qs = ReadingHistory.objects.all()
        if user_id:
            qs = qs.filter(user_id=user_id)
        if cycle_month:
            qs = qs.filter(cycle_month=cycle_month)
        if start_date:
            qs = qs.filter(reading_date__gte=start_date)
        if end_date:
            qs = qs.filter(reading_date__lte=end_date)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        if recorded_by:
            qs = qs.filter(recorded_by__icontains=recorded_by)

        total_count = qs.count()
        qs = qs.order_by('-timestamp')
        page_qs = qs[offset:offset + page_size]

        data = [_serialize_reading_history(h) for h in page_qs]

        summary = {
            'total_records': total_count,
            'total_units': page_qs.aggregate(total=Sum('units_used'))['total'] or 0,
            'unique_customers': ReadingHistory.objects.values('user_id').distinct().count(),
            'latest_cycle': ReadingHistory.objects.order_by('-cycle_month').values('cycle_month').first(),
            'filters_applied': {
                'user_id': user_id, 'cycle_month': cycle_month, 'start_date': start_date,
                'end_date': end_date, 'search': search, 'recorded_by': recorded_by
            }
        }

        return Response({
            'success': True,
            'data': data,
            'summary': summary,
            'pagination': {
                'page': page, 'page_size': page_size, 'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_reading_history_by_user(request, user_id):
    """Fetch reading history for a specific user."""
    try:
        qs = ReadingHistory.objects.filter(user_id=user_id).order_by('-timestamp')
        if not qs.exists():
            return Response({'success': True, 'data': [], 'message': 'No reading history found for this user'})

        data = [_serialize_reading_history(h) for h in qs]

        return Response({
            'success': True,
            'user_id': user_id,
            'reading_history': data,
            'summary': {
                'total_readings': len(data),
                'total_units_used': sum(h['units_used'] for h in data),
                'first_reading': data[-1] if data else None,
                'latest_reading': data[0] if data else None
            }
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_reading_history_summary(request):
    """Get summary statistics of all reading history."""
    try:
        cycle_month = request.GET.get('cycle_month')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        qs = ReadingHistory.objects.all()
        if cycle_month:
            qs = qs.filter(cycle_month=cycle_month)
        if start_date:
            qs = qs.filter(reading_date__gte=start_date)
        if end_date:
            qs = qs.filter(reading_date__lte=end_date)

        total_readings = qs.count()
        total_units = qs.aggregate(total=Sum('units_used'))['total'] or 0

        cycle_breakdown = qs.values('cycle_month').annotate(
            count=Count('id'), total_units=Sum('units_used'),
            unique_customers=Count('user_id', distinct=True)
        ).order_by('-cycle_month')

        recorded_by_breakdown = qs.values('recorded_by').annotate(count=Count('id')).order_by('-count')

        daily_trend = qs.values('reading_date').annotate(
            count=Count('id'), total_units=Sum('units_used')
        ).order_by('-reading_date')[:30]

        return Response({
            'success': True,
            'summary': {
                'total_readings': total_readings,
                'total_units': float(total_units),
                'average_units': float(total_units / total_readings) if total_readings > 0 else 0,
                'unique_customers': qs.values('user_id').distinct().count()
            },
            'cycle_breakdown': list(cycle_breakdown),
            'recorded_by_breakdown': list(recorded_by_breakdown),
            'daily_trend': list(daily_trend)
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_reading_history_json(request):
    """Simple JsonResponse (non-DRF) version of the full reading history."""
    try:
        history_qs = ReadingHistory.objects.all().order_by('-timestamp')
        data = [_serialize_reading_history(h) for h in history_qs]
        total_units = ReadingHistory.objects.aggregate(total=Sum('units_used'))['total'] or 0

        return JsonResponse({
            'success': True,
            'data': data,
            'summary': {'total_records': len(data), 'total_units': float(total_units)}
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)