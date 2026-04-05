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