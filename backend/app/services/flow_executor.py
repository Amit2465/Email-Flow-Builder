import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import pandas as pd
from io import StringIO

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
        lead.status = status
        lead.updated_at = datetime.now(timezone.utc)
        
        if status == "failed": 
            lead.error_message = message
        elif status == "completed": 
            lead.completed_at = datetime.now(timezone.utc)
        elif status == "running" and not lead.started_at:
            lead.started_at = datetime.now(timezone.utc)
            
        await lead.save()
        await self._add_journal_entry(lead.lead_id, message, node_id=node_id, details=details)

    async def load_campaign(self):
        self.campaign = await CampaignModel.find_one({"campaign_id": self.campaign_id})
        if not self.campaign: 
            raise ValueError(f"Campaign {self.campaign_id} not found")
        self.nodes = {node["id"]: node for node in self.campaign.nodes}
        self.connections = {conn["from_node"]: self.connections.get(conn["from_node"], []) + [conn] for conn in self.campaign.connections}
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
            headers = [h.strip().lower() for h in s.readline().split(',')]
            s.seek(0)
            df = pd.read_csv(s)
            df.columns = headers
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
            lead = LeadModel(
                lead_id=f"lead_{self.campaign_id}_{i}_{timestamp}", 
                campaign_id=self.campaign_id, 
                name=d.get("name","N/A"), 
                email=d["email"], 
                status="pending", 
                current_node=start_node_id, 
                execution_path=[start_node_id],
                created_at=current_time,
                updated_at=current_time
            )
            leads.append(lead)
        
        if leads:
            await LeadModel.insert_many(leads)
            for lead in leads: 
                await self._add_journal_entry(lead.lead_id, "Lead created.")
        return leads

    async def start_campaign(self, contact_file_data: dict):
        try:
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
                await self.campaign.save()
            raise

    async def execute_lead(self, lead: LeadModel):
        try:
            if lead.status in ["completed", "failed"]: 
                return
            
            if lead.status == "pending":
                await self._update_lead_status(lead, "running", "Lead execution started.")
                if not lead.started_at: 
                    lead.started_at = datetime.now(timezone.utc)
                    await lead.save()
            
            await self._execute_node(lead.current_node, lead)
        except Exception as e:
            logger.error(f"Execution failed for lead {lead.lead_id}: {e}", exc_info=True)
            await self._update_lead_status(lead, "failed", "Lead execution failed.", details={"error": str(e)})

    async def _execute_node(self, node_id: str, lead: LeadModel):
        node = self.nodes.get(node_id)
        if not node: 
            return await self._update_lead_status(lead, "failed", f"Node {node_id} not found", node_id=node_id)
        
        logger.info(f"[EXECUTE_NODE] Executing node {node_id} (type={node.get('type')}) for lead {lead.lead_id}")
        
        await self._add_journal_entry(lead.lead_id, f"Executing node.", node_id=node_id)
        
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
        if not next_node_id:
            await self._update_lead_status(lead, "completed", "Flow completed (no next node).", node_id=current_node_id)
            return await self._check_campaign_completion()
        
        logger.info(f"[MOVE_TO_NEXT] Lead {lead.lead_id} moving from {current_node_id} to {next_node_id}")
        
        lead.current_node = next_node_id
        if next_node_id not in lead.execution_path: 
            lead.execution_path.append(next_node_id)
        
        await lead.save()
        
        await self._add_journal_entry(lead.lead_id, f"Moved from '{current_node_id}' to '{next_node_id}'.", node_id=next_node_id)
        await self._execute_node(next_node_id, lead)

    async def _execute_start_node(self, lead: LeadModel, node: dict):
        await self._move_to_next_node(lead, node["id"])

    async def _execute_send_email_node(self, lead: LeadModel, node: dict):
        logger.info(f"[DEBUG] SENDING EMAIL from node {node['id']} to {lead.email}")
        
        config = node.get("configuration", {})
        subject = config.get("subject", "No Subject")
        body = config.get("body", "")
        
        # Update email tracking
        lead.email_sent_count += 1
        lead.last_email_sent_at = datetime.now(timezone.utc)
        await lead.save()
        
        send_email_task.delay(
            lead_id=lead.lead_id, 
            campaign_id=self.campaign_id, 
            subject=subject, 
            body=body, 
            recipient_email=lead.email
        )
        
        await self._add_journal_entry(
            lead.lead_id, 
            "Dispatched email task.", 
            node_id=node["id"], 
            details={"subject": subject, "email_count": lead.email_sent_count}
        )
        
        logger.info(f"[EMAIL_SENT] Email #{lead.email_sent_count} dispatched for lead {lead.lead_id}")
        
        await self._move_to_next_node(lead, node["id"])

    async def _execute_condition_node(self, lead: LeadModel, node: dict):
        config = node.get("configuration", {})
        timeout_duration = int(config.get("timeout", 1))
        timeout_unit = config.get("unit", "days")
        
        if timeout_unit not in ["minutes", "hours", "days"]:
            return await self._update_lead_status(
                lead, "failed", 
                f"Invalid timeout unit: {timeout_unit}", 
                node_id=node["id"]
            )

        delta = timedelta(days=timeout_duration)
        if timeout_unit == "minutes": 
            delta = timedelta(minutes=timeout_duration)
        elif timeout_unit == "hours": 
            delta = timedelta(hours=timeout_duration)
        
        eta = datetime.utcnow() + delta
        
        lead.current_node = node["id"]
        
        await self._update_lead_status(
            lead, "paused", 
            f"Paused at condition for {timeout_duration} {timeout_unit}.", 
            node_id=node["id"]
        )
        
        lead.wait_until = eta
        await lead.save()
        
        # Schedule resume task for CONDITION nodes with condition_met parameter
        task = resume_condition_task.apply_async(
            args=[lead.lead_id, self.campaign_id], 
            kwargs={'condition_met': False}, 
            eta=eta
        )
        
        lead.scheduled_task_id = task.id
        await lead.save()

    async def _execute_wait_node(self, lead: LeadModel, node: dict):
        """Fixed wait node execution"""
        config = node.get("configuration", {})
        wait_duration = config.get("waitDuration")
        wait_unit = config.get("waitUnit")

        # Validate required configuration
        if not wait_duration or not wait_unit:
            return await self._update_lead_status(
                lead, "failed", 
                f"Wait node missing duration or unit configuration", 
                node_id=node["id"]
            )

        try:
            wait_duration = int(wait_duration)
        except (ValueError, TypeError):
            return await self._update_lead_status(
                lead, "failed", 
                f"Invalid wait duration: {wait_duration}", 
                node_id=node["id"]
            )

        if wait_unit not in ["minutes", "hours", "days"]:
            return await self._update_lead_status(
                lead, "failed", 
                f"Invalid wait unit: {wait_unit}", 
                node_id=node["id"]
            )

        # Calculate wait time
        if wait_unit == "minutes": 
            delta = timedelta(minutes=wait_duration)
        elif wait_unit == "hours": 
            delta = timedelta(hours=wait_duration)
        else:  # days
            delta = timedelta(days=wait_duration)
        
        eta = datetime.utcnow() + delta
        
        # Get next node before pausing
        next_node = self._get_next_node_id(node["id"])
        if not next_node:
            return await self._update_lead_status(
                lead, "failed", 
                f"Config error: Wait node {node['id']} has no outgoing connection.", 
                node_id=node["id"]
            )
        
        # Update lead state
        lead.current_node = node["id"]
        lead.next_node = next_node  # Store next node for resume
        lead.wait_until = eta
        
        await self._update_lead_status(
            lead, "paused", 
            f"Paused for {wait_duration} {wait_unit}.", 
            node_id=node["id"]
        )
        
        await lead.save()
        
        # Schedule resume task for WAIT nodes - NO condition_met parameter
        task = resume_lead_task.apply_async(
            args=[lead.lead_id, self.campaign_id], 
            eta=eta
        )
        
        lead.scheduled_task_id = task.id
        await lead.save()
        
        logger.info(f"[WAIT_NODE] Lead {lead.lead_id} paused at node {node['id']} for {wait_duration} {wait_unit}, next node: {next_node}, resume at: {eta}")

    async def _execute_end_node(self, lead: LeadModel, node: dict):
        lead.current_node = node["id"]
        if node["id"] not in lead.execution_path: 
            lead.execution_path.append(node["id"])
        await self._update_lead_status(lead, "completed", "Flow completed.", node_id=node["id"])
        await self._check_campaign_completion()

    async def resume_lead(self, lead_id: str, condition_met: bool = False):
        """Fixed resume logic with better debugging"""
        try:
            # Reload campaign data to ensure we have latest state
            await self.load_campaign()
            
            lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})
            if not lead: 
                logger.error(f"Resume failed: Lead {lead_id} not found.")
                return

            logger.info(f"[RESUME_DEBUG] Lead {lead_id} current status: {lead.status}, current_node: {lead.current_node}, next_node: {lead.next_node}")

            if lead.status not in ["paused", "pending"]:
                logger.warning(f"Resume ignored for lead {lead_id}: invalid status {lead.status}")
                return await self._add_journal_entry(
                    lead.lead_id, 
                    "Resume ignored: invalid status.", 
                    details={"status": lead.status}
                )

            paused_node_id = lead.current_node
            paused_node = self.nodes.get(paused_node_id)
            if not paused_node:
                logger.error(f"Resume failed for lead {lead_id}: paused node {paused_node_id} not found")
                return await self._add_journal_entry(
                    lead.lead_id, 
                    "Resume failed: paused node not found.", 
                    details={"node_id": paused_node_id}
                )

            node_type = paused_node.get("type")
            logger.info(f"[RESUME] Lead {lead.lead_id} resuming from node {paused_node_id} (type: {node_type})")

            # Clear pause state first
            lead.wait_until = None
            lead.scheduled_task_id = None
            await lead.save()
            
            # Update status to running
            await self._update_lead_status(
                lead, "running", 
                "Resuming lead execution.", 
                node_id=paused_node_id, 
                details={"condition_met": condition_met}
            )
            
            await self._add_journal_entry(
                lead.lead_id, 
                "Lead resumed execution from pause.", 
                node_id=paused_node_id
            )
            
            # Handle different node types
            if node_type == "start":
                # For start nodes, just execute the node to move to next
                await self._execute_node(paused_node_id, lead)
            elif node_type in ["wait", "condition"]:
                # For pausable nodes, use specific resume logic
                if node_type == "wait": 
                    await self._resume_wait_node(lead, paused_node_id)
                elif node_type == "condition": 
                    await self._resume_condition_node(lead, paused_node_id, condition_met)
            else:
                # For other nodes, just execute them
                await self._execute_node(paused_node_id, lead)
            
            # If lead is still pending, start proper execution
            if lead.status == "pending":
                await self.execute_lead(lead)
            
            await self._check_campaign_completion()
            logger.info(f"[RESUME_COMPLETE] Lead {lead_id} resume process completed")
            
        except Exception as e:
            logger.error(f"Resume lead {lead_id} failed with error: {e}", exc_info=True)
            try:
                lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})
                if lead:
                    await self._update_lead_status(
                        lead, "failed", 
                        f"Resume failed: {str(e)}", 
                        details={"error": str(e)}
                    )
            except Exception as inner_e:
                logger.error(f"Failed to update lead status after resume error: {inner_e}")

    async def _resume_wait_node(self, lead: LeadModel, paused_node_id: str):
        """Fixed wait node resume logic with better debugging"""
        logger.info(f"[RESUME_WAIT] Starting resume for lead {lead.lead_id} from wait node {paused_node_id}")
        
        # Get next node from stored value or calculate it
        next_node = lead.next_node or self._get_next_node_id(paused_node_id)
        logger.info(f"[RESUME_WAIT] Next node after wait: {next_node} (from stored: {lead.next_node})")
        
        if not next_node:
            logger.error(f"[RESUME_WAIT] No next node found for wait node {paused_node_id}")
            return await self._update_lead_status(
                lead, "failed", 
                "Error: Wait node had no next node.", 
                node_id=paused_node_id
            )

        # Clear next_node storage
        lead.next_node = None
        
        # Move to next node
        lead.current_node = next_node
        if next_node not in lead.execution_path:
            lead.execution_path.append(next_node)
        lead.updated_at = datetime.now(timezone.utc)
        await lead.save()
        
        await self._add_journal_entry(
            lead.lead_id, 
            f"Resumed from wait → moving to '{next_node}'", 
            node_id=next_node
        )
        
        logger.info(f"[RESUME_WAIT] Lead {lead.lead_id} moved to node {next_node}, now executing...")
        
        # Execute the next node
        try:
            await self._execute_node(next_node, lead)
            logger.info(f"[RESUME_WAIT] Successfully executed node {next_node} for lead {lead.lead_id}")
        except Exception as e:
            logger.error(f"[RESUME_WAIT] Failed to execute node {next_node} for lead {lead.lead_id}: {e}", exc_info=True)
            await self._update_lead_status(
                lead, "failed", 
                f"Failed to execute node after wait: {str(e)}", 
                node_id=next_node,
                details={"error": str(e)}
            )

    async def _resume_condition_node(self, lead: LeadModel, paused_node_id: str, condition_met: bool):
        """Resume condition node with proper branching"""
        branch = "yes" if condition_met else "no"
        await self._move_to_next_node(lead, paused_node_id, branch=branch)

    async def _check_campaign_completion(self):
        """Check if campaign is complete"""
        active_leads = await LeadModel.find({
            "campaign_id": self.campaign_id, 
            "status": {"$in": ["running", "paused"]}
        }).count()
        
        total_leads = await LeadModel.find({"campaign_id": self.campaign_id}).count()
        
        if active_leads == 0 and total_leads > 0:
            self.campaign.status = "completed"
            self.campaign.completed_at = datetime.now(timezone.utc)
            await self.campaign.save()
            logger.info(f"[CAMPAIGN COMPLETE] Campaign {self.campaign_id} is completed successfully.")
            logger.info(f"Campaign {self.campaign_id} status set to 'completed'.")