from rest_framework import serializers
from .models import Product, Category

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False
    )
    total_quantity = serializers.IntegerField(read_only=True)
    nearest_expiry_date = serializers.DateField(read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
