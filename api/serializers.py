# serializers.py
from rest_framework import serializers
from .models import read_users, readings, billings
from django.utils import timezone

# ============================================================
# WATER USER VIEWSET SERIALIZER
# ============================================================
class WaterUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = read_users
        fields = '__all__'