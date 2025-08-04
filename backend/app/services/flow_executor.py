import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from io import StringIO
import asyncio

from app.models.campaign import CampaignModel
from app.models.lead import LeadModel
from app.models.lead_journal import LeadJournal
from app.tasks import send_email_task, resume_lead_task, resume_condition_task

logger = logging.getLogger(__name__)

class FlowExecutor:
    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id
        self.campaign: Optional[CampaignModel] = None
        self.nodes: Dict[str, Dict] = {}
        self.connections: Dict[str, List[Dict]] = {}

    async def _add_journal_entry(self, lead_id: str, message: str, node_id: Optional[str] = None, details: Optional[dict] = None):
        try:
            node_type = self.nodes.get(node_id, {}).get("type") if node_id else None
            await LeadJournal(lead_id=lead_id, campaign_id=self.campaign_id, message=message, node_id=node_id, node_type=node_type, details=details).insert()
        except Exception as e:
            logger.error(f"Failed to add journal entry for lead {lead_id}: {e}", exc_info=True)

    async def _update_lead_status(self, lead: LeadModel, status: str, message: str, node_id: Optional[str] = None, details: Optional[dict] = None):
        """Updates the lead's status and saves the entire lead document."""
        old_status = lead.status
        lead.status = status
        lead.updated_at = datetime.now(timezone.utc)

        logger.info(f"[STATUS_CHANGE] Lead {lead.lead_id} status changed from '{old_status}' to '{status}', current_node: {lead.current_node}")

        if status == "failed":
            lead.error_message = message
        elif status == "completed":
            lead.completed_at = datetime.now(timezone.utc)
        elif status == "running" and not lead.started_at:
            lead.started_at = datetime.now(timezone.utc)

        # CRITICAL: Save lead state first with retry mechanism
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await lead.save()
                logger.info(f"[STATUS_CHANGE] Successfully saved lead {lead.lead_id} status to {status}")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"[STATUS_CHANGE] Failed to save lead {lead.lead_id} after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"[STATUS_CHANGE] Retry {attempt + 1}/{max_retries} saving lead {lead.lead_id}: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        # Then add journal entry - if this fails, the lead state is still saved
        try:
            await self._add_journal_entry(lead.lead_id, message, node_id=node_id, details=details)
        except Exception as e:
            logger.error(f"[STATUS_CHANGE] Failed to add journal entry for lead {lead.lead_id}: {e}")

    async def load_campaign(self):
        self.campaign = await CampaignModel.find_one({"campaign_id": self.campaign_id})
        if not self.campaign:
            raise ValueError(f"Campaign {self.campaign_id} not found")
        self.nodes = {node["id"]: node for node in self.campaign.nodes}
        
        # FIXED: Properly initialize connections dictionary
        self.connections = {}
        for conn in self.campaign.connections:
            from_node = conn["from_node"]
            if from_node not in self.connections:
                self.connections[from_node] = []
            self.connections[from_node].append(conn)
        
        logger.info(f"[LOAD_CAMPAIGN] Loaded campaign {self.campaign_id}")
        logger.info(f"[LOAD_CAMPAIGN] Nodes: {list(self.nodes.keys())}")
        logger.info(f"[LOAD_CAMPAIGN] Connections: {self.connections}")
        
        self._detect_loops()

    def _detect_loops(self):
        visiting, visited = set(), set()
        def visit(node_id):
            if node_id in visiting:
                raise ValueError(f"Loop detected involving node {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for conn in self.connections.get(node_id, []):
                next_node_id = conn["to_node"]
                visit(next_node_id)
            visiting.remove(node_id)
            visited.add(node_id)

        start_node_id = self.campaign.workflow.get("start_node")
        if start_node_id:
            visit(start_node_id)

    async def parse_contact_file(self, contact_file_data: dict) -> List[Dict[str, str]]:
        content = contact_file_data.get("content")
        if not content:
            return []
        try:
            s = StringIO(content)
            df = pd.read_csv(s)
            df.columns = [h.strip().lower() for h in df.columns]
            if "email" not in df.columns:
                raise ValueError("CSV must contain 'email' column.")
            if "name" not in df.columns:
                df["name"] = "Valued Customer"
            return df[["name", "email"]].to_dict("records")
        except Exception as e:
            raise ValueError(f"Invalid CSV format: {e}")

    async def create_leads(self, leads_data: List[Dict[str, str]]) -> List[LeadModel]:
        start_node_id = self.campaign.workflow.get("start_node")
        if not start_node_id:
            raise ValueError("Campaign has no start node.")

        current_time = datetime.now(timezone.utc)
        timestamp = int(current_time.timestamp())

        leads = []
        for i, d in enumerate(leads_data):
            lead_id = f"lead_{self.campaign_id}_{i}_{timestamp}"
            
            lead = LeadModel(
                lead_id=lead_id,
                campaign_id=self.campaign_id,
                name=d.get("name", "N/A"),
                email=d["email"],
                status="pending",
                current_node=start_node_id,
                execution_path=[start_node_id],
                created_at=current_time,
                updated_at=current_time,
                # Initialize arrays to prevent None issues
                completed_tasks=[],
                sent_emails=[],
                completed_waits=[],
                email_sent_count=0
            )
            leads.append(lead)

        if leads:
            await LeadModel.insert_many(leads)
            for lead in leads:
                await self._add_journal_entry(lead.lead_id, "Lead created.")
        return leads

    async def start_campaign(self, contact_file_data: dict):
        try:
            logger.info(f"[START_CAMPAIGN] Starting campaign {self.campaign_id}")
            await self.load_campaign()
            leads_data = await self.parse_contact_file(contact_file_data)
            if not leads_data:
                self.campaign.status = "completed"
                await self.campaign.save()
                return {"status": "completed", "leads_count": 0}

            leads = await self.create_leads(leads_data)
            self.campaign.status = "running"
            await self.campaign.save()

            for lead in leads:
                await self.execute_lead(lead)

            await self._check_campaign_completion()
            return {"status": "started", "leads_count": len(leads)}
        except Exception as e:
            logger.error(f"Campaign start failed: {e}", exc_info=True)
            if self.campaign:
                self.campaign.status = "failed"
                self.campaign.error_message = str(e)
                await self.campaign.save()
            raise

    async def execute_lead(self, lead: LeadModel):
        try:
            if lead.status in ["completed", "failed"]:
                logger.info(f"[EXECUTE_LEAD_SKIP] Lead {lead.lead_id} already {lead.status}, skipping.")
                return

            if lead.status == "pending":
                await self._update_lead_status(lead, "running", "Lead execution started.")

            await self._execute_node(lead.current_node, lead)
        except Exception as e:
            logger.error(f"Execution failed for lead {lead.lead_id}: {e}", exc_info=True)
            await self._update_lead_status(lead, "failed", f"Lead execution failed: {str(e)}", details={"error": str(e)})

    async def _execute_node(self, node_id: str, lead: LeadModel):
        node = self.nodes.get(node_id)
        if not node:
            return await self._update_lead_status(lead, "failed", f"Node {node_id} not found", node_id=node_id)

        logger.info(f"[EXECUTE_NODE] Executing node {node_id} of type {node.get('type')} for lead {lead.lead_id}")

        # Initialize arrays if None
        if lead.completed_tasks is None:
            lead.completed_tasks = []
        if lead.sent_emails is None:
            lead.sent_emails = []
        if lead.completed_waits is None:
            lead.completed_waits = []

        node_type = node.get('type')
        
        # For wait nodes, check completion differently to prevent double execution
        if node_type == 'wait':
            if node_id in lead.completed_tasks:
                logger.info(f"[NODE_SKIP] Wait node {node_id} already completed for lead {lead.lead_id}, skipping execution")
                return  # Don't move to next - let resume handle it
        else:
            # For other node types, if completed, move to next
            if node_id in lead.completed_tasks:
                logger.info(f"[NODE_SKIP] Node {node_id} already completed for lead {lead.lead_id}, moving to next")
                await self._move_to_next_node(lead, node_id)
                return

        await self._add_journal_entry(lead.lead_id, f"Executing {node_type} node.", node_id=node_id)

        dispatch = {
            "start": self._execute_start_node,
            "sendEmail": self._execute_send_email_node,
            "condition": self._execute_condition_node,
            "wait": self._execute_wait_node,
            "end": self._execute_end_node
        }

        if node['type'] in dispatch:
            await dispatch[node['type']](lead, node)
        else:
            await self._update_lead_status(lead, "failed", f"Unknown node type: {node['type']}", node_id=node_id)

    def _get_next_node_id(self, current_node_id: str, branch: str = "default") -> Optional[str]:
        for conn in self.connections.get(current_node_id, []):
            if conn.get("connection_type", "default") == branch:
                return conn["to_node"]
        return None

    async def _move_to_next_node(self, lead: LeadModel, current_node_id: str, branch: str = "default"):
        next_node_id = self._get_next_node_id(current_node_id, branch)
        logger.info(f"[MOVE_TO_NEXT] Lead {lead.lead_id} moving from {current_node_id} to {next_node_id} (branch: {branch})")
        
        if not next_node_id:
            logger.info(f"[MOVE_TO_NEXT] No next node found, completing flow")
            await self._update_lead_status(lead, "completed", "Flow completed (no next node).", node_id=current_node_id)
            await self._check_campaign_completion()
            return

        # Update lead's current node and execution path
        lead.current_node = next_node_id
        if next_node_id not in lead.execution_path:
            lead.execution_path.append(next_node_id)

        # CRITICAL: Save lead state before executing next node
        await lead.save()
        logger.info(f"[MOVE_TO_NEXT] Saved lead state - current_node: {lead.current_node}")

        await self._add_journal_entry(lead.lead_id, f"Moved from '{current_node_id}' to '{next_node_id}'.", node_id=next_node_id)
        
        # Execute the next node
        await self._execute_node(next_node_id, lead)

    async def _execute_start_node(self, lead: LeadModel, node: dict):
        logger.info(f"[START_NODE] Executing start node {node['id']} for lead {lead.lead_id}")
        
        # Mark as completed and save
        if node["id"] not in lead.completed_tasks:
            lead.completed_tasks.append(node["id"])
            await lead.save()
            logger.info(f"[START_NODE] Marked start node {node['id']} as completed")
        
        # Move to next node
        await self._move_to_next_node(lead, node["id"])

    async def _execute_send_email_node(self, lead: LeadModel, node: dict):
        logger.info(f"[EMAIL_NODE] Executing email node {node['id']} for lead {lead.lead_id}")
        config = node.get("configuration", {})

        # Check if email already sent to prevent duplicates
        if node["id"] in lead.sent_emails:
            logger.info(f"[EMAIL_NODE] Email already sent for node {node['id']}, moving to next")
            await self._move_to_next_node(lead, node["id"])
            return

        # Update email tracking
        lead.email_sent_count += 1
        lead.last_email_sent_at = datetime.now(timezone.utc)
            
        # Mark as completed and sent
        if node["id"] not in lead.completed_tasks:
            lead.completed_tasks.append(node["id"])
        if node["id"] not in lead.sent_emails:
            lead.sent_emails.append(node["id"])

        # CRITICAL: Save lead state BEFORE dispatching email task
        await lead.save()
        logger.info(f"[EMAIL_NODE] Saved lead state before dispatching email")

        # Dispatch email task
        task = send_email_task.delay(
            lead_id=lead.lead_id, 
            campaign_id=self.campaign_id,
            subject=config.get("subject", "No Subject"), 
            body=config.get("body", ""),
            recipient_email=lead.email, 
            node_id=node["id"]
        )
        
        await self._add_journal_entry(
            lead.lead_id, 
            "Dispatched email task.", 
            node_id=node["id"],
            details={"task_id": task.id, "subject": config.get("subject")}
        )
        
        logger.info(f"[EMAIL_NODE] Email dispatched, moving to next node from {node['id']}")
        
        # Always move to next node after email dispatch
        await self._move_to_next_node(lead, node["id"])

    async def _execute_wait_node(self, lead: LeadModel, node: dict):
        logger.info(f"[WAIT_NODE] Executing wait node {node['id']} for lead {lead.lead_id}")
        config = node.get("configuration", {})
        
        try:
            wait_duration = int(config.get("waitDuration"))
            wait_unit = config.get("waitUnit")
            if wait_unit not in ["minutes", "hours", "days"]:
                raise ValueError(f"Invalid wait unit: {wait_unit}")
        except (ValueError, TypeError, KeyError) as e:
            return await self._update_lead_status(lead, "failed", f"Invalid wait configuration: {e}", node_id=node["id"])

        # Calculate wait time
        delta_map = {
            "minutes": timedelta(minutes=wait_duration), 
            "hours": timedelta(hours=wait_duration), 
            "days": timedelta(days=wait_duration)
        }
        delta = delta_map[wait_unit]
        eta = datetime.now(timezone.utc) + delta
        
        # Get next node
        next_node = self._get_next_node_id(node["id"])
        if not next_node:
            return await self._update_lead_status(lead, "failed", f"Wait node {node['id']} has no outgoing connection.", node_id=node["id"])

        logger.info(f"[WAIT_NODE] Wait for {wait_duration} {wait_unit}, next node: {next_node}, resume at: {eta}")

        # Update lead state for waiting - CRITICAL ORDER
        lead.current_node = node["id"]
        lead.next_node = next_node
        lead.wait_until = eta
        
        # Add to execution path if not already there
        if node["id"] not in lead.execution_path:
            lead.execution_path.append(node["id"])
        
        # Track this wait
        if node["id"] not in lead.completed_waits:
            lead.completed_waits.append(node["id"])

        # Mark as completed BEFORE changing status to paused
        if node["id"] not in lead.completed_tasks:
            lead.completed_tasks.append(node["id"])

        # STEP 1: Save lead state with all updates but keep status as "running"
        await lead.save()
        logger.info(f"[WAIT_NODE] Saved lead state before scheduling resume task")

        # STEP 2: Schedule resume task
        task = resume_lead_task.apply_async(args=[lead.lead_id, self.campaign_id], eta=eta)
        lead.scheduled_task_id = task.id

        # STEP 3: Save with task ID
        await lead.save()
        logger.info(f"[WAIT_NODE] Scheduled resume task {task.id} for {eta}")

        # STEP 4: ONLY NOW change status to paused - this ensures the task is scheduled for a lead that will be paused
        await self._update_lead_status(lead, "paused", f"Paused for {wait_duration} {wait_unit} until {eta.isoformat()}.", node_id=node["id"])
        
        logger.info(f"[WAIT_NODE] Successfully paused lead {lead.lead_id} at wait node {node['id']}")

    async def _execute_condition_node(self, lead: LeadModel, node: dict):
        logger.info(f"[CONDITION_NODE] Executing condition node {node['id']} for lead {lead.lead_id}")
        config = node.get("configuration", {})
        timeout_duration = int(config.get("timeout", 1))
        timeout_unit = config.get("unit", "days")
        
        delta_map = {
            "minutes": timedelta(minutes=timeout_duration), 
            "hours": timedelta(hours=timeout_duration), 
            "days": timedelta(days=timeout_duration)
        }
        delta = delta_map[timeout_unit]
        eta = datetime.now(timezone.utc) + delta

        # Update lead state
        lead.current_node = node["id"]
        lead.wait_until = eta
        
        if node["id"] not in lead.completed_tasks:
            lead.completed_tasks.append(node["id"])

        # Save state before scheduling
        await lead.save()
        logger.info(f"[CONDITION_NODE] Saved lead state before scheduling resume task")

        # Schedule resume task
        task = resume_condition_task.apply_async(
            args=[lead.lead_id, self.campaign_id], 
            kwargs={'condition_met': False}, 
            eta=eta
        )
        lead.scheduled_task_id = task.id
        await lead.save()

        logger.info(f"[CONDITION_NODE] Scheduled condition resume task {task.id} for {eta}")
        await self._update_lead_status(lead, "paused", f"Paused at condition for {timeout_duration} {timeout_unit} until {eta.isoformat()}.", node_id=node["id"])
        
    async def _execute_end_node(self, lead: LeadModel, node: dict):
        logger.info(f"[END_NODE] Executing end node {node['id']} for lead {lead.lead_id}")
        
        if node["id"] not in lead.completed_tasks:
            lead.completed_tasks.append(node["id"])
        
        lead.current_node = node["id"]
        if node["id"] not in lead.execution_path:
            lead.execution_path.append(node["id"])
            
        await lead.save()
        
        await self._update_lead_status(lead, "completed", "Flow completed.", node_id=node["id"])
        await self._check_campaign_completion()

    async def resume_lead(self, lead_id: str, condition_met: Optional[bool] = None):
        try:
            await self.load_campaign()
            lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})

            if not lead:
                logger.error(f"[RESUME_FAIL] Lead {lead_id} not found.")
                return

            logger.info(f"[RESUME_DEBUG] Lead {lead_id} status: {lead.status}, current_node: {lead.current_node}, next_node: {lead.next_node}")

            # IMPROVED: Handle different resume scenarios
            if lead.status == "completed":
                logger.info(f"[RESUME_IGNORE] Lead {lead_id} already completed.")
                return
            elif lead.status == "failed":
                logger.info(f"[RESUME_IGNORE] Lead {lead_id} already failed.")
                return
            elif lead.status == "pending":
                # This might be a timing issue - try to execute the lead normally
                logger.warning(f"[RESUME_PENDING] Lead {lead_id} has status 'pending', attempting normal execution.")
                await self.execute_lead(lead)
                return
            elif lead.status == "running":
                # Lead might be stuck - check if it should be paused
                if lead.wait_until and lead.wait_until > datetime.now(timezone.utc):
                    logger.warning(f"[RESUME_EARLY] Resume called early for lead {lead_id}, wait until: {lead.wait_until}")
                    return
                # Continue with resume
                logger.info(f"[RESUME_RUNNING] Lead {lead_id} is running, continuing with resume.")
            elif lead.status != "paused":
                logger.warning(f"[RESUME_IGNORE] Lead {lead_id} has unexpected status '{lead.status}' for resume.")
                return

            paused_node_id = lead.current_node
            paused_node = self.nodes.get(paused_node_id)
            if not paused_node:
                return await self._update_lead_status(lead, "failed", f"Resume failed: paused node {paused_node_id} not found.")

            # Clear pause state
            lead.wait_until = None
            lead.scheduled_task_id = None
            
            # CRITICAL: Save state before status update
            await lead.save()
            logger.info(f"[RESUME] Cleared pause state and saved to database")
            
            await self._update_lead_status(lead, "running", f"Resuming lead execution from {paused_node_id}.", node_id=paused_node_id)
            
            node_type = paused_node.get("type")
            logger.info(f"[RESUME] Resuming from {node_type} node {paused_node_id}")
            
            if node_type == "wait":
                await self._resume_wait_node(lead, paused_node_id)
            elif node_type == "condition":
                await self._resume_condition_node(lead, paused_node_id, condition_met if condition_met is not None else False)
            else:
                logger.warning(f"[RESUME] Unexpected paused node type: {node_type}. Moving to next.")
                await self._move_to_next_node(lead, paused_node_id)

            await self._check_campaign_completion()
            logger.info(f"[RESUME_COMPLETE] Resume completed for lead {lead_id}")

        except Exception as e:
            logger.error(f"[RESUME_ERROR] Resume lead {lead_id} failed: {e}", exc_info=True)
            if 'lead' in locals() and lead:
                await self._update_lead_status(lead, "failed", f"Resume failed: {str(e)}", details={"error": str(e)})

    async def _resume_wait_node(self, lead: LeadModel, paused_node_id: str):
        logger.info(f"[RESUME_WAIT] Resuming lead {lead.lead_id} from wait node {paused_node_id}")
        
        next_node_id = lead.next_node
        if not next_node_id:
            logger.error(f"[RESUME_WAIT] No next_node stored for lead {lead.lead_id}")
            return await self._update_lead_status(lead, "failed", "Resume failed: no next_node stored after wait.")
        
        logger.info(f"[RESUME_WAIT] Moving from wait node {paused_node_id} to next node {next_node_id}")
        
        # Clear next_node storage
        lead.next_node = None
        
        # Move to next node
        lead.current_node = next_node_id
        if next_node_id not in lead.execution_path:
            lead.execution_path.append(next_node_id)
        
        # Save state before executing next node
        await lead.save()
        logger.info(f"[RESUME_WAIT] Saved lead state - current_node: {next_node_id}")
        
        await self._add_journal_entry(lead.lead_id, f"Resumed from wait → moving to '{next_node_id}'", node_id=next_node_id)
        
        # Execute the next node
        await self._execute_node(next_node_id, lead)

    async def _resume_condition_node(self, lead: LeadModel, paused_node_id: str, condition_met: bool):
        logger.info(f"[RESUME_CONDITION] Resuming lead {lead.lead_id} from condition node {paused_node_id}, condition_met: {condition_met}")
        branch = "yes" if condition_met else "no"
        await self._move_to_next_node(lead, paused_node_id, branch=branch)

    async def _check_campaign_completion(self):
        try:
            active_leads_count = await LeadModel.find({
                "campaign_id": self.campaign_id, 
                "status": {"$in": ["running", "paused", "pending"]}  # Include pending leads
            }).count()
            
            logger.info(f"[CAMPAIGN_CHECK] Active leads count for campaign {self.campaign_id}: {active_leads_count}")
            
            if active_leads_count == 0:
                total_leads_count = await LeadModel.find({"campaign_id": self.campaign_id}).count()
                if total_leads_count > 0 and self.campaign.status != "completed":
                    self.campaign.status = "completed"
                    self.campaign.completed_at = datetime.now(timezone.utc)
                    await self.campaign.save()
                    logger.info(f"[CAMPAIGN_COMPLETE] Campaign {self.campaign_id} marked as completed")
        except Exception as e:
            logger.error(f"[CAMPAIGN_CHECK] Error checking campaign completion: {e}", exc_info=True)