from rest_framework import serializers
from .models import Batch, StockTransaction, Alert
from products.serializers import ProductSerializer
from suppliers.serializers import SupplierSerializer

class BatchSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True, required=False)
    product_name = serializers.CharField(write_only=True, required=False)
    supplier = SupplierSerializer(read_only=True)
    supplier_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    category_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    min_stock_level = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = '__all__'

    def get_received_by_name(self, obj):
        if obj.received_by:
            return f"{obj.received_by.first_name} {obj.received_by.last_name}".strip() or obj.received_by.email
        return "System"

    def create(self, validated_data):
        product_id = validated_data.pop('product_id', None)
        product_name = validated_data.pop('product_name', None)
        supplier_id = validated_data.pop('supplier_id', None)
        category_id = validated_data.pop('category_id', None)
        min_stock_level = validated_data.pop('min_stock_level', None)
        
        if product_id:
            from products.models import Product
            product = Product.objects.get(id=product_id)
            save_needed = False
            if category_id and not product.category_id:
                product.category_id = category_id
                save_needed = True
            if min_stock_level is not None and product.min_stock_level != min_stock_level:
                product.min_stock_level = min_stock_level
                save_needed = True
            if save_needed:
                product.save()
        elif product_name:
            request = self.context.get('request')
            campus = request.user.campus if request and hasattr(request.user, 'campus') else None
            
            from products.models import Product
            code = product_name[:3].upper() + str(Product.objects.count() + 1).zfill(3)
            defaults = {'code': code, 'unit_type': 'Unit'}
            if min_stock_level is not None:
                defaults['min_stock_level'] = min_stock_level
            if campus:
                defaults['campus'] = campus
                
            product, created = Product.objects.get_or_create(name=product_name, defaults=defaults)
            save_needed = False
            if not created:
                if min_stock_level is not None and product.min_stock_level != min_stock_level:
                    product.min_stock_level = min_stock_level
                    save_needed = True
                if category_id and product.category_id != category_id:
                    product.category_id = category_id
                    save_needed = True
                if campus and not product.campus:
                    product.campus = campus
                    save_needed = True
                if save_needed:
                    product.save()
            elif created and category_id:
                product.category_id = category_id
                product.save()
        else:
            raise serializers.ValidationError({"product": "Either product_id or product_name must be provided."})
            
        validated_data['product'] = product
        if supplier_id:
            validated_data['supplier_id'] = supplier_id
            
        return super().create(validated_data)

class StockTransactionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = StockTransaction
        fields = '__all__'

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        return "System"

class AlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True, allow_null=True)
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = '__all__'

    def get_resolved_by_name(self, obj):
        if obj.resolved_by:
            return f"{obj.resolved_by.first_name} {obj.resolved_by.last_name}".strip() or obj.resolved_by.username
        return None
