from django.contrib import admin
from django.db.models import Count

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_name",
        "owner",
        "content_type",
        "size",
        "status",
        "created_at",
        "chunks_count",
    )

    list_select_related = ("owner",)

    list_filter = (
        "status",
        "content_type",
        "created_at",
    )

    search_fields = (
        "original_name",
        "owner__username",
    )

    readonly_fields = (
        "created_at",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(chunks_count=Count("chunks"))

    def chunks_count(self, obj):
        return obj.chunks_count

    chunks_count.short_description = "Chunks"


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "order",
        "created_at",
    )

    list_select_related = ("document",)

    list_filter = (
        "document",
    )

    search_fields = (
        "document__original_name",
        "text",
    )
