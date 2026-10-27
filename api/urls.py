from django.urls import path, include
from . import views
from .views import login_user, total_bill,bill_dates_view, total_paid, avg_units, total_cust, total_units,total_bal

urlpatterns =[
    path('login_user/', login_user, name='login_user'),
    path('total_bill/', total_bill, name='total_bill'),    
    path('total_paid', total_paid, name='total_paid'),
    path('avg_units', avg_units, name='avg_units'),
    path('total_cust/', total_cust, name='total_cust'),
    path('total_units/', total_units, name='total_units'),
    path("total_bal/", total_bal, name="total_bal"),    
    path('analytics_summary/', views.analytics_summary),
    path('analytics_monthly_trend/', views.analytics_monthly_trend),
    path('analytics_zone_performance/', views.analytics_zone_performance),
    path('analytics_group_breakdown/', views.analytics_group_breakdown),
    path('analytics_status_breakdown/', views.analytics_status_breakdown),
    path('analytics_tariff_breakdown/', views.analytics_tariff_breakdown),
    path('analytics_consumption_bands/', views.analytics_consumption_bands),
    path('analytics_customer_growth/', views.analytics_customer_growth), 
    path('analytics_top_debtors/', views.analytics_top_debtors), 
    path('analytics_top_consumers/', views.analytics_top_consumers),
    path('analytics_reading_anomalies/', views.analytics_reading_anomalies),
    path("bill_dates/", bill_dates_view),
]