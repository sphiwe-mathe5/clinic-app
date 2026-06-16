from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import ProductViewSet, CategoryViewSet

router = SimpleRouter()
router.register(r'catalog', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = [
    path('', include(router.urls)),
]
