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
    cycle_locked_until = models.DateTimeField(null=True, blank=True)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    version = models.IntegerField(default=1)  # Track reading versions

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
    # NEW FIELD: stores a positive penalty amount or a negative discount amount.
    # Defaults to 0 so all existing billing math is unaffected until a user acts on it.
    penalty = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["user_id"]
        db_table = 'billings'
        managed = False


class Logs(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    action = models.CharField(max_length=50)
    table_name = models.CharField(max_length=100)
    record_id = models.IntegerField()
    field_changed = models.CharField(max_length=100, null=True, blank=True)
    old_val = models.TextField(null=True, blank=True)
    new_val = models.TextField(null=True, blank=True)
    description = models.TextField()
    changed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'logs'
        managed = False
        indexes = [
            models.Index(fields=['table_name', 'record_id']),
            models.Index(fields=['changed_at']),
        ]


class Users(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    role = models.CharField(max_length=100)

    class Meta:
        db_table = 'users'
        managed = False


class history(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    field = models.CharField(max_length=50)
    old_val = models.IntegerField()
    new_val = models.IntegerField()
    changed_on = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'history'
        managed = False


# ============================================
# NEW HISTORY TABLES FOR BETTER TRACKING
# ============================================

class ReadingHistory(models.Model):
    """Complete versioned history of all meter readings"""
    id = models.AutoField(primary_key=True)
    
    # Reference to original records
    reading_id = models.IntegerField(db_index=True)
    user_id = models.IntegerField(db_index=True)
    
    # Customer information
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    metre_num = models.CharField(max_length=40)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    
    # Reading values
    prev_user = models.IntegerField(null=True)
    prev_sup = models.IntegerField(null=True)
    cur_user = models.IntegerField(null=True)
    cur_sup = models.IntegerField(null=True)
    mid_user = models.IntegerField(null=True, blank=True)
    mid_sup = models.IntegerField(null=True, blank=True)
    units_used = models.IntegerField(null=True)
    rate = models.IntegerField(null=True)
    
    # Date information
    reading_date = models.DateField()
    prev_date = models.DateField(null=True)
    cycle_month = models.CharField(max_length=7)  # YYYY-MM format
    
    # Metadata
    recorded_by = models.CharField(max_length=100, default='system')
    role = models.CharField(max_length=50, default='system')
    version = models.IntegerField(default=1)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reading_history'
        managed = False
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user_id', 'cycle_month']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['reading_id']),
        ]

    def __str__(self):
        return f"{self.name} - {self.cycle_month} (v{self.version})"


class PaymentHistory(models.Model):
    """Complete payment history with balances and receipts"""
    
    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('M-PESA', 'M-Pesa'),
        ('BANK', 'Bank Transfer'),
        ('EXCEL', 'Excel Upload'),
        ('BULK', 'Bulk Update'),
        ('CHEQUE', 'Cheque'),
        ('ONLINE', 'Online Payment'),
    ]
    
    PAYMENT_STATUS = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REVERSED', 'Reversed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # Reference to original records
    billing_id = models.IntegerField(db_index=True)
    user_id = models.IntegerField(db_index=True)
    
    # Customer information
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    
    # Payment details
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    previous_balance = models.DecimalField(max_digits=10, decimal_places=2)
    current_balance = models.DecimalField(max_digits=10, decimal_places=2)
    bill_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment method and status
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='COMPLETED')
    receipt_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    
    # Additional info
    notes = models.TextField(null=True, blank=True)
    payment_date = models.DateField(auto_now_add=True)
    
    # Metadata
    recorded_by = models.CharField(max_length=100, default='system')
    role = models.CharField(max_length=50, default='system')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_history'
        managed = False
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['billing_id']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f"Payment {self.receipt_number} - {self.name} - {self.amount_paid}"


