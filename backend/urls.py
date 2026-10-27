from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/', include('readings.urls')),
    path('api/', include('billings.urls')),
    path('api/', include('users.urls')),
]
