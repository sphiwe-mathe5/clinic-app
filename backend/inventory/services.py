from django.utils import timezone
from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from .models import Batch, Alert
from products.models import Product
import logging

logger = logging.getLogger(__name__)

def sync_alerts_system_wide():
    """
    Synchronizes alerts across all campuses. Used by the background notification engine
    and the manual sync API endpoint.
    """
    campuses = [c[0] for c in Batch.CAMPUS_CHOICES] + [None]
    notified_products = set()

    for campus in campuses:
        # 1. Low Stock Logic
        batch_filter = Q(batches__condition='available')
        if campus:
            batch_filter &= Q(batches__campus=campus)

        products = Product.objects.annotate(
            total_quantity=Coalesce(Sum('batches__quantity', filter=batch_filter), 0)
        )
        
        for p in products:
            if campus and not Batch.objects.filter(product=p, campus=campus).exists():
                continue

            if p.total_quantity == 0:
                alert, created = _create_or_update_alert('critical', f"{p.name} is completely out of stock.", product=p, campus=campus)
                if created: _trigger_supplier_notification(p, campus, notified_products)
            elif p.total_quantity <= p.min_stock_level:
                alert, created = _create_or_update_alert('warning', f"{p.name} is running low (Qty: {p.total_quantity}, Min: {p.min_stock_level}).", product=p, campus=campus)
                if created: _trigger_supplier_notification(p, campus, notified_products)
            else:
                _resolve_auto_alerts(product=p, severity_list=['critical', 'warning'], message_contains="stock", campus=campus)

        # 2. Expiry Logic
        today = timezone.now().date()
        batches = Batch.objects.filter(quantity__gt=0, condition='available')
        if campus:
            batches = batches.filter(campus=campus)

        for b in batches:
            days_to_expiry = (b.expiry_date - today).days
            if days_to_expiry < 0:
                b.condition = 'expired'
                b.save()
                _create_or_update_alert('critical', f"Batch {b.batch_number} of {b.product.name} has expired and needs write-off.", product=b.product, batch=b, campus=b.campus)
            elif days_to_expiry <= 7:
                _create_or_update_alert('critical', f"Batch {b.batch_number} of {b.product.name} expires in {days_to_expiry} days.", product=b.product, batch=b, campus=b.campus)
            elif days_to_expiry <= 30:
                _create_or_update_alert('warning', f"Batch {b.batch_number} of {b.product.name} expires in {days_to_expiry} days.", product=b.product, batch=b, campus=b.campus)
            else:
                _resolve_auto_alerts(batch=b, message_contains="expire", campus=b.campus)

        # 3. Damaged/Quarantined Logic
        bad_batches = Batch.objects.exclude(condition='available').filter(quantity__gt=0)
        if campus:
            bad_batches = bad_batches.filter(campus=campus)

        for b in bad_batches:
            if b.condition == 'damaged':
                _create_or_update_alert('critical', f"Batch {b.batch_number} of {b.product.name} is marked as damaged.", product=b.product, batch=b, campus=b.campus)
            elif b.condition == 'quarantined':
                _create_or_update_alert('warning', f"Batch {b.batch_number} of {b.product.name} is quarantined.", product=b.product, batch=b, campus=b.campus)
            elif b.condition == 'expired':
                _create_or_update_alert('critical', f"Batch {b.batch_number} of {b.product.name} has expired and needs write-off.", product=b.product, batch=b, campus=b.campus)

def _create_or_update_alert(severity, message, product=None, batch=None, campus=None):
    return Alert.objects.get_or_create(
        severity=severity,
        message=message,
        product=product,
        batch=batch,
        campus=campus,
        status='unresolved'
    )

def _resolve_auto_alerts(product=None, batch=None, severity_list=None, message_contains=None, campus=None):
    qs = Alert.objects.filter(status='unresolved')
    if product: qs = qs.filter(product=product)
    if batch: qs = qs.filter(batch=batch)
    if severity_list: qs = qs.filter(severity__in=severity_list)
    if message_contains: qs = qs.filter(message__icontains=message_contains)
    if campus: qs = qs.filter(campus=campus)
    
    for alert in qs:
        alert.status = 'resolved'
        alert.resolved_at = timezone.now()
        alert.save()

def _trigger_supplier_notification(product, campus, notified_products=None):
    if notified_products is not None and product.id in notified_products:
        return
    last_batch = Batch.objects.filter(product=product, supplier__isnull=False).order_by('-date_received').first()
    if last_batch and last_batch.supplier:
        send_supplier_low_stock_email(product, last_batch.supplier, campus)
        if notified_products is not None:
            notified_products.add(product.id)

def send_supplier_low_stock_email(product, supplier, campus=None):
    if not supplier.email or not supplier.notify_on_low_stock:
        return
        
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        subject = f"Low Stock Alert: {product.name} needs restocking"
        campus_str = f" at {campus}" if campus else ""
        
        body = f"""Dear {supplier.contact_person or supplier.name},

This is an automated notification from our Inventory Management System.

We are currently running low on stock for the following product{campus_str}:
Product Name: {product.name}
Product Code: {product.code or 'N/A'}
Minimum Required Level: {product.min_stock_level}

Please let us know your availability to supply a new batch.

Thank you,
Clinic Inventory System
"""
        html_message = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; background-color: #f4f4f4; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
      <div style="background-color: #f8f9fa; padding: 20px; text-align: center; border-bottom: 3px solid #007bff;">
        <h2 style="margin: 0; color: #007bff;">Restock Request</h2>
      </div>
      <div style="padding: 30px;">
        <p>Dear <strong>{supplier.contact_person or supplier.name}</strong>,</p>
        <p>This is an automated notification from our Inventory Management System. We are currently running low on stock for the following product{campus_str}:</p>
        
        <div style="background-color: #f1f3f5; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #007bff;">
          <h3 style="margin-top: 0; margin-bottom: 10px; color: #333;">{product.name}</h3>
          <ul style="list-style-type: none; padding: 0; margin: 0; color: #555;">
            <li style="margin-bottom: 8px;"><strong>Product Code:</strong> {product.code or 'N/A'}</li>
            <li><strong>Minimum Required Level:</strong> {product.min_stock_level}</li>
          </ul>
        </div>
        
        <p>Please let us know your availability to supply a new batch. You can reply directly to this email to coordinate the shipment.</p>
        
        <p style="margin-top: 30px; font-size: 0.9em; color: #777;">Thank you,<br/><strong>Clinic Inventory System</strong></p>
      </div>
    </div>
  </body>
</html>
"""
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[supplier.email],
            fail_silently=False,
            html_message=html_message
        )
        logger.info(f"Sent low stock email to {supplier.email} for product {product.name}")
    except Exception as e:
        logger.error(f"Failed to send low stock email to {supplier.email}: {e}")
        _create_or_update_alert('warning', f"Failed to send low stock email to {supplier.name} for {product.name}.", product=product, campus=campus)
