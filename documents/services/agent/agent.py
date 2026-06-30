import logging
import os
from functools import lru_cache
from typing import TypedDict

from asgiref.sync import async_to_sync
from django.conf import settings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

from documents.models import Document
from documents.services.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from documents.services.extraction.text_extraction import get_document_full_text
from documents.services.retrieval.query_rewriter import QueryRewriter
from documents.services.retrieval.reranker import CrossEncoderReranker
from documents.services.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_reranker():
    return CrossEncoderReranker()


@lru_cache(maxsize=1)
def _get_embedding_provider():
    return OpenAIEmbeddingProvider()


@lru_cache(maxsize=1)
def _get_query_rewriter():
    return QueryRewriter()


@lru_cache(maxsize=1)
def _get_llm():
    return ChatOpenAI(
        model=getattr(settings, "OPENAI_AGENT_MODEL", "gpt-4.1"),
        temperature=0,
    )


@lru_cache(maxsize=1)
def _get_tavily_tool():
    return TavilySearchResults(max_results=3)


def _build_mcp_config():
    return {
        "github": {
            "url": "https://api.githubcopilot.com/mcp/",
            "transport": "streamable_http",
            "headers": {"Authorization": f"Bearer {os.environ.get('GITHUB_PAT', '')}"},
        }
    }


_MCP_TOOL_ALLOWLIST = {"get_file_contents", "search_code"}
MAX_RETRIES = 1


@lru_cache(maxsize=1)
def _get_mcp_tools():
    try:
        client = MultiServerMCPClient(_build_mcp_config())
        tools = list(async_to_sync(client.get_tools)())
        return [t for t in tools if t.name in _MCP_TOOL_ALLOWLIST]
    except Exception as exc:
        logger.warning("No se pudieron cargar las tools MCP: %s", exc)
        return []


def build_search_tool(retriever, user, project=None):
    @tool
    def search_uploaded_files(query: str) -> str:
        """Search across all the user's uploaded files and return the most relevant passages with their source file name.

        Use this first to find where information appears, gather evidence from excerpts, or compare across files.
        Do not use this when the user needs the full content of one specific file; use read_full_file instead.

        Args:
            query: The search terms or question to look for across the files.
        """
        logger.info("tool used: search_uploaded_files")
        document_ids = None
        if project is not None:
            document_ids = list(
                Document.objects.filter(owner=user, status="processed", project=project)
                .values_list("id", flat=True)
            )
        results = retriever.retrieve(query=query, user=user, top_k=5, document_ids=document_ids)
        if not results:
            return "No relevant information found in the uploaded files."

        return "\n\n".join(
            f"[Source: {chunk.document.original_name}]\n{chunk.text}"
            for chunk, _ in results
        )

    return search_uploaded_files


def build_read_file_tool(retriever, user, project=None):
    @tool
    def read_full_file(query: str, document_name: str) -> str:
        """Read one uploaded file in full and use it to answer the user's request.

        Use this for deep explanations, full-file summaries, reviewing or analyzing code, config, markdown or documentation, and proposing improvements. This is the right tool when the whole file context matters.

        Args:
            query: The user's goal or question about the file.
            document_name: The name of the file to read (one of the user's uploaded files).
        """
        if not document_name or not document_name.strip():
            return "No document_name provided. Specify which file to read."
        logger.info("tool used: read_full_file")
        documents_qs = Document.objects.filter(
            owner=user, status="processed", original_name__icontains=document_name,
        )
        if project is not None:
            documents_qs = documents_qs.filter(project=project)
        document = documents_qs.order_by("id").first()
        if document is None:
            available_qs = Document.objects.filter(owner=user, status="processed")
            if project is not None:
                available_qs = available_qs.filter(project=project)
            available = list(available_qs.values_list("original_name", flat=True))
            return f"No file matching '{document_name}'. Available files: {', '.join(available) or 'none'}."
        full_text = get_document_full_text(document)
        if not full_text.strip():
            return "No code found in the document"
        MAX_CHARS = 80000
        truncated = full_text[:MAX_CHARS]
        nota = "" if len(full_text) <= MAX_CHARS else "\n\n[Note: file truncated due to size.]"
        return (
            "Analysis instructions:\n"
            f"- User request: {query}\n"
            f"- File analyzed: {document.original_name}\n"
            "- Review the full code below.\n"
            "- Always check for hardcoded secrets, credentials, tokens, or API keys.\n"
            "- Report only issues that are truly present in this code.\n\n"
            "Full file content:\n"
            f"{truncated}{nota}"
        )

    return read_full_file


