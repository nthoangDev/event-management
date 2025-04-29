from rest_framework import serializers
from events.models import User, Category, Event
from django.utils import timezone

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer cho model User.
    Xử lý tạo và cập nhật mật khẩu đúng cách, và hiển thị link avatar nếu có.
    """
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'password', 'avatar', 'is_organizer', 'is_verified']
        extra_kwargs = {
            'password': {'write_only': True},
            'is_verified': {'read_only': True}  # Chỉ admin có thể sửa is_verified
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        d = super().to_representation(instance)
        d['avatar'] = instance.avatar.url if instance.avatar else ''
        return d

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']

class EventSerializer(serializers.ModelSerializer):
    organizer = UserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True
    )
    image = serializers.ImageField(allow_null=True, required=False)
    video = serializers.FileField(allow_null=True, required=False)

    class Meta:
        model = Event
        fields = [
            'id', 'organizer', 'category', 'category_id', 'name', 'description',
            'event_time', 'location', 'ticket_price', 'image', 'video',
            'status', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'status': {'read_only': True},  # Chỉ admin có thể sửa status
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True}
        }

    def validate(self, data):
        """
        Kiểm tra thời gian sự kiện phải ở tương lai.
        """
        if data.get('event_time') and data['event_time'] <= timezone.now():
            raise serializers.ValidationError({"event_time": "Thời gian sự kiện phải ở tương lai."})
        return data

    def create(self, validated_data):
        """
        Tự động gán organizer là user hiện tại.
        """
        validated_data['organizer'] = self.context['request'].user
        return super().create(validated_data)

    def to_representation(self, instance):
        """
        Hiển thị URL cho image và video nếu có.
        """
        d = super().to_representation(instance)
        d['image'] = instance.image.url if instance.image else ''
        d['video'] = instance.video.url if instance.video else ''
        return d