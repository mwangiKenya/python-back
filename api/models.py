from django.db import models

class read_users(models.Model):
    id = models.AutoField(primary_key=True)  # ✅ FIX
    fname = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    metre_num = models.IntegerField()
    zone = models.CharField(max_length=100)
    rate = models.IntegerField()
    created_on = models.DateField()

    class Meta:
        db_table = 'waterusers'
        managed = False

class readings(models.Model):
    id = models.AutoField(primary_key=True) 
    user = models.ForeignKey(read_users, on_delete=models.CASCADE, db_column='user_id')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    prev_user = models.IntegerField()
    prev_sup = models.IntegerField()
    prev_date = models.DateField()
    cur_user = models.IntegerField(null=True, blank=True)
    cur_sup = models.IntegerField(null=True, blank=True)
    cur_date = models.DateField()
    units_used = models.IntegerField()
    rate = models.IntegerField()
    metre_num = models.IntegerField()

    class Meta:
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

    class Meta:
        db_table = 'billings'
        managed = False
'''
class Logs(models.Model):
    id = models.AutoField(primary_key=True)  # ✅ FIX
    reading = models.ForeignKey('readings', on_delete=models.CASCADE, db_column='reading')  # ✅ FK
    field_changed = models.CharField(max_length=100)
    old_val = models.IntegerField()
    new_val = models.IntegerField()
    changed_at = models.DateField()

    class Meta:
        db_table = 'logs'
        managed = False
'''
class Logs(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)   # who performed action
    role = models.CharField(max_length=100)   # role of user
    action = models.CharField(max_length=50)  # CREATE, UPDATE, DELETE, LOGIN
    table_name = models.CharField(max_length=100)  # readings, billings, users
    record_id = models.IntegerField()  # affected row id
    field_changed = models.CharField(max_length=100, null=True, blank=True)
    old_val = models.TextField(null=True, blank=True)
    new_val = models.TextField(null=True, blank=True)
    description = models.TextField()  # human readable message
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'logs'
        managed = False


class Users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    role = models.CharField(max_length=100)

    class Meta:
        db_table = 'users'
        managed = False