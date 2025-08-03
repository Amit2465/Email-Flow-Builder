import os
from celery import Celery

# Hardcoded URLs for Celery services, as they are fixed within the Docker environment.
# This avoids issues with environment variables not being loaded at the right time.
CELERY_BROKER_URL = "amqp://user:password@rabbitmq:5672//"
CELERY_RESULT_BACKEND = "redis://redis:6379/0"

celery_app = Celery(
    "email_builder_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
