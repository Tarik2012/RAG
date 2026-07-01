import json
import logging
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .forms import DocumentUploadForm
from documents.models import Conversation, Document, Message, Project
from documents.services.agent.agent import build_agent
from documents.services.extraction.text_extraction import get_document_full_text
from documents.tasks import generate_documentation_task, ingest_repo_task, process_document_task

logger = logging.getLogger(__name__)

def _build_agent_service(user, project=None, conversation=None):
    return build_agent(user, project=project, conversation=conversation)


def _casual_reply(message: str) -> str:
    """Respuesta breve y directa para charla casual, sin invocar al agente."""
    if not settings.OPENAI_API_KEY:
        return "De nada."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model="gpt-4o-mini",
            temperature=0.5,
            instructions=(
                "Eres TariTech, un asistente sobre codigo y documentos. "
                "Responde de forma breve, amable y natural a este mensaje casual. "
                "No menciones documentos ni herramientas a menos que el usuario pregunte."
            ),
            input=(message or "").strip(),
        )
        return (response.output_text or "De nada.").strip()
    except Exception:
        logger.exception("Casual reply fallback")
        return "De nada."


def _build_agent_messages(*, user, question: str, history: list | None = None, project=None) -> list[dict]:
    docs_qs = Document.objects.filter(owner=user, status="processed")
    if project is not None:
        docs_qs = docs_qs.filter(project=project)
    nombres = list(docs_qs.values_list("original_name", flat=True))
    base_role = (
        "You are TariTech, a code analysis assistant. You help developers understand their "
        "source files and connected GitHub repositories: explaining how code works, locating "
        "functions and classes, reviewing quality, spotting bugs and security risks, and "
        "proposing refactors. You reason step by step: decide what you need, call a tool to get "
        "it, observe the result, and repeat until you can answer. Each tool's description tells "
        "you when to use it; rely on those descriptions to choose the right tool.\n\n"
        "CRITICAL - FILE IDENTITY: Before answering, identify the EXACT file the user means in "
        "their CURRENT message. If it differs from the last file discussed, or you are unsure "
        "which file, call the appropriate tool again for that file (read_full_file, "
        "search_uploaded_files, or list_repository_files). NEVER answer about one file using "
        "content from a different file discussed earlier.\n\n"
        "RESPONSE RULES:\n"
        "1. Answer the user's ACTUAL question with concrete, specific content. Never reply with a "
        "generic capabilities list or vague greeting when they asked something real.\n"
        "2. Cite which file an answer comes from when relevant. Never invent files, functions, or "
        "facts; if something is not in the files, say so.\n"
        "3. For casual remarks or greetings ('thanks', 'ok'), reply briefly WITHOUT any tool.\n"
        "4. Prioritize by impact: lead with the 2-3 most important issues specific to THIS code, "
        "then minor ones. Be concise, no filler. Favor specific observations over generic advice.\n"
    )

    if not nombres:
        system_content = base_role + "\n\nThe user currently has no processed files."
    else:
        scope = "in the current project" if project is not None else ""
        system_content = base_role + f"\n\nAvailable files {scope}: {', '.join(nombres)}."

    if project is not None:
        from documents.models import ProjectMemory

        memories = ProjectMemory.objects.filter(
            project=project,
            status=ProjectMemory.STATUS_ACTIVE,
        ).order_by("-updated_at")[:10]
        if memories:
            lines = []
            for m in memories:
                lines.append(f"- [{m.get_category_display()}] {m.title}: {m.content}")
            memory_block = (
                "\n\nKNOWN FINDINGS about this project (from previous analysis). "
                "Use them as context, but VERIFY with tools before relying on them, "
                "since code may have changed since they were recorded:\n"
                + "\n".join(lines)
            )
            system_content = system_content + memory_block

    messages: list[dict] = [{"role": "system", "content": system_content}]

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


def _extract_used_documents(result) -> list[str]:
    """Saca los document_name pasados a las tools que reciben un archivo."""
    names: list[str] = []
    for message in result.get("messages", []):
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            args = tool_call.get("args") or {}
            doc_name = args.get("document_name")
            if doc_name:
                names.append(doc_name)
    return list(dict.fromkeys(names))


def _append_sources_to_answer(answer: str, result, user, project=None) -> str:
    """Añade una seccion 'Fuentes' con enlaces Markdown a los archivos citados."""
    from django.urls import reverse

    names = _extract_used_documents(result)
    if not names:
        return answer

    links = []
    seen_ids = set()
    for name in names:
        qs = Document.objects.filter(owner=user, status="processed", original_name__icontains=name)
        if project is not None:
            qs = qs.filter(project=project)
        doc = qs.order_by("id").first()
        if doc and doc.id not in seen_ids:
            seen_ids.add(doc.id)
            url = reverse("documents:document_content", args=[doc.id])
            links.append(f"- [{doc.original_name}]({url})")

    if not links:
        return answer
    return answer + "\n\n**Fuentes:**\n" + "\n".join(links)


