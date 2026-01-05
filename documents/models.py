from django.conf import settings
from django.db import models


class Document(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="uploaded",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.original_name


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    order = models.PositiveIntegerField()
    text = models.TextField()

    # Embedding se añadirá en la siguiente fase (RAG)
    embedding = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "order"],
                name="unique_chunk_order_per_document",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document.original_name} · chunk {self.order}"
