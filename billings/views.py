import json
from decimal import Decimal
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from api.models import Billings
import os
from django.conf import settings
from openpyxl import load_workbook
import uuid
import pandas as pd
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response



@csrf_exempt
def update_paid(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            billing = Billings.objects.select_for_update().get(id=data.get("id"))
            new_paid = Decimal(str(data.get("paid", 0)))
            billing.paid = float(new_paid)
            billing.bal = (float(billing.bill or 0.0) + float(billing.b_cd or 0.0) - float(new_paid))
            billing.status = "PAID" if billing.bal <= 0 else "PARTIAL"
            billing.save()
            return JsonResponse({
                "message": "Payment updated",
                "id": billing.id,
                "paid": billing.paid,
                "bal": billing.bal,
                "status": billing.status
            })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def update_billing_penalty(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        billing_id = data.get("id")
        action_type = (data.get("type") or "").lower()
        if not billing_id:
            return JsonResponse({"error": "Billing id is required"}, status=400)
        if action_type not in ("penalty", "discount", "reset"):
            return JsonResponse({"error": "type must be 'penalty', 'discount' or 'reset'"}, status=400)
        with transaction.atomic():
            try:
                billing = Billings.objects.select_for_update().get(id=billing_id)
            except Billings.DoesNotExist:
                return JsonResponse({"error": "Billing record not found"}, status=404)
            if action_type == "reset":
                new_penalty = Decimal("0")
            else:
                try:
                    amount = Decimal(str(data.get("amount", 0)))
                except Exception:
                    return JsonResponse({"error": "Invalid amount"}, status=400)
                amount = abs(amount)
                new_penalty = amount if action_type == "penalty" else -amount
            billing.penalty = new_penalty
            paid = billing.paid or Decimal("0")
            total_due = Decimal(str(billing.bill or 0)) + Decimal(str(billing.b_cd or 0)) + new_penalty
            billing.bal = float(total_due - paid)
            billing.status = "PAID" if billing.bal <= 0 else "PARTIAL"
            billing.save()
            
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

def download_billings_template(request):
    template_path = os.path.join(settings.BASE_DIR, "templates", "Billings.xlsx")
    wb = load_workbook(template_path)
    ws = wb.active
    billings_data = Billings.objects.all().order_by("user_id")
    total_customers = billings_data.count()
    ws.cell(row=2, column=9).value = total_customers
    ws.cell(row=2, column=3).value = 'Aug-2026'
    ws.cell(row=2, column=6).value = '31-Aug-26'
    row = 6
    for billing in billings_data:
        ws.cell(row=row, column=1).value = billing.user_id
        ws.cell(row=row, column=2).value = billing.name
        ws.cell(row=row, column=3).value = billing.phone
        ws.cell(row=row, column=4).value = billing.units_used
        ws.cell(row=row, column=5).value = billing.rate
        ws.cell(row=row, column=6).value = billing.bill
        ws.cell(row=row, column=7).value = billing.b_cd
        ws.cell(row=row, column=8).value = billing.penalty
        bill = billing.bill or Decimal("0")
        b_cd = billing.b_cd or Decimal("0")
        penalty = billing.penalty or Decimal("0")
        ws.cell(row=row, column=9).value = bill + b_cd + penalty
        ws.cell(row=row, column=10).value = None
        ws.cell(row=row, column=11).value = f"=I{row}-J{row}"
        row += 1
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="billings_template.xlsx"'
    wb.save(response)
    return response

from openpyxl import load_workbook
PENDING_BILLINGS_UPLOAD_DIR = os.path.join(settings.BASE_DIR, "temp_uploads", "billings")
os.makedirs(PENDING_BILLINGS_UPLOAD_DIR, exist_ok=True)
def _pending_upload_path(token):
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
            return JsonResponse({"error": "Upload not found or already processed. Please upload the sheet again."}, status=404)
        try:
            rows = _read_pending_billing_rows(saved_path)
        except Exception as read_error:
            return JsonResponse({"error": f"Could not read the Excel file: {read_error}"}, status=400)
        preview = []
        errors = []
        for row_num, billing_id, paid in rows:
            try:
                billing = Billings.objects.filter(user_id=int(billing_id)).first()
                if not billing:
                    errors.append(f"Row {row_num}: Billing ID {billing_id} not found")
                    continue
                new_paid = Decimal(str(paid))
                penalty = billing.penalty or Decimal("0")
                total_due = Decimal(str(billing.bill or 0)) + Decimal(str(billing.b_cd or 0)) + penalty
                new_bal = total_due - new_paid
                new_status = "PAID" if new_bal <= 0 else "PARTIAL"
                preview.append({
                    "id": billing.user_id,
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
            return JsonResponse({"error": "Upload not found or already processed. Please upload the sheet again."}, status=404)
        try:
            rows = _read_pending_billing_rows(saved_path)
        except Exception as read_error:
            return JsonResponse({"error": f"Could not read the Excel file: {read_error}"}, status=400)
        updated = []
        errors = []
        with transaction.atomic():
            for row_num, billing_id, paid in rows:
                try:
                    billing = Billings.objects.select_for_update().get(user_id=int(billing_id))
                    new_paid = Decimal(str(paid))
                    penalty = billing.penalty or Decimal("0")
                    total_due = Decimal(str(billing.bill or 0)) + Decimal(str(billing.b_cd or 0)) + penalty
                    billing.paid = float(new_paid)
                    billing.bal = (float(total_due - new_paid))
                    billing.status = "PAID" if billing.bal <= 0 else "PARTIAL"
                    billing.save()
                    updated.append({
                        "id": billing.user_id,
                        "paid": billing.paid,
                        "bal": billing.bal,
                        "status": billing.status
                    })
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
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
        return JsonResponse({"message": "Rolled back — no changes were saved. The billing table has been restored."})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def send_bulk_sms(customers):
    payload = {
        "count": len(customers),
        "smslist": [
            {
                "partnerID": settings.ADVANTA_PARTNER_ID,
                "apikey": settings.ADVANTA_API_KEY,
                "pass_type": "plain",
                "clientsmsid": i + 1,
                "mobile": c["phone"],
                "message": c["message"],
                "shortcode": settings.ADVANTA_SHORTCODE,
            }
            for i, c in enumerate(customers)
        ],
    }
    return requests.post(settings.ADVANTA_API_URL, json=payload, timeout=30).json()


@csrf_exempt
def send_sms_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        customers = json.loads(request.body).get("customers", [])
        if not customers:
            return JsonResponse({"error": "No customers selected"}, status=400)
        return JsonResponse(send_bulk_sms(customers), safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def bill(request):
    data = [{
        'id': b.id, 'user_id': b.user_id, 'name': b.name, 'phone': b.phone,
        'units_used': b.units_used, 'rate': b.rate, 'bill': b.bill, 'paid': b.paid,
        'bal': b.bal, 'status': b.status, 'b_cd': b.b_cd,
        'penalty': float(b.penalty) if b.penalty is not None else 0,
        'prev_user': b.prev_user, 'cur_user': b.cur_user, 'sms_name': b.sms_name,
        'grp': b.grp, 'parent': b.parent, 'gen_name': b.gen_name
    } for b in Billings.objects.all()]
    return JsonResponse(data, safe=False)