@login_required
def document_list(request):
    documents = Document.objects.filter(owner=request.user).order_by("-created_at")

    standalone = []
    repos = {}
    for doc in documents:
        if doc.source and doc.source.startswith("github:"):
            repo_name = doc.source.replace("github:", "")
            repos.setdefault(repo_name, []).append(doc)
        else:
            standalone.append(doc)

    repo_groups = [
        {"name": name, "files": files, "count": len(files)}
        for name, files in repos.items()
    ]

    return render(
        request,
        "documents/document_list.html",
        {"documents": standalone, "repo_groups": repo_groups},
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
    all_docs = project.documents.all().order_by("-created_at")
    conversations = project.conversations.order_by("-updated_at")

    standalone = []
    repos = {}
    for doc in all_docs:
        if doc.source and doc.source.startswith("github:"):
            repo_name = doc.source.replace("github:", "")
            repos.setdefault(repo_name, []).append(doc)
        else:
            standalone.append(doc)
    repo_groups = [
        {"name": name, "files": files, "count": len(files)}
        for name, files in repos.items()
    ]

    return render(request, "documents/project_detail.html", {
        "project": project,
        "documents": standalone,
        "repo_groups": repo_groups,
        "conversations": conversations,
        "form": DocumentUploadForm(),
    })


@login_required
def project_memories(request, project_id):
    project = get_object_or_404(Project, id=project_id, user=request.user)
    memories = project.memories.all()
    return render(request, "documents/project_memories.html", {
        "project": project,
        "memories": memories,
    })


@login_required
def audit_report(request, audit_run_id):
    from documents.models import AuditRun

    run = get_object_or_404(AuditRun, id=audit_run_id, user=request.user)
    return render(request, "documents/audit_report.html", {
        "run": run,
        "project": run.project,
        "result": run.result_json or {},
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
@require_POST
def conversation_delete(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    project_id = conversation.project_id
    conversation.delete()
    if request.session.get("conversation_id") == conversation_id:
        request.session.pop("conversation_id", None)
    if project_id:
        return redirect("documents:project_detail", project_id=project_id)
    return redirect("documents:ask_ui")


@login_required
@require_POST
def memory_delete(request, memory_id):
    from documents.models import ProjectMemory

    memory = get_object_or_404(ProjectMemory, id=memory_id, user=request.user)
    project_id = memory.project_id
    memory.delete()
    return redirect("documents:project_memories", project_id=project_id)


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
    ingest_repo_task.delay(owner, repo, request.user.id, branch, project_id)
    messages.success(request, f"Ingesta de {owner}/{repo} iniciada. Los archivos apareceran en unos segundos; recarga la pagina.")
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
    project_id = document.project_id
    document.file.delete(save=False)
    document.delete()
    if project_id:
        return redirect("documents:project_detail", project_id=project_id)
    return redirect("documents:list")


@login_required
@require_POST
def repo_delete(request, project_id):
    project = get_object_or_404(Project, id=project_id, user=request.user)
    repo_name = (request.POST.get("repo_name") or "").strip()
    if not repo_name:
        return redirect("documents:project_detail", project_id=project_id)
    docs = Document.objects.filter(
        owner=request.user,
        project=project,
        source=f"github:{repo_name}",
    )
    for doc in docs:
        doc.file.delete(save=False)
    docs.delete()
    return redirect("documents:project_detail", project_id=project_id)


@login_required
def documentation_view(request, pk):
    document = get_object_or_404(Document, pk=pk, owner=request.user)
    return render(request, "documents/documentation.html", {"document": document})


@login_required
def document_content_view(request, pk):
    document = get_object_or_404(Document, pk=pk, owner=request.user)
    content = get_document_full_text(document)
    return render(request, "documents/document_content.html", {
        "document": document,
        "content": content,
    })


@login_required
def generate_documentation_trigger(request, pk):
    document = get_object_or_404(Document, pk=pk, owner=request.user)
    if request.method == "POST" and document.status == "processed":
        document.documentation_status = "processing"
        document.save(update_fields=["documentation_status"])
        generate_documentation_task.delay(document.id)
    if document.project_id:
        return redirect("documents:project_detail", project_id=document.project_id)
    return redirect("documents:list")

@login_required
@ratelimit(key="user", rate="30/m", block=True)
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

        from documents.services.router.intent_router import classify_message
        route = classify_message(question)
        if route == "chat":
            answer = _casual_reply(question)
            tool_names = []
        else:
            try:
                history = list(
                    conversation.messages
                    .order_by("-created_at")
                    .values("role", "content")[:6]
                )
                history.reverse()
                agent = _build_agent_service(
                    request.user,
                    project=conversation.project,
                    conversation=conversation,
                )
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
                answer = _append_sources_to_answer(
                    answer,
                    result,
                    request.user,
                    project=conversation.project,
                )
            except Exception:
                logger.exception("Agent error")
                answer = "Lo siento, ocurrio un error al procesar tu pregunta."
                tool_names = []

        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=question,
        )
        if not conversation.title:
            conversation.title = question[:60]
            conversation.save(update_fields=["title"])
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=answer,
            tool_calls=tool_names,
        )

        return redirect("documents:ask_ui")

    history = list(conversation.messages.order_by("created_at"))
    return render(request, "documents/ask.html", {"history": history})
