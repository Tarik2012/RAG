import logging
import json
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .forms import DocumentUploadForm
from .models import Document
from documents.services.agent.agent import build_agent
from documents.services.ask.ask_service import AskService
from documents.services.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider
from documents.services.llm.openai_llm_provider import OpenAILLMProvider
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever
from documents.tasks import process_document_task

logger = logging.getLogger(__name__)
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".cs", ".cpp", ".go", ".rb",
    ".php", ".swift", ".kt", ".html", ".htm", ".css",
    ".json", ".xml", ".yaml", ".yml", ".md", ".txt", ".rst",
}


def _build_ask_service() -> AskService:
    embedding_provider = OpenAIEmbeddingProvider()
    llm_provider = OpenAILLMProvider()
    query_rewriter = QueryRewriter()
    reranker = CrossEncoderReranker()

    retriever = Retriever(
        embedding_provider=embedding_provider,
        query_rewriter=query_rewriter,
        reranker=reranker,
    )

    return AskService(
        retriever=retriever,
        llm_provider=llm_provider,
    )


def _build_agent_service(user):
    return build_agent(user)


def _get_active_document(user):
    return Document.objects.filter(
        owner=user,
        is_active=True,
        status="processed",
    ).first()


def _build_agent_messages(*, user, question: str) -> list[dict[str, str]]:
    active_document = _get_active_document(user)
    if active_document is None:
        system_content = (
            "No hay un documento activo procesado para este usuario. "
            "Si necesitas contenido del documento, la herramienta puede no encontrar resultados."
        )
    else:
        source_name = active_document.original_name or active_document.file.name or ""
        extension = Path(source_name).suffix.lower() or "unknown"
        content_type = active_document.content_type or "unknown"
        is_code_document = extension in CODE_EXTENSIONS
        document_kind = "código" if is_code_document else "documento"

        system_content = (
            f"El documento activo del usuario es '{active_document.original_name}' "
            f"(tipo {content_type}, extensión {extension}). "
            f"Este documento debe tratarse como {document_kind}. "
            "Regla principal: para CUALQUIER pregunta que pueda responderse con el contenido "
            "del documento activo, DEBES consultar primero el documento (con la herramienta "
            "correspondiente) antes de responder. No respondas con tu conocimiento general si el "
            "documento podría contener la respuesta. "
            "Usa analyze_code si el documento es código (.py, .js, .ts, etc.) y la pregunta trata "
            "sobre errores, mejoras, funciones, refactorización, revisión o seguridad del código. "
            "En cualquier otro caso usa search_document. "
            "Solo si el documento no contiene la respuesta puedes usar tu propio conocimiento "
            "o tavily_search para información externa o de actualidad."
        )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]


def _extract_called_tools(result) -> list[str]:
    tool_names: list[str] = []

    for message in result.get("messages", []):
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            if tool_name:
                tool_names.append(tool_name)

        message_type = getattr(message, "type", "")
        message_name = getattr(message, "name", None)
        if message_type == "tool" and message_name:
            tool_names.append(message_name)

    return list(dict.fromkeys(tool_names))


def _append_tools_to_answer(answer: str, tool_names: list[str]) -> str:
    if not tool_names:
        return answer

    tools_label = ", ".join(tool_names)
    return f"{answer}\n\n🔧 Tools usadas: {tools_label}"


@login_required
def document_list(request):
    documents = Document.objects.filter(owner=request.user).order_by("-created_at")

    return render(
        request,
        "documents/document_list.html",
        {"documents": documents},
    )


@login_required
def document_status(request):
    docs = Document.objects.filter(owner=request.user).values("id", "status")
    return JsonResponse({"documents": list(docs)})


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
            process_document_task.delay(doc.id)

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


@login_required
@ratelimit(key="user", rate="20/m", block=True)
@require_POST
def ask_view(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    question = payload.get("question")
    if not question:
        return JsonResponse({"error": "Missing 'question'"}, status=400)

    try:
        ask_service = _build_ask_service()
        result = ask_service.ask(
            question=question,
            user=request.user,
            top_k=6,
        )
    except Exception:
        logger.exception("Agent failed for user %s", request.user.id)
        return JsonResponse(
            {"error": "Internal error processing the question"},
            status=500,
        )

    return JsonResponse(result, status=200)


@login_required
@ratelimit(key="user", rate="20/m", block=True)
@require_POST
def agent_view(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    question = payload.get("question")
    if not question:
        return JsonResponse({"error": "Missing 'question'"}, status=400)

    try:
        agent = _build_agent_service(request.user)
        result = agent.invoke({"messages": _build_agent_messages(user=request.user, question=question)})
        tool_names = _extract_called_tools(result)
        print(">>> TOOLS CALLED:", tool_names, flush=True)
        answer = _append_tools_to_answer(result["messages"][-1].content, tool_names)
    except Exception:
        logger.exception("Agent failed for user %s", request.user.id)
        return JsonResponse(
            {"error": "Internal error processing the question"},
            status=500,
        )

    return JsonResponse(
        {
            "question": question,
            "answer": answer,
        },
        status=200,
    )


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
            mode = request.POST.get("mode", "documento")
            try:
                if mode == "agente":
                    agent = _build_agent_service(request.user)
                    result = agent.invoke({"messages": _build_agent_messages(user=request.user, question=question)})
                    tool_names = _extract_called_tools(result)
                    print(">>> TOOLS CALLED:", tool_names, flush=True)
                    answer = _append_tools_to_answer(result["messages"][-1].content, tool_names)
                else:
                    ask_service = _build_ask_service()
                    result = ask_service.ask(question=question, user=request.user, top_k=6)
                    answer = result["answer"]
            except Exception:
                logger.exception("Ask failed for user %s", request.user.id)
                answer = "Lo siento..."

            history = request.session.get("chat_history", [])
            if not isinstance(history, list):
                history = []

            history.append(
                {
                    "question": question,
                    "answer": answer,
                }
            )

            request.session["chat_history"] = history

        return redirect("documents:ask_ui")

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
