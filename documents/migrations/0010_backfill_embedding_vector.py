from django.db import migrations


def copy_embeddings(apps, schema_editor):
    DocumentChunk = apps.get_model("documents", "DocumentChunk")
    for chunk in DocumentChunk.objects.filter(
        embedding__isnull=False,
        embedding_vector__isnull=True,
    ).iterator():
        chunk.embedding_vector = chunk.embedding
        chunk.save(update_fields=["embedding_vector"])


def reverse(apps, schema_editor):
    DocumentChunk = apps.get_model("documents", "DocumentChunk")
    DocumentChunk.objects.update(embedding_vector=None)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0009_documentchunk_embedding_vector"),
    ]

    operations = [
        migrations.RunPython(copy_embeddings, reverse),
    ]
