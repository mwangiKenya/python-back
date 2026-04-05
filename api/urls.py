from django.urls import path, include
from .views import  water_users, read_data, login_user, new_user, submit_new_reading, bill, logs

urlpatterns =[
    path('water_users/', water_users, name='water_users'), #fetch water users data
    path('read_data/', read_data, name='read_data'), #fetch readings data
    path('login_user/', login_user, name='login_user'), #admin login
    path('new_user/', new_user, name='new_user'), # reg user
    path('submit_new_reading/', submit_new_reading, name='submit_new_reading'),
    path('bill/', bill, name='bill'), # fetch billings data
    path('logs/', logs, name='logs'), #fetch logs data
]
