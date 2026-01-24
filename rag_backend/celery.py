import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_backend.settings")

app = Celery("rag_backend")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
