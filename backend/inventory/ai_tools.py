import json
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from products.models import Product
from suppliers.models import Supplier
from inventory.models import Batch, StockTransaction, Alert

def get_product_stock(product_name: str) -> str:
    """Retrieve current stock levels and details for a specific product by name."""
    products = Product.objects.filter(name__icontains=product_name)
    if not products.exists():
        return json.dumps({"error": f"No product found matching '{product_name}'"})
    
    results = []
    for product in products:
        total_qty = product.batches.filter(condition='available').aggregate(Sum('quantity'))['quantity__sum'] or 0
        active_batches = list(product.batches.filter(condition='available', quantity__gt=0).values('batch_number', 'quantity', 'expiry_date'))
        
        # Format dates as strings
        for b in active_batches:
            b['expiry_date'] = b['expiry_date'].strftime('%Y-%m-%d') if b['expiry_date'] else None
            
        results.append({
            "product_name": product.name,
            "product_code": product.code,
            "total_quantity": total_qty,
            "min_stock_level": product.min_stock_level,
            "active_batches": active_batches
        })
    return json.dumps(results)

def get_low_stock_products() -> str:
    """Retrieve a list of all products whose total available quantity is below their minimum stock level."""
    products = Product.objects.all()
    low_stock = []
    
    for product in products:
        total_qty = product.batches.filter(condition='available').aggregate(Sum('quantity'))['quantity__sum'] or 0
        if total_qty < product.min_stock_level:
            low_stock.append({
                "product_name": product.name,
                "current_quantity": total_qty,
                "minimum_required": product.min_stock_level,
                "deficit": product.min_stock_level - total_qty
            })
            
    return json.dumps(low_stock)

def get_expiring_products(days: int) -> str:
    """Retrieve products with batches expiring within the specified number of days."""
    today = timezone.now().date()
    target_date = today + timedelta(days=days)
    
    expiring_batches = Batch.objects.filter(
        condition='available',
        quantity__gt=0,
        expiry_date__lte=target_date,
        expiry_date__gte=today
    ).select_related('product').order_by('expiry_date')
    
    results = []
    for batch in expiring_batches:
        days_left = (batch.expiry_date - today).days
        results.append({
            "product_name": batch.product.name,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date.strftime('%Y-%m-%d'),
            "days_remaining": days_left
        })
    return json.dumps(results)

def get_expired_batches() -> str:
    """Retrieve all batches that have expired but still have physical quantity in the system."""
    today = timezone.now().date()
    # Batches that are explicitly marked expired, or dates in past with qty
    expired_batches = Batch.objects.filter(
        quantity__gt=0,
        condition='expired'
    ).select_related('product') | Batch.objects.filter(
        quantity__gt=0,
        expiry_date__lt=today
    ).select_related('product')
    
    expired_batches = expired_batches.distinct().order_by('expiry_date')
    
    results = []
    for batch in expired_batches:
        results.append({
            "product_name": batch.product.name,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date.strftime('%Y-%m-%d')
        })
    return json.dumps(results)

def get_inventory_summary() -> str:
    """Get a high-level summary of the entire inventory health."""
    total_products = Product.objects.count()
    
    # Calculate low stock
    products = Product.objects.all()
    low_stock_count = sum(
        1 for p in products 
        if (p.batches.filter(condition='available').aggregate(Sum('quantity'))['quantity__sum'] or 0) < p.min_stock_level
    )
    
    today = timezone.now().date()
    expiring_30_days = Batch.objects.filter(
        condition='available', quantity__gt=0, 
        expiry_date__lte=today + timedelta(days=30),
        expiry_date__gte=today
    ).count()
    
    expired_qty = Batch.objects.filter(
        quantity__gt=0,
        expiry_date__lt=today
    ).aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    unresolved_alerts = Alert.objects.filter(status='unresolved').count()
    
    summary = {
        "total_unique_products": total_products,
        "products_low_on_stock": low_stock_count,
        "batches_expiring_in_30_days": expiring_30_days,
        "total_expired_units_awaiting_disposal": expired_qty,
        "active_system_alerts": unresolved_alerts
    }
    return json.dumps(summary)

