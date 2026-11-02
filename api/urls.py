from django.urls import path
from . import views
urlpatterns = [
    path('total_units/', views.total_units),
    path('total_bal/', views.total_bal),
    path('total_bill/', views.total_bill),
    path('total_paid/', views.total_paid),
    path('total_cust/', views.total_cust),
    path('avg_units/', views.avg_units),
    path('bill_dates/', views.bill_dates_view),
    path('login_user/', views.login_user),
]