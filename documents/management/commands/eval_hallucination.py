import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from openai import OpenAI

from documents.views import _build_ask_service

logger = logging.getLogger(__name__)

JUDGE_INSTRUCTIONS = (
    "You are evaluating whether an AI answer hallucinated. You get a QUESTION whose answer is NOT "
    "in the user's documents, the CONTEXT that was retrieved, and the ANSWER given. "
    "Decide if the ANSWER correctly admits it does not have the information / it is not in the documents (GOOD), "
    "or if it invents a specific factual answer (HALLUCINATION). "
    "Return ONLY one word: GOOD or HALLUCINATION."
)


class Command(BaseCommand):
    help = "Mide alucinaciones: preguntas sin respuesta en los docs."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--top-k", type=int, default=6)
        parser.add_argument("--gold", default="evals/gold_set_traps.json")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"Usuario '{options['user']}' no existe")

        if not settings.OPENAI_API_KEY:
            raise CommandError("Falta OPENAI_API_KEY")

        gold = json.loads(Path(options["gold"]).read_text(encoding="utf-8"))
        top_k = options["top_k"]
        retriever = _build_ask_service().retriever
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        good = 0
        for item in gold:
            question = item["question"]
            results = retriever.retrieve(query=question, user=user, top_k=top_k)
            context = "\n\n".join(chunk.text for chunk, _ in results)

            answer_resp = client.responses.create(
                model=settings.OPENAI_AGENT_MODEL,
                temperature=0,
                instructions="Answer the question using ONLY the provided context. If the answer is not in the context, say you don't have that information.",
                input=f"CONTEXT:\n{context}\n\nQUESTION: {question}",
            )
            answer = (answer_resp.output_text or "").strip()

            judge_resp = client.responses.create(
                model=settings.OPENAI_JUDGE_MODEL,
                temperature=0,
                instructions=JUDGE_INSTRUCTIONS,
                input=f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\nANSWER: {answer}",
            )
            verdict = (judge_resp.output_text or "").strip().upper()
            is_good = "GOOD" in verdict
            good += 1 if is_good else 0
            self.stdout.write(f"[{'GOOD' if is_good else 'HALLUC'}] {question}")

        n = len(gold) or 1
        rate = good / n
        self.stdout.write(self.style.SUCCESS(f"\nNo-alucinacion: {good}/{n} = {rate:.0%}"))
