import json
from django.utils.deprecation import MiddlewareMixin
from .models import AuditLog

class AuditMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE'] and not request.path.startswith('/admin/'):
            if hasattr(request, 'user') and request.user.is_authenticated:
                action = f"{request.method} {request.path}"
                ip_address = request.META.get('REMOTE_ADDR')
                
                AuditLog.objects.create(
                    user=request.user,
                    action=action,
                    ip_address=ip_address,
                    details={"status_code": response.status_code}
                )
        return response
