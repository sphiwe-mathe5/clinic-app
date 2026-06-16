from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('nurse', 'Nurse'),
        ('coordinator', 'Coordinator'),
        ('administrator', 'Administrator'),
    ]
    CAMPUS_CHOICES = [
        ('APK', 'Auckland Park Kingsway'),
        ('DFC', 'Doornfontein Campus'),
        ('APB', 'Auckland Park Bunting Road'),
        ('SWC', 'Soweto Campus'),
    ]

    staff_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='nurse')
    campus = models.CharField(max_length=3, choices=CAMPUS_CHOICES, null=True, blank=True)
    
    # Override email to make it unique
    email = models.EmailField(unique=True)

    # Preferences
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    email_notifications = models.BooleanField(default=True)
    low_stock_alerts = models.BooleanField(default=True)
    expiry_alerts = models.CharField(max_length=20, default='30_days')
    table_view = models.CharField(max_length=20, default='comfortable')

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"
