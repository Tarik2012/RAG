from django.shortcuts import render
from documents.models import Document, DocumentChunk


def home(request):
    context = {}
    if request.user.is_authenticated:
        docs = Document.objects.filter(owner=request.user)
        context = {
            "total_documents": docs.count(),
            "processed_documents": docs.filter(status="processed").count(),
            "total_chunks": DocumentChunk.objects.filter(document__owner=request.user).count(),
        }
    return render(request, "core/home.html", context)
