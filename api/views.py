from django.http import JsonResponse
from .models import read_users, readings

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
            'created_on' : u.created_on
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