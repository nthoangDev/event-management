from django.contrib.auth import authenticate
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, mixins
from events.models import User, Category, Event, Ticket, Payment
from events import serializers, perms
from rest_framework import viewsets, generics, parsers, permissions
from oauth2_provider.models import AccessToken, Application
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
from oauth2_provider.models import AccessToken, Application, RefreshToken
from events.serializers import UserSerializer
import secrets
from django.db.models import Q
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings

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

