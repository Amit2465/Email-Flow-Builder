import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.celery_config import celery_app
from app.db.init import init_db
from app.services.email import send_email_with_tracking
from app.models.lead import LeadModel

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.send_email_task", acks_late=True, max_retries=3)
def send_email_task(
    lead_id: str, campaign_id: str, subject: str, body: str, recipient_email: str, node_id: str
):
    from app.tasks import resume_lead_task  
    from app.db.init import init_db
    from app.services.email import send_email_with_tracking
    import time

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

        logger.info(f"Successfully processed send_email_task for lead {lead_id}")

        # ✅ CRITICAL: Longer delay to ensure lead state is properly established
        time.sleep(1.0)
        
        # ✅ Trigger continuation of the flow
        resume_lead_task.delay(lead_id, campaign_id)

    except Exception as e:
        logger.error(f"Error in send_email_task for lead {lead_id}: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.resume_lead_task", acks_late=True, max_retries=3)
def resume_lead_task(lead_id: str, campaign_id: str):
    """
    Celery task to resume a lead's execution after a WAIT node or EMAIL node.
    """
    from app.services.flow_executor import FlowExecutor

    async def resume():
        await init_db()
        logger.info(f"Executing resume_lead_task for lead {lead_id}")
        executor = FlowExecutor(campaign_id)
        # Call resume_lead for wait nodes and email nodes (condition_met is None)
        await executor.resume_lead(lead_id=lead_id)

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(f"Error resuming lead {lead_id}: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.resume_condition_task", acks_late=True, max_retries=3)
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


@celery_app.task(name="app.tasks.recover_stuck_leads_task", acks_late=True, max_retries=3)
def recover_stuck_leads_task():
    """
    Celery task to recover leads that are stuck in paused state for too long.
    Runs every minute to check for stuck leads and resume them.
    """
    from app.services.flow_executor import FlowExecutor

    async def recover():
        await init_db()
        logger.info("Executing recover_stuck_leads_task")
        
        # Find leads that have been paused for more than 5 minutes
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        stuck_leads = await LeadModel.find({
            "status": "paused",
            "updated_at": {"$lt": cutoff_time}
        }).to_list()
        
        # Also check for leads with scheduled tasks that are overdue
        overdue_leads = await LeadModel.find({
            "status": "paused",
            "scheduled_task_id": {"$exists": True, "$ne": None},
            "wait_until": {"$lt": datetime.now(timezone.utc)}
        }).to_list()
        
        # Combine and deduplicate
        all_stuck_leads = {lead.lead_id: lead for lead in stuck_leads + overdue_leads}.values()
        
        if not all_stuck_leads:
            logger.info("No stuck leads found")
            return
        
        logger.info(f"Found {len(all_stuck_leads)} stuck leads, attempting recovery")
        
        recovered_count = 0
        for lead in all_stuck_leads:
            try:
                logger.info(f"Attempting to recover stuck lead {lead.lead_id}")
                executor = FlowExecutor(lead.campaign_id)
                await executor.resume_lead(lead_id=lead.lead_id)
                recovered_count += 1
                logger.info(f"Successfully recovered lead {lead.lead_id}")
            except Exception as e:
                logger.error(f"Failed to recover lead {lead.lead_id}: {e}", exc_info=True)
        
        logger.info(f"Recovery completed: {recovered_count}/{len(all_stuck_leads)} leads recovered")

    try:
        asyncio.run(recover())
    except Exception as e:
        logger.error(f"Error in recover_stuck_leads_task: {e}", exc_info=True)
        raise