from django.urls import path, include
from .views import  water_users, read_data, login_user, new_user,update_user,send_sms_api, submit_new_reading, bill, logs, update_paid, total_bill, register_user, list_employees, total_paid, avg_units, total_cust, total_units, users_login, delete_user, delete_employee, update_employee, download_readings_template, upload_readings_excel, hist_data

urlpatterns =[
    path('water_users/', water_users, name='water_users'), #fetch water users data
    path('read_data/', read_data, name='read_data'), #fetch readings data
    path('login_user/', login_user, name='login_user'), #admin login
    path('new_user/', new_user, name='new_user'), # reg user
    path('submit_new_reading/', submit_new_reading, name='submit_new_reading'),
    path('bill/', bill, name='bill'), # fetch billings data
    path('logs/', logs, name='logs'), #fetch logs data
    path('update_paid/', update_paid, name='update_paid'),
    path('total_bill/', total_bill, name='total_bill'),
    path('register_user/', register_user, name='register_user'),
    path('list_employees/', list_employees, name='list_employees'),
    path('total_paid', total_paid, name='total_paid'),
    path('avg_units', avg_units, name='avg_units'),
    path('total_cust/', total_cust, name='total_cust'),
    path('total_units/', total_units, name='total_units'),
    #path('export-readings/', export_readings, name='export_readings'),
    #path('export-billings/', export_billings, name='export_billings'),
    #path('export-users/', export_users, name='export_users'),
    path('users_login/', users_login, name='users_login'),
    path('delete_user/<int:user_id>/', delete_user, name='delete_user'),
    path('delete_employee/<int:emp_id>/', delete_employee),
    path('update_employee/<int:emp_id>/', update_employee),
    path("download_readings_template/", download_readings_template),
    path("upload_readings_excel/", upload_readings_excel),
    path('update_user/<int:user_id>/', update_user, name='update_user'),
    path('hist_data/', hist_data, name='hist_data'),
    path('send-sms/', send_sms_api),
]
