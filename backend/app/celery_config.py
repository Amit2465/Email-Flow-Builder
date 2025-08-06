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
    # Better error handling and retry settings
    task_always_eager=False,
    task_eager_propagates=True,
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    # Worker settings
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    # Result backend settings
    result_expires=3600,  # 1 hour
    # Connection error handling
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    result_backend_transport_options={
        'retry_on_timeout': True,
        'max_retries': 3,
    }
)
