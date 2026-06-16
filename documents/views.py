import json
import logging
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .forms import DocumentUploadForm
from documents.models import Conversation, Document, Message, Project
from documents.services.agent.agent import build_agent
from documents.services.ask.ask_service import AskService
from documents.services.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider
from documents.services.llm.openai_llm_provider import OpenAILLMProvider
from documents.services.router.intent_router import classify_intent
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever
from documents.tasks import generate_documentation_task, ingest_repo_task, process_document_task

logger = logging.getLogger(__name__)


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


def _build_agent_service(user, project=None):
    return build_agent(user, project=project)


FOLLOW_UP_PREFIXES = (
    "y ", "and ", "tambien", "tambien", "entonces",
    "ok", "vale", "bien", "ahora", "sobre eso",
    "de eso", "de ese", "de esa",
)

FOLLOW_UP_REFERENCES = (
    "este archivo", "ese archivo", "este codigo", "ese codigo",
    "esto", "eso", "lo anterior", "la anterior", "anterior",
)


def _looks_like_follow_up(question: str) -> bool:
    normalized = question.strip().lower()
    if not normalized:
        return False
    if normalized.startswith(FOLLOW_UP_PREFIXES):
        return True
    return any(ref in normalized for ref in FOLLOW_UP_REFERENCES)


def _build_agent_messages(*, user, question: str, history: list | None = None, project=None) -> list[dict]:
    docs_qs = Document.objects.filter(owner=user, status="processed")
    if project is not None:
        docs_qs = docs_qs.filter(project=project)
    nombres = list(docs_qs.values_list("original_name", flat=True))
    if not nombres:
        system_content = "El usuario no tiene documentos procesados."
    else:
        system_content = (
            f"El usuario tiene estos documentos: {', '.join(nombres)}. "
            "Use list_repository_files to see what files exist. "
            "Use search_uploaded_files to find relevant passages across files. "
            "Use read_full_file for the full content of a specific file (deep analysis, summaries, code review). "
            "Use tavily_search only for external information."
        )

    messages: list[dict] = [{"role": "system", "content": system_content}]

    if _looks_like_follow_up(question):
        recent_history = (history or [])[-6:]
        for turn in recent_history:
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": question})
    return messages


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
    return f"{answer}\n\nTools usadas: {tools_label}"


@login_required
def document_list(request):
    documents = Document.objects.filter(owner=request.user).order_by("-created_at")

    return render(
        request,
        "documents/document_list.html",
        {"documents": documents},
    )


@login_required
def project_list(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            Project.objects.create(
                user=request.user,
                name=name,
                description=request.POST.get("description", "").strip(),
            )
        return redirect("documents:project_list")
    projects = Project.objects.filter(user=request.user)
    return render(request, "documents/project_list.html", {"projects": projects})


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id, user=request.user)
    documents = project.documents.all()
    conversations = project.conversations.order_by("-updated_at")
    return render(request, "documents/project_detail.html", {
        "project": project,
        "documents": documents,
        "conversations": conversations,
        "form": DocumentUploadForm(),
    })


@login_required
def project_delete(request, project_id):
    project = get_object_or_404(Project, id=project_id, user=request.user)
    if request.method == "POST":
        project.delete()
    return redirect("documents:project_list")


@login_required
@require_POST
def conversation_create(request, project_id):
    project = get_object_or_404(Project, id=project_id, user=request.user)
    conversation = Conversation.objects.create(user=request.user, project=project)
    request.session["conversation_id"] = conversation.id
    return redirect("documents:ask_ui")


@login_required
def conversation_open(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    request.session["conversation_id"] = conversation.id
    return redirect("documents:ask_ui")


@login_required
def document_status(request):
    docs = Document.objects.filter(owner=request.user).values("id", "status", "documentation_status")
    return JsonResponse({"documents": list(docs)})


@login_required
def document_upload(request):
    project_id = request.POST.get("project_id") or request.GET.get("project_id")
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            uploaded_file = request.FILES["file"]
            doc.owner = request.user
            doc.content_type = uploaded_file.content_type or ""
            doc.size = uploaded_file.size
            if project_id:
                from documents.models import Project
                doc.project = Project.objects.filter(id=project_id, user=request.user).first()
            doc.save()
            process_document_task.delay(doc.id)
            if doc.project_id:
                return redirect("documents:project_detail", project_id=doc.project_id)
            return redirect("documents:list")
    else:
        form = DocumentUploadForm()

    return render(
        request,
        "documents/document_upload.html",
        {"form": form, "project_id": project_id},
    )


@login_required
@require_POST
def repo_ingest(request):
    raw = (request.POST.get("repo_full") or "").strip()
    raw = re.sub(r"^https?://", "", raw, flags=re.I)
    raw = re.sub(r"^(www\.)?github\.com/", "", raw, flags=re.I)
    parts = [p for p in raw.split("/") if p]
    if len(parts) < 2:
        messages.error(request, "Formato invalido. Usa owner/repo o la URL del repo, p. ej. Tarik2012/RAG.")
        return redirect("documents:list")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    branch = (request.POST.get("branch") or "").strip() or None
    project_id = request.POST.get("project_id")
    ingest_repo_task.delay(owner, repo, request.user.id, branch)
    messages.success(request, f"Ingesta de {owner}/{repo} iniciada. Los archivos iran apareciendo en la lista.")
    if project_id:
        return redirect("documents:project_detail", project_id=project_id)
    return redirect("documents:list")


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
def documentation_view(request, pk):
    document = get_object_or_404(Document, pk=pk, owner=request.user)
    return render(request, "documents/documentation.html", {"document": document})


@login_required
def generate_documentation_trigger(request, pk):
    document = get_object_or_404(Document, pk=pk, owner=request.user)
    if request.method == "POST" and document.status == "processed":
        document.documentation_status = "processing"
        document.save(update_fields=["documentation_status"])
        generate_documentation_task.delay(document.id)
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
        logger.info("tools called: %s", tool_names)
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
    conversation_id = request.session.get("conversation_id")
    if conversation_id:
        conversation = Conversation.objects.filter(id=conversation_id, user=request.user).first()
    else:
        conversation = None
    if not conversation:
        conversation = Conversation.objects.create(user=request.user)
        request.session["conversation_id"] = conversation.id

    if request.method == "POST":
        action = request.POST.get("action", "ask")

        if action == "clear":
            current_project = conversation.project if conversation else None
            conversation = Conversation.objects.create(user=request.user, project=current_project)
            request.session["conversation_id"] = conversation.id
            return redirect("documents:ask_ui")

        question = request.POST.get("question", "").strip()
        if not question:
            return redirect("documents:ask_ui")

        try:
            history = list(
                conversation.messages
                .order_by("-created_at")
                .values("role", "content")[:6]
            )
            history.reverse()
            agent = _build_agent_service(request.user, project=conversation.project)
            result = agent.invoke(
                {"messages": _build_agent_messages(
                    user=request.user,
                    question=question,
                    history=history,
                    project=conversation.project,
                )}
            )
            tool_names = _extract_called_tools(result)
            logger.info("tools called: %s", tool_names)
            answer = _append_tools_to_answer(result["messages"][-1].content, tool_names)
        except Exception:
            logger.exception("Agent error")
            answer = "Lo siento, ocurrio un error al procesar tu pregunta."
            tool_names = []

        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=question,
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=answer,
            tool_calls=tool_names,
        )

        return redirect("documents:ask_ui")

    history = list(conversation.messages.order_by("created_at"))
    return render(request, "documents/ask.html", {"history": history})
