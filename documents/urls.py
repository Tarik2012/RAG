from django.urls import path
from .views import document_list, document_upload, document_delete

app_name = "documents"   

urlpatterns = [
    path("", document_list, name="list"),
    path("upload/", document_upload, name="upload"),
    path("delete/<int:pk>/", document_delete, name="delete"),
]
