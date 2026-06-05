from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from summarizer import views as summarizer_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('summarizer.urls')),
    path('auth/password_reset/', summarizer_views.forgot_password_request, name='password_reset'),
    path('auth/', include('django.contrib.auth.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
