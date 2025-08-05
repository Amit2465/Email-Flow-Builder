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
