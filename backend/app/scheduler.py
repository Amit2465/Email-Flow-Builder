import logging
from celery.schedules import crontab
from app.celery_config import celery_app
from app.tasks import recover_stuck_leads_task, cleanup_old_data_task

logger = logging.getLogger(__name__)

# Configure periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    logger.info("Setting up periodic tasks...")
    
    # Recover stuck leads every minute
    sender.add_periodic_task(
        crontab(minute="*"),  # Every minute
        recover_stuck_leads_task.s(),
        name="recover-stuck-leads"
    )
    
    # Clean up old data daily at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),  # Daily at 2:00 AM
        cleanup_old_data_task.s(),
        name="cleanup-old-data"
    )
    
    logger.info("Periodic tasks configured successfully") 