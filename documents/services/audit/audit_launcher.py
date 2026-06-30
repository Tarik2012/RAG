import logging

from django.urls import reverse

from documents.models import AuditRun

logger = logging.getLogger(__name__)


def launch_project_audit(user, project, conversation=None) -> dict:
    """Lanza una auditoria de seguridad de todo el proyecto, o devuelve la que ya esta en curso.
    Fuente de verdad UNICA para lanzar auditorias (la usan el pre-router y la tool del agente).
    Devuelve un dict operativo: {status, audit_run_id, report_url, message}.
    """
    if project is None:
        return {
            "status": "no_project",
            "audit_run_id": None,
            "report_url": None,
            "message": "Para auditar un proyecto, abre una conversacion asociada a un proyecto.",
        }

    active = AuditRun.objects.filter(
        project=project,
        status__in=[AuditRun.STATUS_PENDING, AuditRun.STATUS_RUNNING],
    ).first()
    if active:
        report_url = reverse("documents:audit_report", args=[active.id])
        return {
            "status": "already_running",
            "audit_run_id": active.id,
            "report_url": report_url,
            "message": (
                f"Ya hay una auditoria en curso para este proyecto "
                f"(estado: {active.get_status_display()}). [Ver el informe de auditoria]({report_url})"
            ),
        }

    from documents.tasks import run_project_audit_task

    run = AuditRun.objects.create(
        project=project,
        user=user,
        conversation=conversation,
        status=AuditRun.STATUS_PENDING,
    )
    run_project_audit_task.delay(run.id)
    report_url = reverse("documents:audit_report", args=[run.id])
    logger.info("auditoria lanzada via launcher: AuditRun %s, proyecto %s", run.id, project.id)
    return {
        "status": "launched",
        "audit_run_id": run.id,
        "report_url": report_url,
        "message": (
            f"He lanzado la auditoria de seguridad de todo el proyecto '{project.name}'. "
            f"Se esta procesando en segundo plano (suele tardar menos de un minuto). "
            f"[Ver el informe de auditoria]({report_url})"
        ),
    }
