# serializers.py
from rest_framework import serializers
from .models import read_users, readings, billings
from django.utils import timezone


# ============================================================
# CREATE NEW USER + INITIAL READING
# ============================================================
class NewUserSerializer(serializers.ModelSerializer):
    prev_user = serializers.IntegerField(default=0)
    prev_sup = serializers.IntegerField(default=0)
    cur_user = serializers.IntegerField(default=0)
    cur_sup = serializers.IntegerField(default=0)

    class Meta:
        model = read_users
        fields = [
            'fname', 'sname', 'phone', 'metre_num', 'zone', 'rate',
            'prev_user', 'prev_sup', 'cur_user', 'cur_sup'
        ]

    def create(self, validated_data):
        readings_data = {
            'prev_user': validated_data.pop('prev_user', 0),
            'prev_sup': validated_data.pop('prev_sup', 0),
            'cur_user': validated_data.pop('cur_user', 0),
            'cur_sup': validated_data.pop('cur_sup', 0),
        }

        # 1️⃣ Create water user
        user = read_users.objects.create(**validated_data)

        # 2️⃣ Create initial reading safely
        readings.objects.create(
            user_id=user.id,
            name=user.fname,
            phone=user.phone,
            prev_user=readings_data['prev_user'],
            prev_sup=readings_data['prev_sup'],
            prev_date=timezone.now(),
            cur_user=readings_data['cur_user'],
            cur_sup=readings_data['cur_sup'],
            cur_date=timezone.now(),
            rate=user.rate
        )

        return user


# ============================================================
# UPDATE READINGS SAFELY (NO CRASH VERSION)
# ============================================================
'''
class UpdateReadingsSerializer(serializers.ModelSerializer):
    prev_user = serializers.IntegerField(required=True)
    cur_user = serializers.IntegerField(required=True)
    prev_sup = serializers.IntegerField(required=False, default=0)
    cur_sup = serializers.IntegerField(required=False, default=0)

    class Meta:
        model = readings
        fields = ['id', 'prev_user', 'prev_sup', 'cur_user', 'cur_sup', 'units_used']

    def update(self, instance, validated_data):

        # 🔹 Safe previous and current values
        prev = validated_data.get('prev_user', instance.prev_user or 0)
        cur = validated_data.get('cur_user', instance.cur_user or 0)

        prev_sup = validated_data.get('prev_sup', instance.prev_sup or 0)
        cur_sup = validated_data.get('cur_sup', instance.cur_sup or 0)

        # 🔹 Ensure rate is safe
        rate = instance.rate if instance.rate is not None else 0

        # 🔹 Assign safe values
        instance.prev_user = prev
        instance.cur_user = cur
        instance.prev_sup = prev_sup
        instance.cur_sup = cur_sup

        # 🔹 Calculate units safely
        units_used = cur - prev
        instance.units_used = units_used

        instance.save(update_fields=[
            'prev_user',
            'prev_sup',
            'cur_user',
            'cur_sup',
            'units_used'
        ])

        # 🔹 Calculate bill safely
        bill_value = units_used * rate if units_used >= 1 else 300

        # 🔹 Update or create billing safely
        billings.objects.update_or_create(
            user_id=instance.user_id,
            defaults={
                'phone': instance.phone,
                'units_used': units_used,
                'name': instance.name,
                'billed_on': instance.cur_date,
                'rate': rate,
                'bill': bill_value,
                'paid': 0  #default
            }
        )

        return instance

'''


from .models import Logs

def update(self, instance, validated_data):

    # ===============================
    # 1. STORE OLD VALUES
    # ===============================
    old_values = {
        "prev_user": instance.prev_user,
        "cur_user": instance.cur_user,
        "prev_sup": instance.prev_sup,
        "cur_sup": instance.cur_sup,
    }

    # ===============================
    # 2. GET NEW VALUES
    # ===============================
    new_values = {
        "prev_user": validated_data.get('prev_user', instance.prev_user),
        "cur_user": validated_data.get('cur_user', instance.cur_user),
        "prev_sup": validated_data.get('prev_sup', instance.prev_sup),
        "cur_sup": validated_data.get('cur_sup', instance.cur_sup),
    }

    # ===============================
    # 3. LOG CHANGES (ONLY IF DIFFERENT)
    # ===============================
    for field in old_values:
        old = old_values[field]
        new = new_values[field]

        if old != new:
            ReadingLogs.objects.create(
                reading=instance,
                field_name=field,
                old_value=old,
                new_value=new
            )

    # ===============================
    # 4. UPDATE INSTANCE
    # ===============================
    instance.prev_user = new_values["prev_user"]
    instance.cur_user = new_values["cur_user"]
    instance.prev_sup = new_values["prev_sup"]
    instance.cur_sup = new_values["cur_sup"]

    # ===============================
    # 5. CALCULATE UNITS
    # ===============================
    units_used = instance.cur_user - instance.prev_user
    instance.units_used = units_used

    instance.save(update_fields=[
        'prev_user',
        'prev_sup',
        'cur_user',
        'cur_sup',
        'units_used'
    ])

    # ===============================
    # 6. UPDATE BILLING (UNCHANGED)
    # ===============================
    rate = instance.rate if instance.rate else 0
    bill_value = units_used * rate if units_used >= 1 else 300

    billings.objects.update_or_create(
        user_id=instance.user_id,
        defaults={
            'phone': instance.phone,
            'units_used': units_used,
            'name': instance.name,
            'billed_on': instance.cur_date,
            'rate': rate,
            'bill': bill_value,
            'paid': 0
        }
    )

    return instance

# ============================================================
# WATER USER VIEWSET SERIALIZER
# ============================================================
class WaterUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = read_users
        fields = '__all__'