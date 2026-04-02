from django.db import models
from django.db.models import F, Sum, Count, Avg

#FETCH THE CUSTOMERS DATA FROM THE DATABASE AND DISPLAY ON THE FRONT END
#CREATE THE MODEL CLASS TO PASS TO VIEWS.PY
class read_users(models.Model):
    id = models.AutoField(primary_key=True)
    fname = models.CharField(max_length=20)
    sname = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    metre_num = models.IntegerField()
    zone = models.CharField(max_length=40)
    rate = models.IntegerField()
    created_on = models.DateField(editable=False , auto_now_add=True)

    #specify the table
    class Meta:
        db_table = 'waterusers'
        managed = False

    #COUNT THE TOTAL NUMBER OF REGISTERED CUSTOMERS AND DISPLAY THEM ON THE FRONTEND
    @classmethod
    def total_cust(cls):
        return cls.objects.aggregate(total = Count("id"))["total"] or 0
    
    def __str__(self):
        return f"{self.fname} {self.sname}"
    
    def __str__(self):
        return self.name
    

#FETCH THE BILLINGS DATA FROM THE DATABASE TO DISPLAY THEM ON THE FRONTEND
#CREATE A MODEL CLASS TO PULL THE DATA
class billings(models.Model):
    user_id = models.IntegerField()
    name = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    billed_on = models.DateField(auto_now_add=True)
    units_used = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    rate = models.IntegerField()
    bill = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    paid = models.DecimalField(max_digits=10, decimal_places=2, editable=True)
    bal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    status = models.CharField(max_length=40)


    class Meta:
        db_table = 'billings'

    def save(self, *args, **kwargs):
        if self.units_used is None:
            self.units_used = 0

        if self.rate is None:
            self.rate = 0
        if self.units_used >= 1:
            self.bill = self.units_used * self.rate
        else:
            self.bill = 300


        #==================================
        #Save the payment status
        '''        
        if self.bill == self.paid:
            self.status = 'Fully paid'
        elif self.paid < self.bill and self.paid > 0:
            self.status = 'Partial Paid'
        else:
            self.status = 'Unpaid'
        '''
        super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.bal = self.bill - self.paid
        self.status = "Paid" if self.bal <= 0 else "Unpaid"
        super().save(*args, **kwargs)

    #======================================================================
    #CALCULATE THE SUM OF THE AMOUNT BILLED FROM THE BILLING TABLE
    @classmethod
    def total_bill(cls):
        bill = cls.objects.aggregate(total=Sum("bill"))["total"] or 0
        return round(bill, 2)

    #=========================================================================
    #CALCULATE THE SUM OF THE TOTAL AMOUNT PAID FROM THE BILLINGS TABLE
    @classmethod
    def total_paid(cls):
        paid = cls.objects.aggregate(total=Sum("paid"))["total"] or 0
        return round(paid, 2)


#FETCH THE TOTAL uNITS USED FROM THE DATABASE
#ALSO, USE THE SAME CLASS TO FETCH THE READINGS DATA TO SEND THEM TO FRONTEND
class readings(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(read_users, on_delete=models.CASCADE, db_column='user_id')
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=50)
    prev_user = models.IntegerField(null=False, blank=False)
    prev_sup = models.IntegerField()
    prev_date = models.DateField(editable=False)
    cur_user = models.IntegerField(null=False, blank=False)
    cur_sup = models.IntegerField()
    cur_date = models.DateField(editable=False)
    units_used = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    rate = models.IntegerField()
    #created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        prev = self.prev_user if self.prev_user is not None else 0
        cur = self.cur_user if self.cur_user is not None else 0
        self.units_used = cur - prev
        super().save(*args, **kwargs)
    

    class Meta:
        db_table = "readings"

    @classmethod
    def total_units(cls):
        return cls.objects.aggregate(total=Sum("units_used"))["total"] or 0
    

    #READ THE AVERAGE OF UNITS USED TO DISPLAY ON THE FRONTEND
    @classmethod
    def avg_units(cls):
        avg = cls.objects.aggregate(average = Avg("units_used"))["average"] or 0
        return round(avg, 2)
    

    def save(self, *args, **kwargs):
        self.units_used = self.cur_user - self.prev_user
        super().save(*args, **kwargs)



#========================================================================
#Admin Login
from django.contrib.auth.hashers import make_password, check_password

class Admin(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)  # store hashed password

    class Meta:
        db_table = "admin"
        managed = False  # if table already exists

    # Helper method to check password
    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    # Helper method to set password
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()



from django.contrib.auth.hashers import make_password, check_password

#==============================================================================
# ENABLE THE USER TO LOGIN
from django.db import models

class users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)  # plain text now
    role = models.CharField(max_length=255)

    class Meta:
        db_table = 'users'
        managed = False

#================================================================================
#CREATE THE MODEL FOR THE LOGS TABLE
class Logs(models.Model):
    id = models.AutoField(primary_key=True)

    reading = models.ForeignKey(
        'readings',
        on_delete=models.CASCADE,
        db_column='id'   # must match column name in MySQL
    )

    field_changed = models.CharField(max_length=50)

    old_val = models.IntegerField(db_column='old_val', null=True, blank=True)
    new_val = models.IntegerField(db_column='new_val', null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    #changed_at = models.DateTimeField()

    class Meta:
        db_table = "logs"
        managed = False