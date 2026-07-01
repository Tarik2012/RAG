from django.conf import settings
from django.db import models
from django.utils import timezone
from pgvector.django import HnswIndex, VectorField

import hashlib


class Project(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.user})"


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
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="conversations",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation {self.pk} ({self.user})"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tool_calls = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ProjectMemory(models.Model):
    """Un hallazgo estructurado y persistente sobre un proyecto."""

    CATEGORY_BUG = "bug"
    CATEGORY_VULNERABILITY = "vulnerability"
    CATEGORY_ARCHITECTURE = "architecture"
    CATEGORY_LIMITATION = "limitation"
    CATEGORY_DECISION = "decision"
    CATEGORY_AUDIT_SUMMARY = "audit_summary"
    CATEGORY_CHOICES = [
        (CATEGORY_BUG, "Bug"),
        (CATEGORY_VULNERABILITY, "Vulnerability"),
        (CATEGORY_ARCHITECTURE, "Architecture decision"),
        (CATEGORY_LIMITATION, "Known limitation"),
        (CATEGORY_DECISION, "User decision"),
        (CATEGORY_AUDIT_SUMMARY, "Audit summary"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_RESOLVED = "resolved"
    STATUS_OBSOLETE = "obsolete"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_OBSOLETE, "Obsolete"),
    ]

    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="memories",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memories",
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="El detalle del hallazgo.")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Huella para deduplicar (hash de project+category+archivo+resumen).",
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Prueba: archivo, simbolo, lineas, tool que lo origino.",
    )
    times_seen = models.PositiveIntegerField(default=1)
    source_conversation = models.ForeignKey(
        "Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memories_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "Project memories"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "fingerprint"],
                name="unique_project_memory_fingerprint",
            )
        ]

    def __str__(self):
        return f"[{self.category}] {self.title} (project {self.project_id})"


class AuditRun(models.Model):
    """Una ejecucion de auditoria de seguridad sobre todo un proyecto. Fuente de verdad del
    estado y el resultado, para ejecucion async (Celery) y seguimiento (polling)."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="audit_runs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="audit_runs",
    )
    conversation = models.ForeignKey(
        "Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_runs",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    total_files = models.PositiveIntegerField(default=0)
    scanned_files = models.PositiveIntegerField(default=0)
    findings_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    result_json = models.JSONField(default=dict, blank=True)
    error_text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AuditRun {self.pk} [{self.status}] project {self.project_id}"
