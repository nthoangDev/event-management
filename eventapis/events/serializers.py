from rest_framework import serializers
from events.models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer cho model User.
    Xử lý tạo và cập nhật mật khẩu đúng cách, và hiển thị link avatar nếu có.
    """

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'password', 'avatar']
        extra_kwargs = {
            'password': {'write_only': True}  # password chỉ cho phép ghi, không đọc
        }

    def create(self, validated_data):
        """
        Khi tạo người dùng mới, xử lý mã hóa mật khẩu.
        """
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        """
        Khi cập nhật người dùng, nếu có mật khẩu thì phải mã hóa lại.
        """
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        """
        Hiển thị avatar dưới dạng URL nếu có.
        """
        d = super().to_representation(instance)
        d['avatar'] = instance.avatar.url if instance.avatar else ''
        return d
