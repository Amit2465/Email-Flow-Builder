from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from app.models.campaign import CampaignModel
from app.services.flow_executor import FlowExecutor
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Request schema matching frontend format
class CampaignRequest(BaseModel):
    campaign: dict
    nodes: List[dict]
    connections: List[dict]
    workflow: dict
    contact_file: dict = None


# Response schema
class CampaignResponse(BaseModel):
    message: str
    campaign_id: str
    campaign_data: dict


# Only essential request/response models for automatic system


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(campaign_data: CampaignRequest):
    """
    Create a new campaign from frontend JSON data
    """
    logger.info("Campaign creation endpoint called")
    logger.info(f"=== FRONTEND DATA RECEIVED ===")
    logger.info(f"Campaign: {campaign_data.campaign}")
    logger.info(f"Nodes count: {len(campaign_data.nodes)}")
    logger.info(f"Connections count: {len(campaign_data.connections)}")
    logger.info(f"Workflow: {campaign_data.workflow}")
    logger.info(f"Contact file: {campaign_data.contact_file}")
    logger.info(f"=== END FRONTEND DATA ===")
    
    try:
        # Extract campaign info
        campaign_info = campaign_data.campaign
        
        # Create campaign document
        campaign = CampaignModel(
            campaign_id=campaign_info.get("id", f"campaign_{int(datetime.now().timestamp() * 1000)}"),
            name=campaign_info.get("name", "Email Campaign Flow"),
            status=campaign_info.get("status", "ready"),
            created_at=datetime.fromisoformat(campaign_info.get("created_at", datetime.now().isoformat()).replace("Z", "+00:00")),
            nodes=campaign_data.nodes,
            connections=campaign_data.connections,
            workflow=campaign_data.workflow,
            contact_file=campaign_data.contact_file
        )
        
        # Save to database
        await campaign.insert()
        
        # Prepare response
        response_data = {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat(),
            "updated_at": campaign.updated_at.isoformat(),
            "nodes": campaign.nodes,
            "connections": campaign.connections,
            "workflow": campaign.workflow,
            "contact_file": campaign.contact_file
        }
        
        logger.info(f"Campaign created successfully: {campaign.campaign_id}")
        
        # Start campaign execution automatically
        try:
            logger.info("=" * 60)
            logger.info("=== AUTOMATIC CAMPAIGN EXECUTION STARTED ===")
            logger.info(f"Campaign ID: {campaign.campaign_id}")
            logger.info("=" * 60)
            
            # Add a small delay to ensure database consistency
            import asyncio
            await asyncio.sleep(0.1)
            
            # Create FlowExecutor and start execution
            executor = FlowExecutor(campaign.campaign_id)
            result = await executor.start_campaign(campaign_data.contact_file)
            
            logger.info("=" * 60)
            logger.info("=== AUTOMATIC CAMPAIGN EXECUTION COMPLETED ===")
            logger.info(f"Campaign ID: {campaign.campaign_id}")
            logger.info(f"Result: {result}")
            logger.info("=" * 60)
            
        except Exception as execution_error:
            logger.error("=" * 60)
            logger.error("=== AUTOMATIC CAMPAIGN EXECUTION FAILED ===")
            logger.error(f"Campaign ID: {campaign.campaign_id}")
            logger.error(f"Error: {str(execution_error)}")
            logger.error("=" * 60)
            # Don't fail the campaign creation, just log the error
        
        return CampaignResponse(
            message="Campaign created successfully",
            campaign_id=campaign.campaign_id,
            campaign_data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error creating campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating campaign: {str(e)}")


# Manual start endpoint removed - campaigns start automatically when created


# Only essential API: campaign creation (which automatically starts execution)
# All other endpoints removed - system is fully automatic

@router.delete("/campaigns/{campaign_id}/cleanup")
async def cleanup_campaign(campaign_id: str):
    """
    Clean up completed campaign data including leads, events, and tasks.
    This endpoint removes old data to prevent database bloat.
    """
    try:
        logger.info(f"[CLEANUP] Starting cleanup for campaign {campaign_id}")
        
        # Check if campaign exists and is completed
        campaign = await CampaignModel.find_one(CampaignModel.campaign_id == campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        if campaign.status != "completed":
            raise HTTPException(status_code=400, detail="Only completed campaigns can be cleaned up")
        
        # Get all leads for this campaign
        from app.models.lead import LeadModel
        all_leads = await LeadModel.find(LeadModel.campaign_id == campaign_id).to_list()
        logger.info(f"[CLEANUP] Found {len(all_leads)} leads to clean up")
        
        # Clean up leads
        deleted_leads = 0
        for lead in all_leads:
            try:
                await lead.delete()
                deleted_leads += 1
            except Exception as e:
                logger.error(f"[CLEANUP] Failed to delete lead {lead.lead_id}: {e}")
        
        # Clean up events
        from app.models.lead_event import LeadEvent
        events = await LeadEvent.find(LeadEvent.campaign_id == campaign_id).to_list()
        deleted_events = 0
        for event in events:
            try:
                await event.delete()
                deleted_events += 1
            except Exception as e:
                logger.error(f"[CLEANUP] Failed to delete event {event.event_id}: {e}")
        
        # Clean up journal entries
        from app.models.lead_journal import LeadJournal
        journal_entries = await LeadJournal.find(LeadJournal.campaign_id == campaign_id).to_list()
        deleted_journals = 0
        for journal in journal_entries:
            try:
                await journal.delete()
                deleted_journals += 1
            except Exception as e:
                logger.error(f"[CLEANUP] Failed to delete journal entry {journal.journal_id}: {e}")
        
        # Revoke any remaining Celery tasks for this campaign
        try:
            from app.celery_config import celery_app
            from celery.task.control import inspect
            
            i = inspect()
            active_tasks = i.active()
            
            if active_tasks:
                for worker, tasks in active_tasks.items():
                    for task in tasks:
                        if campaign_id in str(task.get('args', [])) or campaign_id in str(task.get('kwargs', {})):
                            try:
                                celery_app.control.revoke(task['id'], terminate=True)
                                logger.info(f"[CLEANUP] Revoked task {task['id']} for campaign {campaign_id}")
                            except Exception as e:
                                logger.error(f"[CLEANUP] Failed to revoke task {task['id']}: {e}")
        except Exception as e:
            logger.error(f"[CLEANUP] Failed to revoke Celery tasks: {e}")
        
        logger.info(f"[CLEANUP] Campaign {campaign_id} cleanup completed:")
        logger.info(f"[CLEANUP] - Deleted {deleted_leads} leads")
        logger.info(f"[CLEANUP] - Deleted {deleted_events} events")
        logger.info(f"[CLEANUP] - Deleted {deleted_journals} journal entries")
        
        return {
            "message": "Campaign cleanup completed successfully",
            "campaign_id": campaign_id,
            "deleted_leads": deleted_leads,
            "deleted_events": deleted_events,
            "deleted_journals": deleted_journals
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CLEANUP] Campaign cleanup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign cleanup failed: {str(e)}")
