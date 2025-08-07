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
    lead_id: str, campaign_id: str, subject: str, body: str, recipient_email: str, node_id: str, links: list = None, add_tracking_link: bool = False
):
    from app.tasks import resume_lead_task  
    from app.db.init import init_db
    from app.services.email import send_email_with_tracking
    import time

    try:
        logger.info(f"=== SEND_EMAIL_TASK STARTED ===")
        logger.info(f"Lead ID: {lead_id}")
        logger.info(f"Campaign ID: {campaign_id}")
        logger.info(f"Node ID: {node_id}")
        logger.info(f"Recipient: {recipient_email}")
        logger.info(f"Subject: {subject}")

        # Send the email with proper error handling
        try:
            send_email_with_tracking(
                subject=subject,
                body=body,
                recipient_email=recipient_email,
                lead_id=lead_id,
                campaign_id=campaign_id,
                links=links,
                add_tracking_link=add_tracking_link,
            )
            logger.info(f"Successfully sent email for lead {lead_id}")
        except Exception as email_error:
            logger.error(f"Failed to send email for lead {lead_id}: {email_error}", exc_info=True)
            # Don't trigger resume if email failed
            raise

        # ✅ CRITICAL: Shorter delay to ensure lead state is properly established
        time.sleep(0.5)
        
                # ✅ CRITICAL: Shorter delay to ensure lead state is properly established
        time.sleep(0.5)
        
        # ✅ Trigger continuation of the flow
        logger.info(f"Triggering resume_lead_task for lead {lead_id}")
        resume_lead_task.delay(lead_id, campaign_id)
        logger.info(f"=== SEND_EMAIL_TASK COMPLETED ===")

    except Exception as e:
        logger.error(f"=== SEND_EMAIL_TASK FAILED ===")
        logger.error(f"Lead ID: {lead_id}")
        logger.error(f"Campaign ID: {campaign_id}")
        logger.error(f"Error: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.resume_lead_task", acks_late=True, max_retries=3)
def resume_lead_task(lead_id: str, campaign_id: str):
    """
    Celery task to resume a lead's execution after a WAIT node or EMAIL node.
    """
    from app.services.flow_executor import FlowExecutor

    async def resume():
        await init_db()
        logger.info(f"=== RESUME_LEAD_TASK STARTED ===")
        logger.info(f"Lead ID: {lead_id}")
        logger.info(f"Campaign ID: {campaign_id}")
        logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        
        # ✅ CRITICAL FIX: Check if an event has already occurred before resuming
        from app.models.lead_event import LeadEvent
        from app.models.lead import LeadModel
        
        # Check for recent processed events (only if they occurred very recently)
        recent_event = await LeadEvent.find_one({
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "processed": True
        }, sort=[("processed_at", -1)])
        
        if recent_event:
            # Only skip if the event occurred in the last 10 seconds (very recent)
            # This prevents skipping during normal campaign execution
            from datetime import timedelta
            event_age = datetime.now(timezone.utc) - recent_event.processed_at
            if event_age < timedelta(seconds=10):
                logger.info(f"Recent event occurred for lead {lead_id}, skipping resume_lead_task to prevent duplicates")
                logger.info(f"Recent event: {recent_event.event_type} at {recent_event.processed_at} (age: {event_age})")
                return
            else:
                logger.info(f"Event occurred but is old ({event_age}), allowing resume_lead_task to continue")
        
        # Check if lead is already being processed by condition task
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if lead and lead.status == "running":
            logger.info(f"Lead {lead_id} is already running, skipping resume_lead_task")
            return
        
        executor = FlowExecutor(campaign_id)
        # Call resume_lead for wait nodes and email nodes (condition_met is None)
        await executor.resume_lead(lead_id=lead_id)
        
        logger.info(f"=== RESUME_LEAD_TASK COMPLETED ===")

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(f"=== RESUME_LEAD_TASK FAILED ===")
        logger.error(f"Lead ID: {lead_id}")
        logger.error(f"Campaign ID: {campaign_id}")
        logger.error(f"Error: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.resume_condition_task", acks_late=True, max_retries=3)
