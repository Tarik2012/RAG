import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

from documents.services.router import classify_intent


class Command(BaseCommand):
    help = "Evalua el router de intención contra un gold set."

    def add_arguments(self, parser):
        parser.add_argument("--gold", default="evals/gold_set_router.json")

    def handle(self, *args, **options):
        gold = json.loads(Path(options["gold"]).read_text(encoding="utf-8"))

        total = len(gold)
        hits = 0
        correct_by_label = defaultdict(int)
        total_by_label = defaultdict(int)
        misses: list[str] = []

        for item in gold:
            question = item["question"]
            expected = item["expected"]
            got = classify_intent(question)

            total_by_label[expected] += 1

            if got == expected:
                hits += 1
                correct_by_label[expected] += 1
            else:
                misses.append(
                    f"MISS: {question} | esperado={expected} | obtenido={got}"
                )

        accuracy = (hits / total * 100.0) if total else 0.0

        self.stdout.write(f"Total: {total}")
        self.stdout.write(f"Aciertos: {hits}")
        self.stdout.write(f"Accuracy: {accuracy:.2f}%")
        self.stdout.write("")
        self.stdout.write("Desglose por etiqueta:")
        self.stdout.write(
            f"rag: {correct_by_label['rag']}/{total_by_label['rag']} correctos"
        )
        self.stdout.write(
            f"agent: {correct_by_label['agent']}/{total_by_label['agent']} correctos"
        )
        self.stdout.write("")
        self.stdout.write("Fallos:")
        if misses:
            for miss in misses:
                self.stdout.write(miss)
        else:
            self.stdout.write("Ninguno.")
