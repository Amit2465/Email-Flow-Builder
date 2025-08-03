import asyncio
import logging

from app.celery_config import celery_app
from app.db.init import init_db  # Import the db initializer
from app.services.email import send_email_with_tracking

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.send_email_task")
def send_email_task(
    lead_id: str, campaign_id: str, subject: str, body: str, recipient_email: str
):
    """
    Celery task to send an email with tracking.
    """
    try:
        logger.info(f"Executing send_email_task for lead {lead_id}")
        send_email_with_tracking(
            subject=subject,
            body=body,
            recipient_email=recipient_email,
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
    except Exception as e:
        logger.error(
            f"Error sending email in background task for lead {lead_id}: {e}",
            exc_info=True,
        )
        raise


@celery_app.task(name="app.tasks.resume_lead_task")
def resume_lead_task(lead_id: str, campaign_id: str):
    """
    Celery task to resume a lead's execution after a WAIT node.
    This task does NOT pass condition_met parameter - it's only for wait nodes.
    """
    # Import inside the task to avoid circular dependencies
    from app.services.flow_executor import FlowExecutor

    async def resume():
        # Initialize a fresh DB connection for this async task
        await init_db()

        logger.info(
            f"Executing resume_lead_task for lead {lead_id} in campaign {campaign_id}"
        )
        executor = FlowExecutor(campaign_id)
        await executor.load_campaign()

        # Call resume_lead WITHOUT condition_met parameter (for wait nodes)
        await executor.resume_lead(lead_id=lead_id)
        logger.info(f"Successfully resumed lead {lead_id}")

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(
            f"Error resuming lead {lead_id} in background task: {e}", exc_info=True
        )
        raise


@celery_app.task(name="app.tasks.resume_condition_task")
def resume_condition_task(lead_id: str, campaign_id: str, condition_met: bool = False):
    """
    Celery task to resume a lead's execution after a CONDITION node.
    This task passes the condition_met parameter for condition node branching.
    """
    # Import inside the task to avoid circular dependencies
    from app.services.flow_executor import FlowExecutor

    async def resume():
        # Initialize a fresh DB connection for this async task
        await init_db()

        logger.info(
            f"Executing resume_condition_task for lead {lead_id} in campaign {campaign_id}, condition_met: {condition_met}"
        )
        executor = FlowExecutor(campaign_id)
        await executor.load_campaign()

        # Call resume_lead WITH condition_met parameter (for condition nodes)
        await executor.resume_lead(lead_id=lead_id, condition_met=condition_met)
        logger.info(
            f"Successfully resumed lead {lead_id} with condition_met={condition_met}"
        )

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(
            f"Error resuming condition lead {lead_id} in background task: {e}",
            exc_info=True,
        )
        raise
