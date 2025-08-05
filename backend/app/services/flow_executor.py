import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from io import StringIO
import asyncio
import uuid

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
        self.execution_id = str(uuid.uuid4())[:8]

    def _log_flow(self, lead_id: str, message: str, level: str = "info", **kwargs):
        """Structured logging for flow execution"""
        log_data = {
            "execution_id": self.execution_id,
            "campaign_id": self.campaign_id,
            "lead_id": lead_id,
            "message": message,
            **kwargs
        }
        if level == "info":
            logger.info(f"[FLOW] {log_data}")
        elif level == "warning":
            logger.warning(f"[FLOW] {log_data}")
        elif level == "error":
            logger.error(f"[FLOW] {log_data}")
        elif level == "debug":
            logger.debug(f"[FLOW] {log_data}")

    async def _add_journal_entry(self, lead_id: str, message: str, node_id: Optional[str] = None, details: Optional[dict] = None):
        try:
            node_type = self.nodes.get(node_id, {}).get("type") if node_id else None
            await LeadJournal(
                lead_id=lead_id,
                campaign_id=self.campaign_id,
                message=message,
                node_id=node_id,
                node_type=node_type,
                details=details
            ).insert()
            self._log_flow(lead_id, f"Journal entry added: {message}", node_id=node_id)
        except Exception as e:
            logger.error(f"[JOURNAL_ERROR] Failed to add journal entry for lead {lead_id}: {e}", exc_info=True)

    async def _update_lead_status(self, lead: LeadModel, status: str, message: str, node_id: Optional[str] = None, details: Optional[dict] = None):
        old_status = lead.status
        lead.status = status
        lead.updated_at = datetime.now(timezone.utc)

        self._log_flow(
            lead.lead_id,
            f"Status change: {old_status} → {status}",
            level="info",
            old_status=old_status,
            new_status=status,
            current_node=lead.current_node,
            node_id=node_id
        )

        if status == "failed":
            lead.error_message = message
        elif status == "completed":
            lead.completed_at = datetime.now(timezone.utc)
        elif status == "running" and not getattr(lead, "started_at", None):
            lead.started_at = datetime.now(timezone.utc)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await lead.save()
                self._log_flow(lead.lead_id, f"Status saved successfully: {status}", level="info")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    self._log_flow(lead.lead_id, f"Failed to save status after {max_retries} attempts: {e}", level="error")
                    raise
                self._log_flow(lead.lead_id, f"Retry {attempt + 1}/{max_retries} saving status: {e}", level="warning")
                await asyncio.sleep(0.1 * (attempt + 1))

        try:
            await self._add_journal_entry(lead.lead_id, message, node_id=node_id, details=details)
        except Exception as e:
            self._log_flow(lead.lead_id, f"Failed to add journal entry: {e}", level="error")

    async def load_campaign(self):
        self.campaign = await CampaignModel.find_one({"campaign_id": self.campaign_id})
        if not self.campaign:
            raise ValueError(f"Campaign {self.campaign_id} not found")
        self.nodes = {node["id"]: node for node in self.campaign.nodes}
        self.connections = {}
        for conn in self.campaign.connections:
            from_node = conn["from_node"]
            if from_node not in self.connections:
                self.connections[from_node] = []
            self.connections[from_node].append(conn)

        logger.info(f"[CAMPAIGN_LOAD] Campaign {self.campaign_id} loaded successfully")
        logger.info(f"[CAMPAIGN_LOAD] Nodes: {list(self.nodes.keys())}")
        logger.info(f"[CAMPAIGN_LOAD] Connections: {self.connections}")
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
                visit(conn["to_node"])
            visiting.remove(node_id)
            visited.add(node_id)

        start_node_id = self.campaign.workflow.get("start_node")
        if start_node_id:
            visit(start_node_id)
            logger.info(f"[FLOW_VALIDATION] Campaign flow validated - no loops detected")

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
            logger.info(f"[CREATE_LEAD_DEBUG] Creating lead {lead_id} for campaign {self.campaign_id}")
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
                completed_tasks=[],
                sent_emails=[],
                completed_waits=[],
                email_sent_count=0
            )
            leads.append(lead)

        if leads:
            await LeadModel.insert_many(leads)
            journal_tasks = [self._add_journal_entry(lead.lead_id, "Lead created.") for lead in leads]
            await asyncio.gather(*journal_tasks, return_exceptions=True)
            
        return leads

    async def start_campaign(self, contact_file_data: dict):
        try:
            logger.info(f"[CAMPAIGN_START] Starting campaign {self.campaign_id} with execution_id {self.execution_id}")
            await self.load_campaign()
            leads_data = await self.parse_contact_file(contact_file_data)
            if not leads_data:
                self.campaign.status = "completed"
                await self.campaign.save()
                logger.info(f"[CAMPAIGN_START] Campaign {self.campaign_id} completed - no leads to process")
                return {"status": "completed", "leads_count": 0}

            leads = await self.create_leads(leads_data)
            self.campaign.status = "running"
            await self.campaign.save()

            logger.info(f"[CAMPAIGN_START] Created {len(leads)} leads, starting concurrent execution")

            # ✅ CRITICAL: Reload leads from database to get fresh state
            fresh_leads = []
            for lead in leads:
                fresh_lead = await LeadModel.find_one({"lead_id": lead.lead_id})
                if fresh_lead:
                    fresh_leads.append(fresh_lead)
                else:
                    logger.error(f"[CAMPAIGN_START] Failed to reload lead {lead.lead_id} from database")

            tasks = [self.execute_lead(lead) for lead in fresh_leads]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            failed_leads = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_leads += 1
                    logger.error(f"[CONCURRENT_ERROR] Lead {leads[i].lead_id} failed: {result}")

            logger.info(f"[CAMPAIGN_START] Concurrent execution completed - {len(leads)} total, {failed_leads} failed")

            await self._check_campaign_completion()
            return {"status": "started", "leads_count": len(leads)}

        except Exception as e:
            logger.error(f"[CAMPAIGN_START_ERROR] Campaign start failed: {e}", exc_info=True)
            if self.campaign:
                self.campaign.status = "failed"
                self.campaign.error_message = str(e)
                await self.campaign.save()
            raise

    async def execute_lead(self, lead: LeadModel):
        """Main entry point for lead execution - handles initial execution only"""
        try:
            self._log_flow(lead.lead_id, f"Lead execution started - Status: {lead.status}, Current Node: {lead.current_node}", level="info")
            
            if lead.status in ["completed", "failed"]:
                self._log_flow(lead.lead_id, f"Lead already {lead.status}, skipping execution", level="info")
                return
            
            if lead.status == "paused":
                self._log_flow(lead.lead_id, "Lead is paused, will be resumed by Celery task", level="info")
                return
            
            # Set status to running for pending leads
            if lead.status == "pending":
                self._log_flow(lead.lead_id, "Updating status from pending to running", level="info")
                await self._update_lead_status(lead, "running", "Lead execution started.")
                # ✅ CRITICAL: Reload lead to get updated status
                lead = await LeadModel.find_one({"lead_id": lead.lead_id})
                self._log_flow(lead.lead_id, f"Reloaded lead, status is now: {lead.status}", level="info")
            
            # Start execution from current node
            self._log_flow(lead.lead_id, "About to call _execute_flow_from_current_node", level="info")
            await self._execute_flow_from_current_node(lead)
            self._log_flow(lead.lead_id, "Finished _execute_flow_from_current_node", level="info")
            
        except Exception as e:
            self._log_flow(lead.lead_id, f"Lead execution failed: {str(e)}", level="error", exc_info=True)
            await self._update_lead_status(lead, "failed", f"Lead execution failed: {str(e)}", details={"error": str(e)})

    async def _execute_flow_from_current_node(self, lead: LeadModel):
        """Execute the flow starting from the current node - handles any flow configuration"""
        try:
            self._log_flow(lead.lead_id, f"DEBUG: lead.current_node = {lead.current_node}", level="info")
            self._log_flow(lead.lead_id, f"DEBUG: self.nodes keys = {list(self.nodes.keys())}", level="info")
            
            if not lead.current_node:
                self._log_flow(lead.lead_id, "No current node found", level="error")
                await self._update_lead_status(lead, "failed", "No current node found.")
                return
            
            if lead.current_node not in self.nodes:
                self._log_flow(lead.lead_id, f"Current node {lead.current_node} not found in campaign", level="error")
                await self._update_lead_status(lead, "failed", f"Current node {lead.current_node} not found in campaign.")
                return
            
            # Start execution loop from current node
            current_node_id = lead.current_node
            self._log_flow(lead.lead_id, f"Starting flow execution from node: {current_node_id}", level="info")
            
            while current_node_id and lead.status == "running":
                # Check if lead was paused during execution
                fresh_lead = await LeadModel.find_one({"lead_id": lead.lead_id})
                if fresh_lead and fresh_lead.status != "running":
                    self._log_flow(lead.lead_id, f"Lead status changed to {fresh_lead.status}, stopping execution", level="info")
                    break
                
                # Execute current node
                self._log_flow(lead.lead_id, f"About to execute node: {current_node_id}", level="info")
                result = await self._execute_single_node(current_node_id, lead)
                self._log_flow(lead.lead_id, f"Node execution result: {result}", level="info")
                
                if result["status"] == "completed":
                    # Node completed successfully, move to next
                    current_node_id = result.get("next_node")
                elif result["status"] == "paused":
                    # Node paused (email/wait/condition), execution will resume via Celery
                    self._log_flow(lead.lead_id, f"Flow paused at node {current_node_id}", level="info")
                    break
                elif result["status"] == "failed":
                    # Node failed, stop execution
                    await self._update_lead_status(lead, "failed", result.get("message", "Node execution failed"))
                    break
                elif result["status"] == "flow_completed":
                    # Flow completed (end node or no next node)
                    await self._update_lead_status(lead, "completed", "Flow completed.")
                    await self._check_campaign_completion()
                    break
                    
        except Exception as e:
            self._log_flow(lead.lead_id, f"Flow execution failed: {str(e)}", level="error")
            await self._update_lead_status(lead, "failed", f"Flow execution failed: {str(e)}")

    async def _execute_single_node(self, node_id: str, lead: LeadModel) -> Dict[str, Any]:
        """Execute a single node and return execution result"""
        try:
            # Validate node exists
            node = self.nodes.get(node_id)
            if not node:
                return {"status": "failed", "message": f"Node {node_id} not found"}

            node_type = node.get("type")
            if not node_type:
                return {"status": "failed", "message": f"Node {node_id} missing type field"}
            
            self._log_flow(lead.lead_id, f"Executing node {node_id} of type {node_type}", level="info", node_id=node_id, node_type=node_type)
            
            # Check if node is already completed to prevent duplicates
            if node_id in lead.completed_tasks:
                self._log_flow(lead.lead_id, f"Node {node_id} already completed, skipping", level="info")
                next_node_id = self._get_next_node_id(node_id)
                return {"status": "completed", "next_node": next_node_id}
            
            # Mark node as being executed (atomic operation)
            await self._mark_node_as_executing(lead, node_id)
            
            # Execute node based on type
            dispatch = {
                "start": self._execute_start_node,
                "sendEmail": self._execute_send_email_node,
                "condition": self._execute_condition_node,
                "wait": self._execute_wait_node,
                "end": self._execute_end_node
            }

            if node_type not in dispatch:
                return {"status": "failed", "message": f"Unknown node type: {node_type}"}
            
            return await dispatch[node_type](lead, node)
            
        except Exception as e:
            self._log_flow(lead.lead_id, f"Node {node_id} execution failed: {str(e)}", level="error")
            return {"status": "failed", "message": f"Node execution failed: {str(e)}"}

    async def _mark_node_as_executing(self, lead: LeadModel, node_id: str):
        """Atomically mark a node as being executed to prevent duplicates"""
        if node_id not in lead.completed_tasks:
            lead.completed_tasks.append(node_id)
        if node_id not in lead.execution_path:
            lead.execution_path.append(node_id)
        
        lead.current_node = node_id
        lead.updated_at = datetime.now(timezone.utc)
        await lead.save()
        
        await self._add_journal_entry(lead.lead_id, f"Executing node {node_id}", node_id=node_id)

    def _get_next_node_id(self, current_node_id: str, branch: str = "default") -> Optional[str]:
        """Get the next node ID based on connection type"""
        for conn in self.connections.get(current_node_id, []):
            if conn.get("connection_type", "default") == branch:
                return conn["to_node"]
        return None

    async def _execute_start_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute start node - just move to next"""
        try:
            self._log_flow(lead.lead_id, f"Start node {node['id']} completed", level="info", node_id=node["id"])
            next_node_id = self._get_next_node_id(node["id"])
            return {"status": "completed", "next_node": next_node_id}
        except Exception as e:
            return {"status": "failed", "message": f"Start node execution failed: {str(e)}"}

    async def _execute_send_email_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute email node - send email and pause for Celery continuation"""
        try:
            config = node.get("configuration", {})
            subject = config.get("subject")
            body = config.get("body")
            
            # Validate configuration
            if not subject or not body:
                return {"status": "failed", "message": f"Email node {node['id']} missing subject or body"}
            
            if not lead.email:
                return {"status": "failed", "message": "Lead missing email address"}
            
            # Prevent duplicate email sending
            if node["id"] in lead.sent_emails:
                self._log_flow(lead.lead_id, f"Email node {node['id']} already sent, skipping", level="warning")
                next_node_id = self._get_next_node_id(node["id"])
                return {"status": "completed", "next_node": next_node_id}
            
            # ✅ ATOMIC OPERATION: Mark as sent and paused IMMEDIATELY
            lead.sent_emails.append(node["id"])
            lead.email_sent_count += 1
            lead.last_email_sent_at = datetime.now(timezone.utc)
            lead.status = "paused"  # Pause for Celery task

            # ✅ CRITICAL: Save IMMEDIATELY to establish atomic state
            await lead.save()
            await asyncio.sleep(0.5)  # Longer delay to ensure atomic state is fully established
            
            # Dispatch email task
            task_params = {
                "lead_id": lead.lead_id,
                "campaign_id": self.campaign_id,
                "subject": subject,
                "body": body,
                "recipient_email": lead.email,
                "node_id": node["id"]
            }
            
            task = send_email_task.delay(**task_params)
            
            self._log_flow(lead.lead_id, f"Email task dispatched for node {node['id']}", level="info", 
                          node_id=node["id"], task_id=task.id, subject=subject)
            
            await self._add_journal_entry(lead.lead_id, "Email task dispatched and lead paused.", 
                                        node_id=node["id"], details={"task_id": task.id, "subject": subject})
            
            return {"status": "paused", "message": "Email task dispatched"}
            
        except Exception as e:
            return {"status": "failed", "message": f"Email node execution failed: {str(e)}"}

    async def _execute_wait_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute wait node - schedule resume task and pause"""
        try:
            config = node.get("configuration", {})
            wait_duration = config.get("waitDuration")
            wait_unit = config.get("waitUnit")
            
            # Validate configuration
            if wait_duration is None or not wait_unit:
                return {"status": "failed", "message": f"Wait node {node['id']} missing duration or unit"}
            
            try:
                wait_duration = int(wait_duration)
                if wait_duration <= 0:
                    raise ValueError("Wait duration must be positive")
            except (ValueError, TypeError):
                return {"status": "failed", "message": f"Invalid wait duration: {wait_duration}"}
            
            if wait_unit not in ["minutes", "hours", "days"]:
                return {"status": "failed", "message": f"Invalid wait unit: {wait_unit}"}

            # Calculate resume time
            delta_map = {
                "minutes": timedelta(minutes=wait_duration),
                "hours": timedelta(hours=wait_duration),
                "days": timedelta(days=wait_duration)
            }
            delta = delta_map[wait_unit]
            eta = datetime.now(timezone.utc) + delta

            # Get next node
            next_node_id = self._get_next_node_id(node["id"])
            if not next_node_id:
                return {"status": "failed", "message": f"Wait node {node['id']} has no outgoing connection"}
            
            # Prevent duplicate wait execution
            if node["id"] in lead.completed_waits:
                self._log_flow(lead.lead_id, f"Wait node {node['id']} already completed, skipping", level="warning")
                return {"status": "completed", "next_node": next_node_id}
            
            # Mark as waiting and pause
            lead.completed_waits.append(node["id"])
            lead.next_node = next_node_id  # Store next node for resume
            lead.wait_until = eta
            lead.status = "paused"

            # Schedule resume task
            task = resume_lead_task.apply_async(args=[lead.lead_id, self.campaign_id], eta=eta)
            lead.scheduled_task_id = task.id
                    
            await lead.save()

            self._log_flow(lead.lead_id, f"Wait node {node['id']} paused for {wait_duration} {wait_unit}", 
                          level="info", node_id=node["id"], resume_at=eta.isoformat(), task_id=task.id)
            
            await self._add_journal_entry(lead.lead_id, f"Paused for {wait_duration} {wait_unit} until {eta.isoformat()}", 
                                        node_id=node["id"], details={"resume_task": task.id})
            
            return {"status": "paused", "message": f"Waiting for {wait_duration} {wait_unit}"}
            
        except Exception as e:
            return {"status": "failed", "message": f"Wait node execution failed: {str(e)}"}

    async def _execute_condition_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute condition node - pause for timeout"""
        try:
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

            # Pause and schedule condition timeout
            lead.wait_until = eta
            lead.status = "paused"

            task = resume_condition_task.apply_async(
                args=[lead.lead_id, self.campaign_id],
                kwargs={'condition_met': False},
                eta=eta
            )
            lead.scheduled_task_id = task.id
                    
            await lead.save()

            await self._update_lead_status(lead, "paused", 
                f"Paused at condition for {timeout_duration} {timeout_unit} until {eta.isoformat()}.",
                node_id=node["id"])
            
            return {"status": "paused", "message": f"Condition timeout set for {timeout_duration} {timeout_unit}"}
            
        except Exception as e:
            return {"status": "failed", "message": f"Condition node execution failed: {str(e)}"}

    async def _execute_end_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute end node - complete the flow"""
        try:
            self._log_flow(lead.lead_id, f"End node {node['id']} completed - flow finished", level="info", node_id=node["id"])
            return {"status": "flow_completed", "message": "Flow completed at end node"}
        except Exception as e:
            return {"status": "failed", "message": f"End node execution failed: {str(e)}"}

    async def resume_lead(self, lead_id: str, condition_met: Optional[bool] = None):
        """Resume lead execution after pause (called by Celery tasks)"""
        try:
            self._log_flow(lead_id, "Resume operation started", level="info")
            
            await self.load_campaign()
            lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})

            if not lead:
                self._log_flow(lead_id, "Lead not found", level="error")
                return

            if lead.status in ["completed", "failed"]:
                self._log_flow(lead_id, f"Lead already {lead.status}, skipping resume", level="info")
                return

            # Clear pause state
            paused_node_id = lead.current_node
            lead.wait_until = None
            lead.scheduled_task_id = None
            lead.status = "running"
            await lead.save()
            
            await self._update_lead_status(lead, "running", f"Resuming from {paused_node_id}")
            
            # Determine resume strategy based on paused node type
            paused_node = self.nodes.get(paused_node_id)
            if not paused_node:
                await self._update_lead_status(lead, "failed", f"Paused node {paused_node_id} not found")
                return

            node_type = paused_node.get("type")
            
            if node_type == "wait":
                # Resume from wait: move to stored next_node
                next_node_id = lead.next_node
                if not next_node_id:
                    await self._update_lead_status(lead, "failed", "No next node stored after wait")
                    return
                
                # ✅ CRITICAL: Validate next_node exists in campaign
                if next_node_id not in self.nodes:
                    await self._update_lead_status(lead, "failed", f"Next node {next_node_id} not found in campaign")
                    return
                
                lead.next_node = None  # Clear stored next node
                lead.current_node = next_node_id
                await lead.save()
                await self._execute_flow_from_current_node(lead)
                    
            elif node_type == "condition":
                # Resume from condition: use condition result to determine branch
                branch = "yes" if condition_met else "no"
                next_node_id = self._get_next_node_id(paused_node_id, branch)
                if next_node_id:
                    lead.current_node = next_node_id
                    await lead.save()
                    await self._execute_flow_from_current_node(lead)
                else:
                    await self._update_lead_status(lead, "completed", f"No next node for condition branch: {branch}")
                    
            else:
                # Resume from other node types (email, etc.): move to next node
                next_node_id = self._get_next_node_id(paused_node_id)
                if not next_node_id:
                    await self._update_lead_status(lead, "completed", "Flow completed (no next node)")
                    return
                
                # ✅ CRITICAL: Validate next_node exists in campaign
                if next_node_id not in self.nodes:
                    await self._update_lead_status(lead, "failed", f"Next node {next_node_id} not found in campaign")
                    return
                
                lead.current_node = next_node_id
                await lead.save()
                await self._execute_flow_from_current_node(lead)

            await self._check_campaign_completion()
            
        except Exception as e:
            self._log_flow(lead_id, f"Resume operation failed: {str(e)}", level="error")
            if 'lead' in locals() and lead:
                await self._update_lead_status(lead, "failed", f"Resume failed: {str(e)}")

    async def _check_campaign_completion(self):
        """Check if campaign is complete"""
        try:
            # Debug: Check all leads for this campaign
            all_leads = await LeadModel.find({"campaign_id": self.campaign_id}).to_list()
            logger.info(f"[CAMPAIGN_CHECK_DEBUG] Found {len(all_leads)} total leads for campaign {self.campaign_id}")
            
            for lead in all_leads:
                logger.info(f"[CAMPAIGN_CHECK_DEBUG] Lead {lead.lead_id}: status={lead.status}, current_node={lead.current_node}")
            
            active_leads_count = await LeadModel.find({
                "campaign_id": self.campaign_id,
                "status": {"$in": ["running", "paused", "pending"]}
            }).count()

            if active_leads_count == 0:
                total_leads_count = await LeadModel.find({"campaign_id": self.campaign_id}).count()
                if total_leads_count > 0 and self.campaign.status != "completed":
                    self.campaign.status = "completed"
                    self.campaign.completed_at = datetime.now(timezone.utc)
                    await self.campaign.save()
                    logger.info(f"[CAMPAIGN_COMPLETE] Campaign {self.campaign_id} completed with {total_leads_count} leads")
                else:
                    logger.info(f"[CAMPAIGN_CHECK] Campaign {self.campaign_id} - {active_leads_count} active leads, {total_leads_count} total leads")
            else:
                logger.info(f"[CAMPAIGN_CHECK] Campaign {self.campaign_id} - {active_leads_count} active leads remaining")
        except Exception as e:
            logger.error(f"[CAMPAIGN_CHECK] Error checking campaign completion: {e}", exc_info=True)