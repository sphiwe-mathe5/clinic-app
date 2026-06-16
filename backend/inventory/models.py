from django.db import models
from django.conf import settings
from products.models import Product
from suppliers.models import Supplier

class Batch(models.Model):
    CONDITION_CHOICES = [
        ('available', 'Available'),
        ('quarantined', 'Quarantined'),
        ('damaged', 'Damaged'),
        ('expired', 'Expired'),
    ]
    CAMPUS_CHOICES = [
        ('APK', 'Auckland Park Kingsway'),
        ('DFC', 'Doornfontein Campus'),
        ('APB', 'Auckland Park Bunting Road'),
        ('SWC', 'Soweto Campus'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    expiry_date = models.DateField()
    date_received = models.DateField(auto_now_add=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='batches')
    barcode = models.CharField(max_length=255, blank=True, null=True)
    qr_code = models.CharField(max_length=255, blank=True, null=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='available')
    campus = models.CharField(max_length=3, choices=CAMPUS_CHOICES, null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_batches')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} - Batch {self.batch_number}"

    def __str__(self):
        return f"{self.product.name} - Batch {self.batch_number}"

class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('issue', 'Issue'),
        ('receive', 'Receive')
    ]
    REASON_CHOICES = [
        ('patient_use', 'Patient Use'),
        ('internal_use', 'Internal Use'),
        ('emergency_use', 'Emergency Use'),
        ('expired', 'Expired / Disposal'),
        ('other', 'Other')
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transactions')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.PositiveIntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reason = models.CharField(max_length=50, choices=REASON_CHOICES, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type.capitalize()} - {self.product.name} ({self.quantity})"

class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]
    STATUS_CHOICES = [
        ('unresolved', 'Unresolved'),
        ('resolved', 'Resolved'),
    ]
    
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.CharField(max_length=255)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    campus = models.CharField(max_length=3, choices=Batch.CAMPUS_CHOICES, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unresolved')
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alerts')

    def __str__(self):
        return f"[{self.severity.upper()}] {self.message}"
