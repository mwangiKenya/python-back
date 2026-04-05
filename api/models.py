from django.db import models

class read_users(models.Model):
    id = models.IntegerField()
    fname = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)
    metre_num = models.IntegerField()
    zone = models.CharField(max_length=100)
    rate = models.IntegerField()
    created_on = models.DateField()

    class Meta:
        db_table = 'waterusers'
        managed = False
'''
class readings(models.Model):
    id = models.IntegerField()
    user_id = models.IntegerField()
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    prev_user = models.IntegerField()
    prev_sup = models.IntegerField()
    prev_date = models.DateField()
    cur_user = models.IntegerField()
    cur_sup = models.IntegerField()
    cur_date = models.DateField()
    units_used = models.IntegerField()
    rate = models.IntegerField()

    class Meta:
        db_table = 'readings'
        managed = False
'''