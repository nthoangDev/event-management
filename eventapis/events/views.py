from django.contrib.auth import authenticate, login, logout
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from events.models import User
from events import serializers, perms
from rest_framework import viewsets, generics, parsers, permissions


class UserViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.UpdateAPIView):
    """
    ViewSet cho người dùng bao gồm các chức năng: đăng ký, cập nhật, đăng nhập, đăng xuất, và lấy thông tin hiện tại.
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
        API trả về thông tin người dùng hiện tại nếu đã đăng nhập.
        """
        return Response(serializers.UserSerializer(request.user).data)

    @action(methods=['post'], url_path='login', detail=False, permission_classes=[permissions.AllowAny])
    def login_user(self, request):
        """
        API đăng nhập người dùng với username và password.
        Nếu đúng sẽ trả về thông tin người dùng, sai trả lỗi.
        """
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)

        if user:
            login(request, user)  # lưu thông tin đăng nhập vào session
            return Response(serializers.UserSerializer(user).data)
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    @action(methods=['post'], url_path='logout', detail=False, permission_classes=[permissions.IsAuthenticated])
    def logout_user(self, request):
        """
        API đăng xuất người dùng hiện tại (xóa session).
        """
        logout(request)
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
