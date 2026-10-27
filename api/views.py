from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
import json
import secrets
from .models import (
    read_users, readings, Admin, Billings,  Users, BillDates
)
from collections import defaultdict
from django.db.models import Avg, Count, Max, Q, Sum, F, FloatField, ExpressionWrapper
from django.http import JsonResponse
from django.utils import timezone
from django.db.models.functions import TruncMonth
from datetime import date
from django.views.decorators.http import require_http_methods


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
        return JsonResponse({"token": token})
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
# ----------------------------------------------------------------- helpers
OUTSTANDING = ExpressionWrapper(F('bill') + F('b_cd') - F('paid'), output_field=FloatField())
def r2(v):
    return round(float(v or 0), 2)
def pct(a, b):
    return round(float(a) / float(b) * 100, 1) if b else 0
def int_param(request, name, default, lo, hi):
    try:
        return max(lo, min(hi, int(request.GET.get(name, default))))
    except (TypeError, ValueError):
        return default
def latest_cycle():
    """(queryset of billings in the latest month, date of latest billing)."""
    d = Billings.objects.aggregate(m=Max('billed_on'))['m']
    if not d:
        return Billings.objects.none(), None
    return Billings.objects.filter(billed_on__year=d.year, billed_on__month=d.month), d
def finish(billed, prev, paid, units=0, customers=0, **extra):
    """Turn raw sums into the standard metric block."""
    billed, prev, paid = r2(billed), r2(prev), r2(paid)
    due = round(billed + prev, 2)
    units = r2(units)
    return {
        'billed': billed, 'prev': prev, 'due': due, 'paid': paid,
        'outstanding': round(due - paid, 2),
        'collection_rate': pct(paid, due),
        'units': units, 'customers': customers,
        'yield_per_unit': round(paid / units, 2) if units else 0,
        **extra,
    }
def group_cycle(key):
    """Aggregate the latest cycle by a Billings column."""
    qs, _ = latest_cycle()
    rows = qs.order_by().values(key).annotate(
        billed=Sum('bill'), prev=Sum('b_cd'), paid=Sum('paid'),
        units=Sum('units_used'), customers=Count('user_id', distinct=True))
    return [finish(r['billed'], r['prev'], r['paid'], r['units'], r['customers'], **{key: r[key]})
            for r in rows]
# ----------------------------------------------------------------- views
def analytics_summary(request):
    """Headline numbers for the latest cycle plus operational health."""
    qs, d = latest_cycle()
    c = qs.aggregate(billed=Sum('bill'), prev=Sum('b_cd'), paid=Sum('paid'),
                     units=Sum('units_used'), pen=Sum('penalty'),
                     cust=Count('user_id', distinct=True), n=Count('id'))
    due_expr = F('bill') + F('b_cd')
    full = Count('id', filter=Q(paid__gte=due_expr))
    none = Count('id', filter=Q(paid__lte=0) & ~Q(paid__gte=due_expr))
    mix = qs.aggregate(full=full, none=none)
    partial = c['n'] - mix['full'] - mix['none']
    all_time_pen = Billings.objects.aggregate(v=Sum('penalty'))['v']
    r = readings.objects.aggregate(total=Count('id'),
                                   done=Count('id', filter=Q(cur_user__isnull=False)),
                                   locked=Count('id', filter=Q(cycle_locked_until__gt=timezone.now())))
    roles = list(Users.objects.values('role').annotate(n=Count('id')).order_by('role'))
    out = finish(c['billed'], c['prev'], c['paid'], c['units'], c['cust'])
    return JsonResponse({
        'cycle': d.strftime('%B %Y') if d else None,
        'cycle_date': d.isoformat() if d else None,
        'cycle_stats': out,
        'penalties_cycle': r2(c['pen']),
        'penalties_total': r2(all_time_pen),
        'payment_mix': {'fully_paid': mix['full'], 'partial': partial, 'unpaid': mix['none']},
        'readings_total': r['total'], 'readings_done': r['done'],
        'reading_completion': pct(r['done'], r['total']),
        'locked_readings': r['locked'],
        'staff': {'users': sum(x['n'] for x in roles), 'admins': Admin.objects.count(), 'by_role': roles},
    })
