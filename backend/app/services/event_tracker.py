import logging
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from app.models.lead_event import LeadEvent
from app.models.lead import LeadModel
from app.services.flow_executor import FlowExecutor

logger = logging.getLogger(__name__)


class EventTracker:
    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id

    async def create_waiting_event_with_context(self, lead_id: str, condition_node_id: str, 
                                              email_context: dict, event_type: str, target_url: Optional[str] = None) -> str:
        """✅ ENHANCED: Create event with full context for proper mapping"""
        try:
            # Validate input parameters
            if not lead_id or not lead_id.strip():
                logger.error(f"[EVENT] Missing lead_id for event creation")
                raise ValueError("Lead ID is required")
            
            if not condition_node_id or not condition_node_id.strip():
                logger.error(f"[EVENT] Missing condition_node_id for event creation")
                raise ValueError("Condition node ID is required")
            
            if not event_type or event_type not in ["email_open", "link_click"]:
                logger.error(f"[EVENT] Invalid event_type: {event_type}")
                raise ValueError("Event type must be 'email_open' or 'link_click'")
            
            # Validate target_url for link_click events
            if event_type == "link_click" and not target_url:
                logger.error(f"[EVENT] Missing target_url for link_click event")
                raise ValueError("Target URL is required for link_click events")
            
            event_id = f"event_{lead_id}_{condition_node_id}_{uuid.uuid4().hex[:8]}"
            
            logger.info(f"[EVENT] Creating waiting event with context:", {
                "event_id": event_id,
                "lead_id": lead_id,
                "condition_node_id": condition_node_id,
                "event_type": event_type,
                "target_url": target_url,
                "email_node_id": email_context.get("email_node_id"),
                "email_subject": email_context.get("subject"),
                "campaign_id": self.campaign_id
            })
            
            event = LeadEvent(
                event_id=event_id,
                lead_id=lead_id,
                campaign_id=self.campaign_id,
                event_type=event_type,
                condition_node_id=condition_node_id,
                target_url=target_url,
                email_node_id=email_context.get("email_node_id"),
                email_subject=email_context.get("subject"),
                condition_chain=email_context.get("condition_chain", []),
                email_links=email_context.get("links", []),
                event_context=email_context.get("context", {}),
                created_at=datetime.now(timezone.utc),
                processed=False
            )
            
            await event.insert()
            logger.info(f"[EVENT] Created waiting event {event_id} for lead {lead_id} at condition node {condition_node_id}")
            logger.info(f"[EVENT] Event details: type={event.event_type}, processed={event.processed}, created_at={event.created_at}")
            
            return event_id
            
        except Exception as e:
            logger.error(f"[EVENT] Failed to create waiting event for lead {lead_id}: {e}", exc_info=True)
            raise

    async def create_waiting_event(self, lead_id: str, condition_node_id: str, event_type: str, target_url: Optional[str] = None) -> str:
        """Legacy method for backward compatibility"""
        # Create minimal context for backward compatibility
        email_context = {
            "email_node_id": None,
            "subject": "Unknown",
            "condition_chain": [],
            "links": [],
            "context": {}
        }
        return await self.create_waiting_event_with_context(lead_id, condition_node_id, email_context, event_type, target_url)

    async def process_event(self, lead_id: str, event_type: str, target_url: Optional[str] = None) -> Optional[str]:
        """Process an incoming event and return the condition node ID if it matches"""
        try:
            # Validate input parameters
            if not lead_id or not lead_id.strip():
                logger.error(f"[EVENT] Missing lead_id for event processing")
                return None
            
            if not event_type or event_type not in ["email_open", "link_click"]:
                logger.error(f"[EVENT] Invalid event_type: {event_type}")
                return None
            
            logger.info(f"[EVENT] Processing event:", {
                "lead_id": lead_id,
                "event_type": event_type,
                "target_url": target_url,
                "campaign_id": self.campaign_id
            })
            
            # Find unprocessed events for this lead and event type
            query = {
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "event_type": event_type,
                "processed": False
            }
            
            if target_url:
                # For link clicks, also match the target URL
                query["target_url"] = target_url
                logger.info(f"[EVENT] Adding target_url to query: {target_url}")
            
            logger.info(f"[EVENT] Query for event processing: {query}")
            
            # Get all matching events and process the oldest one
            events = await LeadEvent.find(query, sort=[("created_at", 1)]).to_list()
            logger.info(f"[EVENT] Found {len(events)} matching events")
            
            if not events:
                logger.warning(f"[EVENT] No matching waiting event found for lead {lead_id}, event_type: {event_type}")
                logger.warning(f"[EVENT] Query used: {query}")
                
                # Debug: Check all events for this lead
                all_events = await LeadEvent.find({
                    "lead_id": lead_id,
                    "campaign_id": self.campaign_id
                }).to_list()
                logger.warning(f"[EVENT] All events for lead {lead_id}: {len(all_events)} total")
                for event in all_events:
                    logger.warning(f"[EVENT] Event: {event.event_id}, type: {event.event_type}, processed: {event.processed}, condition: {event.condition_node_id}, target_url: {getattr(event, 'target_url', 'N/A')}")
                
                # Also check if there are any events with different target URLs
                if target_url:
                    similar_events = await LeadEvent.find({
                        "lead_id": lead_id,
                        "campaign_id": self.campaign_id,
                        "event_type": event_type,
                        "processed": False
                    }).to_list()
                    logger.warning(f"[EVENT] Events with same type but different URLs: {len(similar_events)}")
                    for event in similar_events:
                        logger.warning(f"[EVENT] Similar event: {event.event_id}, target_url: {getattr(event, 'target_url', 'N/A')}")
                
                logger.warning(f"[EVENT] This could mean:")
                logger.warning(f"[EVENT] 1. The condition node hasn't been reached yet")
                logger.warning(f"[EVENT] 2. The event was already processed")
                logger.warning(f"[EVENT] 3. The event type doesn't match (expected: {event_type})")
                logger.warning(f"[EVENT] 4. The lead is not in the correct campaign")
                return None
            
            # Process the oldest event
            event = events[0]
            
            # Check for duplicate processing
            if event.processed:
                logger.warning(f"[EVENT] Event {event.event_id} already processed")
                return None
            
            # Mark event as processed atomically
            try:
                event.processed = True
                event.processed_at = datetime.now(timezone.utc)
                await event.save()
                
                logger.info(f"[EVENT] Processed event {event.event_id} for lead {lead_id}, condition node: {event.condition_node_id}")
                
                # If there are more events for this lead, log them
                if len(events) > 1:
                    logger.info(f"[EVENT] Found {len(events)} total events for lead {lead_id}, processed oldest one")
                
                # ✅ ENHANCED: Trigger immediate execution via Celery task
                await self._trigger_condition_execution(lead_id, event.condition_node_id, event_type)
            except Exception as save_error:
                logger.error(f"[EVENT] Failed to save processed event {event.event_id}: {save_error}")
                # Don't raise - we still want to return the condition_node_id
            
            return event.condition_node_id
            
        except Exception as e:
            logger.error(f"[EVENT] Failed to process event for lead {lead_id}: {e}", exc_info=True)
            raise

    async def _trigger_condition_execution(self, lead_id: str, condition_node_id: str, event_type: str):
        """Trigger immediate execution of condition node via Celery task"""
        try:
            from app.tasks import resume_condition_task
            
            logger.info(f"[EVENT_TRIGGER] Triggering condition execution for lead {lead_id}, node {condition_node_id}, event: {event_type}")
            
            # Trigger Celery task for immediate execution
            resume_condition_task.delay(
                lead_id=lead_id,
                campaign_id=self.campaign_id,
                condition_met=True
            )
            
            logger.info(f"[EVENT_TRIGGER] Celery task triggered successfully for lead {lead_id}")
            
        except Exception as e:
            logger.error(f"[EVENT_TRIGGER] Failed to trigger condition execution for lead {lead_id}: {e}", exc_info=True)
            # Don't raise - we still want to return the condition_node_id

    async def get_waiting_events(self, lead_id: str) -> List[LeadEvent]:
        """Get all waiting events for a lead"""
        try:
            events = await LeadEvent.find({
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "processed": False
            }).to_list()
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to get waiting events for lead {lead_id}: {e}")
            return []

    async def clear_waiting_events(self, lead_id: str, condition_node_id: str):
        """Clear waiting events for a specific condition node (when lead is resumed)"""
        try:
            result = await LeadEvent.find({
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "condition_node_id": condition_node_id,
                "processed": False
            }).update_many({"$set": {"processed": True, "processed_at": datetime.now(timezone.utc)}})
            
            logger.info(f"Cleared {result.modified_count} waiting events for lead {lead_id} at condition node {condition_node_id}")
            
        except Exception as e:
            logger.error(f"Failed to clear waiting events for lead {lead_id}: {e}")
            # Don't raise - this is not critical for flow execution

    async def check_existing_event(self, lead_id: str, event_type: str, target_url: Optional[str] = None) -> bool:
        """Check if an event has already occurred for this lead"""
        try:
            logger.info(f"[EVENT] Checking existing event for lead {lead_id}, type: {event_type}, target_url: {target_url}")
            
            # Look for processed events (events that have already happened)
            query = {
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "event_type": event_type,
                "processed": True
            }
            
            if target_url and event_type == "link_click":
                query["target_url"] = target_url
                logger.debug(f"[EVENT] Added target_url to query: {target_url}")
            
            logger.debug(f"[EVENT] Query for existing event: {query}")
            existing_event = await LeadEvent.find_one(query, sort=[("created_at", -1)])
            
            if existing_event:
                logger.info(f"[EVENT] Found existing {event_type} event for lead {lead_id} at {existing_event.created_at}")
                return True
            
            logger.info(f"[EVENT] No existing {event_type} event found for lead {lead_id}")
            return False
            
        except Exception as e:
            logger.error(f"[EVENT] Failed to check existing event for lead {lead_id}: {e}", exc_info=True)
            return False

    async def get_event_statistics(self, lead_id: str) -> dict:
        """Get event statistics for a lead"""
        try:
            total_events = await LeadEvent.find({
                "lead_id": lead_id,
                "campaign_id": self.campaign_id
            }).count()
            
            processed_events = await LeadEvent.find({
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "processed": True
            }).count()
            
            waiting_events = await LeadEvent.find({
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "processed": False
            }).count()
            
            return {
                "total_events": total_events,
                "processed_events": processed_events,
                "waiting_events": waiting_events,
                "lead_id": lead_id,
                "campaign_id": self.campaign_id
            }
            
        except Exception as e:
            logger.error(f"[EVENT] Failed to get event statistics for lead {lead_id}: {e}", exc_info=True)
            return {} 