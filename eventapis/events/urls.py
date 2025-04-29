from django.urls import path, include
from rest_framework.routers import DefaultRouter
from events.views import UserViewSet, CategoryViewSet, EventViewSet, OrganizerViewSet

from . import tests

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'events', EventViewSet, basename='event')
router.register(r'organizers', OrganizerViewSet, basename='organizer')

urlpatterns = [
    path('', include(router.urls)),

    path('home/', tests.home, name='home'),
    path('home/logout/', tests.logout_tests, name='logout'),
]
