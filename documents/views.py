from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .models import Document
from .forms import DocumentUploadForm
from documents.services.document_processor import process_document


@login_required
def document_list(request):
    documents = (
        Document.objects
        .filter(owner=request.user)
        .order_by("-created_at")
    )
    return render(
        request,
        "documents/document_list.html",
        {"documents": documents}
    )


@login_required
def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            doc = form.save(commit=False)
            uploaded_file = request.FILES["file"]

            # 🔐 Propietario
            doc.owner = request.user

            # 📄 Metadatos
            doc.content_type = uploaded_file.content_type or ""
            doc.size = uploaded_file.size
            doc.status = "processing"

            doc.save()

            try:
                # 🔥 INGESTIÓN RAG (sync por ahora)
                chunks_created = process_document(doc)

                doc.status = "processed" if chunks_created > 0 else "failed"
                doc.save(update_fields=["status"])

            except Exception:
                # ⚠️ Falla controlada
                doc.status = "failed"
                doc.save(update_fields=["status"])
                raise  # en dev queremos ver el error

            return redirect("documents:list")

    else:
        form = DocumentUploadForm()

    return render(
        request,
        "documents/document_upload.html",
        {"form": form}
    )


@login_required
@require_POST
def document_delete(request, pk):
    document = get_object_or_404(
        Document,
        pk=pk,
        owner=request.user,
    )

    document.file.delete(save=False)
    document.delete()

    return redirect("documents:list")
