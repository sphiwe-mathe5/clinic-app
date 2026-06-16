from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Product(models.Model):
    CAMPUS_CHOICES = [
        ('APK', 'Auckland Park Kingsway'),
        ('DFC', 'Doornfontein Campus'),
        ('APB', 'Auckland Park Bunting Road'),
        ('SWC', 'Soweto Campus'),
    ]

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    unit_type = models.CharField(max_length=50, help_text="e.g., Box, Bottle, Tablet, Unit")
    description = models.TextField(blank=True, null=True)
    barcode = models.CharField(max_length=255, blank=True, null=True)
    qr_code = models.CharField(max_length=255, blank=True, null=True)
    min_stock_level = models.PositiveIntegerField(default=10)
    max_stock_level = models.PositiveIntegerField(default=1000)
    campus = models.CharField(max_length=3, choices=CAMPUS_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('code', 'campus')

    def __str__(self):
        return f"{self.name} ({self.code})"
