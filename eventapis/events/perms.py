from rest_framework import permissions
from events.models import User

class OwnerPerms(permissions.IsAuthenticated):
    """
    Kiểm tra người dùng có phải là chủ sở hữu của object.
    - Đối với User: request.user == obj
    - Đối với Event: request.user == obj.organizer
    """
    def has_object_permission(self, request, view, obj):
        if not super().has_object_permission(request, view, obj):
            return False
        if hasattr(obj, 'organizer'):
            return request.user == obj.organizer
        return request.user == obj

class IsVerifiedOrganizer(permissions.BasePermission):
    """
    Chỉ nhà tổ chức đã được xác thực (is_organizer=True, is_verified=True) mới có quyền.
    """
    def has_permission(self, request, view):
        return (request.user.is_authenticated and
                request.user.is_organizer and
                request.user.is_verified)

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Cho phép admin chỉnh sửa, người khác chỉ đọc.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff