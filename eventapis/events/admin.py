from django.contrib import admin
from django.db.models import Count, Sum, Avg
from django.db.models.functions import TruncMonth, TruncQuarter,ExtractQuarter
from django.template.response import TemplateResponse
from django import forms
from django.urls import path
from django.utils.html import mark_safe
from ckeditor_uploader.widgets import CKEditorUploadingWidget
from .models import User, OrganizerRequest, Category, Event, EventTag, Ticket, Payment, Like, Interest, Review, Notification
from django.db.models import Q
from datetime import datetime
from django.utils import timezone


# Custom Admin Site
class MyAdminSite(admin.AdminSite):
    site_header = 'Quản lý sự kiện trực tuyến'

    def get_urls(self):
        return [
            path('event-stats/', self.event_stats_view, name='event-stats'),
            path('organizer-stats/', self.organizer_stats_view, name='organizer-stats'),
            path('admin-stats/', self.admin_stats_view, name='admin-stats'),
        ] + super().get_urls()

    def event_stats_view(self, request):
        if not request.user.is_organizer:
            return TemplateResponse(request, 'admin/error.html', {
                'message': 'Bạn cần có quyền quản trị viên để xem báo cáo này.'
            })

        stats = Event.objects.annotate(ticket_count=Count('ticket__id')).values('id', 'name', 'ticket_count')
        return TemplateResponse(request, 'admin/event_stats.html', {
            'stats': stats
        })

    def organizer_stats_view(self, request):
        if not request.user.is_organizer:
            return TemplateResponse(request, 'admin/error.html', {
                'message': 'Bạn cần có quyền nhà tổ chức để xem báo cáo này.'
            })

        # Lấy danh sách sự kiện của nhà tổ chức
        events = Event.objects.filter(organizer=request.user, active=True)

        # Thống kê vé đã bán và giá vé của sự kiện
        ticket_stats = events.annotate(
            total_tickets=Count('ticket__id', filter=Q(ticket__status='booked'))
        ).values('id', 'name', 'total_tickets', 'ticket_price')

        # Tính total_revenue trong Python
        for stat in ticket_stats:
            stat['total_revenue'] = stat['total_tickets'] * stat['ticket_price'] if stat['total_tickets'] and stat['ticket_price'] else 0

        # Thống kê phản hồi
        review_stats = Review.objects.filter(event__organizer=request.user).values(
            'event__name', 'rating', 'comment'
        ).annotate(avg_rating=Avg('rating'))

        return TemplateResponse(request, 'admin/organizer_stats.html', {
            'ticket_stats': ticket_stats,
            'review_stats': review_stats,
        })

    def admin_stats_view(self, request):
        if not request.user.is_superuser:
            return TemplateResponse(request, 'admin/error.html', {
                'message': 'Bạn cần có quyền quản trị viên để xem báo cáo này.'
            })

        monthly_events = Event.objects.annotate(
            month=TruncMonth('event_time')
        ).values('month').annotate(
            event_count=Count('id')
        ).order_by('month')

        quarterly_events = Event.objects.annotate(
            quarter=TruncQuarter('event_time'),
            quarter_number=ExtractQuarter('event_time')
        ).values('quarter', 'quarter_number').annotate(
            event_count=Count('id')
        ).order_by('quarter')

        monthly_attendees = Ticket.objects.filter(status='booked').annotate(
            month=TruncMonth('event__event_time')
        ).values('month').annotate(
            attendee_count=Count('id')
        ).order_by('month')

        quarterly_attendees = Ticket.objects.filter(status='booked').annotate(
            quarter=TruncQuarter('event__event_time'),
            quarter_number=ExtractQuarter('event__event_time')
        ).values('quarter', 'quarter_number').annotate(
            attendee_count=Count('id')
        ).order_by('quarter')

        return TemplateResponse(request, 'admin/admin_stats.html', {
            'monthly_events': monthly_events,
            'quarterly_events': quarterly_events,
            'monthly_attendees': monthly_attendees,
            'quarterly_attendees': quarterly_attendees,
        })

admin_site = MyAdminSite(name='admin')


# Form for Event to use CKEditor for description
class EventForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorUploadingWidget, required=False)

    class Meta:
        model = Event
        fields = '__all__'


# Custom Admin for User
class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'email', 'is_organizer', 'balance', 'is_active']
    search_fields = ['username', 'email']
    list_filter = ['is_organizer', 'is_active']
    readonly_fields = ['avatar_view']

    def avatar_view(self, obj):
        if obj.avatar:
            return mark_safe(f'<img src="{obj.avatar.url}" width="120" />')
        return "No avatar"

    avatar_view.short_description = 'Avatar'


# Custom Admin for OrganizerRequest
class OrganizerRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'created_at']
    search_fields = ['user__username', 'info']
    list_filter = ['status', 'created_at']


# Custom Admin for Category
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'active']
    search_fields = ['name']
    list_filter = ['active']


# Custom Admin for Event
class EventAdmin(admin.ModelAdmin):
    form = EventForm
    list_display = ['id', 'name', 'organizer', 'event_time', 'status', 'category', 'active']
    search_fields = ['name', 'description', 'location']
    list_filter = ['status', 'category', 'event_time', 'active']
    readonly_fields = ['image_view']

    def image_view(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="120" />')
        return "No image"

    image_view.short_description = 'Image'


# Custom Admin for EventTag
class EventTagAdmin(admin.ModelAdmin):
    list_display = ['id', 'tag', 'event', 'active']
    search_fields = ['tag', 'event__name']
    list_filter = ['active']


# Custom Admin for Ticket
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'event', 'user', 'ticket_type', 'status', 'expires_at']
    search_fields = ['event__name', 'user__username', 'qr_code']
    list_filter = ['ticket_type', 'status', 'expires_at']


# Custom Admin for Payment
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'method', 'amount', 'status', 'created_date']
    search_fields = ['ticket__qr_code']
    list_filter = ['method', 'status', 'created_date']


# Custom Admin for Like
class LikeAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'event', 'created_date']
    search_fields = ['user__username', 'event__name']
    list_filter = ['created_date']


# Custom Admin for Interest
class InterestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'event', 'created_date']
    search_fields = ['user__username', 'event__name']
    list_filter = ['created_date']


# Custom Admin for Review
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'event', 'user', 'rating', 'created_date']
    search_fields = ['event__name', 'user__username', 'comment']
    list_filter = ['rating', 'created_date']


# Custom Admin for Notification
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'message_preview', 'is_read', 'created_date']
    search_fields = ['user__username', 'message']
    list_filter = ['is_read', 'created_date']

    def message_preview(self, obj):
        return obj.message[:50] + ('...' if len(obj.message) > 50 else '')

    message_preview.short_description = 'Message'


# Register models with admin site
admin_site.register(User, UserAdmin)
admin_site.register(OrganizerRequest, OrganizerRequestAdmin)
admin_site.register(Category, CategoryAdmin)
admin_site.register(Event, EventAdmin)
admin_site.register(EventTag, EventTagAdmin)
admin_site.register(Ticket, TicketAdmin)
admin_site.register(Payment, PaymentAdmin)
admin_site.register(Like, LikeAdmin)
admin_site.register(Interest, InterestAdmin)
admin_site.register(Review, ReviewAdmin)
admin_site.register(Notification, NotificationAdmin)