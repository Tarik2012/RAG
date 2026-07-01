import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.models import Project
from documents.views import _build_agent_service, _build_agent_messages, _extract_called_tools


class Command(BaseCommand):
    help = "Evalua al agente con un gold set de codigo. Falla si accuracy < umbral."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--project-id", type=int, default=None)
        parser.add_argument("--gold", default="evals/gold_set_code.json")
        parser.add_argument("--min-accuracy", type=float, default=0.0,
                            help="Umbral minimo (0-1). Si accuracy < umbral, exit code 1.")
        parser.add_argument("--debug-file", default=None,
                            help="Si se indica, vuelca a este archivo la respuesta del agente en los casos MISS.")

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
        debug_lines = []

        snippet_hits = 0
        both_hits = 0
        tool_hits = 0
        tool_cases = 0

        for item in gold:
            question = item["question"]
            snippets = [s.lower() for s in item["expected_snippets"]]
            expected_tools = item.get("expected_tools") or (
                [item["expected_tool"]] if item.get("expected_tool") else []
            )
            result = agent.invoke(
                {"messages": _build_agent_messages(user=user, question=question, project=project)}
            )
            tools_used = _extract_called_tools(result)
            answer = result["messages"][-1].content.lower()
            snippet_ok = any(s in answer for s in snippets)
            tool_ok = (not expected_tools) or any(t in tools_used for t in expected_tools)
            if (not snippet_ok or (expected_tools and not tool_ok)) and options.get("debug_file"):
                debug_lines.append(
                    f"=== {question}\n"
                    f"SNIP_OK={snippet_ok} TOOL_OK={tool_ok}\n"
                    f"expected_snippets={snippets}\n"
                    f"expected_tools={expected_tools}\n"
                    f"tools_used={tools_used}\n"
                    f"answer={answer}\n"
                )

            snippet_hits += 1 if snippet_ok else 0
            if expected_tools:
                tool_cases += 1
                tool_hits += 1 if tool_ok else 0
            if snippet_ok and tool_ok:
                both_hits += 1

            tool_status = "N/A" if not expected_tools else ("OK" if tool_ok else "MISS")
            self.stdout.write(
                f"[SNIP {'OK ' if snippet_ok else 'MISS'} | TOOL {tool_status}] {question}"
            )

        total = len(gold)
        accuracy = snippet_hits / total if total else 0.0
        tool_accuracy = tool_hits / tool_cases if tool_cases else 0.0
        both_accuracy = both_hits / total if total else 0.0

        if options.get("debug_file") and debug_lines:
            Path(options["debug_file"]).write_text("\n".join(debug_lines), encoding="utf-8")
            self.stdout.write(f"Debug de MISS escrito en {options['debug_file']}")

        self.stdout.write(
            self.style.SUCCESS(f"\nSnippet accuracy: {snippet_hits}/{total} = {accuracy:.0%}")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Tool accuracy: {tool_hits}/{tool_cases} = {tool_accuracy:.0%} "
                f"(solo casos con expected_tool)"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"Both correct: {both_hits}/{total} = {both_accuracy:.0%}")
        )

        min_acc = options["min_accuracy"]
        if accuracy < min_acc:
            raise CommandError(
                f"Accuracy {accuracy:.0%} por debajo del umbral {min_acc:.0%}"
            )
