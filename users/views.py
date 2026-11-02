from api.models import Users, read_users, readings, Billings
from api.auth import agency_required, admin_required, make_token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from datetime import date
from django.db import transaction
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
@admin_required
def register_user(request):
    try:
        username = request.data.get("username")
        password = request.data.get("password")
        role = request.data.get("role")
        phone = request.data.get("phone")
        reg_on = request.data.get("reg_on")
        status = request.data.get("status")
        if not username or not password or not role or not phone or not reg_on or not status:
            return Response({"error": "All fields are required"}, status=400)
        if Users.objects.filter(username=username).exists():
            return Response({"error": "Username already exists"}, status=400)
        Users.objects.create(
            username=username,
            password=make_password(password),
            role=role,
            phone=phone,
            agency=request.agency,
            reg_on=reg_on,
            status=status,
        )
        return Response({"message": "User registered successfully"}, status=201)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def users_login(request):
    try:
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response({"error": "Username and password are required"}, status=400)
        user = Users.objects.filter(username=username).first()
        if not user or not check_password(password, user.password):
            return Response({"error": "Invalid credentials"}, status=401)
        return Response({
            "token": make_token(user),
            "username": user.username,
            "role": user.role,
            "agency": user.agency
        })
    except Exception as e:
        print('failed to login: ', e)
@csrf_exempt
@admin_required
def update_employee(request, emp_id):
    if request.method != "PUT":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        emp = Users.objects.get(id=emp_id, agency=request.agency)
        emp.username = data.get("username", emp.username)
        emp.role = data.get("role", emp.role)
        emp.save()
        return JsonResponse({"message": "Employee updated"})
    except Users.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
@admin_required
def list_employees(request):
    return Response(list(Users.objects.filter(agency=request.agency).values('id', 'username', 'role', 'phone', 'status', 'reg_on')))
