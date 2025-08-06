from fastapi import APIRouter, HTTPException, Query
from app.models.lead import LeadModel
from app.services.flow_executor import FlowExecutor
from app.services.event_tracker import EventTracker
import logging
from fastapi.responses import Response, RedirectResponse
from app.celery_config import celery_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os
from urllib.parse import unquote
from typing import Optional

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

@router.get("/track/test")
async def test_tracking():
    """Simple test endpoint to verify tracking API is accessible"""
    import time
    timestamp = time.time()
    logger.info(f"=== TRACKING TEST ENDPOINT CALLED ===")
    logger.info(f"Timestamp: {timestamp}")
    logger.info(f"=== END TRACKING TEST ===")
    return {"message": "Tracking test successful", "timestamp": timestamp}

@router.get("/track/open")
async def track_email_open(token: str = Query(..., description="Signed tracking token")):
    """
    Tracks email opens via a signed token. Processes events for multiple condition nodes.
    """
    try:
        logger.info(f"[TRACKING] === EMAIL OPEN TRACKING REQUEST ===")
        logger.info(f"[TRACKING] Token: {token[:20]}...")
        logger.info(f"[TRACKING] Token: {token[:20]}...")
        
        # Validate token parameter
        if not token or not token.strip():
            logger.warning("[TRACKING] Empty tracking token received")
            return Response(content=TRACKING_PIXEL, media_type="image/gif")
        
        logger.info(f"[TRACKING] Processing email open tracking request")
        
        # Deserialize the token to get lead and campaign IDs
        data = serializer.loads(token, max_age=2592000) 
        lead_id = data["lead_id"]
        campaign_id = data["campaign_id"]
        
        logger.info(f"[TRACKING] Email open tracked for lead {lead_id} in campaign {campaign_id}")
        logger.info(f"[TRACKING] Token data: {data}")
        
        # Verify the lead exists in the database
        from app.models.lead import LeadModel
        lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
        if not lead:
            logger.error(f"[TRACKING] Lead {lead_id} not found in campaign {campaign_id}")
            return Response(content=TRACKING_PIXEL, media_type="image/gif")
        
        logger.info(f"[TRACKING] Lead found: {lead.lead_id}, status: {lead.status}, current_node: {lead.current_node}")
        
    except SignatureExpired:
        logger.warning("[TRACKING] Expired tracking token received")
        return Response(content=TRACKING_PIXEL, media_type="image/gif")
    except BadTimeSignature:
        logger.warning("[TRACKING] Invalid tracking token received")
        return Response(content=TRACKING_PIXEL, media_type="image/gif")
    except Exception as e:
        logger.error(f"[TRACKING] Failed to decode tracking token: {e}", exc_info=True)
        return Response(content=TRACKING_PIXEL, media_type="image/gif")

    try:
        logger.info(f"[TRACKING] Processing email open event for lead {lead_id}")
        
        # ✅ ENHANCED: Process the email open event with retry logic
        event_tracker = EventTracker(campaign_id)
        logger.info(f"[TRACKING] Created EventTracker for campaign {campaign_id}")
        
        # Retry logic for event processing
        max_retries = 3
        retry_count = 0
        condition_node_id = None
        
        while retry_count < max_retries:
            try:
                condition_node_id = await event_tracker.process_event(lead_id, "email_open")
                logger.info(f"[TRACKING] Event processing result: condition_node_id = {condition_node_id}")
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"[TRACKING] Event processing attempt {retry_count} failed: {e}")
                if retry_count < max_retries:
                    import asyncio
                    await asyncio.sleep(0.5 * retry_count)  # Exponential backoff
                else:
                    logger.error(f"[TRACKING] All {max_retries} attempts failed for lead {lead_id}")
        
        if condition_node_id:
            logger.info(f"[TRACKING] Found waiting condition node {condition_node_id} for lead {lead_id}")
            
            # ✅ ENHANCED: Resume the lead with proper error handling
            try:
                executor = FlowExecutor(campaign_id)
                await executor.load_campaign()
                await executor.resume_lead_from_condition(lead_id, condition_node_id, condition_met=True)
                logger.info(f"[TRACKING] Resumed lead {lead_id} from condition node {condition_node_id} after email open.")
            except Exception as resume_error:
                logger.error(f"[TRACKING] Failed to resume lead {lead_id}: {resume_error}")
                # Don't fail the tracking request - the event was still recorded
        else:
            logger.warning(f"[TRACKING] No waiting condition node found for lead {lead_id} email open event.")
            logger.warning(f"[TRACKING] This could mean:")
            logger.warning(f"[TRACKING] 1. The email was opened before reaching the condition node")
            logger.warning(f"[TRACKING] 2. The condition node hasn't been reached yet")
            logger.warning(f"[TRACKING] 3. The event was already processed")
            logger.warning(f"[TRACKING] 4. There's an issue with the tracking setup")
            
    except Exception as e:
        logger.error(f"[TRACKING] Error processing email open for lead {lead_id}: {e}", exc_info=True)
    
    logger.info(f"[TRACKING] === EMAIL OPEN TRACKING COMPLETED ===")
    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@router.get("/track/click")
