import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from documents.models import AuditRun, Document, ProjectMemory
from documents.services.audit.audit_service import audit_project
from documents.services.document_processor import process_document
from documents.services.github.repo_ingestor import ingest_repo_file
from documents.services.github.repo_reader import get_default_branch, list_repo_code_files
from documents.services.documentation.documentation_service import DocumentationService
from documents.services.llm.openai_llm_provider import OpenAILLMProvider

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_document_task(self, document_id: int):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return

    if document.status == "processed":
        return

    process_document(document)


@shared_task(bind=True)
def generate_documentation_task(self, document_id: int):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return

    document.documentation_status = "processing"
    document.save(update_fields=["documentation_status"])

    try:
        llm_provider = OpenAILLMProvider()
        service = DocumentationService(llm_provider=llm_provider)
        result = service.generate(document_id=document.id, user=document.owner)

        if "error" in result:
            document.documentation_status = "failed"
            document.save(update_fields=["documentation_status"])
            return

        document.documentation = result["documentation"]
        document.documentation_status = "ready"
        document.save(update_fields=["documentation", "documentation_status"])
    except Exception:
        document.documentation_status = "failed"
        document.save(update_fields=["documentation_status"])
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_repo_task(
    self,
    owner: str,
    repo: str,
    user_id: int,
    branch: str | None = None,
    project_id=None,
) -> int:
    user = get_user_model().objects.get(id=user_id)
    branch = branch or get_default_branch(owner, repo)
    source = f"github:{owner}/{repo}"
    delete_qs = Document.objects.filter(owner=user, source=source)
    if project_id is not None:
        delete_qs = delete_qs.filter(project_id=project_id)
    delete_qs.delete()
    paths = list_repo_code_files(owner, repo, branch)
    created = 0
    for path in paths:
        try:
            ingest_repo_file(
                owner=owner,
                repo=repo,
                path=path,
                user=user,
                branch=branch,
                project_id=project_id,
            )
            created += 1
        except Exception:
            logger.exception("Fallo al ingerir %s de %s/%s", path, owner, repo)
            continue
    return created


@shared_task(bind=True)
def run_project_audit_task(self, audit_run_id: int):
    """Ejecuta una auditoria de proyecto en background y actualiza el AuditRun.
    El estado vive en el AuditRun (fuente de verdad)."""
    try:
        run = AuditRun.objects.select_related("project", "user").get(id=audit_run_id)
    except AuditRun.DoesNotExist:
        logger.warning("run_project_audit_task: AuditRun %s no existe", audit_run_id)
        return

    run.status = AuditRun.STATUS_RUNNING
    run.started_at = timezone.now()
    run.celery_task_id = self.request.id or ""
    run.save(update_fields=["status", "started_at", "celery_task_id"])

    try:
        result = audit_project(run.user, run.project)

        run.result_json = result
        run.scanned_files = result.get("scanned", 0)
        run.total_files = result.get("scanned", 0) + result.get("skipped", 0)
        run.findings_count = result.get("total_findings", 0)
        run.error_count = len(result.get("errors", []))
        run.status = AuditRun.STATUS_COMPLETED
        run.finished_at = timezone.now()
        run.save(update_fields=[
            "result_json", "scanned_files", "total_files", "findings_count",
            "error_count", "status", "finished_at",
        ])
        try:
            from documents.services.agent.agent import _upsert_project_memory

            result = run.result_json or {}
            files_with_findings = result.get("files_with_findings", [])

            error_count_saved = 0
            MAX_MEMORIES = 10
            for file_data in files_with_findings:
                if error_count_saved >= MAX_MEMORIES:
                    break
                file_name = file_data.get("file", "unknown")
                for finding in file_data.get("findings", []):
                    if error_count_saved >= MAX_MEMORIES:
                        break
                    severity = (finding.get("severity") or "").upper()
                    if severity != "ERROR":
                        continue
                    rule = finding.get("rule", "unknown-rule")
                    line = finding.get("line")
                    title = f"Vulnerability in {file_name}: {rule}"
                    content = (
                        f"Audit found a {severity} severity issue in {file_name} "
                        f"(line {line}): {finding.get('message', '')[:300]}"
                    )
                    _upsert_project_memory(
                        user=run.user,
                        project=run.project,
                        category="vulnerability",
                        title=title,
                        content=content,
                        evidence={
                            "file": file_name,
                            "rule": rule,
                            "line": line,
                            "severity": severity,
                            "source": "project_audit",
                        },
                    )
                    error_count_saved += 1

            summary_title = "Project security audit summary"
            summary_content = (
                f"Last project-wide audit found {run.findings_count} security finding(s) "
                f"across {len(files_with_findings)} file(s), {run.scanned_files} files scanned."
            )
            _upsert_project_memory(
                user=run.user,
                project=run.project,
                category=ProjectMemory.CATEGORY_AUDIT_SUMMARY,
                title=summary_title,
                content=summary_content,
                evidence={
                    "findings_count": run.findings_count,
                    "scanned_files": run.scanned_files,
                    "source": "project_audit",
                },
            )
            logger.info(
                "auditoria: %s memorias ERROR + resumen guardadas (AuditRun %s)",
                error_count_saved,
                run.id,
            )
        except Exception:
            logger.exception(
                "auditoria: fallo al destilar hallazgos a memoria (AuditRun %s)",
                run.id,
            )
        logger.info(
            "auditoria completada: AuditRun %s, %s hallazgos",
            audit_run_id,
            run.findings_count,
        )
    except Exception as exc:
        logger.exception("auditoria fallo: AuditRun %s", audit_run_id)
        run.status = AuditRun.STATUS_FAILED
        run.error_text = str(exc)[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_text", "finished_at"])
        raise
