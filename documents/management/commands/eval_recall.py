import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.views import _build_ask_service


class Command(BaseCommand):
    help = "Mide recall@k del retrieval contra un gold set."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="username dueño del documento activo")
        parser.add_argument("--top-k", type=int, default=6)
        parser.add_argument("--gold", default="evals/gold_set.json")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"Usuario '{options['user']}' no existe")

        gold = json.loads(Path(options["gold"]).read_text(encoding="utf-8"))
        top_k = options["top_k"]
        retriever = _build_ask_service().retriever

        hits = 0
        for item in gold:
            question = item["question"]
            snippets = [s.lower() for s in item["expected_snippets"]]
            results = retriever.retrieve(query=question, user=user, top_k=top_k)
            chunks_text = " ".join(chunk.text.lower() for chunk, _ in results)
            found = any(s in chunks_text for s in snippets)
            hits += 1 if found else 0
            self.stdout.write(f"[{'OK ' if found else 'MISS'}] {question}")

        total = len(gold)
        recall = hits / total if total else 0.0
        self.stdout.write(self.style.SUCCESS(f"\nRecall@{top_k}: {hits}/{total} = {recall:.0%}"))