def analytics_monthly_trend(request):
    """Month-by-month billing, collections, consumption (last N months)."""
    months = int_param(request, 'months', 12, 1, 60)
    rows = (Billings.objects.annotate(m=TruncMonth('billed_on')).order_by().values('m')
            .annotate(billed=Sum('bill'), prev=Sum('b_cd'), paid=Sum('paid'), units=Sum('units_used'),
                      customers=Count('user_id', distinct=True), penalty=Sum('penalty'))
            .order_by('-m')[:months])
    data = [finish(x['billed'], x['prev'], x['paid'], x['units'], x['customers'],
                   month=x['m'].strftime('%Y-%m'), penalty=r2(x['penalty']))
            for x in reversed(list(rows))]
    return JsonResponse({'data': data})
def analytics_zone_performance(request):
    """Latest-cycle performance per zone (Billings.user_id -> waterusers.zone)."""
    zone_of = dict(read_users.objects.values_list('id', 'zone'))
    qs, _ = latest_cycle()
    per_user = qs.order_by().values('user_id').annotate(
        billed=Sum('bill'), prev=Sum('b_cd'), paid=Sum('paid'), units=Sum('units_used'))
    acc = defaultdict(lambda: dict(billed=0, prev=0, paid=0, units=0, customers=0))
    for u in per_user:
        z = acc[zone_of.get(u['user_id']) or 'Unassigned']
        z['billed'] += u['billed'] or 0
        z['prev'] += u['prev'] or 0
        z['paid'] += u['paid'] or 0
        z['units'] += u['units'] or 0
        z['customers'] += 1
    data = [finish(v['billed'], v['prev'], v['paid'], v['units'], v['customers'], zone=k,
                   avg_units=round(v['units'] / v['customers'], 1) if v['customers'] else 0)
            for k, v in acc.items()]
    data.sort(key=lambda x: x['outstanding'], reverse=True)
    return JsonResponse({'data': data})
def analytics_group_breakdown(request):
    """Latest-cycle performance per customer group (grp)."""
    return JsonResponse({'data': sorted(group_cycle('grp'), key=lambda x: -x['due'])})
def analytics_status_breakdown(request):
    """Latest-cycle count and value by billing status."""
    qs, _ = latest_cycle()
    rows = qs.order_by().values('status').annotate(count=Count('id'), billed=Sum('bill'), paid=Sum('paid'))
    return JsonResponse({'data': [{'status': x['status'] or 'Unknown', 'count': x['count'],
                                   'billed': r2(x['billed']), 'paid': r2(x['paid'])} for x in rows]})
def analytics_tariff_breakdown(request):
    """Latest cycle by tariff rate: customers, units and revenue per rate."""
    return JsonResponse({'data': sorted(group_cycle('rate'), key=lambda x: x['rate'] or 0)})
def analytics_consumption_bands(request):
    """How many customers fall in each consumption band (latest cycle)."""
    qs, d = latest_cycle()
    bands = [('0', 0, 0), ('1-5', 1, 5), ('6-10', 6, 10), ('11-20', 11, 20), ('21-40', 21, 40), ('40+', 41, 10**9)]
    counts = {b[0]: 0 for b in bands}
    for u in qs.values_list('units_used', flat=True):
        u = u or 0
        for label, lo, hi in bands:
            if lo <= u <= hi:
                counts[label] += 1
                break
    return JsonResponse({'cycle': d.strftime('%B %Y') if d else None,
                         'data': [{'band': k, 'count': v} for k, v in counts.items()]})
def analytics_customer_growth(request):
    """New connections per month and running total."""
    months = int_param(request, 'months', 12, 1, 60)
    rows = (read_users.objects.annotate(m=TruncMonth('created_on')).order_by().values('m')
            .annotate(n=Count('id')).order_by('m'))
    running, out = 0, []
    for x in rows:
        if not x['m']:
            running += x['n']
            continue
        running += x['n']
        out.append({'month': x['m'].strftime('%Y-%m'), 'new': x['n'], 'total': running})
    return JsonResponse({'data': out[-months:]})

