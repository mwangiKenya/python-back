from django.db import models
from django.db.models import Sum, Count, Avg


# =========================================
# 1. WATER USERS (CUSTOMERS)
# =========================================
class read_users(models.Model):
    id = models.AutoField(primary_key=True)
    fname = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    metre_num = models.IntegerField()
    zone = models.CharField(max_length=40)
    rate = models.IntegerField()
    created_on = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'waterusers'
        managed = False

    @classmethod
    def total_cust(cls):
        return cls.objects.aggregate(total=Count("id"))["total"] or 0

    def __str__(self):
        return self.fname   # ✅ FIXED (removed wrong self.name)


# =========================================
# 2. BILLINGS
# =========================================
class billings(models.Model):
    user_id = models.IntegerField()
    name = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    billed_on = models.DateField(auto_now_add=True)
    units_used = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.IntegerField()
    bill = models.DecimalField(max_digits=10, decimal_places=2)
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bal = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=40)

    class Meta:
        db_table = 'billings'

    def save(self, *args, **kwargs):
        # Ensure safe values
        if self.units_used is None:
            self.units_used = 0

        if self.rate is None:
            self.rate = 0

        # Calculate bill
        if self.units_used >= 1:
            self.bill = self.units_used * self.rate
        else:
            self.bill = 300

        # Calculate balance
        if self.paid is None:
            self.paid = 0

        self.bal = self.bill - self.paid

        # Status
        self.status = "Paid" if self.bal <= 0 else "Unpaid"

        super().save(*args, **kwargs)

    @classmethod
    def total_bill(cls):
        total = cls.objects.aggregate(total=Sum("bill"))["total"] or 0
        return round(total, 2)

    @classmethod
    def total_paid(cls):
        total = cls.objects.aggregate(total=Sum("paid"))["total"] or 0
        return round(total, 2)


# =========================================
# 3. READINGS
# =========================================
class readings(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(read_users, on_delete=models.CASCADE, db_column='user_id')
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=50)
    prev_user = models.IntegerField()
    prev_sup = models.IntegerField()
    prev_date = models.DateField()
    cur_user = models.IntegerField()
    cur_sup = models.IntegerField()
    cur_date = models.DateField()
    units_used = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.IntegerField()

    class Meta:
        db_table = "readings"

    def save(self, *args, **kwargs):
        prev = self.prev_user or 0
        cur = self.cur_user or 0
        self.units_used = cur - prev
        super().save(*args, **kwargs)

    @classmethod
    def total_units(cls):
        return cls.objects.aggregate(total=Sum("units_used"))["total"] or 0

    @classmethod
    def avg_units(cls):
        avg = cls.objects.aggregate(avg=Avg("units_used"))["avg"] or 0
        return round(avg, 2)


# =========================================
# 4. ADMIN LOGIN
# =========================================
class Admin(models.Model):
    username = models.CharField(max_length=50)
    password = models.CharField(max_length=50)

    class Meta:
        db_table = "admin"
        managed = False


# =========================================
# 5. SYSTEM USERS
# =========================================
class users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=255)

    class Meta:
        db_table = 'users'
        managed = False


# =========================================
# 6. LOGS
# =========================================
class Logs(models.Model):
    id = models.AutoField(primary_key=True)

    reading = models.ForeignKey(
        readings,
        on_delete=models.CASCADE,
        db_column='reading'
    )

    field_changed = models.CharField(max_length=50)
    old_val = models.IntegerField(null=True, blank=True)
    new_val = models.IntegerField(null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "logs"
        managed = False