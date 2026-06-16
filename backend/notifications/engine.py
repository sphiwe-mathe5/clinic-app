import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from inventory.models import Alert
from users.models import User
from inventory.services import sync_alerts_system_wide

logger = logging.getLogger(__name__)

def process_notifications():
    """
    Background job that syncs alerts and dispatches a single consolidated digest email per user.
    """
    try:
        # 1. Update the alerts table across all campuses
        sync_alerts_system_wide()
        
        # 2. Grab all unresolved alerts that haven't triggered an email yet
        unsent_alerts = Alert.objects.filter(status='unresolved', email_sent=False)
        
        if not unsent_alerts.exists():
            return
            
        # 3. Determine which users get which alerts
        user_alerts = {}
        target_users = User.objects.filter(email_notifications=True)
        
        for alert in unsent_alerts:
            is_low_stock = 'stock' in alert.message.lower()
            is_expiry = 'expire' in alert.message.lower() or 'expired' in alert.message.lower()
            
            for user in target_users:
                if alert.campus and alert.campus != user.campus:
                    continue
                    
                should_notify = False
                
                if is_low_stock and user.low_stock_alerts:
                    should_notify = True
                elif is_expiry:
                    days_left = 0
                    if 'expired!' in alert.message.lower():
                        days_left = -1
                    elif 'expires in' in alert.message.lower():
                        import re
                        match = re.search(r'expires in (\d+) days', alert.message)
                        if match:
                            days_left = int(match.group(1))

                    if user.expiry_alerts == '90_days' and days_left <= 90:
                        should_notify = True
                    elif user.expiry_alerts == '30_days' and days_left <= 30:
                        should_notify = True
                    elif user.expiry_alerts == '7_days' and days_left <= 7:
                        should_notify = True
                    elif days_left < 0:
                        should_notify = True
                elif not is_low_stock and not is_expiry:
                    should_notify = True
                    
                if should_notify:
                    if user not in user_alerts:
                        user_alerts[user] = {'critical': [], 'warning': []}
                    
                    if alert.severity == 'critical':
                        user_alerts[user]['critical'].append(alert)
                    else:
                        user_alerts[user]['warning'].append(alert)

        # 4. Dispatch consolidated emails
        for user, alerts_dict in user_alerts.items():
            if not alerts_dict['critical'] and not alerts_dict['warning']:
                continue
                
            context = {
                'user': user,
                'critical_alerts': alerts_dict['critical'],
                'warning_alerts': alerts_dict['warning']
            }
            
            html_message = render_to_string('emails/inventory_digest.html', context)
            plain_message = strip_tags(html_message)
            
            try:
                send_mail(
                    subject="CIMS Daily Inventory Digest",
                    message=plain_message,
                    html_message=html_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Failed to send digest email to {user.email}: {e}")
                
        # 5. Mark all as sent
        unsent_alerts.update(email_sent=True)
            
    except Exception as e:
        logger.error(f"Error in notification engine: {str(e)}")
