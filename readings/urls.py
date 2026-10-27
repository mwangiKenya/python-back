from django.urls import path, include
from . import views

urlpatterns = [
    path('read_data/',views.read_data, name='readi_data'),
    path('submit_new_reading/',views.submit_new_reading,name='submit_new_reading'),
    path('download_readings_template/', views.download_readings_template,name='download_readings_template'),
    path('upload_readings_excel/', views.upload_readings_excel,name='upload_readings_excel'),
    path('shift_readings/', views.shift_readings),
]