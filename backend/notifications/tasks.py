from celery import shared_task
from inventory.models import Batch
from products.models import Product
from django.utils import timezone
import datetime

@shared_task
def check_expiring_stock():
    today = timezone.now().date()
    thresholds = [7, 30, 60, 90]
    
    for threshold in thresholds:
        target_date = today + datetime.timedelta(days=threshold)
        expiring_batches = Batch.objects.filter(expiry_date=target_date, condition='available', quantity__gt=0)
        
        for batch in expiring_batches:
            # Here we would normally trigger an email or push notification to the dashboard
            print(f"ALERT: Batch {batch.batch_number} of {batch.product.name} expires in {threshold} days!")

@shared_task
def check_low_stock():
    products = Product.objects.all()
    for product in products:
        total_quantity = sum(b.quantity for b in product.batches.filter(condition='available'))
        if total_quantity < product.min_stock_level:
            # Trigger notification
            print(f"ALERT: Low stock for {product.name}. Current: {total_quantity}, Minimum: {product.min_stock_level}")
