from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0007_document_unique_active_document_per_owner"),
    ]

    operations = [
        VectorExtension(),
    ]