async def track_link_click(token: str = Query(..., description="Signed tracking token"), url: str = Query(..., description="Original URL")):
    """
    Tracks link clicks via a signed token. Processes events and sends button email.
    """
    try:
        # Deserialize the token to get lead and campaign IDs
        data = serializer.loads(token, max_age=2592000)
        lead_id = data["lead_id"]
        campaign_id = data["campaign_id"]
        original_url = unquote(url)  # Decode URL
        
        # ✅ ENHANCED: Add timestamp and request details for debugging
        import time
        timestamp = time.time()
        
        logger.info(f"=== LINK CLICK EVENT RECEIVED ===")
        logger.info(f"Timestamp: {timestamp}")
        logger.info(f"Lead ID: {lead_id}")
        logger.info(f"Campaign ID: {campaign_id}")
        logger.info(f"URL: {original_url}")
        logger.info(f"Token: {token[:50]}...")
        logger.info(f"=== END LINK CLICK EVENT ===")
        
    except SignatureExpired:
        logger.warning("Expired tracking token received.")
        return RedirectResponse(url=url)
    except BadTimeSignature:
        logger.warning("Invalid tracking token received.")
        return RedirectResponse(url=url)
    except Exception:
        logger.error("Failed to decode tracking token.", exc_info=True)
        return RedirectResponse(url=url)

    try:
        # ✅ ENHANCED: Process the link click event with retry logic
        event_tracker = EventTracker(campaign_id)
        
        # Retry logic for event processing
        max_retries = 3
        retry_count = 0
        condition_node_id = None
        
        logger.info(f"=== PROCESSING LINK CLICK EVENT ===")
        logger.info(f"Lead ID: {lead_id}")
        logger.info(f"Event Type: link_click")
        logger.info(f"Target URL: {original_url}")
        
        while retry_count < max_retries:
            try:
                condition_node_id = await event_tracker.process_event(lead_id, "link_click", original_url)
                logger.info(f"Event processing result: condition_node_id = {condition_node_id}")
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"[TRACKING] Link click event processing attempt {retry_count} failed: {e}")
                if retry_count < max_retries:
                    import asyncio
                    await asyncio.sleep(0.5 * retry_count)  # Exponential backoff
                else:
                    logger.error(f"[TRACKING] All {max_retries} attempts failed for lead {lead_id} link click")
        
        logger.info(f"=== EVENT PROCESSING COMPLETE ===")
        logger.info(f"Condition node ID: {condition_node_id}")
        
        if condition_node_id:
            # ✅ ENHANCED: Get lead details for resume
            try:
                lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": campaign_id})
                if lead:
                    logger.info(f"Found lead {lead_id} for resume after link click")
            except Exception as lead_error:
                logger.error(f"[TRACKING] Failed to find lead {lead_id}: {lead_error}")
                # Continue with resume even if lead lookup fails
            
            # ✅ ENHANCED: Resume the lead with proper error handling
            try:
                executor = FlowExecutor(campaign_id)
                await executor.load_campaign()
                await executor.resume_lead_from_condition(lead_id, condition_node_id, condition_met=True)
                logger.info(f"Resumed lead {lead_id} from condition node {condition_node_id} after link click.")
            except Exception as resume_error:
                logger.error(f"[TRACKING] Failed to resume lead {lead_id} after link click: {resume_error}")
                # Don't fail the tracking request - the event was still recorded
        else:
            logger.info(f"No waiting condition node found for lead {lead_id} link click event.")
            
    except Exception as e:
        logger.error(f"Error processing link click for lead {lead_id}: {e}", exc_info=True)
    
    # Always redirect to the original URL
    return RedirectResponse(url=original_url)