class BillingHistory(models.Model):
    """Complete billing records for each billing cycle"""
    
    BILLING_STATUS = [
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('ADJUSTED', 'Adjusted'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # Reference to original records
    billing_id = models.IntegerField(db_index=True)
    user_id = models.IntegerField(db_index=True)
    
    # Customer information
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    metre_num = models.CharField(max_length=40)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    
    # Billing details
    units_used = models.IntegerField()
    rate = models.IntegerField()
    current_bill = models.DecimalField(max_digits=10, decimal_places=2)
    previous_balance = models.DecimalField(max_digits=10, decimal_places=2)
    total_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Reading details
    prev_reading = models.IntegerField(null=True)
    current_reading = models.IntegerField(null=True)
    
    # Cycle information
    cycle_month = models.CharField(max_length=7)  # YYYY-MM
    billing_date = models.DateField()
    due_date = models.DateField()
    
    # Status
    status = models.CharField(max_length=20, choices=BILLING_STATUS, default='UNPAID')
    
    # Metadata
    generated_by = models.CharField(max_length=100, default='system')
    role = models.CharField(max_length=50, default='system')
    notes = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'billing_history'
        managed = False
        ordering = ['-cycle_month', '-timestamp']
        indexes = [
            models.Index(fields=['user_id', 'cycle_month']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['billing_id']),
            models.Index(fields=['billing_date']),
        ]

    def __str__(self):
        return f"Billing {self.billing_id} - {self.name} - {self.cycle_month}"


class AuditTrail(models.Model):
    """System-wide comprehensive audit trail"""
    
    ACTION_TYPES = [
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('CREATE', 'Create Record'),
        ('UPDATE', 'Update Record'),
        ('DELETE', 'Delete Record'),
        ('VIEW', 'View Record'),
        ('EXPORT', 'Export Data'),
        ('IMPORT', 'Import Data'),
        ('BULK', 'Bulk Operation'),
        ('SYSTEM', 'System Action'),
        ('ERROR', 'Error Occurred'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # User information
    user_id = models.IntegerField(null=True)
    username = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    
    # Action details
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    table_name = models.CharField(max_length=50, null=True, blank=True)
    record_id = models.IntegerField(null=True, blank=True)
    field_changed = models.CharField(max_length=100, null=True, blank=True)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    
    # Additional context
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    session_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'audit_trail'
        managed = False
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['table_name', 'record_id']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['username']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f"{self.username} - {self.action} - {self.timestamp}"


class BillingCycleHistory(models.Model):
    """Track billing cycle operations"""
    
    id = models.AutoField(primary_key=True)
    cycle_month = models.CharField(max_length=7, unique=True)  # YYYY-MM
    start_date = models.DateField()
    end_date = models.DateField()
    next_cycle_date = models.DateField()
    
    # Summary statistics
    total_customers = models.IntegerField(default=0)
    total_units_consumed = models.IntegerField(default=0)
    total_bill_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ], default='PENDING')
    
    # Metadata
    started_by = models.CharField(max_length=100)
    completed_by = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'billing_cycle_history'
        managed = False
        ordering = ['-cycle_month']

    def __str__(self):
        return f"Cycle {self.cycle_month} - {self.status}"


class CustomerPaymentSummary(models.Model):
    """Summary of customer payments for quick reference"""
    
    id = models.AutoField(primary_key=True)
    user_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=50)
    metre_num = models.CharField(max_length=40)
    grp = models.CharField(max_length=20)
    parent = models.CharField(max_length=20)
    
    # Summary fields
    total_billed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_payment_date = models.DateField(null=True, blank=True)
    last_payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_count = models.IntegerField(default=0)
    
    # Billing cycles
    last_billing_cycle = models.CharField(max_length=7, null=True, blank=True)
    average_consumption = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    payment_status = models.CharField(max_length=20, choices=[
        ('CURRENT', 'Current'),
        ('OVERDUE', 'Overdue'),
        ('DELINQUENT', 'Delinquent'),
        ('PAID', 'Fully Paid'),
    ], default='CURRENT')
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'customer_payment_summary'
        managed = False
        ordering = ['-current_balance']

    def __str__(self):
        return f"{self.name} - Balance: {self.current_balance}"