def _upsert_project_memory(user, project, category, title, content, evidence=None, conversation=None):
    """Crea o actualiza una memoria de proyecto por fingerprint (dedup). Devuelve (memory, created)."""
    import hashlib

    from django.utils import timezone

    from documents.models import ProjectMemory

    norm = f"{project.id}:{category}:{title.lower()}"
    fingerprint = hashlib.sha256(norm.encode("utf-8")).hexdigest()

    existing = ProjectMemory.objects.filter(project=project, fingerprint=fingerprint).first()
    if existing:
        existing.times_seen += 1
        existing.last_seen_at = timezone.now()
        existing.content = content
        existing.status = ProjectMemory.STATUS_ACTIVE
        if evidence:
            existing.evidence = evidence
        existing.save(update_fields=[
            "times_seen", "last_seen_at", "content", "status", "evidence", "updated_at"
        ])
        return existing, False

    memory = ProjectMemory.objects.create(
        project=project, user=user, category=category,
        title=title[:200], content=content,
        fingerprint=fingerprint, evidence=evidence or {},
        source_conversation=conversation,
    )
    return memory, True


def build_static_analysis_tool(user, project=None):
    from documents.services.agent.static_analysis import analyze_code, resolve_language_suffix

    @tool
    def run_static_analysis(document_name: str) -> str:
        """Run a real static analysis security scanner (opengrep) on one uploaded code file and return verified findings.

        For whole-project security requests, use the full-project audit flow instead of repeating this tool file by file. For understanding, explanation, legacy code, architecture, style, or general quality, prefer read_full_file.

        Use this when the user asks about code quality, bugs, security vulnerabilities, or risks in a specific file. This runs an actual linter with 1000+ rules across many languages — prefer it over your own judgment when making claims about security or quality, because it returns verified results instead of guesses.

        Args:
            document_name: The name of the file to analyze (one of the user's uploaded files).
        """
        if not document_name or not document_name.strip():
            return "No document_name provided. Specify which file to analyze."
        logger.info("tool used: run_static_analysis")
        documents_qs = Document.objects.filter(
            owner=user, status="processed", original_name__icontains=document_name,
        )
        if project is not None:
            documents_qs = documents_qs.filter(project=project)
        document = documents_qs.order_by("id").first()
        if document is None:
            available_qs = Document.objects.filter(owner=user, status="processed")
            if project is not None:
                available_qs = available_qs.filter(project=project)
            available = list(available_qs.values_list("original_name", flat=True))
            return f"No file matching '{document_name}'. Available files: {', '.join(available) or 'none'}."

        full_text = get_document_full_text(document)
        if not full_text.strip():
            return "The file is empty or its content could not be read."

        MAX_CHARS = 50000
        code = full_text[:MAX_CHARS]
        truncated_note = "" if len(full_text) <= MAX_CHARS else "\n\n[Note: file truncated to 50000 chars before analysis.]"

        suffix = resolve_language_suffix(document.original_name, document.content_type)
        findings = analyze_code(code, document.original_name, suffix=suffix)

        if findings.get("errors"):
            return f"The analyzer reported errors: {findings['errors']}"

        results = findings.get("results", [])
        if not results:
            return f"Static analysis ran successfully on {document.original_name} and found no issues.{truncated_note}"

        lines = [f"Static analysis of {document.original_name} found {len(results)} issue(s):\n"]
        for r in results[:25]:
            check = r.get("check_id", "unknown-rule")
            line_no = r.get("start", {}).get("line", "?")
            msg = r.get("extra", {}).get("message", "").strip()
            sev = r.get("extra", {}).get("severity", "")
            lines.append(f"- [{sev}] line {line_no}: {msg} (rule: {check})")
        if len(results) > 25:
            lines.append(f"\n...and {len(results) - 25} more.")

        # Persistencia por evidencia: guardar vulnerabilidades verificadas en memoria del proyecto
        if project is not None and results:
            try:
                top = []
                for r in results[:10]:
                    top.append({
                        "rule": r.get("check_id", "unknown-rule"),
                        "line": r.get("start", {}).get("line"),
                        "severity": r.get("extra", {}).get("severity", ""),
                        "message": r.get("extra", {}).get("message", "").strip(),
                    })
                title = f"Vulnerabilidades detectadas en {document.original_name}"
                content = f"El analisis estatico encontro {len(results)} hallazgo(s) en {document.original_name}."
                _upsert_project_memory(
                    user=user, project=project,
                    category="vulnerability", title=title, content=content,
                    evidence={"file": document.original_name, "findings": top},
                )
                logger.info("memoria persistida por evidencia: %s", document.original_name)
            except Exception as exc:
                logger.warning("fallo persistiendo memoria de vulnerabilidad: %s", exc)
        return "\n".join(lines) + truncated_note

    return run_static_analysis


