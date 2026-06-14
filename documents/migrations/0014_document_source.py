from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0013_document_documentation_document_documentation_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="source",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Origen del documento, p.ej. 'github:Tarik2012/RAG'. Vacio para subidas manuales.",
                max_length=255,
            ),
        ),
    ]
