from rest_framework.exceptions import ValidationError
from django.contrib.auth import authenticate
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, mixins
from events.models import User, Category, Event, Ticket, Payment
from events import serializers, perms
from rest_framework import viewsets, generics, parsers, permissions
from oauth2_provider.models import AccessToken, Application, RefreshToken
from oauth2_provider.settings import oauth2_settings
from datetime import datetime
from django.utils import timezone
import hashlib
import hmac
import urllib.parse
from django.conf import settings
from rest_framework.authtoken.models import Token
from django.utils import timezone
from datetime import timedelta
from events.serializers import UserSerializer
import secrets
from django.db.models import Q
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.http import JsonResponse
from events.vnpay import vnpay

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def hmacsha512(key, data):
    byteKey = key.encode('utf-8')
    byteData = data.encode('utf-8')
    return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()

class UserViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.UpdateAPIView):
    """
    ViewSet cho người dùng: đăng ký, cập nhật, đăng nhập, đăng xuất, lấy thông tin hiện tại,
    yêu cầu trở thành nhà tổ chức, và xác thực nhà tổ chức.
    """
    queryset = User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]

    def get_permissions(self):
        if self.action in ['login', 'register']:  # Đăng ký và đăng nhập
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    # API Đăng ký
    @action(methods=['post'], detail=False, url_path='register', permission_classes=[permissions.AllowAny])
    def register(self, request):
        """
        Đăng ký người dùng mới và trả về DRF Token.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Tạo DRF Token
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            'user': serializer.data,
            'token': token.key
        }, status=status.HTTP_201_CREATED)

    # API Đăng nhập
    @action(methods=['post'], detail=False, url_path='login', permission_classes=[permissions.AllowAny()])
    def login(self, request):
        """
        Đăng nhập người dùng và trả về DRF Token và OAuth2 access token.
        """
        identifier = request.data.get('username')  # Có thể là username hoặc email
        password = request.data.get('password')

        user = authenticate(username=identifier, password=password)

        # Nếu không tìm được bằng username, thử bằng email
        if not user:
            try:
                user_obj = User.objects.get(email=identifier)
                if user_obj.check_password(password):
                    user = user_obj
            except User.DoesNotExist:
                pass

        if not user:
            return Response({'error': 'Thông tin đăng nhập không hợp lệ'}, status=status.HTTP_401_UNAUTHORIZED)

        # Tạo hoặc lấy DRF Token
        token, _ = Token.objects.get_or_create(user=user)

        # Tạo hoặc lấy ứng dụng OAuth2
        # app, _ = Application.objects.get_or_create(
        #     user=user,
        #     client_type=Application.CLIENT_CONFIDENTIAL,
        #     authorization_grant_type=Application.GRANT_PASSWORD,
        #     defaults={'name': f'{user.username}_app'}
        # )

        try:
            app = Application.objects.get(
                client_id=settings.DEFAULT_OAUTH2_CLIENT_ID)  # Thay 'abc' bằng client_id bạn đã tạo trong admin
        except Application.DoesNotExist:
            return Response({'error': 'Ứng dụng OAuth2 không tồn tại.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Tạo token an toàn cho AccessToken
        access_token_value = secrets.token_urlsafe(32)  # Tạo token 32 byte an toàn
        access_token = AccessToken.objects.create(
            user=user,
            application=app,
            expires=timezone.now() + timedelta(seconds=oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS),
            token=access_token_value,  # Sử dụng token đã tạo
            scope='read write'
        )
        # Tạo token an toàn cho RefreshToken
        refresh_token_value = secrets.token_urlsafe(32)  # Tạo token 32 byte an toàn
        refresh_token = RefreshToken.objects.create(
            user=user,
            application=app,
            token=refresh_token_value,  # Sử dụng token đã tạo
            access_token=access_token
        )

        return Response({
            'drf_token': token.key,
            'oauth2': {
                'access_token': access_token.token,
                'refresh_token': refresh_token.token,
                'expires_in': oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            },
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False, url_path='google-login', permission_classes=[permissions.AllowAny])
    def google_login(self, request):
        token = request.data.get('id_token')

        if not token:
            return Response({'error': 'ID Token is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)

            email = idinfo['email']
            full_name = idinfo.get('name', '')
            first_name = full_name.split()[0] if full_name else ''
            last_name = ' '.join(full_name.split()[1:]) if full_name else ''

            user, created = User.objects.get_or_create(email=email, defaults={
                'username': email.split('@')[0] + secrets.token_hex(2),
                'first_name': first_name,
                'last_name': last_name,
                'is_active': True,
            })

            app = Application.objects.get(client_id=settings.DEFAULT_OAUTH2_CLIENT_ID)

            access_token_value = secrets.token_urlsafe(32)
            access_token = AccessToken.objects.create(
                user=user,
                application=app,
                expires=timezone.now() + timedelta(seconds=3600),
                token=access_token_value,
                scope='read write'
            )

            refresh_token_value = secrets.token_urlsafe(32)
            RefreshToken.objects.create(
                user=user,
                application=app,
                token=refresh_token_value,
                access_token=access_token
            )

            return Response({
                'access_token': access_token.token,
                'refresh_token': refresh_token_value,
                'expires_in': 3600,
                'user': {
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            })

        except ValueError:
            return Response({'error': 'ID Token không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)

    # API Đăng xuất
    @action(methods=['post'], detail=False, url_path='logout')
    def logout(self, request):
        """
        Đăng xuất: xóa DRF Token và OAuth2 Access Token/Refresh Token.
        """
        # Xóa DRF Token
        Token.objects.filter(user=request.user).delete()

        # Xóa tất cả OAuth2 AccessToken và RefreshToken của user
        access_tokens = AccessToken.objects.filter(user=request.user)
        for token in access_tokens:
            RefreshToken.objects.filter(access_token=token).delete()
        access_tokens.delete()

        return Response({'message': 'Đăng xuất thành công'}, status=status.HTTP_200_OK)


class OrganizerViewSet(viewsets.GenericViewSet):
    """
    ViewSet cho các hành động liên quan đến nhà tổ chức, như xác thực.
    """
    queryset = User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer

    @action(methods=['post'], url_path='request-organizer', detail=False,
            permission_classes=[permissions.IsAuthenticated])
    def request_organizer(self, request):
        """
        Người dùng yêu cầu trở thành nhà tổ chức.
        """
        user = request.user
        if user.is_organizer:
            return Response({"detail": "Bạn đã là nhà tổ chức."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_organizer = True
        user.save()
        serializer = self.get_serializer(user)
        return Response({
            "detail": "Yêu cầu đã được gửi. Vui lòng chờ admin xác thực.",
            "user": serializer.data
        }, status=status.HTTP_200_OK)

    @action(methods=['post'], url_path='verify', detail=True, permission_classes=[perms.IsAdminOrReadOnly])
    def verify_organizer(self, request, pk=None):
        """
        Admin xác thực cho nhà tổ chức.
        """
        user = self.get_object()
        if not user.is_organizer:
            return Response({"detail": "Người dùng không phải nhà tổ chức."}, status=status.HTTP_400_BAD_REQUEST)
        if user.is_verified:
            return Response({"detail": "Nhà tổ chức đã được xác thực."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_verified = True
        user.save()
        return Response({"detail": "Nhà tổ chức đã được xác thực."})


class CategoryViewSet(viewsets.ViewSet, generics.ListAPIView):
    """
    ViewSet cho danh mục sự kiện.
    """
    queryset = Category.objects.all()
    serializer_class = serializers.CategorySerializer
    permission_classes = [perms.IsAdminOrReadOnly]


class EventViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Event.objects.all()
    serializer_class = serializers.EventSerializer
    parser_classes = [parsers.MultiPartParser]
    permission_classes = [perms.IsVerifiedOrganizer | perms.IsAdminOrReadOnly]

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [perms.OwnerPerms()]
        return super().get_permissions()

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return Event.objects.all()
            return Event.objects.filter(organizer=self.request.user)
        return Event.objects.filter(status='approved')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='approve_event', permission_classes=[perms.IsAdminOrReadOnly])
    def approve_event(self, request, pk=None):
        event = self.get_object()
        if event.status == 'approved':
            return Response({"detail": "Sự kiện đã được duyệt."}, status=status.HTTP_400_BAD_REQUEST)
        event.status = 'approved'
        event.save()
        return Response({"detail": "Sự kiện đã được duyệt."})

    @action(detail=True, methods=['post'], url_path='reject_event', permission_classes=[perms.IsAdminOrReadOnly])
    def reject_event(self, request, pk=None):
        event = self.get_object()
        if event.status == 'rejected':
            return Response({"detail": "Sự kiện đã bị từ chối."}, status=status.HTTP_400_BAD_REQUEST)
        event.status = 'rejected'
        event.save()
        return Response({"detail": "Sự kiện đã bị từ chối."})

    @action(detail=False, methods=['get'], url_path='search', permission_classes=[permissions.AllowAny])
    def search(self, request):
        """
        Tìm kiếm sự kiện theo:
        - keyword (tên / mô tả),
        - category (id),
        - location,
        - start_date (ngày bắt đầu tìm kiếm),
        - end_date (ngày kết thúc tìm kiếm)
        """
        keyword = request.query_params.get('keyword')
        category_id = request.query_params.get('category')
        location = request.query_params.get('location')
        start_date = request.query_params.get('start_date')  # YYYY-MM-DD
        end_date = request.query_params.get('end_date')  # YYYY-MM-DD

        # Chỉ tìm kiếm sự kiện đã được duyệt
        events = Event.objects.filter(status='approved')

        if keyword:
            events = events.filter(
                Q(name__icontains=keyword) |
                Q(description__icontains=keyword)
            )
        if category_id:
            events = events.filter(category_id=category_id)
        if location:
            events = events.filter(location__icontains=location)

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                events = events.filter(end_time__gte=start_dt)
            except ValueError:
                return Response({'error': 'start_date không đúng định dạng YYYY-MM-DD'}, status=400)

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                events = events.filter(start_time__lte=end_dt)
            except ValueError:
                return Response({'error': 'end_date không đúng định dạng YYYY-MM-DD'}, status=400)

        serializer = self.serializer_class(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class EventTicketViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    """
    ViewSet cho các API liên quan đến vé của một sự kiện cụ thể (cần event_id).
    """
    queryset = Ticket.objects.all()
    serializer_class = serializers.TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """
        API Đặt vé: /events/{event_id}/tickets/
        """
        event_id = self.kwargs.get('event_id')
        if not event_id:
            return Response({"detail": "Thiếu event_id trong URL."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event = Event.objects.get(id=event_id, status='approved')
        except Event.DoesNotExist:
            return Response({"detail": "Sự kiện không tồn tại hoặc chưa được duyệt."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = serializer.save(
                user=request.user,
                event=event,
                expires_at=timezone.now() + timedelta(minutes=30)
            )
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            return Response({"detail": f"Lỗi khi tạo vé: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TicketViewSet(viewsets.GenericViewSet):
    """
    ViewSet cho các API liên quan đến vé nói chung
    """
    queryset = Ticket.objects.all()
    serializer_class = serializers.TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(methods=['post'], url_path='validate', detail=True, permission_classes=[perms.IsVerifiedOrganizer])
    def validate_ticket(self, request, pk=None):
        """
        API Xác nhận mã QR: /tickets/{ticket_id}/validate/
        Cho phép nhà tổ chức quét mã QR để xác nhận người tham gia tại sự kiện.
        """
        try:
            ticket = self.get_object()
        except Ticket.DoesNotExist:
            return Response({"detail": "Vé không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        qr_code = request.data.get('qr_code')
        if not qr_code:
            return Response({"detail": "Mã QR không được cung cấp."}, status=status.HTTP_400_BAD_REQUEST)

        if ticket.qr_code != qr_code:
            return Response({"status": "invalid", "detail": "Mã QR không hợp lệ."}, status=status.HTTP_400_BAD_REQUEST)
        if ticket.status != 'booked':
            return Response({"status": "invalid", "detail": "Vé không ở trạng thái hợp lệ."}, status=status.HTTP_400_BAD_REQUEST)
        if ticket.expires_at < timezone.now():
            return Response({"status": "invalid", "detail": "Vé đã hết hạn."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "ticket_id": ticket.id,
            "event_id": ticket.event.id,
            "participant_id": ticket.user.id,
            "status": "valid",
            "message": "Xác nhận vé thành công."
        }, status=status.HTTP_200_OK)

    @action(methods=['get'], url_path='history', detail=False, permission_classes=[permissions.IsAuthenticated])
    def ticket_history(self, request):
        """
        API Xem lịch sử đặt vé: /tickets/history/
        Cho phép người tham gia xem danh sách các vé đã đặt.
        """
        tickets = Ticket.objects.filter(user=request.user).order_by('-created_date')
        serializer = self.get_serializer(tickets, many=True)
        return Response({
            "message": "Lịch sử đặt vé được trả về thành công.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(methods=['post'], url_path='cancel', detail=True, permission_classes=[permissions.IsAuthenticated])
    def cancel_ticket(self, request, pk=None):
        """
        API Hủy vé: /tickets/{ticket_id}/cancel/
        Cho phép người tham gia hủy vé nếu vé ở trạng thái chờ.
        """
        try:
            ticket = self.get_object()
        except Ticket.DoesNotExist:
            return Response({"detail": "Vé không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.user != request.user:
            return Response({"detail": "Bạn không có quyền hủy vé này."}, status=status.HTTP_403_FORBIDDEN)

        if ticket.status == 'cancelled':
            return Response({"detail": "Vé đã bị hủy trước đó."}, status=status.HTTP_400_BAD_REQUEST)

        if ticket.status != 'pending':
            return Response({"detail": "Chỉ có thể hủy vé ở trạng thái chờ."}, status=status.HTTP_400_BAD_REQUEST)

        ticket.status = 'cancelled'
        ticket.save()

        try:
            payment = Payment.objects.get(ticket=ticket)
            payment.status = 'failed'
            payment.save()
        except Payment.DoesNotExist:
            pass

        return Response({"detail": "Vé đã được hủy thành công."}, status=status.HTTP_200_OK)

class PaymentViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    queryset = Payment.objects.all()
    serializer_class = serializers.PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        ticket_id = request.data.get('ticket_id')
        if not ticket_id:
            return Response({"detail": "Thiếu ticket_id"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ticket = Ticket.objects.get(id=ticket_id, user=request.user, status='pending')
        except Ticket.DoesNotExist:
            return Response({"detail": "Vé không tồn tại hoặc không ở trạng thái chờ."},
                            status=status.HTTP_404_NOT_FOUND)
        if Payment.objects.filter(ticket_id=ticket_id, status='pending').exists():
            return Response({"detail": "Đã tồn tại thanh toán đang chờ cho vé này."},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        total_price = ticket.quantity * (
            ticket.event.ticket_price_regular if ticket.ticket_type == 'regular' else ticket.event.ticket_price_vip)
        payment = serializer.save(
            ticket=ticket,
            amount=total_price,
            status='pending'
        )
        if payment.method == 'vnpay':
            payment_url = self.create_vnpay_payment_url(payment, request)
            payment.payment_url = payment_url
            payment.save()
        return Response({
            "payment_url": payment.payment_url,
            "ticket_id": ticket.id,
            "status": payment.status
        }, status=status.HTTP_201_CREATED)

    def create_vnpay_payment_url(self, payment, request):
        vnp = vnpay()
        vnp.requestData['vnp_Version'] = '2.1.0'
        vnp.requestData['vnp_Command'] = 'pay'
        vnp.requestData['vnp_TmnCode'] = settings.VNPAY_TMN_CODE
        vnp.requestData['vnp_Amount'] = int(payment.amount * 100)  # VNPay requires amount in VND * 100
        vnp.requestData['vnp_CurrCode'] = 'VND'
        vnp.requestData['vnp_TxnRef'] = f"{payment.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        vnp.requestData['vnp_OrderInfo'] = f"Thanh toan ve {payment.ticket.event.name}"
        vnp.requestData['vnp_OrderType'] = 'billpayment'
        vnp.requestData['vnp_Locale'] = 'vn'
        vnp.requestData['vnp_CreateDate'] = datetime.now().strftime('%Y%m%d%H%M%S')
        vnp.requestData['vnp_IpAddr'] = get_client_ip(request)
        vnp.requestData['vnp_ReturnUrl'] = settings.VNPAY_RETURN_URL
        payment_url = vnp.get_payment_url(settings.VNPAY_PAYMENT_URL, settings.VNPAY_HASH_SECRET_KEY)
        return payment_url

    @action(methods=['get'], url_path='return', detail=False, permission_classes=[permissions.AllowAny])
    def payment_return(self, request):
        input_data = request.query_params
        if not input_data:
            return Response({"detail": "Không có dữ liệu trả về"}, status=status.HTTP_400_BAD_REQUEST)
        vnp = vnpay()
        vnp.responseData = input_data.dict()
        payment_id = input_data.get('vnp_TxnRef', '').split('_')[0]
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Thanh toán không tồn tại."}, status=status.HTTP_404_NOT_FOUND)
        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            response_code = input_data.get('vnp_ResponseCode')
            if response_code == '00':
                payment.status = 'completed'
                payment.ticket.status = 'booked'
                payment.ticket.save()
                payment.save()
                return Response({
                    "detail": "Thanh toán thành công.",
                    "payment_id": payment.id,
                    "ticket_id": payment.ticket.id
                }, status=status.HTTP_200_OK)
            else:
                payment.status = 'failed'
                payment.save()
                return Response({
                    "detail": f"Thanh toán thất bại. Mã lỗi: {response_code}"
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            payment.status = 'failed'
            payment.save()
            return Response({
                "detail": "Sai chữ ký. Thanh toán không hợp lệ."
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get', 'post'], url_path='ipn', detail=False, permission_classes=[permissions.AllowAny])
    def payment_ipn(self, request):
        input_data = request.GET
        if not input_data:
            return JsonResponse({'RspCode': '99', 'Message': 'Invalid request'})
        vnp = vnpay()
        vnp.responseData = input_data.dict()
        payment_id = input_data.get('vnp_TxnRef', '').split('_')[0]
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            return JsonResponse({'RspCode': '01', 'Message': 'Order not found'})
        if payment.status == 'completed':
            return JsonResponse({'RspCode': '02', 'Message': 'Order Already Updated'})
        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            response_code = input_data.get('vnp_ResponseCode')
            if response_code == '00':
                payment.status = 'completed'
                payment.ticket.status = 'booked'
                payment.ticket.save()
                payment.save()
                return JsonResponse({'RspCode': '00', 'Message': 'Confirm Success'})
            else:
                payment.status = 'failed'
                payment.save()
                return JsonResponse({'RspCode': '00', 'Message': 'Confirm Success'})
        else:
            return JsonResponse({'RspCode': '97', 'Message': 'Invalid Signature'})