def resume_condition_task(lead_id: str, campaign_id: str, condition_met: bool = False):
    """
    Celery task to resume a lead's execution after a CONDITION node.
    Enhanced for immediate execution when events occur.
    """
    from app.services.flow_executor import FlowExecutor

    async def resume():
        await init_db()
        logger.info(f"=== CONDITION_RESUME_TASK STARTED ===")
        logger.info(f"Lead ID: {lead_id}")
        logger.info(f"Campaign ID: {campaign_id}")
        logger.info(f"Condition Met: {condition_met}")
        logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        
        executor = FlowExecutor(campaign_id)
        
        if condition_met:
            # Find the specific condition node that was triggered
            from app.services.event_tracker import EventTracker
            event_tracker = EventTracker(campaign_id)
            
            # Get the most recent processed event for this lead
            from app.models.lead_event import LeadEvent
            recent_event = await LeadEvent.find_one({
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "processed": True
            }, sort=[("processed_at", -1)])
            
            if recent_event:
                logger.info(f"Found recent event for condition node: {recent_event.condition_node_id}")
                await executor.load_campaign()
                
                # ✅ CRITICAL FIX: Cancel any pending resume_lead_task to prevent duplicates
                from app.models.lead import LeadModel
                lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
                if lead and lead.scheduled_task_id:
                    try:
                        from app.celery_config import celery_app
                        celery_app.control.revoke(lead.scheduled_task_id, terminate=True)
                        logger.info(f"Cancelled pending resume_lead_task: {lead.scheduled_task_id}")
                        lead.scheduled_task_id = None
                        await lead.save()
                    except Exception as e:
                        logger.warning(f"Failed to cancel pending task: {e}")
                
                await executor.resume_lead_from_condition(
                    lead_id=lead_id, 
                    condition_node_id=recent_event.condition_node_id, 
                    condition_met=True
                )
            else:
                logger.warning(f"No recent event found for lead {lead_id}, using general resume")
                await executor.resume_lead(lead_id=lead_id, condition_met=condition_met)
        else:
            # General resume for non-event scenarios
            await executor.resume_lead(lead_id=lead_id, condition_met=condition_met)
        
        logger.info(f"=== CONDITION_RESUME_TASK COMPLETED ===")

    try:
        asyncio.run(resume())
    except Exception as e:
        logger.error(f"=== CONDITION_RESUME_TASK FAILED ===")
        logger.error(f"Lead ID: {lead_id}")
        logger.error(f"Campaign ID: {campaign_id}")
        logger.error(f"Error: {e}", exc_info=True)
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


@celery_app.task(name="app.tasks.cleanup_old_data_task", acks_late=True, max_retries=3)
def cleanup_old_data_task():
    """
    Celery task to automatically clean up old campaign data.
    Runs periodically to prevent database bloat.
    """
    from app.models.campaign import CampaignModel
    from app.models.lead import LeadModel
    from app.models.lead_event import LeadEvent
    from app.models.lead_journal import LeadJournal

    async def cleanup():
        await init_db()
        logger.info("=== AUTOMATIC CLEANUP TASK STARTED ===")
        
        # Find campaigns completed more than 7 days ago
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        
        old_campaigns = await CampaignModel.find({
            "status": "completed",
            "completed_at": {"$lt": cutoff_date}
        }).to_list()
        
        if not old_campaigns:
            logger.info("No old campaigns found for cleanup")
            return
        
        logger.info(f"Found {len(old_campaigns)} old campaigns for cleanup")
        
        total_deleted_leads = 0
        total_deleted_events = 0
        total_deleted_journals = 0
        
        for campaign in old_campaigns:
            try:
                logger.info(f"Cleaning up campaign {campaign.campaign_id}")
                
                # Delete leads
                leads_result = await LeadModel.delete_many({"campaign_id": campaign.campaign_id})
                deleted_leads = leads_result.deleted_count
                total_deleted_leads += deleted_leads
                
                # Delete events
                events_result = await LeadEvent.delete_many({"campaign_id": campaign.campaign_id})
                deleted_events = events_result.deleted_count
                total_deleted_events += deleted_events
                
                # Delete journal entries
                journals_result = await LeadJournal.delete_many({"campaign_id": campaign.campaign_id})
                deleted_journals = journals_result.deleted_count
                total_deleted_journals += deleted_journals
                
                # Delete the campaign itself
                await campaign.delete()
                
                logger.info(f"Campaign {campaign.campaign_id} cleanup completed: {deleted_leads} leads, {deleted_events} events, {deleted_journals} journals")
                
            except Exception as e:
                logger.error(f"Failed to cleanup campaign {campaign.campaign_id}: {e}")
        
        logger.info(f"=== AUTOMATIC CLEANUP COMPLETED ===")
        logger.info(f"Total deleted: {total_deleted_leads} leads, {total_deleted_events} events, {total_deleted_journals} journals")
        
        # Also clean up orphaned events and journals (no matching campaign)
        try:
            # Find all campaign IDs
            campaign_ids = await CampaignModel.distinct("campaign_id")
            
            # Delete events for non-existent campaigns
            orphaned_events_result = await LeadEvent.delete_many({
                "campaign_id": {"$nin": campaign_ids}
            })
            
            # Delete journals for non-existent campaigns
            orphaned_journals_result = await LeadJournal.delete_many({
                "campaign_id": {"$nin": campaign_ids}
            })
            
            if orphaned_events_result.deleted_count > 0 or orphaned_journals_result.deleted_count > 0:
                logger.info(f"Cleaned up {orphaned_events_result.deleted_count} orphaned events and {orphaned_journals_result.deleted_count} orphaned journals")
                
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned data: {e}")

    try:
        asyncio.run(cleanup())
    except Exception as e:
        logger.error(f"=== AUTOMATIC CLEANUP TASK FAILED ===")
        logger.error(f"Error: {e}", exc_info=True)
        raise