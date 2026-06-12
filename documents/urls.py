from django.urls import path
from .views import (
    document_list,
    document_status,
    document_upload,
    document_delete,
    documentation_view,
    generate_documentation_trigger,
    agent_view,
    ask_view,
    ask_page,
)

app_name = "documents"

urlpatterns = [
    path("", document_list, name="list"),
    path("status/", document_status, name="status"),
    path("upload/", document_upload, name="upload"),
    path("delete/<int:pk>/", document_delete, name="delete"),

    # API (RAG)
    path("ask/", ask_view, name="ask"),
    path("agent/", agent_view, name="agent"),

    # UI (interfaz humana)
    path("ask/ui/", ask_page, name="ask_ui"),
    path("documentation/<int:pk>/", documentation_view, name="documentation"),
    path("documentation/<int:pk>/generate/", generate_documentation_trigger, name="documentation_generate"),
]
