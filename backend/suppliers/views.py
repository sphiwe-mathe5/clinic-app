from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from .models import Supplier
from .serializers import SupplierSerializer

class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filter_backends = [SearchFilter]
    search_fields = ['name', 'contact_person', 'email']
