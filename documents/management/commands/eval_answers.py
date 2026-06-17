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
    "You are a strict RAG evaluator. You are given a QUESTION, the CONTEXT passages "
    "retrieved from the user's documents, and an ANSWER generated from that context. "
    "Score two dimensions from 1 to 5:\n"
    "- faithfulness: is the ANSWER fully supported by the CONTEXT (no invented facts)? "
    "5 = every claim is supported, 1 = mostly hallucinated.\n"
    "- relevancy: does the ANSWER actually address the QUESTION? "
    "5 = fully answers it, 1 = off-topic.\n"
    "Return ONLY a compact JSON object like {\"faithfulness\": X, \"relevancy\": Y} with no extra text."
)


class Command(BaseCommand):
    help = "Evalua faithfulness y relevancy de respuestas RAG con un LLM juez."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--top-k", type=int, default=6)
        parser.add_argument("--gold", default="evals/gold_set.json")

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
        service = _build_ask_service()
        retriever = service.retriever
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        faith_scores = []
        rel_scores = []
        for item in gold:
            question = item["question"]
            results = retriever.retrieve(query=question, user=user, top_k=top_k)
            context = "\n\n".join(chunk.text for chunk, _ in results)

            # Generar respuesta desde el contexto (RAG simple, modelo del agente)
            answer_resp = client.responses.create(
                model=settings.OPENAI_AGENT_MODEL,
                temperature=0,
                instructions="Answer the question using ONLY the provided context. Be concise.",
                input=f"CONTEXT:\n{context}\n\nQUESTION: {question}",
            )
            answer = (answer_resp.output_text or "").strip()

            # Juez
            judge_resp = client.responses.create(
                model=settings.OPENAI_JUDGE_MODEL,
                temperature=0,
                instructions=JUDGE_INSTRUCTIONS,
                input=f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\nANSWER: {answer}",
            )
            raw = (judge_resp.output_text or "").strip()
            try:
                scores = json.loads(raw)
                f = float(scores.get("faithfulness", 0))
                r = float(scores.get("relevancy", 0))
            except Exception:
                logger.warning("No se pudo parsear juicio: %s", raw)
                f = r = 0.0
            faith_scores.append(f)
            rel_scores.append(r)
            self.stdout.write(f"[F={f:.0f} R={r:.0f}] {question}")

        n = len(gold) or 1
        avg_f = sum(faith_scores) / n
        avg_r = sum(rel_scores) / n
        self.stdout.write(self.style.SUCCESS(f"\nFaithfulness media: {avg_f:.2f}/5"))
        self.stdout.write(self.style.SUCCESS(f"Relevancy media: {avg_r:.2f}/5"))
