import asyncio
from celery.signals import worker_process_init
from app.celery_config import celery_app
from app.db.init import init_db
import logging

# This file is the entry point for the Celery worker.
# It imports the celery_app instance, and the tasks are discovered
# from the `include` parameter in the Celery configuration.

logger = logging.getLogger(__name__)

@worker_process_init.connect
def on_worker_init(**kwargs):
    """
    Initialize the database connection when a Celery worker process starts.
    This ensures that Beanie models are ready to be used within tasks.
    """
    logger.info("Celery worker process initializing...")
    try:
        asyncio.run(init_db())
        logger.info("Database connection initialized for Celery worker.")
    except Exception as e:
        logger.error(f"Failed to initialize database for Celery worker: {e}", exc_info=True)
        # Depending on the desired behavior, you might want to exit the worker
        # if the database connection is critical for all tasks.
        # For now, we log the error and let it continue.
        pass

# The 'celery' variable is automatically detected by Celery
# as long as it's an instance of the Celery class.
celery = celery_app
