import asyncio
import logging

from app.celery_config import celery_app
from app.db.init import init_db
from app.services.email import send_email_with_tracking

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.send_email_task", acks_late=True, max_retries=3)
def send_email_task(
    lead_id: str, campaign_id: str, subject: str, body: str, recipient_email: str, node_id: str
):
    """
    Celery task to send an email. Node completion is handled by the flow executor.
    """
    try:
        logger.info(f"Executing send_email_task for lead {lead_id} from node {node_id}")
        
        # Send the email
        send_email_with_tracking(
            subject=subject,
            body=body,
            recipient_email=recipient_email,
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
        
        # Node completion is now handled by the flow executor to prevent race conditions
        logger.info(f"Successfully processed send_email_task for lead {lead_id}")

    except Exception as e:
        logger.error(f"Error in send_email_task for lead {lead_id}: {e}", exc_info=True)
        # Celery will retry the task based on the max_retries setting
        raise


@celery_app.task(name="app.tasks.resume_lead_task")
def resume_lead_task(lead_id: str, campaign_id: str):
    """
    Celery task to resume a lead's execution after a WAIT node.
    """
    from app.services.flow_executor import FlowExecutor

    async def resume():
        await init_db()
        logger.info(f"Executing resume_lead_task for lead {lead_id}")
        executor = FlowExecutor(campaign_id)
        # Call resume_lead for wait nodes (condition_met is None)
        await executor.resume_lead(lead_id=lead_id)

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(f"Error resuming lead {lead_id}: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.resume_condition_task")
def resume_condition_task(lead_id: str, campaign_id: str, condition_met: bool = False):
    """
    Celery task to resume a lead's execution after a CONDITION node.
    """
    from app.services.flow_executor import FlowExecutor

    async def resume():
        await init_db()
        logger.info(f"Executing resume_condition_task for lead {lead_id}, condition_met: {condition_met}")
        executor = FlowExecutor(campaign_id)
        # Call resume_lead with the condition_met parameter
        await executor.resume_lead(lead_id=lead_id, condition_met=condition_met)

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(f"Error resuming condition lead {lead_id}: {e}", exc_info=True)
        raise