from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from django.db.models import Sum, Q, Min
from django.db.models.functions import Coalesce
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    filter_backends = [SearchFilter]
    search_fields = ['name', 'code', 'barcode']

    def get_queryset(self):
        user_campus = self.request.user.campus if hasattr(self.request.user, 'campus') else None
        
        if user_campus:
            batch_filter = Q(batches__condition='available', batches__campus=user_campus)
        else:
            batch_filter = Q(batches__condition='available')

        qs = Product.objects.all()
        if user_campus:
            qs = qs.filter(campus=user_campus)

        return qs.annotate(
            total_quantity=Coalesce(Sum('batches__quantity', filter=batch_filter), 0),
            nearest_expiry_date=Min('batches__expiry_date', filter=batch_filter & Q(batches__quantity__gt=0))
        )

    def perform_create(self, serializer):
        campus = self.request.user.campus if hasattr(self.request.user, 'campus') else None
        serializer.save(campus=campus)
    search_fields = ['name', 'code', 'barcode']
