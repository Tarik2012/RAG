from django.urls import path
from .views import (
    document_list,
    project_list,
    project_detail,
    project_delete,
    conversation_create,
    conversation_open,
    conversation_delete,
    document_status,
    document_upload,
    repo_ingest,
    repo_delete,
    document_delete,
    documentation_view,
    document_content_view,
    generate_documentation_trigger,
    agent_view,
    ask_page,
)

app_name = "documents"

urlpatterns = [
    path("", document_list, name="list"),
    path("projects/", project_list, name="project_list"),
    path("projects/<int:project_id>/", project_detail, name="project_detail"),
    path("projects/<int:project_id>/delete/", project_delete, name="project_delete"),
    path("projects/<int:project_id>/conversations/new/", conversation_create, name="conversation_create"),
    path("conversations/<int:conversation_id>/open/", conversation_open, name="conversation_open"),
    path("conversations/<int:conversation_id>/delete/", conversation_delete, name="conversation_delete"),
    path("status/", document_status, name="status"),
    path("upload/", document_upload, name="upload"),
    path("repos/ingest/", repo_ingest, name="repo_ingest"),
    path("projects/<int:project_id>/repos/delete/", repo_delete, name="repo_delete"),
    path("delete/<int:pk>/", document_delete, name="delete"),

    path("agent/", agent_view, name="agent"),

    # UI (interfaz humana)
    path("ask/ui/", ask_page, name="ask_ui"),
    path("documentation/<int:pk>/", documentation_view, name="documentation"),
    path("documents/<int:pk>/view/", document_content_view, name="document_content"),
    path("documentation/<int:pk>/generate/", generate_documentation_trigger, name="documentation_generate"),
]
