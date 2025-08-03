from fastapi import APIRouter, HTTPException, Query
from app.models.lead import LeadModel
from app.services.flow_executor import FlowExecutor
import logging
from fastapi.responses import Response, RedirectResponse
from app.celery_config import celery_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os

logger = logging.getLogger(__name__)
router = APIRouter()

# This key must be identical to the one in services/email.py
SECRET_KEY = "your-super-secret-key-that-is-hardcoded"
serializer = URLSafeTimedSerializer(SECRET_KEY)

# 1x1 transparent GIF pixel
TRACKING_PIXEL = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff'
    b'\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
    b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
)

@router.get("/track/open")
async def track_email_open(token: str = Query(..., description="Signed tracking token")):
    """
    Tracks email opens via a signed token. If the lead was paused, this revokes
    the scheduled timeout task and resumes the lead.
    """
    try:
        # Deserialize the token to get lead and campaign IDs
        # The token expires after 30 days
        data = serializer.loads(token, max_age=2592000) 
        lead_id = data["lead_id"]
        campaign_id = data["campaign_id"]
        logger.info(f"Email open tracked for lead {lead_id} in campaign {campaign_id}")
        
    except SignatureExpired:
        logger.warning("Expired tracking token received.")
        return Response(content=TRACKING_PIXEL, media_type="image/gif")
    except BadTimeSignature:
        logger.warning("Invalid tracking token received.")
        return Response(content=TRACKING_PIXEL, media_type="image/gif")
    except Exception:
        logger.error("Failed to decode tracking token.", exc_info=True)
        return Response(content=TRACKING_PIXEL, media_type="image/gif")

    try:
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            logger.warning(f"Lead {lead_id} not found.")
            return Response(content=TRACKING_PIXEL, media_type="image/gif")
            
        if lead.status == "paused" and lead.scheduled_task_id:
            logger.info(f"Lead {lead_id} is paused. Revoking task {lead.scheduled_task_id}.")
            
            # Revoke the scheduled timeout task
            celery_app.control.revoke(lead.scheduled_task_id, terminate=True)
            
            # Resume execution
            executor = FlowExecutor(campaign_id)
            await executor.load_campaign()
            await executor.resume_lead(lead_id, condition_met=True)
            
            logger.info(f"Resumed lead {lead_id} after email open.")
        else:
            logger.info(f"Lead {lead_id} is not in a pausable state or has no scheduled task.")
            
    except Exception as e:
        logger.error(f"Error processing email open for lead {lead_id}: {e}", exc_info=True)
        # Still return the pixel to avoid breaking the email client
    
    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
