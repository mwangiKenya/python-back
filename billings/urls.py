from django.urls import path
from . import views

urlpatterns = [
    path('update_paid/',views.update_paid,name='update_paid'),
    path('update-billing-penalty/',views.update_billing_penalty,name='update_billing_penalty'),
    path('download-billings-template/',views.download_billings_template,name='download_billings_template'),
    path('upload-billings-excel/',views.upload_billings_excel,name='upload_billings_excel'),
    path('extract-billings-excel/',views.extract_billings_excel,name='extract_billings_excel'),
    path('commit-billings-excel/',views.commit_billings_excel,name='commit_billings_excel'),
    path('rollback-billings-excel/',views.rollback_billings_excel,name='rollback_billings_excel'),
    path('send_sms_view/', views.send_sms_view, name='send_bulk_sms'),
    path('bill/', views.bill, name='bill'),
]