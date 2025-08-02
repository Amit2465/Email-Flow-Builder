from fastapi import APIRouter, HTTPException, Query
from app.models.lead import LeadModel
from app.services.flow_executor import FlowExecutor
import logging
from datetime import datetime
from fastapi.responses import Response, RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/track/open")
async def track_email_open(
    lead_id: str = Query(..., description="Lead ID from tracking pixel"),
    campaign_id: str = Query(..., description="Campaign ID from tracking pixel")
):
    """
    Track email opens via tracking pixel and resume lead execution
    """
    try:
        logger.info(f"Email open tracked for lead {lead_id} in campaign {campaign_id}")
        
        # Find the lead
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            logger.warning(f"Lead {lead_id} not found for campaign {campaign_id}")
            raise HTTPException(status_code=404, detail="Lead not found")
            
        # Check if lead is paused waiting for email open
        if lead.status == "paused" and lead.next_node:
            logger.info(f"Lead {lead_id} is paused waiting for email open")
            
            # Resume execution with condition met
            executor = FlowExecutor(campaign_id)
            await executor.load_campaign()
            await executor.resume_lead(lead_id, condition_met=True)
            
            logger.info(f"Resumed lead {lead_id} after email open")
        else:
            logger.info(f"Lead {lead_id} is not paused or no next_node set")
            
        # Return tracking pixel (1x1 transparent GIF)
        tracking_pixel = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff'
            b'\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
            b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        )
        
        return Response(
            content=tracking_pixel,
            media_type="image/gif",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        logger.error(f"Error tracking email open for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/track/click")
async def track_email_click(
    lead_id: str = Query(..., description="Lead ID from click tracking"),
    campaign_id: str = Query(..., description="Campaign ID from click tracking"),
    url: str = Query(..., description="URL that was clicked")
):
    """
    Track email clicks and redirect to original URL
    """
    try:
        logger.info(f"Email click tracked for lead {lead_id} in campaign {campaign_id} to {url}")
        
        # Find the lead
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            logger.warning(f"Lead {lead_id} not found for campaign {campaign_id}")
            # Still redirect even if lead not found
            return RedirectResponse(url=url)
            
        # Update lead stats (you can add click tracking here)
        lead.updated_at = datetime.now()
        await lead.save()
        
        # Redirect to original URL
        return RedirectResponse(url=url)
        
    except Exception as e:
        logger.error(f"Error tracking email click for lead {lead_id}: {e}")
        # Still redirect even if tracking fails
        return RedirectResponse(url=url)


@router.post("/track/test-condition")
async def test_condition_resume(
    lead_id: str = Query(..., description="Lead ID to test"),
    campaign_id: str = Query(..., description="Campaign ID"),
    condition_node_id: str = Query(..., description="Condition node ID to mark as met")
):
    """
    Test endpoint to manually trigger condition resumption
    """
    try:
        logger.info(f"Manual condition test for lead {lead_id} in campaign {campaign_id}")
        
        # Find the lead
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
            
        # Resume execution with condition met
        executor = FlowExecutor(campaign_id)
        await executor.load_campaign()
        await executor.resume_lead(lead_id, condition_met=True, condition_node_id=condition_node_id)
        
        logger.info(f"Manually resumed lead {lead_id} with condition {condition_node_id} met")
        
        return {"message": "Condition test successful", "lead_id": lead_id, "condition_node": condition_node_id}
        
    except Exception as e:
        logger.error(f"Error in condition test for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/track/test-wait")
async def test_wait_resume(
    lead_id: str = Query(..., description="Lead ID to test"),
    campaign_id: str = Query(..., description="Campaign ID")
):
    """
    Test endpoint to manually trigger wait node resumption
    """
    try:
        logger.info(f"Manual wait test for lead {lead_id} in campaign {campaign_id}")
        
        # Find the lead
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
            
        # Resume execution (no condition met, just resume from wait)
        executor = FlowExecutor(campaign_id)
        await executor.load_campaign()
        await executor.resume_lead(lead_id)
        
        logger.info(f"Manually resumed lead {lead_id} from wait")
        
        return {"message": "Wait test successful", "lead_id": lead_id}
        
    except Exception as e:
        logger.error(f"Error in wait test for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 