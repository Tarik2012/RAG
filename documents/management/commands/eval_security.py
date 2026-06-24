import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.models import Project
from documents.views import _build_agent_service, _build_agent_messages


class Command(BaseCommand):
    help = "Evalua la deteccion de seguridad del agente (must_contain / must_not_contain). Falla si accuracy < umbral."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--project-id", type=int, default=None)
        parser.add_argument("--gold", default="evals/gold_set_security.json")
        parser.add_argument("--min-accuracy", type=float, default=0.0,
                            help="Umbral minimo (0-1). Si accuracy < umbral, exit code 1.")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"Usuario '{options['user']}' no existe")

        project = None
        project_id = options.get("project_id")
        if project_id is not None:
            try:
                project = Project.objects.get(id=project_id, user=user)
            except Project.DoesNotExist:
                raise CommandError(f"Proyecto {project_id} no existe para {user.username}")

        gold = json.loads(Path(options["gold"]).read_text(encoding="utf-8"))
        agent = _build_agent_service(user, project=project)

        hits = 0
        for item in gold:
            question = item["question"]
            must = [s.lower() for s in item.get("must_contain", [])]
            must_not = [s.lower() for s in item.get("must_not_contain", [])]
            result = agent.invoke(
                {"messages": _build_agent_messages(user=user, question=question, project=project)}
            )
            answer = result["messages"][-1].content.lower()

            contains_all = all(s in answer for s in must)
            contains_none = not any(s in answer for s in must_not)
            ok = contains_all and contains_none
            hits += 1 if ok else 0

            detail = ""
            if not contains_all:
                missing = [s for s in must if s not in answer]
                detail = f" (falta: {missing})"
            elif not contains_none:
                leaked = [s for s in must_not if s in answer]
                detail = f" (no deberia decir: {leaked})"
            self.stdout.write(f"[{'OK ' if ok else 'MISS'}] {question}{detail}")

        total = len(gold)
        accuracy = hits / total if total else 0.0
        self.stdout.write(self.style.SUCCESS(f"\nSecurity accuracy: {hits}/{total} = {accuracy:.0%}"))

        min_acc = options["min_accuracy"]
        if accuracy < min_acc:
            raise CommandError(
                f"Accuracy {accuracy:.0%} por debajo del umbral {min_acc:.0%}"
            )
