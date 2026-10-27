from api.models import Users, read_users, readings, Billings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password
import secrets
from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from datetime import date
from django.db import transaction


@api_view(['POST'])
def register_user(request):
    username = request.data.get("username")
    password = request.data.get("password")
    role = request.data.get("role")
    if not username or not password or not role:
        return Response({"error": "All fields are required"}, status=400)
    if Users.objects.filter(username=username).exists():
        return Response({"error": "Username already exists"}, status=400)
    Users.objects.create(
        username=username,
        password=make_password(password),
        role=role
    )
    return Response({"message": "User registered successfully"}, status=201)

@api_view(['POST'])
def users_login(request):
    username = request.data.get("username")
    password = request.data.get("password")
    if not username or not password:
        return Response({"error": "Username and password are required"}, status=400)
    user = Users.objects.filter(username=username).first()
    if not user or not check_password(password, user.password):
        return Response({"error": "Invalid credentials"}, status=401)
    return Response({
        "token": secrets.token_hex(16),
        "username": user.username,
        "role": user.role
    })

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

@api_view(['POST'])
def change_password(request):
    try:
        username = request.data.get("username")
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")
        if not username or not current_password or not new_password:
            return Response({"error": "Username, current password and new password are required."}, status=400)
        if len(new_password) < 6:
            return Response({"error": "New password must be at least 6 characters."}, status=400)
        user = Users.objects.filter(username=username).first()
        if not user:
            return Response({"error": "User not found."}, status=404)
        if not check_password(current_password, user.password):
            return Response({"error": "Current password is incorrect."}, status=401)
        if check_password(new_password, user.password):
            return Response({"error": "New password must be different from the current password."}, status=400)
        user.password = make_password(new_password)
        user.save(update_fields=["password"])
        return Response({"message": "Password changed successfully."}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

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
            readings.objects.filter(user_id=user_id).delete()
            Billings.objects.filter(user_id=user_id).delete()
            Billings.objects.filter(name=user.fname).delete()
            user.delete()
        return JsonResponse({"message": "User fully deleted"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


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
        gen_name = data.get("gen_name")
        if not all([fname, phone, metre_num, zone, rate]):
            return JsonResponse({"error": "Missing fields"}, status=400)
        with transaction.atomic():
            user = read_users.objects.create(
                fname=fname, phone=phone, metre_num=metre_num,
                zone=zone, rate=rate, grp=grp, parent=parent, gen_name=gen_name,
            )
            today = date.today()
            reading = readings.objects.create(
                user=user, name=fname, phone=phone,
                prev_user=0, prev_sup=0, prev_date=today,
                cur_user=None, cur_sup=None, cur_date=today,
                units_used=0, rate=rate, metre_num=metre_num,
                grp=grp, parent=parent,gen_name=gen_name,
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
        gen_name = data.get("gen_name")
        with transaction.atomic():
            try:
                user = read_users.objects.get(id=user_id)
            except read_users.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)
            old_name = user.fname
            old_data = {
                'fname': user.fname, 'phone': user.phone, 'metre_num': user.metre_num,
                'zone': user.zone, 'rate': user.rate, 'grp': user.grp, 'parent': user.parent,
                'gen_name': user.gen_name
            }
            user.fname = fname or user.fname
            user.phone = phone or user.phone
            user.metre_num = metre_num or user.metre_num
            user.zone = zone or user.zone
            user.rate = rate or user.rate
            user.grp = grp or user.grp
            user.parent = parent or user.parent
            user.gen_name = gen_name or user.gen_name
            user.save()
            readings.objects.filter(user_id=user_id).update(
                name=fname, phone=phone, metre_num=metre_num,
                rate=rate, grp=grp, parent=parent, gen_name=gen_name
            )
            Billings.objects.filter(user_id=user_id).update(
                name=fname, phone=phone, rate=rate,
                sms_name=metre_num, grp=grp, parent=parent, gen_name=gen_name
            )
            
        return JsonResponse({"message": "User updated successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

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
                user.gen_name = customer["gen_name"]
                user.save()
                readings.objects.filter(user_id=user.id).update(
                    name=user.fname, phone=user.phone, metre_num=user.metre_num,
                    rate=user.rate, grp=user.grp, parent=user.parent,gen_name=user.gen_name
                )
                Billings.objects.filter(user_id=user.id).update(
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
def update_all_bill_phones(request):
    if request.method != "PUT":
        return JsonResponse({"error": "PUT request required"}, status=405)
    try:
        data = json.loads(request.body)
        phone = data.get("phone")
        if not phone:
            return JsonResponse({"error": "Phone number is required"}, status=400)
        updated = Billings.objects.update(phone=phone)
        return JsonResponse({"success": True, "updated": updated})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def water_users(request):
    data = [{
        'id': u.id, 'fname': u.fname, 'phone': u.phone, 'metre_num': u.metre_num,
        'zone': u.zone, 'rate': u.rate,
        'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None,
        'grp': u.grp, 'parent': u.parent, 'gen_name': u.gen_name
    } for u in read_users.objects.all()]
    return JsonResponse(data, safe=False)