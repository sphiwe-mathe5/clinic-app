from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import SupplierViewSet

router = SimpleRouter()
router.register(r'', SupplierViewSet, basename='supplier')

urlpatterns = [
    path('', include(router.urls)),
]
