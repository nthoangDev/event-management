from django.contrib.auth import authenticate
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from events.models import User, Category, Event
from events import serializers, perms
from rest_framework import viewsets, generics, parsers, permissions
from oauth2_provider.models import AccessToken, Application
from oauth2_provider.settings import oauth2_settings
from datetime import datetime
from django.utils import timezone

class UserViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.UpdateAPIView):
    """
    ViewSet cho người dùng: đăng ký, cập nhật, đăng nhập, đăng xuất, lấy thông tin hiện tại,
    yêu cầu trở thành nhà tổ chức, và xác thực nhà tổ chức.
    """
    queryset = User.objects.filter(is_active=True)
    serializer_class = serializers.UserSerializer
    parser_classes = [parsers.MultiPartParser]

    def get_permissions(self):
        """
        Gán quyền tùy theo method:
        - PUT/PATCH: chỉ cho chủ sở hữu sửa
        - Còn lại: cho phép tất cả (ví dụ: đăng ký, đăng nhập)
        """
        if self.request.method in ['PUT', 'PATCH']:
            return [perms.OwnerPerms()]
        return [permissions.AllowAny()]

    @action(methods=['get'], url_path='current-user', detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_current_user(self, request):
        """
        Trả về thông tin người dùng hiện tại nếu đã đăng nhập.
        """
        return Response(serializers.UserSerializer(request.user).data)

    @action(methods=['post'], url_path='login', detail=False, permission_classes=[permissions.AllowAny])
    def login_user(self, request):
        """
        Đăng nhập người dùng với username và password.
        Trả về OAuth2 access token và thông tin người dùng.
        """
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)

        if user:
            # Tạo hoặc lấy ứng dụng OAuth2
            app, _ = Application.objects.get_or_create(
                user=user,
                client_type=Application.CLIENT_CONFIDENTIAL,
                authorization_grant_type=Application.GRANT_PASSWORD,
                defaults={'name': f'{user.username}_app'}
            )
            # Tạo access token
            token = AccessToken.objects.create(
                user=user,
                application=app,
                expires=timezone.now() + oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
                token=AccessToken.objects.generate_token(),
                scope='read write'
            )
            return Response({
                'access_token': token.token,
                'expires_in': oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
                'user': serializers.UserSerializer(user).data
            })
        return Response({'error': 'Thông tin đăng nhập không hợp lệ'}, status=status.HTTP_401_UNAUTHORIZED)

    @action(methods=['post'], url_path='logout', detail=False, permission_classes=[permissions.IsAuthenticated])
    def logout_user(self, request):
        """
        Đăng xuất: xóa OAuth2 access token của người dùng.
        """
        AccessToken.objects.filter(user=request.user, token=request.auth).delete()
        return Response({'message': 'Đăng xuất thành công'}, status=status.HTTP_200_OK)

    @action(methods=['post'], url_path='request-organizer', detail=True, permission_classes=[permissions.IsAuthenticated])
    def request_organizer(self, request, pk=None):
        """
        Người dùng yêu cầu trở thành nhà tổ chức.
        """
        user = self.get_object()
        if user.is_organizer:
            return Response({"detail": "Bạn đã là nhà tổ chức."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_organizer = True
        user.save()
        return Response({"detail": "Yêu cầu đã được gửi. Vui lòng chờ admin xác thực."})

class OrganizerViewSet(viewsets.ViewSet):
    """
    ViewSet cho các hành động liên quan đến nhà tổ chức, như xác thực.
    """
    queryset = User.objects.filter(is_active=True, is_organizer=True)
    serializer_class = serializers.UserSerializer

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

class EventViewSet(viewsets.ViewSet):
    """
    ViewSet cho sự kiện: tạo, liệt kê, cập nhật, xóa.
    Chỉ nhà tổ chức đã xác thực hoặc admin có thể tạo.
    """
    queryset = Event.objects.all()
    serializer_class = serializers.EventSerializer
    parser_classes = [parsers.MultiPartParser]
    permission_classes = [perms.IsVerifiedOrganizer | perms.IsAdminOrReadOnly]

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [perms.OwnerPerms()]
        return super().get_permissions()

    def get_queryset(self):
        """
        - Admin: thấy tất cả sự kiện.
        - Nhà tổ chức: thấy sự kiện của mình.
        - Người dùng chưa xác thực: thấy tất cả sự kiện công khai
        """
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return Event.objects.all()
            return Event.objects.filter(organizer=self.request.user)
        return Event.objects.filter(status='approved')

    @action(detail=True, methods=['post'], url_path='approve_event', permission_classes=[perms.IsAdminOrReadOnly])
    def approve_event(self, request, pk=None):
        """
        Admin duyệt sự kiện.
        """
        event = self.get_object()
        if event.status == 'approved':
            return Response({"detail": "Sự kiện đã được duyệt."}, status=status.HTTP_400_BAD_REQUEST)
        event.status = 'approved'
        event.save()
        return Response({"detail": "Sự kiện đã được duyệt."})

    @action(detail=True, methods=['post'],  url_path='reject_event', permission_classes=[perms.IsAdminOrReadOnly])
    def reject_event(self, request, pk=None):
        """
        Admin từ chối sự kiện.
        """
        event = self.get_object()
        if event.status == 'rejected':
            return Response({"detail": "Sự kiện đã bị từ chối."}, status=status.HTTP_400_BAD_REQUEST)
        event.status = 'rejected'
        event.save()
        return Response({"detail": "Sự kiện đã bị từ chối."})