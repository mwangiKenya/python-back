from django.urls import path, include
from .views import  water_users, read_data

urlpatterns =[
    path('water_users/', water_users, name='water_users'), #fetch water users data
    path('read_data/', read_data, name='read_data'), #fetch readings data
]
