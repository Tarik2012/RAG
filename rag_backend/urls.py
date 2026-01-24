from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Django Auth (login, logout, password views)
    path("accounts/", include("django.contrib.auth.urls")),

    # Core (home, landing)
    path("", include("core.urls")),

    # Documents (upload, list, ask)
    path("documents/", include("documents.urls")),
]

# Media (local only)
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
