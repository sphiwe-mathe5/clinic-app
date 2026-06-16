from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Batch, StockTransaction, Alert
from products.models import Product
from audit.models import AuditLog
from .serializers import BatchSerializer, StockTransactionSerializer, AlertSerializer
from django.utils import timezone
from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from .ai_utils import analyze_image_with_vision
from .services import sync_alerts_system_wide
from .ai_service import ask_inventory_assistant
from rest_framework.permissions import IsAuthenticated
import base64

class AlertViewSet(viewsets.ModelViewSet):
    serializer_class = AlertSerializer
    filterset_fields = ['severity', 'status', 'product']

    def get_queryset(self):
        qs = Alert.objects.all().order_by('-created_at')
        if hasattr(self.request.user, 'campus') and self.request.user.campus:
            qs = qs.filter(campus=self.request.user.campus)
        return qs

    @action(detail=False, methods=['post'])
    def sync(self, request):
        sync_alerts_system_wide()
        return Response({"message": "Alerts synced successfully"})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.status = 'resolved'
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user if request.user.is_authenticated else None
        alert.save()
        
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action="Resolved Alert",
            details={"alert_id": alert.id, "message": alert.message}
        )
        return Response({"message": "Alert marked as resolved"})

class StockTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockTransaction.objects.all().order_by('-timestamp')
    serializer_class = StockTransactionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request.user, 'campus') and self.request.user.campus:
            queryset = queryset.filter(batch__campus=self.request.user.campus)
            
        t_type = self.request.query_params.get('transaction_type')
        product_id = self.request.query_params.get('product')
        user_id = self.request.query_params.get('user')
        if t_type:
            queryset = queryset.filter(transaction_type=t_type)
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset

