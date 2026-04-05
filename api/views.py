from django.http import JsonResponse
from .models import read_users

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
