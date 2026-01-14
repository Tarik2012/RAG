from django.urls import path
from .views import (
    document_list,
    document_upload,
    document_delete,
    ask_view,
    ask_page,
)

app_name = "documents"

urlpatterns = [
    path("", document_list, name="list"),
    path("upload/", document_upload, name="upload"),
    path("delete/<int:pk>/", document_delete, name="delete"),

    # API (RAG)
    path("ask/", ask_view, name="ask"),

    # UI (interfaz humana)
    path("ask/ui/", ask_page, name="ask_ui"),
]