class BatchViewSet(viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    filterset_fields = ['product', 'condition']

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request.user, 'campus') and self.request.user.campus:
            queryset = queryset.filter(campus=self.request.user.campus)
            
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset

    @action(detail=False, methods=['get'])
    def available_for_product(self, request):
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({"error": "product_id is required"}, status=400)
        
        batches = Batch.objects.filter(product_id=product_id, condition='available', quantity__gt=0)
        if hasattr(request.user, 'campus') and request.user.campus:
            batches = batches.filter(campus=request.user.campus)
            
        batches = batches.order_by('expiry_date')
        serializer = self.get_serializer(batches, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = request.data.get('product_id')
        product_name = request.data.get('product_name')
        batch_number = request.data.get('batch_number')
        expiry_date = request.data.get('expiry_date')
        quantity = int(request.data.get('quantity', 0))
        campus = request.user.campus if hasattr(request.user, 'campus') else None
        min_stock_level = request.data.get('min_stock_level')
        category_id = request.data.get('category_id')

        if expiry_date:
            today = timezone.now().strftime('%Y-%m-%d')
            if expiry_date < today:
                return Response({
                    "error": "Expiry date cannot be in the past."
                }, status=status.HTTP_400_BAD_REQUEST)

        product = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()
        elif product_name:
            product = Product.objects.filter(name=product_name).first()

        if product:
            save_needed = False
            if min_stock_level is not None and product.min_stock_level != int(min_stock_level):
                product.min_stock_level = int(min_stock_level)
                save_needed = True
            if category_id and str(product.category_id) != str(category_id):
                product.category_id = category_id
                save_needed = True
            if save_needed:
                product.save()

        if product and batch_number:
            existing_batch = Batch.objects.filter(product=product, batch_number=batch_number, campus=campus).first()
            if existing_batch:
                if existing_batch.condition == 'expired' or str(existing_batch.expiry_date) < timezone.now().strftime('%Y-%m-%d'):
                    return Response({
                        "error": f"Batch {batch_number} is expired. You cannot add stock to an expired batch. Please create a new batch instead."
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                if str(existing_batch.expiry_date) == expiry_date:
                    existing_batch.quantity += quantity
                    if existing_batch.condition in ['quarantined', 'damaged'] and existing_batch.quantity > 0:
                        pass
                    existing_batch.save()
                    
                    StockTransaction.objects.create(
                        product=product,
                        batch=existing_batch,
                        transaction_type='receive',
                        quantity=quantity,
                        user=request.user if request.user.is_authenticated else None,
                        reason='other',
                    )
                    
                    return Response({
                        "message": f"Batch {batch_number} already exists. Increased quantity by {quantity}.",
                        "batch": self.get_serializer(existing_batch).data
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        "error": f"Batch {batch_number} already exists but with a DIFFERENT expiry date ({existing_batch.expiry_date}). Automatic merging prevented."
                    }, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        campus = self.request.user.campus if hasattr(self.request.user, 'campus') else None
        batch = serializer.save(campus=campus, received_by=self.request.user if self.request.user.is_authenticated else None)
        
        StockTransaction.objects.create(
            product=batch.product,
            batch=batch,
            transaction_type='receive',
            quantity=batch.quantity,
            user=self.request.user if self.request.user.is_authenticated else None,
            reason='other',
        )

    @action(detail=False, methods=['post'])
    def issue_stock(self, request):
        product_id = request.data.get('product_id')
        quantity_to_issue = request.data.get('quantity')
        reason = request.data.get('reason', 'patient_use')
        batch_id = request.data.get('batch_id')
        
        if not product_id or not quantity_to_issue:
            return Response({"error": "Product ID and quantity are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            quantity_to_issue = int(quantity_to_issue)
            product = Product.objects.get(id=product_id)
        except (ValueError, Product.DoesNotExist):
            return Response({"error": "Invalid Product ID or quantity."}, status=status.HTTP_400_BAD_REQUEST)

        # Handle specific batch override
        if batch_id:
            try:
                batch = Batch.objects.get(id=batch_id, product=product, condition='available')
                if batch.quantity < quantity_to_issue:
                    return Response({"error": f"Not enough stock in selected batch. Only {batch.quantity} available."}, status=status.HTTP_400_BAD_REQUEST)
                
                batch.quantity -= quantity_to_issue
                batch.save()

                StockTransaction.objects.create(
                    product=product,
                    batch=batch,
                    transaction_type='issue',
                    quantity=quantity_to_issue,
                    user=request.user if request.user.is_authenticated else None,
                    reason=reason
                )

                AuditLog.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    action="Issued Stock (Manual Override)",
                    product=product,
                    details={"quantity_issued": quantity_to_issue, "batch_id": batch.id}
                )

                return Response({"message": f"Successfully issued {quantity_to_issue} from batch {batch.batch_number}."})

            except Batch.DoesNotExist:
                return Response({"error": "Invalid Batch ID or batch not available."}, status=status.HTTP_400_BAD_REQUEST)

        # FEFO Logic: Get available batches ordered by earliest expiry date
        available_batches = Batch.objects.filter(
            product=product,
            condition='available',
            quantity__gt=0,
            expiry_date__gte=timezone.now().date()
        )
        if hasattr(request.user, 'campus') and request.user.campus:
            available_batches = available_batches.filter(campus=request.user.campus)
            
        available_batches = available_batches.order_by('expiry_date')

        total_available = sum(batch.quantity for batch in available_batches)
        if total_available < quantity_to_issue:
            return Response({"error": f"Not enough available stock. Only {total_available} available."}, status=status.HTTP_400_BAD_REQUEST)

        issued_quantity = 0
        issued_batches = []
        for batch in available_batches:
            if issued_quantity >= quantity_to_issue:
                break
            
            needed = quantity_to_issue - issued_quantity
            deducted = min(batch.quantity, needed)
            
            batch.quantity -= deducted
            batch.save()
            issued_quantity += deducted

            StockTransaction.objects.create(
                product=product,
                batch=batch,
                transaction_type='issue',
                quantity=deducted,
                user=request.user if request.user.is_authenticated else None,
                reason=reason
            )
            issued_batches.append(batch.batch_number)

        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action="Issued Stock (FEFO)",
            product=product,
            details={"quantity_issued": quantity_to_issue, "batches": issued_batches}
        )

        return Response({"message": f"Successfully issued {quantity_to_issue} of {product.name}."})

    @action(detail=True, methods=['post'])
    def write_off(self, request, pk=None):
        batch = self.get_object()
        quantity_to_dispose = request.data.get('quantity')
        notes = request.data.get('notes', 'Expired stock disposal')
        
        if not quantity_to_dispose:
            return Response({"error": "Quantity is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            quantity_to_dispose = int(quantity_to_dispose)
        except ValueError:
            return Response({"error": "Invalid quantity"}, status=status.HTTP_400_BAD_REQUEST)
            
        if quantity_to_dispose > batch.quantity:
            return Response({"error": f"Cannot write off more than available ({batch.quantity})"}, status=status.HTTP_400_BAD_REQUEST)
            
        if quantity_to_dispose <= 0:
            return Response({"error": "Quantity must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)
            
        batch.quantity -= quantity_to_dispose
        batch.save()
        
        StockTransaction.objects.create(
            product=batch.product,
            batch=batch,
            transaction_type='issue',
            quantity=quantity_to_dispose,
            user=request.user if request.user.is_authenticated else None,
            reason='expired',
            notes=notes
        )
        
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action="Stock Write-Off (Disposal)",
            product=batch.product,
            details={"batch_number": batch.batch_number, "quantity": quantity_to_dispose, "notes": notes}
        )
        
        return Response({"message": f"Successfully wrote off {quantity_to_dispose} units from batch {batch.batch_number}."})

    @action(detail=False, methods=['post'])
    def analyze_label(self, request):
        image_data = request.data.get('image')
        region_scan = request.data.get('region_scan')
        if not image_data:
            return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Handle base64 encoded image (data:image/jpeg;base64,...)
            if 'base64,' in image_data:
                format, imgstr = image_data.split('base64,') 
            else:
                imgstr = image_data
                
            image_content = base64.b64decode(imgstr)
            results = analyze_image_with_vision(image_content, region_scan=region_scan)
            return Response(results)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DashboardStatsView(APIView):
    def get(self, request):
        user_campus = request.user.campus if hasattr(request.user, 'campus') else None
        today = timezone.now().date()
        
        # Base filters
        product_filter = Q(campus=user_campus) if user_campus else Q()
        batch_filter = Q(campus=user_campus) if user_campus else Q()
        alert_filter = Q(campus=user_campus) if user_campus else Q()
        tx_filter = Q(batch__campus=user_campus) if user_campus else Q()

        # 1. KPIs
        total_products = Product.objects.filter(product_filter).count()
        
        issued_today = StockTransaction.objects.filter(
            tx_filter, 
            transaction_type='issue',
            timestamp__date=today
        ).aggregate(total=Sum('quantity'))['total'] or 0

        # Calculate quantities per product for low stock logic
        if user_campus:
            b_filter = Q(batches__condition='available', batches__campus=user_campus)
        else:
            b_filter = Q(batches__condition='available')
            
        products_with_stock = Product.objects.filter(product_filter).annotate(
            total_quantity=Coalesce(Sum('batches__quantity', filter=b_filter), 0)
        )
        
        low_stock_products = products_with_stock.filter(total_quantity__lte=F('min_stock_level'))
        low_stock_count = low_stock_products.count()

        expiring_soon_count = Batch.objects.filter(
            batch_filter,
            condition='available',
            quantity__gt=0,
            expiry_date__lte=today + timezone.timedelta(days=90),
            expiry_date__gte=today
        ).count()

        # 2. Requires Attention (Alerts) - Grouped by Product
        recent_alerts = Alert.objects.filter(
            alert_filter, 
            status='unresolved',
            severity__in=['critical', 'warning']
        ).order_by('-created_at')[:20]
        
        alerts_by_product = {}
        for a in recent_alerts:
            pid = a.product.id if a.product else f"sys_{a.id}"
            if pid not in alerts_by_product:
                alerts_by_product[pid] = {
                    "id": a.id,
                    "product_name": a.product.name if a.product else "System",
                    "batches": [],
                    "messages": [],
                    "severities": [],
                    "days_left": None
                }
            
            if a.batch and a.batch.batch_number:
                if a.batch.batch_number not in alerts_by_product[pid]["batches"]:
                    alerts_by_product[pid]["batches"].append(a.batch.batch_number)
                    
            alerts_by_product[pid]["messages"].append(a.message)
            alerts_by_product[pid]["severities"].append(a.severity)
            
            if a.batch and a.batch.expiry_date:
                days = (a.batch.expiry_date - today).days
                if alerts_by_product[pid]["days_left"] is None or days < alerts_by_product[pid]["days_left"]:
                    alerts_by_product[pid]["days_left"] = days

        alerts_data = []
        for pid, data in list(alerts_by_product.items())[:5]:
            overall_severity = 'critical' if 'critical' in data['severities'] else 'warning'
            alerts_data.append({
                "id": data["id"],
                "product_name": data["product_name"],
                "batch_number": ", ".join(data["batches"]) if data["batches"] else "N/A",
                "message": " | ".join(data["messages"]),
                "severity": overall_severity,
                "days_left": data["days_left"]
            })

        # 3. Recent Activity
        recent_txs = StockTransaction.objects.filter(tx_filter).order_by('-timestamp')[:10]
        activity_data = []
        for tx in recent_txs:
            user_name = f"{tx.user.first_name} {tx.user.last_name}" if tx.user else "System"
            action_text = f"{'Received' if tx.transaction_type == 'receive' else 'Issued'} {tx.quantity} {tx.product.name}"
            activity_data.append({
                "id": tx.id,
                "time": tx.timestamp.strftime("%H:%M"),
                "date": tx.timestamp.strftime("%Y-%m-%d"),
                "action": action_text,
                "user": user_name
            })

        # 4. Expiring Within 10 Days
        expiring_batches = Batch.objects.filter(
            batch_filter,
            condition='available',
            quantity__gt=0,
            expiry_date__lte=today + timezone.timedelta(days=10),
            expiry_date__gte=today
        ).order_by('expiry_date')[:5]
        
        expiring_data = []
        for b in expiring_batches:
            expiring_data.append({
                "product_name": b.product.name,
                "batch_number": b.batch_number,
                "days_left": (b.expiry_date - today).days
            })

        # 5. Low Stock Watchlist
        low_stock_data = []
        for p in low_stock_products.order_by('total_quantity')[:5]:
            low_stock_data.append({
                "product_name": p.name,
                "available": p.total_quantity,
                "minimum": p.min_stock_level
            })

        return Response({
            "kpis": {
                "total_products": total_products,
                "expiring_soon": expiring_soon_count,
                "low_stock": low_stock_count,
                "issued_today": issued_today
            },
            "alerts": alerts_data,
            "activity": activity_data,
            "expiring": expiring_data,
            "low_stock_watchlist": low_stock_data
        })

class AssistantView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get('message')
        chat_history = request.data.get('history', [])
        
        if not user_message:
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            response_text = ask_inventory_assistant(user_message, chat_history)
            return Response({"response": response_text})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
