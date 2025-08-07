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
        logger.info(f"[EVENT] === PROCESS_EVENT STARTED ===")
        logger.info(f"[EVENT] Input parameters: lead_id='{lead_id}', event_type='{event_type}', target_url='{target_url}'")
        logger.info(f"[EVENT] Campaign ID: '{self.campaign_id}'")
        
        try:
            # Validate input parameters
            logger.info(f"[EVENT] Step 1: Validating input parameters")
            logger.info(f"[EVENT] lead_id.strip() result: '{lead_id.strip() if lead_id else 'None'}'")
            logger.info(f"[EVENT] event_type in ['email_open', 'link_click']: {event_type in ['email_open', 'link_click']}")
            
            if not lead_id or not lead_id.strip():
                logger.error(f"[EVENT] ERROR: Missing lead_id for event processing")
                logger.error(f"[EVENT] lead_id value: '{lead_id}'")
                return None
            
            if not event_type or event_type not in ["email_open", "link_click"]:
                logger.error(f"[EVENT] ERROR: Invalid event_type: '{event_type}'")
                logger.error(f"[EVENT] Valid types: ['email_open', 'link_click']")
                return None
            
            logger.info(f"[EVENT] Step 2: Input validation passed")
            logger.info(f"[EVENT] Processing event with values:", {
                "lead_id": f"'{lead_id}'",
                "event_type": f"'{event_type}'",
                "target_url": f"'{target_url}'",
                "campaign_id": f"'{self.campaign_id}'"
            })
            
            # Find unprocessed events for this lead and event type
            logger.info(f"[EVENT] Step 3: Building query for unprocessed events")
            query = {
                "lead_id": lead_id,
                "campaign_id": self.campaign_id,
                "event_type": event_type,
                "processed": False
            }
            logger.info(f"[EVENT] Base query values: lead_id='{query['lead_id']}', campaign_id='{query['campaign_id']}', event_type='{query['event_type']}', processed={query['processed']}")
            
            if target_url:
                logger.info(f"[EVENT] Step 4a: Target URL provided, using flexible URL matching")
                logger.info(f"[EVENT] Target URL value: '{target_url}'")
                # ✅ CRITICAL FIX: Use more flexible URL matching
                # First try exact match
                exact_query = query.copy()
                exact_query["target_url"] = target_url
                logger.info(f"[EVENT] Exact query values: lead_id='{exact_query['lead_id']}', campaign_id='{exact_query['campaign_id']}', event_type='{exact_query['event_type']}', processed={exact_query['processed']}, target_url='{exact_query['target_url']}'")
                events = await LeadEvent.find(exact_query, sort=[("created_at", 1)]).to_list()
                logger.info(f"[EVENT] Exact match found {len(events)} events")
                
                if not events:
                    # If exact match fails, try without URL matching (just event type)
                    logger.warning(f"[EVENT] Exact URL match failed for {target_url}, trying without URL matching")
                    fallback_query = {
                        "lead_id": lead_id,
                        "campaign_id": self.campaign_id,
                        "event_type": event_type,
                        "processed": False
                    }
                    logger.info(f"[EVENT] Fallback query: {fallback_query}")
                    events = await LeadEvent.find(fallback_query, sort=[("created_at", 1)]).to_list()
                    logger.info(f"[EVENT] Fallback query found {len(events)} events")
                    
                    if events:
                        logger.info(f"[EVENT] Found {len(events)} events without URL matching")
                        # Log the URLs for debugging
                        for i, event in enumerate(events):
                            logger.info(f"[EVENT] Event {i+1}: {event.event_id}, URL: {getattr(event, 'target_url', 'N/A')}")
                else:
                    logger.info(f"[EVENT] Found {len(events)} events with exact URL match")
                    for i, event in enumerate(events):
                        logger.info(f"[EVENT] Exact match event {i+1}: {event.event_id}, URL: {getattr(event, 'target_url', 'N/A')}")
            else:
                logger.info(f"[EVENT] Step 4b: No target URL, using base query")
                # Get all matching events and process the oldest one
                events = await LeadEvent.find(query, sort=[("created_at", 1)]).to_list()
                logger.info(f"[EVENT] Base query found {len(events)} events")
            
            logger.info(f"[EVENT] Step 5: Final query used: {query}")
            logger.info(f"[EVENT] Step 6: Total events found: {len(events)}")
            
            if not events:
                logger.warning(f"[EVENT] Step 7: NO EVENTS FOUND - This is the problem!")
                logger.warning(f"[EVENT] No matching waiting event found for lead {lead_id}, event_type: {event_type}")
                logger.warning(f"[EVENT] Query used: {query}")
                
                # Debug: Check all events for this lead
                logger.info(f"[EVENT] Step 8: Debugging - checking all events for this lead")
                all_events = await LeadEvent.find({
                    "lead_id": lead_id,
                    "campaign_id": self.campaign_id
                }).to_list()
                logger.warning(f"[EVENT] All events for lead {lead_id}: {len(all_events)} total")
                for i, event in enumerate(all_events):
                    logger.warning(f"[EVENT] Event {i+1}: {event.event_id}, type: {event.event_type}, processed: {event.processed}, condition: {event.condition_node_id}, target_url: {getattr(event, 'target_url', 'N/A')}, created_at: {event.created_at}")
                
                # Also check if there are any events with different target URLs
                if target_url:
                    logger.info(f"[EVENT] Step 9: Checking for events with same type but different URLs")
                    similar_events = await LeadEvent.find({
                        "lead_id": lead_id,
                        "campaign_id": self.campaign_id,
                        "event_type": event_type,
                        "processed": False
                    }).to_list()
                    logger.warning(f"[EVENT] Events with same type but different URLs: {len(similar_events)}")
                    for i, event in enumerate(similar_events):
                        logger.warning(f"[EVENT] Similar event {i+1}: {event.event_id}, target_url: {getattr(event, 'target_url', 'N/A')}")
                
                logger.warning(f"[EVENT] Step 10: Possible reasons for no events:")
                logger.warning(f"[EVENT] 1. The condition node hasn't been reached yet")
                logger.warning(f"[EVENT] 2. The event was already processed")
                logger.warning(f"[EVENT] 3. The event type doesn't match (expected: {event_type})")
                logger.warning(f"[EVENT] 4. The lead is not in the correct campaign")
                logger.warning(f"[EVENT] 5. The event was never created")
                logger.warning(f"[EVENT] === PROCESS_EVENT ENDED WITH NO EVENTS ===")
                return None
            
            # Process the oldest event
            logger.info(f"[EVENT] Step 11: Processing the oldest event")
            event = events[0]
            logger.info(f"[EVENT] Selected event: {event.event_id}, type: {event.event_type}, condition_node: {event.condition_node_id}")
            
            # Check for duplicate processing
            logger.info(f"[EVENT] Step 12: Checking if event already processed")
            if event.processed:
                logger.warning(f"[EVENT] ERROR: Event {event.event_id} already processed")
                logger.warning(f"[EVENT] === PROCESS_EVENT ENDED WITH ALREADY PROCESSED ===")
                return None
            
            # Mark event as processed atomically
            logger.info(f"[EVENT] Step 13: Marking event as processed")
            try:
                event.processed = True
                event.processed_at = datetime.now(timezone.utc)
                logger.info(f"[EVENT] About to save event {event.event_id} as processed")
                await event.save()
                logger.info(f"[EVENT] Successfully saved event {event.event_id} as processed")
                
                logger.info(f"[EVENT] Step 14: Event processing completed")
                logger.info(f"[EVENT] Processed event {event.event_id} for lead {lead_id}, condition node: {event.condition_node_id}")
                
                # If there are more events for this lead, log them
                if len(events) > 1:
                    logger.info(f"[EVENT] Found {len(events)} total events for lead {lead_id}, processed oldest one")
                
                # ✅ ENHANCED: Trigger immediate execution via Celery task
                logger.info(f"[EVENT] Step 15: Triggering condition execution via Celery")
                await self._trigger_condition_execution(lead_id, event.condition_node_id, event_type)
                
                # ✅ CRITICAL: Add small delay to ensure Celery task starts
                import asyncio
                logger.info(f"[EVENT] Step 16: Adding delay to ensure Celery task starts")
                await asyncio.sleep(0.2)
                logger.info(f"[EVENT] Delay completed")
                
                # ✅ CRITICAL: Also trigger direct execution as fallback
                logger.info(f"[EVENT] Step 17: Triggering direct execution as fallback for lead {lead_id}")
                try:
                    logger.info(f"[EVENT] Creating FlowExecutor instance")
                    executor = FlowExecutor(self.campaign_id)
                    logger.info(f"[EVENT] Loading campaign")
                    await executor.load_campaign()
                    logger.info(f"[EVENT] Calling resume_lead_from_condition")
                    await executor.resume_lead_from_condition(lead_id, event.condition_node_id, condition_met=True)
                    logger.info(f"[EVENT] Direct execution completed for lead {lead_id}")
                except Exception as direct_error:
                    logger.error(f"[EVENT] Direct execution failed: {direct_error}")
                    logger.error(f"[EVENT] Direct execution error details:", exc_info=True)
                    # Don't raise - we still want to return the condition_node_id
                
                logger.info(f"[EVENT] Step 18: All execution triggers completed")
                
            except Exception as save_error:
                logger.error(f"[EVENT] ERROR: Failed to save processed event {event.event_id}: {save_error}")
                logger.error(f"[EVENT] Save error details:", exc_info=True)
                # Don't raise - we still want to return the condition_node_id
            
            logger.info(f"[EVENT] Step 19: Returning condition_node_id: {event.condition_node_id}")
            logger.info(f"[EVENT] === PROCESS_EVENT ENDED SUCCESSFULLY ===")
            return event.condition_node_id
            
        except Exception as e:
            logger.error(f"[EVENT] CRITICAL ERROR: Failed to process event for lead {lead_id}: {e}")
            logger.error(f"[EVENT] Exception details:", exc_info=True)
            logger.error(f"[EVENT] === PROCESS_EVENT ENDED WITH EXCEPTION ===")
            raise

    async def _trigger_condition_execution(self, lead_id: str, condition_node_id: str, event_type: str):
        """Trigger immediate execution of condition node via Celery task"""
        logger.info(f"[EVENT_TRIGGER] === TRIGGER_CONDITION_EXECUTION STARTED ===")
        logger.info(f"[EVENT_TRIGGER] Parameters: lead_id={lead_id}, condition_node_id={condition_node_id}, event_type={event_type}")
        
        try:
            logger.info(f"[EVENT_TRIGGER] Step 1: Importing resume_condition_task")
            from app.tasks import resume_condition_task
            logger.info(f"[EVENT_TRIGGER] Step 2: Import successful")
            
            logger.info(f"[EVENT_TRIGGER] Step 3: Triggering condition execution")
            logger.info(f"[EVENT_TRIGGER] Triggering condition execution for lead {lead_id}, node {condition_node_id}, event: {event_type}")
            logger.info(f"[EVENT_TRIGGER] Campaign ID: {self.campaign_id}")
            
            # Trigger Celery task for immediate execution
            logger.info(f"[EVENT_TRIGGER] Step 4: Calling resume_condition_task.delay")
            task_result = resume_condition_task.delay(
                lead_id=lead_id,
                campaign_id=self.campaign_id,
                condition_met=True
            )
            logger.info(f"[EVENT_TRIGGER] Step 5: Celery task called successfully")
            
            logger.info(f"[EVENT_TRIGGER] Celery task triggered successfully for lead {lead_id}")
            logger.info(f"[EVENT_TRIGGER] Task ID: {task_result.id}")
            logger.info(f"[EVENT_TRIGGER] === TRIGGER_CONDITION_EXECUTION COMPLETED SUCCESSFULLY ===")
            
        except Exception as e:
            logger.error(f"[EVENT_TRIGGER] CRITICAL ERROR: Failed to trigger condition execution for lead {lead_id}: {e}")
            logger.error(f"[EVENT_TRIGGER] Exception details:", exc_info=True)
            logger.error(f"[EVENT_TRIGGER] === TRIGGER_CONDITION_EXECUTION FAILED ===")
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
            # Update all waiting events for this condition node
            events_to_update = await LeadEvent.find(
                LeadEvent.lead_id == lead_id,
                LeadEvent.campaign_id == self.campaign_id,
                LeadEvent.condition_node_id == condition_node_id,
                LeadEvent.processed == False
            ).to_list()
            
            modified_count = 0
            for event in events_to_update:
                event.processed = True
                event.processed_at = datetime.now(timezone.utc)
                await event.save()
                modified_count += 1
            
            result = type('Result', (), {'modified_count': modified_count})()
            
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
            
            # Build query conditions
            conditions = [
                LeadEvent.lead_id == query["lead_id"],
                LeadEvent.campaign_id == query["campaign_id"],
                LeadEvent.event_type == query["event_type"],
                LeadEvent.processed == query["processed"]
            ]
            
            # Add target_url condition if present
            if "target_url" in query:
                conditions.append(LeadEvent.target_url == query["target_url"])
            
            existing_event = await LeadEvent.find(*conditions).sort(-LeadEvent.created_at).limit(1).to_list()
            existing_event = existing_event[0] if existing_event else None
            
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