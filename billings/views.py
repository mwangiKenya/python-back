import json
from decimal import Decimal
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from api.models import Billings, Payments, payDetails
from api.auth import agency_required
import os
from django.conf import settings
from openpyxl import load_workbook
import uuid
from django.http import HttpResponse, JsonResponse
import requests
from datetime import date
def apply_payment(billing_id, paid, agency):
    billing = Billings.objects.select_for_update().get(id=billing_id, agency=agency)
    new_paid = Decimal(str(paid or 0))
    billing.paid = float(new_paid)
    billing.bal = float(billing.bill or 0.0) + float(billing.b_cd or 0.0) - float(new_paid)
    billing.status = "PAID" if billing.bal <= 0 else "PARTIAL"
    billing.save()
    Payments.objects.create(
        user_id=billing.user_id, agency=agency,
        bill=(billing.bill or 0) + (billing.b_cd or 0), paid=billing.paid, bal=billing.bal,
        month=billing.billed_on
    )
    return billing
@csrf_exempt
@agency_required
def update_paid(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        items = data if isinstance(data, list) else [data]
        with transaction.atomic():
            results = [apply_payment(i.get("id"), i.get("paid", 0), request.agency) for i in items]
        if isinstance(data, list):
            return JsonResponse({"message": "Payments updated", "count": len(results)})
        billing = results[0]
        return JsonResponse({
            "message": "Payment updated",
            "id": billing.id,
            "paid": billing.paid,
            "bal": billing.bal,
            "status": billing.status,
        })
    except Billings.DoesNotExist:
        return JsonResponse({"error": "Billing record not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@agency_required
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
                billing = Billings.objects.select_for_update().get(id=billing_id, agency=request.agency)
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
            paid = Decimal(str(billing.paid or 0))
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
@agency_required
def download_billings_template(request):
    try:
        template_path = os.path.join(settings.BASE_DIR, "templates", "Billings.xlsx")
        wb = load_workbook(template_path)
        ws = wb.active
        billings_data = Billings.objects.filter(agency=request.agency).order_by("user_id")
        ws.cell(row=2, column=9).value = billings_data.count()
        ws.cell(row=2, column=3).value = ''
        ws.cell(row=2, column=6).value = date.today()
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
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
PENDING_BILLINGS_UPLOAD_DIR = os.path.join(settings.BASE_DIR, "temp_uploads", "billings")
os.makedirs(PENDING_BILLINGS_UPLOAD_DIR, exist_ok=True)
def _pending_upload_path(token, agency):
    safe_token = "".join(ch for ch in str(token) if ch.isalnum())
    return os.path.join(PENDING_BILLINGS_UPLOAD_DIR, f"{agency}_{safe_token}.xlsx")
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
@agency_required
def upload_billings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)
        token = uuid.uuid4().hex
        with open(_pending_upload_path(token, request.agency), "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)
        return JsonResponse({
            "message": "Sheet uploaded successfully. Click \"Extract Data\" to preview the changes.",
            "token": token
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@agency_required
def extract_billings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        if not token:
            return JsonResponse({"error": "Missing upload token"}, status=400)
        saved_path = _pending_upload_path(token, request.agency)
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
                billing = Billings.objects.filter(user_id=int(billing_id), agency=request.agency).first()
                if not billing:
                    errors.append(f"Row {row_num}: Billing ID {billing_id} not found")
                    continue
                new_paid = Decimal(str(paid))
                penalty = Decimal(str(billing.penalty or 0))
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
@agency_required
def commit_billings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        if not token:
            return JsonResponse({"error": "Missing upload token"}, status=400)
        saved_path = _pending_upload_path(token, request.agency)
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
                    with transaction.atomic():
                        billing = Billings.objects.select_for_update().get(user_id=int(billing_id), agency=request.agency)
                        new_paid = Decimal(str(paid))
                        penalty = Decimal(str(billing.penalty or 0))
                        total_due = Decimal(str(billing.bill or 0)) + Decimal(str(billing.b_cd or 0)) + penalty
                        billing.paid = float(new_paid)
                        billing.bal = float(total_due - new_paid)
                        billing.status = "PAID" if billing.bal <= 0 else "PARTIAL"
                        billing.save()
                        Payments.objects.create(
                            user_id=billing.user_id, agency=request.agency,
                            bill=(billing.bill or 0) + (billing.b_cd or 0), paid=billing.paid, bal=billing.bal,
                            month=billing.billed_on
                        )
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
@agency_required
def rollback_billings_excel(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body) if request.body else {}
        token = data.get("token")
        if token:
            saved_path = _pending_upload_path(token, request.agency)
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
    res = requests.post(settings.ADVANTA_API_URL, json=payload, timeout=30)
    try:
        return res.json()
    except ValueError:
        raise RuntimeError(f"SMS provider returned an invalid response (status {res.status_code})")
@csrf_exempt
@agency_required
def send_sms_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        customers = json.loads(request.body).get("customers", [])
        if not customers:
            return JsonResponse({"error": "No customers selected"}, status=400)
        return JsonResponse(send_bulk_sms(customers), safe=False)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return JsonResponse({"error": "Cannot reach the SMS provider. Check the internet connection and try again."}, status=503)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@agency_required
def bill(request):
    data = [{
        'id': b.id, 'user_id': b.user_id, 'name': b.name, 'phone': b.phone,
        'units_used': b.units_used, 'rate': b.rate, 'bill': b.bill, 'paid': b.paid,
        'bal': b.bal, 'status': b.status, 'b_cd': b.b_cd,
        'penalty': float(b.penalty) if b.penalty is not None else 0,
        'prev_user': b.prev_user, 'cur_user': b.cur_user, 'sms_name': b.sms_name,
        'grp': b.grp, 'parent': b.parent, 'gen_name': b.gen_name
    } for b in Billings.objects.filter(agency=request.agency)]
    return JsonResponse(data, safe=False)
FIELDS = ["method_type", "provider", "acc_num", "acc_name", "is_active"]
def payment_data(p):
    return {"id": p.pk, "agency": p.agency, "method_type": p.method_type, "provider": p.provider, "acc_num": p.acc_num, "acc_name": p.acc_name, "is_active": p.is_active}
def get_payment(request, pk=None):
    agency = request.agency
    if request.method == "GET" and pk is None:
        return JsonResponse([payment_data(p) for p in payDetails.objects.filter(agency=agency).order_by("-pk")], safe=False)
    if request.method == "POST" and pk is None:
        try:
            data = json.loads(request.body)
            if any(not str(data.get(f, "")).strip() for f in FIELDS):
                return JsonResponse({"error": "All fields are required."}, status=400)
            p = payDetails.objects.create(agency=agency, method_type=data["method_type"].strip(), provider=data["provider"].strip(), acc_num=data["acc_num"].strip(), acc_name=data["acc_name"].strip(), is_active=data["is_active"])
            return JsonResponse(payment_data(p), status=201)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid payment details."}, status=400)
    try:
        p = payDetails.objects.get(pk=pk, agency=agency)
    except payDetails.DoesNotExist:
        return JsonResponse({"error": "Payment details not found."}, status=404)
    if request.method == "DELETE":
        p.delete()
        return JsonResponse({"message": "Payment details deleted."})
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if any(f not in data or str(data[f]).strip() == "" for f in FIELDS):
                return JsonResponse({"error": "All fields are required."}, status=400)
            p.method_type = str(data["method_type"]).strip()
            p.provider = str(data["provider"]).strip()
            p.acc_num = str(data["acc_num"]).strip()
            p.acc_name = str(data["acc_name"]).strip()
            if not isinstance(data["is_active"], bool):
                return JsonResponse({"error": "Invalid active status."}, status=400)
            p.is_active = data["is_active"]
            p.save()
            return JsonResponse(payment_data(p))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid payment details."}, status=400)
    return JsonResponse({"error": "Method not allowed."}, status=405)
@csrf_exempt
@agency_required
def payment_list(request):
    if request.method not in ["GET", "POST"]:
        return JsonResponse({"error": "Method not allowed."}, status=405)
    return get_payment(request)
@csrf_exempt
@agency_required
def payment_detail(request, pk):
    if request.method not in ["PUT", "DELETE"]:
        return JsonResponse({"error": "Method not allowed."}, status=405)
    return get_payment(request, pk)
@agency_required
def active_pay_details(request):
    rows = payDetails.objects.filter(agency=request.agency, is_active=True).order_by("pk")
    return JsonResponse([payment_data(p) for p in rows], safe=False)