@csrf_exempt
@admin_required
def delete_employee(request, emp_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request"}, status=400)
    if emp_id == request.auth_user.id:
        return JsonResponse({"error": "You cannot delete your own account"}, status=400)
    try:
        Users.objects.get(id=emp_id, agency=request.agency).delete()
        return JsonResponse({"message": "Employee deleted"})
    except Users.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
@agency_required
def change_password(request):
    try:
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")
        if not current_password or not new_password:
            return Response({"error": "Current password and new password are required."}, status=400)
        if len(new_password) < 6:
            return Response({"error": "New password must be at least 6 characters."}, status=400)
        user = request.auth_user
        if not check_password(current_password, user.password):
            return Response({"error": "Current password is incorrect."}, status=400)
        if check_password(new_password, user.password):
            return Response({"error": "New password must be different from the current password."}, status=400)
        user.password = make_password(new_password)
        user.save(update_fields=["password"])
        return Response({"message": "Password changed successfully."}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
@csrf_exempt
@admin_required
def delete_user(request, user_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        with transaction.atomic():
            try:
                user = read_users.objects.get(id=user_id, agency=request.agency)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)
            readings.objects.filter(user_id=user_id, agency=request.agency).delete()
            Billings.objects.filter(user_id=user_id, agency=request.agency).delete()
            Billings.objects.filter(name=user.fname, agency=request.agency).delete()
            user.delete()
        return JsonResponse({"message": "User fully deleted"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@agency_required
def new_user(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)
    print(f'Agency of the user: {request.agency}')
    try:
        data = json.loads(request.body)
        fname = data.get("fname")
        phone = data.get("phone")
        metre_num = data.get("metre_num")
        zone = data.get("zone")
        rate = data.get("rate")
        grp = data.get("grp")
        parent = data.get("parent")
        gen_name = data.get("gen_name")
        email = data.get("email")
        password = data.get("password")
        agency = request.agency
        if not all([fname, phone, metre_num, zone, rate, email, password]):
            return JsonResponse({"error": "Missing fields"}, status=400)
        with transaction.atomic():
            user = read_users.objects.create(
                fname=fname, phone=phone, metre_num=metre_num,
                zone=zone, rate=rate, created_on=date.today(), grp=grp, parent=parent, gen_name=gen_name,
                email=email, password=make_password(password), agency=agency,
            )
            readings.objects.create(
                user=user, name=fname, phone=phone,
                prev_user=0, prev_sup=0,
                cur_user=None, cur_sup=None,
                units_used=0, rate=rate, metre_num=metre_num,
                grp=grp, parent=parent, gen_name=gen_name, agency=agency,
            )
        return JsonResponse({"message": "User registered successfully"})
    except Exception as e:
        print('Cant register customer: ', e)
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@agency_required
def update_user(request, user_id):
    if request.method != "PUT":
        return JsonResponse({"error": "Invalid request"}, status=400)
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            try:
                user = read_users.objects.get(id=user_id, agency=request.agency)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)
            user.fname = data.get("fname") or user.fname
            user.phone = data.get("phone") or user.phone
            user.metre_num = data.get("metre_num") or user.metre_num
            user.zone = data.get("zone") or user.zone
            user.rate = data.get("rate") or user.rate
            user.grp = data.get("grp") or user.grp
            user.parent = data.get("parent") or user.parent
            user.gen_name = data.get("gen_name") or user.gen_name
            user.save()
            readings.objects.filter(user_id=user_id, agency=request.agency).update(
                name=user.fname, phone=user.phone, metre_num=user.metre_num,
                rate=user.rate, grp=user.grp, parent=user.parent, gen_name=user.gen_name
            )
            Billings.objects.filter(user_id=user_id, agency=request.agency).update(
                name=user.fname, phone=user.phone, rate=user.rate,
                sms_name=user.metre_num, grp=user.grp, parent=user.parent, gen_name=user.gen_name
            )
        return JsonResponse({"message": "User updated successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
@agency_required
def update_all_users(request):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT request required"}, status=405)
    try:
        customers = json.loads(request.body)
        with transaction.atomic():
            for customer in customers:
                user = read_users.objects.get(id=customer["id"], agency=request.agency)
                user.fname = customer["fname"]
                user.phone = customer["phone"]
                user.metre_num = customer["metre_num"]
                user.rate = customer["rate"]
                user.grp = customer["grp"]
                user.parent = customer["parent"]
                user.gen_name = customer["gen_name"]
                user.save()
                readings.objects.filter(user_id=user.id, agency=request.agency).update(
                    name=user.fname, phone=user.phone, metre_num=user.metre_num,
                    rate=user.rate, grp=user.grp, parent=user.parent, gen_name=user.gen_name
                )
                Billings.objects.filter(user_id=user.id, agency=request.agency).update(
                    name=user.fname, phone=user.phone, rate=user.rate,
                    sms_name=user.metre_num, grp=user.grp, parent=user.parent,
                    gen_name=user.gen_name
                )
        return JsonResponse({"success": True, "message": "All users updated successfully."})
    except read_users.DoesNotExist:
        return JsonResponse({"error": "One or more users do not exist."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
@csrf_exempt
@agency_required
def update_all_bill_phones(request):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT request required"}, status=405)
    try:
        phone = json.loads(request.body).get("phone")
        if not phone:
            return JsonResponse({"error": "Phone number is required"}, status=400)
        updated = Billings.objects.filter(agency=request.agency).update(phone=phone)
        return JsonResponse({"success": True, "updated": updated})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
@agency_required
def water_users(request):
    data = [{
        'id': u.id, 'fname': u.fname, 'phone': u.phone, 'metre_num': u.metre_num,
        'zone': u.zone, 'rate': u.rate,
        'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None,
        'grp': u.grp, 'parent': u.parent, 'gen_name': u.gen_name
    } for u in read_users.objects.filter(agency=request.agency)]
    return JsonResponse(data, safe=False)