from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0010_backfill_embedding_vector"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="documentchunk",
            index=HnswIndex(
                fields=["embedding_vector"],
                name="docchunk_embed_vector_hnsw_idx",
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            ),
        ),
    ]
