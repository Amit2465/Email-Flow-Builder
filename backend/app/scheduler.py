from celery.schedules import crontab
from app.celery_config import celery_app
from app.tasks import recover_stuck_leads_task

# Configure periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks for the application."""
    
    # Schedule stuck leads recovery every minute
    sender.add_periodic_task(
        crontab(minute='*'),  # Every minute
        recover_stuck_leads_task.s(),
        name='recover-stuck-leads-every-minute'
    )
    
    print("✅ Periodic tasks configured:")
    print("   - recover_stuck_leads_task: every minute") 