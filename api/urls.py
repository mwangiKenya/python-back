from django.urls import path, include
from .views import  water_users, read_data, login_user, new_user,update_user, submit_new_reading, bill, logs, update_paid, total_bill, register_user, list_employees, total_paid, avg_units, total_cust, total_units, users_login, delete_user, delete_employee, update_employee, download_readings_template, upload_readings_excel, hist_data, send_sms_view, download_billings_template, upload_billings_excel, reset_mid_month_readings, billing_timer, finalize_month, restore_readings, start_billing_month, cycle_timer_status, set_cycle_duration, auto_shift_if_due, total_bal, download_users_excel, update_all_users, update_all_bill_phones, get_all_payment_history, get_billing_history, get_payment_history, get_payment_history_by_user, get_payment_history_json, get_payment_summary, get_payment_receipt, download_payment_receipt

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
    #path('send_sms_api/', send_sms_api, name='send_sms_api'),
    path("send_sms_view/", send_sms_view, name='send_sms_view'),
    path("download-billings-template/", download_billings_template),
    path("upload-billings-excel/", upload_billings_excel),
    path("reset-mid-month-readings/", reset_mid_month_readings),
    path("billing_timer/", billing_timer, name="billing_timer"),
    path("finalize_month/", finalize_month, name="finalize_month"),
    path("restore_readings/", restore_readings, name="restore_readings"),
    path("start_billing_month/", start_billing_month),
    path("set_cycle_duration/", set_cycle_duration),
    path("cycle_timer_status/", cycle_timer_status),
    path("auto_shift_if_due/", auto_shift_if_due),
    path("total_bal/", total_bal, name="total_bal"),
    path("download_users/", download_users_excel),
    path(
    "update_all_users/",
    update_all_users,
    name="update_all_users",
    ),
    path(
        "update_all_bill_phones/",
        update_all_bill_phones,
        name="update_all_bill_phones",
    ),
    path('payment-history/', get_all_payment_history, name='get_all_payment_history'),
    path('payment-history/user/<int:user_id>/', get_payment_history_by_user, name='get_payment_history_by_user'),
    path('payment-history/summary/', get_payment_summary, name='get_payment_summary'),
    path('payment-history/receipt/<str:receipt_number>/', get_payment_receipt, name='get_payment_receipt'),
    path('payment-history/json/', get_payment_history_json, name='get_payment_history_json'),
    path('download_receipt/<str:receipt_number>/', download_payment_receipt, name='download_receipt'),
]