def build_find_references_tool(user, project=None):
    from documents.services.agent.find_references import find_symbol_usages
    from documents.services.extraction.text_extraction import get_document_full_text

    @tool
    def find_references(symbol: str) -> str:
        """Find where a Python function, class, or variable is USED across all the user's files.

        Use this when the user asks who calls a function, where something is used, what depends on a symbol, or what would be affected by changing it. Results come from real AST parsing (tree-sitter), not text matching, so comments and strings are excluded. NOTE: this matches by name, so if two different symbols share the same name across files, both may appear. Currently supports Python files only.

        Args:
            symbol: The exact name of the function, class, or variable to find (e.g. 'analyze_code').
        """
        if not symbol or not symbol.strip():
            return "No symbol provided. Specify the function, class, or variable name to find."
        logger.info("tool used: find_references")
        symbol = symbol.strip()

        qs = Document.objects.filter(owner=user, status="processed")
        if project is not None:
            qs = qs.filter(project=project)

        results = []
        total = 0
        for doc in qs:
            name = doc.original_name
            is_python = name.endswith(".py") or "python" in (doc.content_type or "").lower()
            if not is_python:
                continue
            code = get_document_full_text(doc)
            if not code.strip():
                continue
            try:
                usages = find_symbol_usages(code, symbol)
            except Exception as exc:
                logger.warning("find_references fallo en %s: %s", name, exc)
                continue
            if usages:
                results.append((name, usages))
                total += len(usages)

        if not results:
            return f"No usages of '{symbol}' found in the Python files of this project."

        lines = [f"Found {total} usage(s) of '{symbol}':\n"]
        for name, usages in results:
            lines.append(f"\n{name}:")
            for u in usages[:30]:
                lines.append(f"  line {u['line']}: {u['text']}")
            if len(usages) > 30:
                lines.append(f"  ...and {len(usages) - 30} more in this file.")
        return "\n".join(lines)

    return find_references


def build_save_memory_tool(user, project=None, conversation=None):
    @tool
    def save_memory(category: str, title: str, content: str) -> str:
        """ALWAYS call this immediately after run_static_analysis confirms a security
        vulnerability, or after you confirm a real bug, an architecture decision, or a decision
        the user explicitly stated. This persists the finding so future conversations about this
        project remember it. Saving is a REQUIRED follow-up step, not optional: if you just
        reported a verified vulnerability or confirmed bug and did NOT call save_memory, you have
        not finished the task.

        Do NOT call it for trivial observations, casual remarks, generic advice, style nitpicks,
        or uncertain impressions. One call per distinct finding.

        Args:
            category: one of 'bug', 'vulnerability', 'architecture', 'limitation', 'decision'.
            title: a short one-line summary of the finding (max ~15 words).
            content: the detail of the finding, including the file/symbol it concerns.
        """
        if project is None:
            return "No project in context; cannot save memory."
        valid = {"bug", "vulnerability", "architecture", "limitation", "decision"}
        category = (category or "").strip().lower()
        if category not in valid:
            return f"Invalid category '{category}'. Use one of: {', '.join(sorted(valid))}."
        title = (title or "").strip()
        content = (content or "").strip()
        if not title or not content:
            return "Both title and content are required."

        logger.info("tool used: save_memory")
        memory, created = _upsert_project_memory(
            user=user,
            project=project,
            category=category,
            title=title,
            content=content,
            conversation=conversation,
        )
        if created:
            return f"Saved new memory: '{memory.title}'."
        return f"Updated existing memory: '{memory.title}' (seen {memory.times_seen}x)."

    return save_memory


