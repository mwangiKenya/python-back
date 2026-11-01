from django.db import models
from datetime import date
from django.db.models import GeneratedField, F, ExpressionWrapper, FloatField

class read_users(models.Model):
    id = models.AutoField(primary_key=True)
    fname = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    metre_num = models.CharField(max_length=40)
    zone = models.CharField(max_length=100)
    rate = models.IntegerField()
    created_on = models.DateField()
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    gen_name = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    password = models.CharField(max_length=200)
    agency = models.IntegerField()

    class Meta:
        ordering = ["id"]
        db_table = 'waterusers'
        managed = False


class readings(models.Model):
    id = models.AutoField(primary_key=True) 
    user = models.ForeignKey(read_users, on_delete=models.CASCADE, db_column='user_id')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    prev_user = models.IntegerField(null=True)
    prev_sup = models.IntegerField(null=True)
    cur_user = models.IntegerField(null=True, blank=True)
    cur_sup = models.IntegerField(null=True, blank=True)
    units_used = models.IntegerField(null=True)
    rate = models.IntegerField(null=True)
    metre_num = models.CharField(max_length=40)
    mid_user = models.IntegerField(null=True, blank=True)
    mid_sup = models.IntegerField(null=True, blank=True)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    gen_name = models.CharField(max_length=50)
    agency = models.IntegerField()

    class Meta:
        ordering = ["user"]
        db_table = 'readings'
        managed = False


class Admin(models.Model):
    id = models.IntegerField(primary_key=True)
    username = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    password = models.CharField(max_length=100)

    class Meta:
        db_table = 'admin'
        managed = False


class Billings(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.IntegerField()
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    billed_on = models.DateField()
    units_used = models.IntegerField()
    rate = models.IntegerField()
    bill = models.FloatField()
    paid = models.FloatField()
    bal = models.FloatField()
    status = models.CharField(max_length=100)
    b_cd = models.FloatField()
    prev_user = models.IntegerField()
    cur_user = models.IntegerField()
    sms_name = models.CharField(max_length=50)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    last_modified = models.DateTimeField(auto_now=True)
    penalty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gen_name = models.CharField(max_length=50)
    agency = models.IntegerField()

    class Meta:
        ordering = ["user_id"]
        db_table = 'billings'
        managed = False

class BillDates(models.Model):
    billing = models.DateField()
    due = models.DateField()
    month = models.CharField(max_length=7)
    agency = models.IntegerField(null=True)
    class Meta:
        db_table = "bill_dates"

class Users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    agency = models.IntegerField()
    reg_on = models.DateField()
    status = models.CharField(max_length=50)

    class Meta:
        db_table = 'users'
        managed = False

class ReadingsHist(models.Model):
    user_id = models.IntegerField()
    agency = models.IntegerField()
    prev_user = models.IntegerField()
    prev_sup = models.IntegerField()
    cur_user = models.IntegerField()
    cur_sup = models.IntegerField()
    month = models.DateField()

    class Meta:
        db_table = 'read_hist'
        managed = False

class Payments(models.Model):
    user_id = models.IntegerField()
    agency = models.IntegerField()
    bill = models.DecimalField(decimal_places=2, max_digits=10)
    paid = models.DecimalField(decimal_places=2, max_digits=10)
    bal = models.DecimalField(decimal_places=2, max_digits=10)
    month = models.CharField(max_length=50)

    class Meta:
        db_table = 'payments'
        managed = False

class payDetails(models.Model):
    agency = models.IntegerField()
    method_type = models.CharField(max_length=100)
    provider = models.CharField(max_length=100)
    acc_num = models.CharField(max_length=100)
    acc_name = models.CharField(max_length=100)
    is_active = models.BooleanField()

    class Meta:
        db_table = 'pay_details'
        managed = False