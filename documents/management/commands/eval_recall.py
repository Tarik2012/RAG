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
        reciprocal_ranks = []
        for item in gold:
            question = item["question"]
            snippets = [s.lower() for s in item["expected_snippets"]]
            results = retriever.retrieve(query=question, user=user, top_k=top_k)

            # Buscar la posicion (1-indexed) del primer chunk que contiene un snippet esperado
            rank = 0
            for idx, (chunk, _) in enumerate(results, start=1):
                text = chunk.text.lower()
                if any(s in text for s in snippets):
                    rank = idx
                    break

            found = rank > 0
            hits += 1 if found else 0
            reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

            pos = f"pos {rank}" if rank > 0 else "no encontrado"
            self.stdout.write(f"[{'OK ' if found else 'MISS'}] ({pos}) {question}")

        total = len(gold)
        recall = hits / total if total else 0.0
        mrr = sum(reciprocal_ranks) / total if total else 0.0
        self.stdout.write(self.style.SUCCESS(f"\nRecall@{top_k}: {hits}/{total} = {recall:.0%}"))
        self.stdout.write(self.style.SUCCESS(f"MRR@{top_k}: {mrr:.3f}"))