def get_top_issued_products() -> str:
    """Retrieve the most issued products in the last 30 days to identify fast movers."""
    last_30_days = timezone.now() - timedelta(days=30)
    
    top_issued = StockTransaction.objects.filter(
        transaction_type='issue',
        timestamp__gte=last_30_days
    ).values('product__name').annotate(
        total_issued=Sum('quantity')
    ).order_by('-total_issued')[:10]
    
    results = [{"product_name": item['product__name'], "total_issued_30_days": item['total_issued']} for item in top_issued]
    return json.dumps(results)

def get_supplier_statistics() -> str:
    """Retrieve statistics on which suppliers have provided the most stock."""
    stats = Batch.objects.exclude(supplier__isnull=True).values('supplier__name').annotate(
        total_batches=Count('id'),
        total_units_supplied=Sum('quantity')
    ).order_by('-total_units_supplied')[:10]
    
    results = [{"supplier_name": item['supplier__name'], "total_batches": item['total_batches'], "total_units": item['total_units_supplied']} for item in stats]
    return json.dumps(results)

def get_recent_stock_movements() -> str:
    """Retrieve the 10 most recent stock issues or receipts."""
    recent_txs = StockTransaction.objects.select_related('product', 'user').order_by('-timestamp')[:10]
    
    results = []
    for tx in recent_txs:
        results.append({
            "action": tx.transaction_type,
            "product_name": tx.product.name,
            "quantity": tx.quantity,
            "user": tx.user.get_full_name() if tx.user else "System",
            "time": tx.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    return json.dumps(results)

def get_write_off_summary() -> str:
    """Retrieve a summary of recent stock write-offs / disposals."""
    write_offs = StockTransaction.objects.filter(
        transaction_type='issue',
        reason='expired'
    ).select_related('product').order_by('-timestamp')[:10]
    
    results = []
    for w in write_offs:
        results.append({
            "product_name": w.product.name,
            "quantity_disposed": w.quantity,
            "date": w.timestamp.strftime('%Y-%m-%d'),
            "user": w.user.get_full_name() if w.user else "System",
            "notes": w.notes
        })
    return json.dumps(results)

# Map of tool names to their actual python functions
AI_TOOLS_MAP = {
    "get_product_stock": get_product_stock,
    "get_low_stock_products": get_low_stock_products,
    "get_expiring_products": get_expiring_products,
    "get_expired_batches": get_expired_batches,
    "get_inventory_summary": get_inventory_summary,
    "get_top_issued_products": get_top_issued_products,
    "get_supplier_statistics": get_supplier_statistics,
    "get_recent_stock_movements": get_recent_stock_movements,
    "get_write_off_summary": get_write_off_summary,
}

# OpenAI JSON Schemas for these tools
AI_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_product_stock",
            "description": "Get current stock levels, active batches, and expiry dates for a specific product by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The name of the product (e.g., 'Panado')"
                    }
                },
                "required": ["product_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_products",
            "description": "Get a list of all products that are currently below their minimum required stock level.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expiring_products",
            "description": "Get a list of product batches that will expire within the specified number of days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days from today to check for expiry (e.g., 7, 30)"
                    }
                },
                "required": ["days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expired_batches",
            "description": "Get a list of all batches that have already expired but still have physical stock in the system.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_summary",
            "description": "Get a high-level summary of the entire inventory health, including counts of low stock items, expiring items, and active alerts.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_issued_products",
            "description": "Get a list of the most frequently issued (fastest moving) products over the last 30 days.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_supplier_statistics",
            "description": "Get statistics on which suppliers have provided the most stock.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_stock_movements",
            "description": "Get a log of the most recent stock issues and receipts.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_write_off_summary",
            "description": "Get a summary of recent stock write-offs and disposals.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
