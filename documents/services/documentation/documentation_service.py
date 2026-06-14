from documents.models import Document
from documents.services.extraction.text_extraction import get_document_full_text

MAX_CHARS = 80000
DOC_INSTRUCTIONS = """
Eres un ingeniero senior especializado en modernización de código legacy.
Te dan el contenido de un archivo de código. Genera documentación técnica clara
en Markdown y en español, con esta estructura:

## Resumen
Qué hace el archivo, en 2-3 frases.
## Funciones y clases principales
Lista; qué hace cada una.
## Dependencias
Librerías/módulos externos que usa.
## Riesgos y deuda técnica
Problemas, code smells o prácticas obsoletas que detectes.
## Notas de modernización
Sugerencias concretas de mejora.

Básate ÚNICAMENTE en el código proporcionado. No inventes. Si algo no está claro, dilo.
"""


class DocumentationService:
    def __init__(self, *, llm_provider):
        self.llm_provider = llm_provider

    def generate(self, *, document_id, user) -> dict:
        document = Document.objects.filter(
            id=document_id,
            owner=user,
            status="processed",
        ).first()
        if not document:
            return {"error": "Documento no encontrado o no procesado."}

        text = get_document_full_text(document)
        if not text:
            return {"error": "El documento no tiene contenido legible."}

        truncated = text[:MAX_CHARS]
        if len(text) > MAX_CHARS:
            truncated += "\n\n[Nota: archivo truncado por tamaño.]"

        documentation = self.llm_provider.complete(
            instructions=DOC_INSTRUCTIONS,
            input=truncated,
        )

        return {
            "document_id": document.id,
            "document_name": document.original_name,
            "documentation": documentation,
        }