async def send_button_email(recipient_email: str, clicked_url: str, lead_id: str, campaign_id: str, condition_node_id: str):
    """Send an email with button added to existing email body when link click is detected"""
    try:
        # Validate input parameters
        if not recipient_email or not recipient_email.strip():
            logger.error(f"[BUTTON_EMAIL] Missing recipient email for lead {lead_id}")
            return
        
        if not clicked_url or not clicked_url.strip():
            logger.error(f"[BUTTON_EMAIL] Missing clicked URL for lead {lead_id}")
            return
        
        if not lead_id or not campaign_id or not condition_node_id:
            logger.error(f"[BUTTON_EMAIL] Missing required parameters: lead_id={lead_id}, campaign_id={campaign_id}, condition_node_id={condition_node_id}")
            return
        
        # Validate email format
        if "@" not in recipient_email or "." not in recipient_email:
            logger.error(f"[BUTTON_EMAIL] Invalid email format: {recipient_email}")
            return
        
        logger.info(f"[BUTTON_EMAIL] Preparing button email:", {
            "recipient_email": recipient_email,
            "clicked_url": clicked_url,
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "condition_node_id": condition_node_id
        })
        
        from app.services.email import send_email_with_tracking
        from app.services.flow_executor import FlowExecutor
        
        # Get campaign and find the email node that comes before this condition node
        executor = FlowExecutor(campaign_id)
        await executor.load_campaign()
        
        # Find the email node that comes before this condition node (could be through other condition nodes)
        email_node = None
        
        def find_preceding_email_node(target_node_id: str, visited: set = None) -> Optional[dict]:
            if visited is None:
                visited = set()
            
            if target_node_id in visited:
                logger.warning(f"[BUTTON_EMAIL] Infinite loop detected in node traversal: {target_node_id}")
                return None  # Prevent infinite loops
            visited.add(target_node_id)
            
            logger.debug(f"[BUTTON_EMAIL] Searching for email node before: {target_node_id}")
            
            # Find all nodes that connect to our target node
            for node_id, node in executor.nodes.items():
                if node.get("type") == "sendEmail":
                    # Check if this email node connects to our target node
                    next_node_id = executor._get_next_node_id(node_id)
                    if next_node_id == target_node_id:
                        logger.info(f"[BUTTON_EMAIL] Found email node {node_id} before condition node {target_node_id}")
                        return node
                elif node.get("type") == "condition":
                    # Check if this condition node connects to our target node
                    next_node_id = executor._get_next_node_id(node_id)
                    if next_node_id == target_node_id:
                        logger.debug(f"[BUTTON_EMAIL] Found condition node {node_id} before target, recursing")
                        # Recursively find email node before this condition node
                        result = find_preceding_email_node(node_id, visited)
                        if result:
                            return result
            
            logger.warning(f"[BUTTON_EMAIL] No email node found before {target_node_id}")
            return None
        
        email_node = find_preceding_email_node(condition_node_id)
        
        if not email_node:
            logger.error(f"[BUTTON_EMAIL] Could not find email node before condition node {condition_node_id}. This condition node must be connected to an email node (directly or through other condition nodes).")
            return
        
        # Get the original email content
        config = email_node.get("configuration", {})
        original_subject = config.get("subject", "Follow-up Email")
        original_body = config.get("body", "")
        
        # Add button to the existing body
        button_html = f"""
        <div style="text-align: center; margin: 30px 0; padding: 20px; background-color: #f8f9fa; border-radius: 8px;">
            <p style="color: #666; font-size: 16px; margin-bottom: 15px;">
                You clicked on a link! Here's a special button for you:
            </p>
            <a href="{clicked_url}" 
               style="background-color: #007bff; color: white; padding: 15px 30px; 
                      text-decoration: none; border-radius: 5px; font-size: 18px; 
                      font-weight: bold; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                Click Me!
            </a>
        </div>
        """
        
        # Combine original body with button
        enhanced_body = original_body + button_html
        
        # Send the enhanced email
        try:
            from app.services.email import send_email_with_tracking
            send_email_with_tracking(
                subject=f"Follow-up: {original_subject}",
                body=enhanced_body,
                recipient_email=recipient_email,
                lead_id=lead_id,
                campaign_id=campaign_id
            )
            logger.info(f"[BUTTON_EMAIL] Successfully sent button email to {recipient_email}")
        except Exception as email_error:
            logger.error(f"[BUTTON_EMAIL] Failed to send button email: {email_error}", exc_info=True)
            # Don't raise - this is not critical for the main flow
        
        # Send the modified email
        send_email_with_tracking(
            subject=original_subject,
            body=modified_body,
            recipient_email=recipient_email,
            lead_id=lead_id,
            campaign_id=campaign_id
        )
        
        logger.info(f"Button email sent to {recipient_email} for URL: {clicked_url}")
        
    except Exception as e:
        logger.error(f"Failed to send button email to {recipient_email}: {e}", exc_info=True)
