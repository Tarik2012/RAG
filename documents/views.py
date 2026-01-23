import json

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import Document
from .forms import DocumentUploadForm

from documents.services.document_processor import process_document
from documents.services.ask.ask_service import AskService
from documents.services.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.retriever import Retriever
from documents.services.llm.openai_llm_provider import OpenAILLMProvider


def _build_ask_service() -> AskService:
    embedding_provider = OpenAIEmbeddingProvider()
    llm_provider = OpenAILLMProvider()
    query_rewriter = QueryRewriter()
    retriever = Retriever(
        embedding_provider,
        query_rewriter=query_rewriter,
    )

    return AskService(
        retriever=retriever,
        llm_provider=llm_provider,
    )


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
        {"documents": documents},
    )


@login_required
def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            doc = form.save(commit=False)
            uploaded_file = request.FILES["file"]

            doc.owner = request.user
            doc.content_type = uploaded_file.content_type or ""
            doc.size = uploaded_file.size

            doc.save()

            # Ingesta RAG (sync por ahora)
            process_document(doc)

            return redirect("documents:list")
    else:
        form = DocumentUploadForm()

    return render(
        request,
        "documents/document_upload.html",
        {"form": form},
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


@csrf_exempt
@require_POST
def ask_view(request):
    """
    Endpoint para hacer preguntas al sistema RAG.
    """

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    question = payload.get("question")
    if not question:
        return JsonResponse({"error": "Missing 'question'"}, status=400)

    # Wiring del RAG
    ask_service = _build_ask_service()

    result = ask_service.ask(question=question, top_k=6)

    return JsonResponse(result, status=200)

@login_required
def ask_page(request):
    if request.GET.get("clear") == "1":
        request.session.pop("chat_history", None)
        return redirect("documents:ask_ui")

    if request.method == "POST":
        if request.POST.get("clear") == "1":
            request.session.pop("chat_history", None)
            return redirect("documents:ask_ui")

        question = request.POST.get("question", "").strip()

        if question:
            ask_service = _build_ask_service()

            result = ask_service.ask(question=question, top_k=6)

            # Guardamos la respuesta en sesión (temporal)
            history = request.session.get("chat_history", [])
            if not isinstance(history, list):
                history = []

            history.append(
                {
                    "question": question,
                    "answer": result.get("answer"),
                    "chunks_used": result.get("chunks_used"),
                }
            )
            request.session["chat_history"] = history

        return redirect("documents:ask_ui")

    # GET
    history = request.session.get("chat_history", [])
    if not isinstance(history, list):
        history = []

    return render(
        request,
        "documents/ask.html",
        {
            "history": history,
            "question": "",
        },
    )
