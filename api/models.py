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
    prev_date = models.DateField()
    cur_user = models.IntegerField(null=True, blank=True)
    cur_sup = models.IntegerField(null=True, blank=True)
    cur_date = models.DateField()
    units_used = models.IntegerField(null=True)
    rate = models.IntegerField(null=True)
    metre_num = models.CharField(max_length=40)
    mid_user = models.IntegerField(null=True, blank=True)
    mid_sup = models.IntegerField(null=True, blank=True)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    version = models.IntegerField(default=1)
    gen_name = models.CharField(max_length=50)

    class Meta:
        ordering = ["user"]
        db_table = 'read_back'
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

    class Meta:
        ordering = ["user_id"]
        db_table = 'bill_back'
        managed = False

class BillDates(models.Model):
    billing = models.DateField()
    due = models.DateField()
    month = models.CharField(max_length=7)
    class Meta:
        db_table = "bill_dates"

class Users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    role = models.CharField(max_length=100)

    class Meta:
        db_table = 'users'
        managed = False