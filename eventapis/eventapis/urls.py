
from django.contrib import admin
from django.urls import path, include, re_path
from events.admin import admin_site
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Event APIs",
        default_version='v1',
        description="APIs for EventApp",
        contact=openapi.Contact(email="2251050061quan@ou.edu.vn"),
        license=openapi.License(name="Dương Hữu Thành@2025"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path('', include('events.urls')),
    path('admin/', admin_site.urls),
    re_path(r'^ckeditor/', include('ckeditor_uploader.urls')),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$',
            schema_view.without_ui(cache_timeout=0),
            name='schema-json'),
    re_path(r'^swagger/$',
            schema_view.with_ui('swagger', cache_timeout=0),
            name='schema-swagger-ui'),
    re_path(r'^redoc/$',
            schema_view.with_ui('redoc', cache_timeout=0),
            name='schema-redoc'),

    path('o/', include('oauth2_provider.urls',
                       namespace='oauth2_provider')),

]
