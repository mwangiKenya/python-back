from django.http import JsonResponse
from .models import read_users, readings, Admin
from django.views.decorators.csrf import csrf_exempt
import json
import secrets

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
            'created_on': u.created_on.strftime('%Y-%m-%d') if u.created_on else None
        })
    return JsonResponse(data, safe=False)

def read_data(request):
    read = readings.objects.all()
    data = []
    for r in read:
        data.append({
            'name' : r.name,
            'phone' : r.phone,
            'prev_user' : r.prev_user,
            'prev_sup' : r.prev_sup,
            'cur_user' : r.cur_user,
            'cur_sup' : r.cur_sup,
            'rate' : r.rate
        })
    return JsonResponse(data, safe=False)

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
            return JsonResponse({"token": token})
        else:
            return JsonResponse({"error": "Invalid login credentials"}, status=401)

    except:
        return JsonResponse({"error": "Something went wrong"}, status=500)