def build_list_files_tool(user, project=None):
    @tool
    def list_repository_files(query: str = "") -> str:
        """List the names of all the user's uploaded and processed files.

        Use this to discover which files are available before deciding which one to read, or when the user asks what files or repository contents exist.

        Args:
            query: Optional filter text to narrow the listing (substring match on file name).
        """
        logger.info("tool used: list_repository_files")
        qs = Document.objects.filter(owner=user, status="processed")
        if project is not None:
            qs = qs.filter(project=project)
        if query:
            qs = qs.filter(original_name__icontains=query)
        nombres = list(qs.values_list("original_name", flat=True))
        if not nombres:
            return "No processed files available."
        return "Available files:\n" + "\n".join(f"- {n}" for n in nombres)

    return list_repository_files


def build_tavily_tool():
    @tool("tavily_search")
    def tavily_search(query: str) -> str:
        """Search the web for recent external information only when the uploaded files do not contain the answer or the user explicitly asks for external sources.

        Args:
            query: The web search query.
        """
        logger.info("tool used: tavily_search")
        result = _get_tavily_tool().invoke({"query": query})
        return str(result)

    return tavily_search


class AgentState(TypedDict, total=False):
    messages: list
    answer_ok: bool
    retries: int


def build_agent(user, project=None, conversation=None):
    retriever = Retriever(
        embedding_provider=_get_embedding_provider(),
        query_rewriter=_get_query_rewriter(),
        reranker=_get_reranker(),
    )

    tools = [
        build_search_tool(retriever, user, project=project),
        build_read_file_tool(retriever, user, project=project),
        build_list_files_tool(user, project=project),
        build_static_analysis_tool(user, project=project),
        build_find_references_tool(user, project=project),
        build_save_memory_tool(user, project=project, conversation=conversation),
        build_tavily_tool(),
    ]
    tools = tools + _get_mcp_tools()

    llm = _get_llm()
    query_rewriter = _get_query_rewriter()
    react_agent = create_react_agent(llm, tools, debug=False)

    def run_agent(state: AgentState) -> dict:
        result = async_to_sync(react_agent.ainvoke)({"messages": state["messages"]})
        return {"messages": result["messages"]}

    def reflect(state: AgentState) -> dict:
        messages = state["messages"]
        question = next(
            (m.content for m in reversed(messages) if getattr(m, "type", None) == "human"),
            "",
        )
        answer = messages[-1].content if messages else ""

        grader_prompt = (
            "You are a strict grader for a question-answering assistant. "
            "Given the user's QUESTION and the assistant's ANSWER, decide if the answer "
            "actually addresses the question with concrete, relevant content. "
            "If the answer fails to find the information, is empty, evasive, or off-topic, output RETRY. "
            "Otherwise output GOOD. Respond with exactly one word: GOOD or RETRY.\n\n"
            f"QUESTION:\n{question}\n\nANSWER:\n{answer}"
        )
        verdict = (llm.invoke(grader_prompt).content or "").strip().upper()
        answer_ok = verdict.startswith("GOOD")
        logger.debug("reflect verdict=%s answer_ok=%s", verdict, answer_ok)
        return {"answer_ok": answer_ok}

    def reformulate(state: AgentState) -> dict:
        messages = list(state["messages"])
        original_question = next(
            (m.content for m in reversed(messages) if getattr(m, "type", None) == "human"),
            "",
        )
        reformulated_question = query_rewriter.reformulate(original_question)
        messages.append(HumanMessage(content=reformulated_question))
        retries = state.get("retries", 0) + 1
        logger.debug("reformulate retries=%s", retries)
        return {"messages": messages, "retries": retries}

    def should_retry(state: AgentState) -> str:
        if state["answer_ok"] is True:
            return "end"
        if state.get("retries", 0) >= MAX_RETRIES:
            return "end"
        return "retry"

    builder = StateGraph(AgentState)
    builder.add_node("run_agent", run_agent)
    builder.add_node("reflect", reflect)
    builder.add_node("reformulate", reformulate)
    builder.add_edge(START, "run_agent")
    builder.add_edge("run_agent", "reflect")
    builder.add_conditional_edges(
        "reflect",
        should_retry,
        {
            "retry": "reformulate",
            "end": END,
        },
    )
    builder.add_edge("reformulate", "run_agent")
    return builder.compile()