def analytics_top_debtors(request):
    """Customers owing the most in the latest cycle + concentration of debt."""
    limit = int_param(request, 'limit', 10, 1, 100)
    qs, _ = latest_cycle()
    owing = qs.annotate(out=OUTSTANDING).filter(out__gt=0)
    total_out = r2(owing.aggregate(v=Sum('out'))['v'])
    zone_of = dict(read_users.objects.values_list('id', 'zone'))
    rows = list(owing.order_by('-out')[:limit])
    data = [{'user_id': b.user_id, 'name': b.name, 'phone': b.phone,
             'zone': zone_of.get(b.user_id, ''), 'bill': r2(b.bill), 'prev': r2(b.b_cd),
             'paid': r2(b.paid), 'outstanding': r2(b.out), 'status': b.status,
             'share': pct(b.out, total_out)} for b in rows]
    return JsonResponse({'data': data, 'total_outstanding': total_out,
                         'debtor_count': owing.count(),
                         'top_share': pct(sum(x['outstanding'] for x in data), total_out)})

def analytics_top_consumers(request):
    """Highest water users in the latest cycle and their share of total volume."""
    limit = int_param(request, 'limit', 10, 1, 100)
    qs, _ = latest_cycle()
    total_units = r2(qs.aggregate(v=Sum('units_used'))['v'])
    zone_of = dict(read_users.objects.values_list('id', 'zone'))
    rows = qs.order_by('-units_used')[:limit]
    data = [{'user_id': b.user_id, 'name': b.name, 'zone': zone_of.get(b.user_id, ''),
             'units': b.units_used, 'bill': r2(b.bill),
             'share': pct(b.units_used, total_units)} for b in rows]
    return JsonResponse({'data': data, 'total_units': total_units,
                         'top_share': pct(sum(x['units'] for x in data), total_units)})

def analytics_reading_anomalies(request):
    """Meter-reading quality: zero use, reverse readings, spikes, pending."""
    avg = float(readings.objects.aggregate(a=Avg('units_used'))['a'] or 0)
    threshold = round(avg * 3, 1)
    counts = readings.objects.aggregate(
        zero=Count('id', filter=Q(units_used=0)),
        negative=Count('id', filter=Q(cur_user__lt=F('prev_user'))),
        spike=Count('id', filter=Q(units_used__gt=threshold)) if threshold else Count('id', filter=Q(pk__isnull=True)),
        pending=Count('id', filter=Q(cur_user__isnull=True)),
        total=Count('id'))

    def pack(qs, reason):
        return [{'name': r.name, 'metre_num': r.metre_num, 'zone': r.user.zone,
                 'prev': r.prev_user, 'cur': r.cur_user, 'units': r.units_used, 'issue': reason}
                for r in qs.select_related('user')]

    items = (pack(readings.objects.filter(units_used__gt=threshold).order_by('-units_used')[:8], 'High consumption')
             if threshold else [])
    items += pack(readings.objects.filter(cur_user__lt=F('prev_user'))[:5], 'Reading lower than previous')
    items += pack(readings.objects.filter(units_used=0)[:5], 'Zero consumption')
    return JsonResponse({**counts, 'threshold': threshold, 'average_units': round(avg, 1), 'data': items})

def serialize(row):
    return {"billing": row.billing.isoformat(), "due": row.due.isoformat(), "month": row.month}
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def bill_dates_view(request):
    row = BillDates.objects.order_by("id").first()
    if not row:
        return JsonResponse({"error": "No row found in bill_dates. Create the first one manually."}, status=404)
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            billing = date.fromisoformat(data["billing"])
            due = date.fromisoformat(data["due"])
        except (ValueError, KeyError, TypeError):
            return JsonResponse({"error": "billing and due must be valid YYYY-MM-DD dates"}, status=400)
        if due < billing:
            return JsonResponse({"error": "Pay by date cannot be before the billing date"}, status=400)
        row.billing, row.due, row.month = billing, due, billing.strftime("%Y-%m")
        row.save()
    return JsonResponse(serialize(row))