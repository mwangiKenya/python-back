from django.urls import path, include
from .views import  water_users

urlpatterns =[
    path('water_users/', water_users, name='water_users'), #fetch water users data
]
