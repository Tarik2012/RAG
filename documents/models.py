from django.conf import settings
from django.db import models
from django.utils import timezone
from pgvector.django import HnswIndex, VectorField

import hashlib


class Document(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    ]
    DOCUMENTATION_STATUS_CHOICES = [
        ("none", "None"),
        ("processing", "Processing"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    original_name = models.CharField(max_length=255)
    source = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Origen del documento, p.ej. 'github:Tarik2012/RAG'. Vacio para subidas manuales.",
    )
    file = models.FileField(upload_to="documents/")
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="uploaded",
    )
    documentation = models.TextField(blank=True, default="")
    documentation_status = models.CharField(
        max_length=20,
        choices=DOCUMENTATION_STATUS_CHOICES,
        default="none",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.original_name


class DocumentChunk(models.Model):
    EMBEDDING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("embedded", "Embedded"),
        ("failed", "Failed"),
    ]

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    order = models.PositiveIntegerField()
    text = models.TextField()

    text_hash = models.CharField(max_length=64, db_index=True)

    embedding = models.JSONField(null=True, blank=True)
    embedding_vector = VectorField(dimensions=1536, null=True, blank=True)

    embedding_status = models.CharField(
        max_length=20,
        choices=EMBEDDING_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    embedding_model = models.CharField(max_length=100, null=True, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "order"],
                name="unique_chunk_order_per_document",
            )
        ]
        indexes = [
            HnswIndex(
                fields=["embedding_vector"],
                name="docchunk_embed_vector_hnsw_idx",
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            )
        ]

    def __str__(self) -> str:
        return f"{self.document.original_name} - chunk {self.order}"

    def compute_text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")

        if update_fields and "text" in update_fields:
            update_fields = set(update_fields)
            update_fields.add("text_hash")
            kwargs["update_fields"] = list(update_fields)

        self.text_hash = self.compute_text_hash()
        super().save(*args, **kwargs)

    def mark_embedded(self, *, model_name: str):
        self.embedding_status = "embedded"
        self.embedding_model = model_name
        self.embedded_at = timezone.now()
        self.save(update_fields=["embedding_status", "embedding_model", "embedded_at"])
