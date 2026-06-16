from django.apps import AppConfig


import os

class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        # Prevent scheduler from running multiple times in dev with auto-reloader
        if os.environ.get('RUN_MAIN', None) != 'true':
            return
            
        from apscheduler.schedulers.background import BackgroundScheduler
        from .engine import process_notifications

        scheduler = BackgroundScheduler()
        # Run every 1 minute for testing purposes
        scheduler.add_job(process_notifications, 'interval', minutes=1, id='inventory_sync', replace_existing=True)
        scheduler.start()
        print("APScheduler started: Inventory notification engine running every 1 minute.")
