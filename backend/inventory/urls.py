from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import BatchViewSet, StockTransactionViewSet, AlertViewSet, DashboardStatsView, AssistantView

router = SimpleRouter()
router.register(r'batches', BatchViewSet, basename='batch')
router.register(r'transactions', StockTransactionViewSet, basename='transaction')
router.register(r'alerts', AlertViewSet, basename='alert')

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('assistant/', AssistantView.as_view(), name='assistant'),
    path('', include(router.urls)),
]
