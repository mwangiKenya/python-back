from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import  water_users, bill, total_units, total_bill, total_cust, avg_units, new_user, read_data, update_readings, export_readings_excel,export_billings_excel, export_users_excel, send_billing_sms, login_user, login_users, update_paid, user_profile, total_paid, logs, submit_new_reading
from rest_framework.routers import DefaultRouter
from .views import WaterUserViewSet

router = DefaultRouter()
router.register(r'water_user', WaterUserViewSet, basename='water_user')

urlpatterns =[
    path('water_users/', water_users), #fetch water users data
    path('bill/', bill), #fetch billings data
    path('total_units/', total_units), #read the total units used from the db to display frontend
    path('total_bill/', total_bill), #read the total bill from billings table and display on frontend
    path('total_paid', total_paid), #read the total amount paid from the billings table
    path('total_cust/', total_cust), #Fetch total number of Customers
    path('avg_units', avg_units), #Average units used from readings table
    path('new_user/', new_user), #Register new user
    path('read_data/', read_data), #read readings data
    path("update-readings/", update_readings, name="update_readings"),
    path('export-readings/', export_readings_excel, name='export_readings'), #download readings excel
    path('export-billings/', export_billings_excel), #export billings excel
    path('export-users/', export_users_excel), #Export users excel file
    path('send-billing-sms/', send_billing_sms, name='send_billing_sms'),
    path('login/', login_user, name='login'),
    path('users_login/', login_users, name = 'users_login'),
    path('update_paid/', update_paid, name='update_paid'),
    path('', include(router.urls)),
    path("user-profile/<int:user_id>/", user_profile),
    path('logs/', logs, name='logs'), # Fetch logs data and display in the frontend
    path('submit_new_reading', submit_new_reading, name='submit_new_reading'),
]
