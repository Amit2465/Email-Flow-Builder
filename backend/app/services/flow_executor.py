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
        logger.info(f"[CAMPAIGN_LOAD] Attempting to load campaign {self.campaign_id}")
        self.campaign = await CampaignModel.find_one({"campaign_id": self.campaign_id})
        
        if not self.campaign:
            logger.error(f"[CAMPAIGN_LOAD] Campaign {self.campaign_id} not found in database")
            # Try to find any campaigns to debug
            all_campaigns = await CampaignModel.find().to_list()
            logger.error(f"[CAMPAIGN_LOAD] Available campaigns: {[c.campaign_id for c in all_campaigns]}")
            raise ValueError(f"Campaign {self.campaign_id} not found in database")
        
        logger.info(f"[CAMPAIGN_LOAD] Campaign {self.campaign_id} loaded successfully")
        logger.info(f"[CAMPAIGN_LOAD] Campaign status: {self.campaign.status}")
        logger.info(f"[CAMPAIGN_LOAD] Campaign nodes count: {len(self.campaign.nodes)}")
        
        self.nodes = {node["id"]: node for node in self.campaign.nodes}
        self.connections = {}
        for conn in self.campaign.connections:
            from_node = conn["from_node"]
            if from_node not in self.connections:
                self.connections[from_node] = []
            self.connections[from_node].append(conn)

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

    async def _validate_condition_nodes(self):
        """✅ ENHANCED: Comprehensive validation for condition nodes and campaign structure"""
        try:
            condition_nodes = [node for node in self.campaign.nodes if node.get("type") == "condition"]
            
            for condition_node in condition_nodes:
                condition_id = condition_node["id"]
                config = condition_node.get("configuration", {})
                condition_type = config.get("conditionType", "open")
                
                # ✅ ENHANCED: Validate condition node has both YES and NO paths
                yes_node_id = self._get_next_node_id(condition_id, "yes")
                no_node_id = self._get_next_node_id(condition_id, "no")
                
                if not yes_node_id:
                    error_msg = f"Condition node {condition_id} missing YES path"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                if not no_node_id:
                    error_msg = f"Condition node {condition_id} missing NO path"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                # ✅ ENHANCED: Validate NO path starts with wait node
                no_node = self.nodes.get(no_node_id)
                if not no_node or no_node.get("type") != "wait":
                    error_msg = f"Condition node {condition_id} NO path must start with wait node, found: {no_node.get('type') if no_node else 'None'}"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                # Find the preceding email node
                preceding_email_node = self._find_preceding_email_node(condition_id)
                
                if not preceding_email_node:
                    error_msg = f"Condition node {condition_id} must be connected to an email node for tracking"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                # ✅ ENHANCED: Validate condition type
                if condition_type not in ["open", "click"]:
                    error_msg = f"Condition node {condition_id} invalid condition type: {condition_type}"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                # For link click conditions, validate links exist
                if condition_type == "click":
                    email_links = preceding_email_node.get("configuration", {}).get("links", [])
                    valid_links = [link for link in email_links if link.get("text") and link.get("url")]
                    
                    if not valid_links:
                        error_msg = f"Condition node {condition_id} (click type) must have valid links in preceding email"
                        logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                        raise ValueError(error_msg)
                
                logger.info(f"[CAMPAIGN_VALIDATION] Condition node {condition_id} validated successfully")
            
            logger.info(f"[CAMPAIGN_VALIDATION] All {len(condition_nodes)} condition nodes validated successfully")
            
            # ✅ ENHANCED: Validate campaign structure
            await self._validate_campaign_structure()
            
        except Exception as e:
            logger.error(f"[CAMPAIGN_VALIDATION] Campaign validation failed: {e}", exc_info=True)
            raise

    async def _validate_campaign_structure(self):
        """✅ NEW: Validate overall campaign structure"""
        try:
            # Check for infinite loops
            if self._detect_loops():
                error_msg = "Campaign contains infinite loops"
                logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                raise ValueError(error_msg)
            
            # Validate all paths reach end nodes
            start_nodes = [node for node in self.campaign.nodes if node.get("type") == "start"]
            end_nodes = [node for node in self.campaign.nodes if node.get("type") == "end"]
            
            if not start_nodes:
                error_msg = "Campaign must have at least one start node"
                logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                raise ValueError(error_msg)
            
            if not end_nodes:
                error_msg = "Campaign must have at least one end node"
                logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                raise ValueError(error_msg)
            
            # Validate node connections
            for connection in self.campaign.connections:
                from_node = connection.get("from_node")
                to_node = connection.get("to_node")
                
                if from_node not in self.nodes:
                    error_msg = f"Connection from non-existent node: {from_node}"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
                
                if to_node not in self.nodes:
                    error_msg = f"Connection to non-existent node: {to_node}"
                    logger.error(f"[CAMPAIGN_VALIDATION] {error_msg}")
                    raise ValueError(error_msg)
            
            logger.info(f"[CAMPAIGN_VALIDATION] Campaign structure validation passed")
            
        except Exception as e:
            logger.error(f"[CAMPAIGN_VALIDATION] Campaign structure validation failed: {e}", exc_info=True)
            raise

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
            
            # Load campaign first
            await self.load_campaign()
            
            # Validate campaign state
            if not self.campaign:
                logger.error(f"[CAMPAIGN_START] Campaign {self.campaign_id} not loaded")
                return {"status": "failed", "message": "Campaign not found"}
            
            if self.campaign.status in ["running", "completed", "failed"]:
                logger.warning(f"[CAMPAIGN_START] Campaign {self.campaign_id} already in state: {self.campaign.status}")
                return {"status": self.campaign.status, "message": f"Campaign already {self.campaign.status}"}
            
            # Log campaign configuration
            logger.info(f"[CAMPAIGN_START] Campaign configuration:", {
                "campaign_id": self.campaign_id,
                "nodes_count": len(self.nodes),
                "connections_count": len(self.connections),
                "start_node": self.campaign.workflow.get("start_node")
            })
            
            # Validate condition nodes have proper email connections
            await self._validate_condition_nodes()
            
            leads_data = await self.parse_contact_file(contact_file_data)
            
            logger.info(f"[CAMPAIGN_START] Contact file parsed:", {
                "total_contacts": len(leads_data),
                "valid_emails": len([lead for lead in leads_data if lead.get("email", "").strip()]),
                "invalid_emails": len([lead for lead in leads_data if not lead.get("email", "").strip()])
            })
            
            if not leads_data:
                logger.warning(f"[CAMPAIGN_START] No valid leads found in contact file")
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
            try:
                if self.campaign:
                    self.campaign.status = "failed"
                    self.campaign.error_message = str(e)
                    await self.campaign.save()
                else:
                    # Try to load campaign and update status
                    await self.load_campaign()
                    if self.campaign:
                        self.campaign.status = "failed"
                        self.campaign.error_message = str(e)
                        await self.campaign.save()
            except Exception as save_error:
                logger.error(f"[CAMPAIGN_START_ERROR] Failed to update campaign status: {save_error}")
            raise

    async def execute_lead(self, lead: LeadModel):
        """Main entry point for lead execution - handles initial execution only"""
        try:
            self._log_flow(lead.lead_id, f"Lead execution started - Status: {lead.status}, Current Node: {lead.current_node}", level="info")
            
            # Validate lead state
            if not lead.email or not lead.email.strip():
                self._log_flow(lead.lead_id, "Lead missing email address", level="error")
                await self._update_lead_status(lead, "failed", "Lead missing email address")
                return
            
            if lead.status in ["completed", "failed"]:
                self._log_flow(lead.lead_id, f"Lead already {lead.status}, skipping execution", level="info")
                return
            
            if lead.status == "paused":
                self._log_flow(lead.lead_id, "Lead is paused, will be resumed by Celery task", level="info")
                return
            
            # Validate current node exists
            if not lead.current_node:
                self._log_flow(lead.lead_id, "Lead missing current node", level="error")
                await self._update_lead_status(lead, "failed", "Lead missing current node")
                return
            
            if lead.current_node not in self.nodes:
                self._log_flow(lead.lead_id, f"Lead current node {lead.current_node} not found in campaign", level="error")
                await self._update_lead_status(lead, "failed", f"Lead current node {lead.current_node} not found in campaign")
                return
            
            # Set status to running for pending leads
            if lead.status == "pending":
                self._log_flow(lead.lead_id, "Updating status from pending to running", level="info")
                await self._update_lead_status(lead, "running", "Lead execution started.")
                # ✅ CRITICAL: Reload lead to get updated status
                lead = await LeadModel.find_one({"lead_id": lead.lead_id})
                if not lead:
                    self._log_flow(lead.lead_id, "Failed to reload lead from database", level="error")
                    return
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
            self._log_flow(lead.lead_id, "=== FLOW EXECUTION STARTED ===", level="info")
            self._log_flow(lead.lead_id, f"Lead ID: {lead.lead_id}", level="info")
            self._log_flow(lead.lead_id, f"Campaign ID: {self.campaign_id}", level="info")
            self._log_flow(lead.lead_id, f"Current node: {lead.current_node}", level="info")
            self._log_flow(lead.lead_id, f"Available nodes: {list(self.nodes.keys())}", level="debug")
            self._log_flow(lead.lead_id, f"Lead status: {lead.status}", level="debug")
            
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
            
            execution_count = 0
            while current_node_id and lead.status == "running":
                execution_count += 1
                self._log_flow(lead.lead_id, f"=== EXECUTION STEP {execution_count} ===", level="info")
                self._log_flow(lead.lead_id, f"Current node: {current_node_id}", level="info")
                
                # Check if lead was paused during execution
                try:
                    fresh_lead = await LeadModel.find_one({"lead_id": lead.lead_id})
                    if fresh_lead and fresh_lead.status != "running":
                        self._log_flow(lead.lead_id, f"Lead status changed to {fresh_lead.status}, stopping execution", level="info")
                        break
                except Exception as fresh_error:
                    self._log_flow(lead.lead_id, f"Failed to check fresh lead status: {fresh_error}", level="warning")
                    # Continue execution if we can't check fresh status
                
                # Execute current node
                self._log_flow(lead.lead_id, f"Executing node: {current_node_id}", level="info")
                result = await self._execute_single_node(current_node_id, lead)
                self._log_flow(lead.lead_id, f"Node execution result: {result}", level="info")
                
                if result["status"] == "completed":
                    # Node completed successfully, move to next
                    current_node_id = result.get("next_node")
                    # ✅ FIXED: Update lead's current_node to reflect the new position
                    if current_node_id:
                        lead.current_node = current_node_id
                        await lead.save()
                elif result["status"] == "condition_met":
                    # ✅ FIXED: Original lead continues NO path, YES path triggers in parallel
                    yes_node_id = self._get_next_node_id(current_node_id, "yes")
                    no_node_id = self._get_next_node_id(current_node_id, "no")
                    
                    self._log_flow(lead.lead_id, f"Condition met - triggering YES path in parallel, continuing NO path", level="info")
                    
                    # Trigger YES path in parallel (doesn't affect original lead)
                    if yes_node_id:
                        self._log_flow(lead.lead_id, f"Triggering YES path in parallel with node: {yes_node_id}", level="info")
                        await self._trigger_yes_path_parallel(lead, yes_node_id)
                    else:
                        self._log_flow(lead.lead_id, f"No YES path found for condition node", level="warning")
                    
                    # ✅ CRITICAL: Original lead continues NO path (timeout mechanism)
                    if no_node_id:
                        self._log_flow(lead.lead_id, f"Original lead continuing NO path with node: {no_node_id}", level="info")
                        current_node_id = no_node_id
                        # ✅ FIXED: Update lead's current_node to reflect the new position
                        lead.current_node = current_node_id
                        await lead.save()
                        # Continue execution loop - don't break!
                    else:
                        self._log_flow(lead.lead_id, f"ERROR: No NO path found for condition node", level="error")
                        await self._update_lead_status(lead, "failed", "No NO path found for condition node")
                        break
                elif result["status"] == "no_branch_executing":
                    # NO branch executes automatically as timeout mechanism
                    if "next_node" in result:
                        current_node_id = result["next_node"]
                        self._log_flow(lead.lead_id, f"NO branch executing automatically: {current_node_id}", level="info")
                        # ✅ FIXED: Update lead's current_node to reflect the new position
                        lead.current_node = current_node_id
                        await lead.save()
                    else:
                        current_node_id = self._get_next_node_id(current_node_id, "no")
                        if current_node_id:
                            self._log_flow(lead.lead_id, f"NO branch executing automatically: {current_node_id}", level="info")
                            # ✅ FIXED: Update lead's current_node to reflect the new position
                            lead.current_node = current_node_id
                            await lead.save()
                        else:
                            self._log_flow(lead.lead_id, f"ERROR: No NO path found for condition node", level="error")
                            await self._update_lead_status(lead, "failed", "No NO path found for condition node")
                            break
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
            self._log_flow(lead.lead_id, f"=== SINGLE NODE EXECUTION STARTED ===", level="debug")
            self._log_flow(lead.lead_id, f"Node ID: {node_id}", level="debug")
            self._log_flow(lead.lead_id, f"Lead ID: {lead.lead_id}", level="debug")
            
            # Validate node exists
            node = self.nodes.get(node_id)
            if not node:
                self._log_flow(lead.lead_id, f"Node {node_id} not found in campaign", level="error")
                return {"status": "failed", "message": f"Node {node_id} not found"}

            node_type = node.get("type")
            if not node_type:
                self._log_flow(lead.lead_id, f"Node {node_id} missing type field", level="error")
                return {"status": "failed", "message": f"Node {node_id} missing type field"}
            
            self._log_flow(lead.lead_id, f"Executing node {node_id} of type {node_type}", level="info", node_id=node_id, node_type=node_type)
            
            # Check if node is already completed to prevent duplicates
            if node_id in lead.completed_tasks:
                self._log_flow(lead.lead_id, f"Node {node_id} already completed, skipping", level="info")
                next_node_id = self._get_next_node_id(node_id)
                return {"status": "completed", "next_node": next_node_id}
            
            # Mark node as being executed (atomic operation)
            self._log_flow(lead.lead_id, f"Marking node {node_id} as executing", level="debug")
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
        try:
            # Reload lead to get fresh state and prevent race conditions
            fresh_lead = await LeadModel.find_one({"lead_id": lead.lead_id})
            if fresh_lead:
                lead = fresh_lead
            
            if node_id not in lead.completed_tasks:
                lead.completed_tasks.append(node_id)
            if node_id not in lead.execution_path:
                lead.execution_path.append(node_id)
            
            lead.current_node = node_id
            lead.updated_at = datetime.now(timezone.utc)
            await lead.save()
            
            await self._add_journal_entry(lead.lead_id, f"Executing node {node_id}", node_id=node_id)
        except Exception as e:
            logger.error(f"[NODE_EXECUTION] Failed to mark node {node_id} as executing: {e}", exc_info=True)
            raise

    def _get_next_node_id(self, current_node_id: str, branch: str = "default") -> Optional[str]:
        """Get the next node ID based on connection type or branch"""
        connections = self.connections.get(current_node_id, [])
        
        # Debug logging
        if branch in ["yes", "no"]:
            self._log_flow("system", f"Looking for {branch} branch for node {current_node_id}", level="debug")
            self._log_flow("system", f"Available connections: {[c.get('id', '') for c in connections]}", level="debug")
            self._log_flow("system", f"Connection details: {connections}", level="debug")
        
        # First try to find by connection_type
        for conn in connections:
            if conn.get("connection_type", "default") == branch:
                self._log_flow("system", f"Found {branch} branch by connection_type: {conn['to_node']}", level="debug")
                return conn["to_node"]
        
        # If not found and branch is "yes" or "no", look for connections with branch in the ID
        if branch in ["yes", "no"]:
            for conn in connections:
                if branch in conn.get("id", ""):
                    self._log_flow("system", f"Found {branch} branch by connection ID: {conn['to_node']}", level="debug")
                    return conn["to_node"]
        
        # For default branch, return the first connection
        if branch == "default" and connections:
            self._log_flow("system", f"Using default branch: {connections[0]['to_node']}", level="debug")
            return connections[0]["to_node"]
        
        self._log_flow("system", f"No {branch} branch found for node {current_node_id}", level="warning")
        return None

    def _find_preceding_email_node(self, target_node_id: str, visited: set = None) -> Optional[dict]:
        """Find the email node that comes before the target node (recursively through condition nodes)"""
        if visited is None:
            visited = set()
        
        if target_node_id in visited:
            self._log_flow("system", f"Infinite loop detected in node traversal: {target_node_id}", level="warning")
            return None  # Prevent infinite loops
        visited.add(target_node_id)
        
        self._log_flow("system", f"Searching for email node before {target_node_id}", level="debug")
        
        # Find all nodes that connect to our target node
        for node_id, node in self.nodes.items():
            if node.get("type") == "sendEmail":
                # Check if this email node connects to our target node
                next_node_id = self._get_next_node_id(node_id)
                if next_node_id == target_node_id:
                    self._log_flow("system", f"Found email node {node_id} before condition node {target_node_id}", level="info")
                    return node
            elif node.get("type") == "condition":
                # Check if this condition node connects to our target node
                next_node_id = self._get_next_node_id(node_id)
                if next_node_id == target_node_id:
                    self._log_flow("system", f"Found condition node {node_id} before target, recursing", level="debug")
                    # Recursively find email node before this condition node
                    result = self._find_preceding_email_node(node_id, visited)
                    if result:
                        return result
        
        # Also check connections from the campaign data
        for connection in self.campaign.connections:
            if connection.get("to_node") == target_node_id:
                from_node_id = connection.get("from_node")
                from_node = self.nodes.get(from_node_id)
                
                if from_node and from_node.get("type") == "sendEmail":
                    self._log_flow("system", f"Found email node {from_node_id} before condition node {target_node_id}", level="info")
                    return from_node
                elif from_node and from_node.get("type") == "condition":
                    self._log_flow("system", f"Found condition node {from_node_id} before target, recursing", level="debug")
                    # Recursively find email node before this condition node
                    result = self._find_preceding_email_node(from_node_id, visited)
                    if result:
                        return result
        
        self._log_flow("system", f"No email node found before {target_node_id}", level="warning")
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
            
            # Validate email content length
            if len(subject.strip()) == 0:
                return {"status": "failed", "message": f"Email node {node['id']} has empty subject"}
            
            if len(body.strip()) == 0:
                return {"status": "failed", "message": f"Email node {node['id']} has empty body"}
            
            # Validate email content length limits
            if len(subject) > 200:
                return {"status": "failed", "message": f"Email node {node['id']} subject too long (max 200 chars)"}
            
            if len(body) > 50000:
                return {"status": "failed", "message": f"Email node {node['id']} body too long (max 50KB)"}
            
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
            
            # Get links from email node configuration
            email_links = config.get("links", [])
            valid_links = [link for link in email_links if link.get("text") and link.get("url")]
            
            # Dispatch email task
            task_params = {
                "lead_id": lead.lead_id,
                "campaign_id": self.campaign_id,
                "subject": subject,
                "body": body,
                "recipient_email": lead.email,
                "node_id": node["id"],
                "links": valid_links
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
            self._log_flow(lead.lead_id, f"Starting wait node execution: {node['id']}", level="info", node_id=node["id"])
            
            config = node.get("configuration", {})
            wait_duration = config.get("waitDuration")
            wait_unit = config.get("waitUnit")
            
            self._log_flow(lead.lead_id, f"Wait node config: duration={wait_duration}, unit={wait_unit}", level="debug", node_id=node["id"])
            
            # Validate configuration
            if wait_duration is None or not wait_unit:
                self._log_flow(lead.lead_id, f"Wait node {node['id']} missing duration or unit", level="error", node_id=node["id"])
                return {"status": "failed", "message": f"Wait node {node['id']} missing duration or unit"}
            
            try:
                wait_duration = int(wait_duration)
                if wait_duration <= 0:
                    raise ValueError("Wait duration must be positive")
            except (ValueError, TypeError):
                self._log_flow(lead.lead_id, f"Invalid wait duration: {wait_duration}", level="error", node_id=node["id"])
                return {"status": "failed", "message": f"Invalid wait duration: {wait_duration}"}
            
            if wait_unit not in ["minutes", "hours", "days"]:
                self._log_flow(lead.lead_id, f"Invalid wait unit: {wait_unit}", level="error", node_id=node["id"])
                return {"status": "failed", "message": f"Invalid wait unit: {wait_unit}"}

            # Calculate resume time
            delta_map = {
                "minutes": timedelta(minutes=wait_duration),
                "hours": timedelta(hours=wait_duration),
                "days": timedelta(days=wait_duration)
            }
            delta = delta_map[wait_unit]
            eta = datetime.now(timezone.utc) + delta

            self._log_flow(lead.lead_id, f"Calculated wait time: {wait_duration} {wait_unit} = {delta}, ETA: {eta.isoformat()}", level="debug", node_id=node["id"])

            # Get next node
            next_node_id = self._get_next_node_id(node["id"])
            if not next_node_id:
                self._log_flow(lead.lead_id, f"Wait node {node['id']} has no outgoing connection", level="error", node_id=node["id"])
                return {"status": "failed", "message": f"Wait node {node['id']} has no outgoing connection"}
            
            self._log_flow(lead.lead_id, f"Wait node next node: {next_node_id}", level="debug", node_id=node["id"])
            
            # Prevent duplicate wait execution
            if node["id"] in lead.completed_waits:
                self._log_flow(lead.lead_id, f"Wait node {node['id']} already completed, skipping", level="warning", node_id=node["id"])
                return {"status": "completed", "next_node": next_node_id}
            
            # Mark as waiting and pause
            lead.completed_waits.append(node["id"])
            lead.next_node = next_node_id  # Store next node for resume
            lead.wait_until = eta
            lead.status = "paused"

            self._log_flow(lead.lead_id, f"Updated lead status to paused, next_node={next_node_id}, wait_until={eta.isoformat()}", level="debug", node_id=node["id"])

            # Schedule resume task
            self._log_flow(lead.lead_id, f"Scheduling Celery task for resume at {eta.isoformat()}", level="info", node_id=node["id"])
            task = resume_lead_task.apply_async(args=[lead.lead_id, self.campaign_id], eta=eta)
            lead.scheduled_task_id = task.id
            
            self._log_flow(lead.lead_id, f"Celery task scheduled: {task.id}", level="debug", node_id=node["id"])
                        
            await lead.save()
            self._log_flow(lead.lead_id, f"Lead saved with paused status and scheduled task", level="debug", node_id=node["id"])

            self._log_flow(lead.lead_id, f"Wait node {node['id']} paused for {wait_duration} {wait_unit}", 
                          level="info", node_id=node["id"], resume_at=eta.isoformat(), task_id=task.id)
            
            await self._add_journal_entry(lead.lead_id, f"Paused for {wait_duration} {wait_unit} until {eta.isoformat()}", 
                                        node_id=node["id"], details={"resume_task": task.id})
            
            return {"status": "paused", "message": f"Waiting for {wait_duration} {wait_unit}"}
            
        except Exception as e:
            self._log_flow(lead.lead_id, f"Wait node execution failed: {str(e)}", level="error", node_id=node["id"])
            return {"status": "failed", "message": f"Wait node execution failed: {str(e)}"}

    async def _execute_condition_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute condition node - NO branch runs automatically as timeout mechanism"""
        try:
            from app.services.event_tracker import EventTracker
            
            config = node.get("configuration", {})
            condition_type = config.get("conditionType", "open")
            
            self._log_flow(lead.lead_id, f"Executing condition node {node['id']}: {condition_type}", level="info", node_id=node["id"])
            self._log_flow(lead.lead_id, f"Condition node config: {config}", level="debug", node_id=node["id"])
            
            # Find the preceding email node to get the original email content
            preceding_email_node = self._find_preceding_email_node(node["id"])
            if not preceding_email_node:
                self._log_flow(lead.lead_id, f"No preceding email node found for condition {node['id']}", level="error", node_id=node["id"])
                return {"status": "failed", "message": "Condition node must be connected to an email node"}
            
            # For link click conditions, validate the target link exists in the email
            if condition_type == "click":
                email_links = preceding_email_node.get("configuration", {}).get("links", [])
                valid_links = [link for link in email_links if link.get("text") and link.get("url")]
                
                if not valid_links:
                    self._log_flow(lead.lead_id, f"No valid links found in preceding email for click tracking", level="error", node_id=node["id"])
                    return {"status": "failed", "message": "No valid links found in preceding email"}
                
                # Always use the first valid link (automatic detection)
                link_url = valid_links[0].get("url")
                link_text = valid_links[0].get("text", "Click here")
                self._log_flow(lead.lead_id, f"Using first valid link: {link_text} -> {link_url}", level="info", node_id=node["id"])
            else:
                link_url = ""
                link_text = ""
            
            # ✅ CRITICAL FIX: Check if there's already an event for this lead (email was opened before reaching condition)
            event_tracker = EventTracker(self.campaign_id)
            existing_event = await event_tracker.check_existing_event(lead.lead_id, condition_type, link_url if condition_type == "click" else None)
            
            self._log_flow(lead.lead_id, f"Checking for existing event: type={condition_type}, existing={existing_event}", level="debug", node_id=node["id"])
            
            if existing_event:
                # Event already happened, switch to YES path immediately
                self._log_flow(lead.lead_id, f"Event already occurred, switching to YES path", level="info", node_id=node["id"])
                await self._add_journal_entry(lead.lead_id, f"Condition met - switching to YES path", node_id=node["id"])
                
                # ✅ FIXED: Switch original lead to YES path immediately
                yes_node_id = self._get_next_node_id(node["id"], "yes")
                if yes_node_id:
                    self._log_flow(lead.lead_id, f"Switching to YES path immediately: {yes_node_id}", level="info", node_id=node["id"])
                    
                    # Update the original lead to continue with YES path
                    lead.current_node = yes_node_id
                    lead.execution_path.append(yes_node_id)
                    await lead.save()
                    
                    # Execute the YES path with the original lead
                    await self._execute_flow_from_current_node(lead)
                    self._log_flow(lead.lead_id, f"Original lead now executing YES path", level="info")
                else:
                    self._log_flow(lead.lead_id, f"No YES path found for condition node", level="warning")
                    await self._update_lead_status(lead, "completed", "No YES path found")
                
                return {"status": "condition_met", "message": "Event already occurred, switched to YES path"}
            
            # ✅ ENHANCED: Create waiting event with full email context
            # ✅ FIXED: Ensure correct event type based on condition type
            if condition_type == "open":
                event_type = "email_open"
            elif condition_type == "click":
                event_type = "link_click"
            else:
                # Fallback for unknown condition types
                event_type = "link_click" if condition_type else "email_open"
            
            # ✅ DEBUG: Log the condition type and event type for debugging
            self._log_flow(lead.lead_id, f"Condition type: {condition_type}, Event type: {event_type}", level="debug", node_id=node["id"])
            
            # Build email context for proper event tracking
            email_context = {
                "email_node_id": preceding_email_node["id"],
                "subject": preceding_email_node.get("configuration", {}).get("subject", "Unknown"),
                "body": preceding_email_node.get("configuration", {}).get("body", ""),
                "links": preceding_email_node.get("configuration", {}).get("links", []),
                "condition_chain": lead.execution_path[-3:] if len(lead.execution_path) >= 3 else lead.execution_path,  # Last 3 nodes for context
                "context": {
                    "condition_type": condition_type,
                    "target_link_text": link_text,
                    "target_link_url": link_url,
                    "lead_type": lead.lead_type
                }
            }
            
            try:
                self._log_flow(lead.lead_id, f"Creating waiting event for {event_type} with context", level="debug", node_id=node["id"])
                self._log_flow(lead.lead_id, f"Event context: {email_context}", level="debug", node_id=node["id"])
                
                await event_tracker.create_waiting_event_with_context(
                    lead_id=lead.lead_id,
                    condition_node_id=node["id"],
                    email_context=email_context,
                    event_type=event_type,
                    target_url=link_url if condition_type == "click" else None
                )
                self._log_flow(lead.lead_id, f"Created waiting event for {event_type} with context", level="info", node_id=node["id"])
            except Exception as event_error:
                self._log_flow(lead.lead_id, f"Failed to create waiting event: {event_error}", level="error", node_id=node["id"])
                return {"status": "failed", "message": f"Failed to create waiting event: {event_error}"}
            
            # Log the target URL for debugging
            if condition_type == "click" and link_url:
                self._log_flow(lead.lead_id, f"Waiting for click on URL: {link_url}", level="info", node_id=node["id"])
            
            # ✅ UPDATED: NO branch executes automatically as timeout mechanism
            self._log_flow(lead.lead_id, f"NO branch executes automatically as timeout mechanism", level="info", node_id=node["id"])
            await self._add_journal_entry(lead.lead_id, f"NO branch started automatically - waiting for event to trigger YES path", node_id=node["id"])
            
            # Get the NO path node and execute it immediately
            no_node_id = self._get_next_node_id(node["id"], "no")
            if no_node_id:
                self._log_flow(lead.lead_id, f"NO path node found: {no_node_id} - executing immediately", level="info", node_id=node["id"])
                return {"status": "no_branch_executing", "message": "NO branch executing as timeout mechanism", "next_node": no_node_id}
            else:
                self._log_flow(lead.lead_id, f"ERROR: No NO path node found for condition {node['id']}", level="error", node_id=node["id"])
                return {"status": "failed", "message": "No NO path node found for condition"}
            
        except Exception as e:
            return {"status": "failed", "message": f"Condition node execution failed: {str(e)}"}

    async def _execute_end_node(self, lead: LeadModel, node: dict) -> Dict[str, Any]:
        """Execute end node - complete the flow"""
        try:
            self._log_flow(lead.lead_id, f"End node {node['id']} completed - flow finished", level="info", node_id=node["id"])
            
            # ✅ FIXED: Check if this lead affects campaign completion (original or no_branch leads)
            if lead.lead_type in ["original", "no_branch"]:
                self._log_flow(lead.lead_id, f"Lead type '{lead.lead_type}' end node reached - this affects campaign completion", level="info", node_id=node["id"])
                await self._add_journal_entry(lead.lead_id, f"Lead type '{lead.lead_type}' completed - campaign completion check needed", node_id=node["id"])
                
                # Trigger campaign completion check since a timeout mechanism finished
                await self._check_campaign_completion()
            else:
                self._log_flow(lead.lead_id, f"YES branch lead end node reached - does not affect campaign completion", level="info", node_id=node["id"])
            
            return {"status": "flow_completed", "message": "Flow completed at end node"}
        except Exception as e:
            return {"status": "failed", "message": f"End node execution failed: {str(e)}"}

    async def resume_lead(self, lead_id: str, condition_met: Optional[bool] = None):
        """Resume lead execution after pause (called by Celery tasks)"""
        try:
            self._log_flow(lead_id, "=== RESUME LEAD OPERATION STARTED ===", level="info")
            self._log_flow(lead_id, f"Lead ID: {lead_id}", level="info")
            self._log_flow(lead_id, f"Campaign ID: {self.campaign_id}", level="info")
            self._log_flow(lead_id, f"Condition met: {condition_met}", level="info")
            self._log_flow(lead_id, f"Timestamp: {datetime.now(timezone.utc).isoformat()}", level="info")
            
            await self.load_campaign()
            self._log_flow(lead_id, "Campaign loaded successfully", level="debug")
            
            lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})

            if not lead:
                self._log_flow(lead_id, "Lead not found in database", level="error")
                return

            self._log_flow(lead_id, f"Found lead: status={lead.status}, current_node={lead.current_node}", level="debug")

            if lead.status in ["completed", "failed"]:
                self._log_flow(lead_id, f"Lead already {lead.status}, skipping resume", level="info")
                return

            # Clear pause state
            paused_node_id = lead.current_node
            old_status = lead.status
            lead.wait_until = None
            lead.scheduled_task_id = None
            lead.status = "running"
            await lead.save()
            
            self._log_flow(lead_id, f"Lead status changed: {old_status} → running", level="info")
            self._log_flow(lead_id, f"Cleared wait_until and scheduled_task_id", level="debug")
            await self._update_lead_status(lead, "running", f"Resuming from {paused_node_id}")
            
            # Determine resume strategy based on paused node type
            paused_node = self.nodes.get(paused_node_id)
            if not paused_node:
                self._log_flow(lead_id, f"Paused node {paused_node_id} not found in campaign", level="error")
                await self._update_lead_status(lead, "failed", f"Paused node {paused_node_id} not found")
                return

            node_type = paused_node.get("type")
            self._log_flow(lead_id, f"Resuming from node type: {node_type}", level="info")
            
            if node_type == "wait":
                # Resume from wait: move to stored next_node
                next_node_id = lead.next_node
                self._log_flow(lead_id, f"Wait node resume - stored next_node: {next_node_id}", level="debug")
                
                if not next_node_id:
                    self._log_flow(lead_id, "No next node stored after wait", level="error")
                    await self._update_lead_status(lead, "failed", "No next node stored after wait")
                    return
                
                # ✅ CRITICAL: Validate next_node exists in campaign
                if next_node_id not in self.nodes:
                    self._log_flow(lead_id, f"Next node {next_node_id} not found in campaign", level="error")
                    await self._update_lead_status(lead, "failed", f"Next node {next_node_id} not found in campaign")
                    return
                
                lead.next_node = None  # Clear stored next node
                lead.current_node = next_node_id
                await lead.save()
                self._log_flow(lead_id, f"Wait resume: moved to next node {next_node_id}", level="info")
                await self._execute_flow_from_current_node(lead)
                    
            elif node_type == "condition":
                # Resume from condition: use condition result to determine branch
                if condition_met is None:
                    # This shouldn't happen for condition nodes, but handle gracefully
                    self._log_flow(lead_id, f"Condition resume with condition_met=None - this is unexpected", level="warning")
                    next_node_id = self._get_next_node_id(paused_node_id, "no")  # Default to NO branch
                else:
                    branch = "yes" if condition_met else "no"
                    next_node_id = self._get_next_node_id(paused_node_id, branch)
                
                self._log_flow(lead_id, f"Condition resume: condition_met={condition_met}, branch={branch}, next_node={next_node_id}", level="info")
                
                if next_node_id:
                    lead.current_node = next_node_id
                    await lead.save()
                    self._log_flow(lead_id, f"Condition resume: moved to {branch} branch node {next_node_id}", level="info")
                    await self._execute_flow_from_current_node(lead)
                else:
                    self._log_flow(lead_id, f"No next node for condition branch: {branch}", level="error")
                    await self._update_lead_status(lead, "completed", f"No next node for condition branch: {branch}")
                    
            elif node_type == "sendEmail":
                # ✅ FIXED: Email nodes are completed, not resumed - move to next node
                self._log_flow(lead_id, f"Email node completed, moving to next node", level="info")
                next_node_id = self._get_next_node_id(paused_node_id)
                
                if not next_node_id:
                    self._log_flow(lead_id, "Flow completed (no next node after email)", level="info")
                    await self._update_lead_status(lead, "completed", "Flow completed (no next node after email)")
                    return
                
                # ✅ CRITICAL: Validate next_node exists in campaign
                if next_node_id not in self.nodes:
                    self._log_flow(lead_id, f"Next node {next_node_id} not found in campaign", level="error")
                    await self._update_lead_status(lead, "failed", f"Next node {next_node_id} not found in campaign")
                    return
                
                lead.current_node = next_node_id
                await lead.save()
                self._log_flow(lead_id, f"Email resume: moved to next node {next_node_id}", level="info")
                await self._execute_flow_from_current_node(lead)
                    
            else:
                # Resume from other node types (wait, etc.): move to next node
                next_node_id = self._get_next_node_id(paused_node_id)
                self._log_flow(lead_id, f"Other node resume - next_node: {next_node_id}", level="debug")
                
                if not next_node_id:
                    self._log_flow(lead_id, "Flow completed (no next node)", level="info")
                    await self._update_lead_status(lead, "completed", "Flow completed (no next node)")
                    return
                
                # ✅ CRITICAL: Validate next_node exists in campaign
                if next_node_id not in self.nodes:
                    self._log_flow(lead_id, f"Next node {next_node_id} not found in campaign", level="error")
                    await self._update_lead_status(lead, "failed", f"Next node {next_node_id} not found in campaign")
                    return
                
                lead.current_node = next_node_id
                await lead.save()
                self._log_flow(lead_id, f"Other node resume: moved to next node {next_node_id}", level="info")
                await self._execute_flow_from_current_node(lead)

            await self._check_campaign_completion()
            
            self._log_flow(lead_id, "=== RESUME LEAD OPERATION COMPLETED ===", level="info")
            
        except Exception as e:
            self._log_flow(lead_id, "=== RESUME LEAD OPERATION FAILED ===", level="error")
            self._log_flow(lead_id, f"Error: {str(e)}", level="error")
            if 'lead' in locals() and lead:
                await self._update_lead_status(lead, "failed", f"Resume failed: {str(e)}")

    async def resume_lead_from_condition(self, lead_id: str, condition_node_id: str, condition_met: bool):
        """Resume lead execution from a specific condition node when event occurs - interrupts NO branch"""
        try:
            from app.services.event_tracker import EventTracker
            
            logger.info(f"=== RESUMING LEAD FROM CONDITION ===")
            logger.info(f"Lead ID: {lead_id}")
            logger.info(f"Condition Node ID: {condition_node_id}")
            logger.info(f"Condition Met: {condition_met}")
            logger.info(f"Campaign ID: {self.campaign_id}")
            
            self._log_flow(lead_id, f"Resume from condition {condition_node_id} started - event occurred", level="info")
            
            await self.load_campaign()
            lead = await LeadModel.find_one({"lead_id": lead_id, "campaign_id": self.campaign_id})

            if not lead:
                self._log_flow(lead_id, "Lead not found", level="error")
                return

            if lead.status in ["completed", "failed"]:
                self._log_flow(lead_id, f"Lead already {lead.status}, skipping resume", level="info")
                return

            # Validate condition node exists
            condition_node = self.nodes.get(condition_node_id)
            if not condition_node or condition_node.get("type") != "condition":
                self._log_flow(lead_id, f"Condition node {condition_node_id} not found or invalid", level="error")
                return

            # Clear waiting events for this condition node
            event_tracker = EventTracker(self.campaign_id)
            await event_tracker.clear_waiting_events(lead_id, condition_node_id)

            # ✅ ENHANCED: Robust task revocation with verification
            if lead.scheduled_task_id:
                try:
                    from app.celery_config import celery_app
                    
                    # Revoke with verification
                    celery_app.control.revoke(lead.scheduled_task_id, terminate=True, reply=True)
                    
                    # Wait for confirmation
                    await asyncio.sleep(0.1)
                    
                    # Verify task is actually cancelled
                    from celery.result import AsyncResult
                    result = AsyncResult(lead.scheduled_task_id, app=celery_app)
                    
                    if result.state == 'REVOKED':
                        self._log_flow(lead_id, f"Task {lead.scheduled_task_id} successfully revoked", level="info")
                        lead.scheduled_task_id = None
                        await lead.save()
                    else:
                        self._log_flow(lead_id, f"Task {lead.scheduled_task_id} revocation uncertain, state: {result.state}", level="warning")
                        
                except Exception as e:
                    self._log_flow(lead_id, f"Failed to cancel scheduled task: {e}", level="warning")
                    lead.scheduled_task_id = None

            # Clear pause state
            lead.status = "running"
            await lead.save()
            
            await self._update_lead_status(lead, "running", f"Event occurred - resuming from condition node {condition_node_id}")
            
            # ✅ FIXED: When event occurs, switch original lead to YES path
            if condition_met:
                yes_node_id = self._get_next_node_id(condition_node_id, "yes")
                
                self._log_flow(lead_id, f"Event occurred - switching to YES path", level="info")
                self._log_flow(lead_id, f"YES path: {yes_node_id}", level="info")
                
                # Switch the original lead to YES path (this is what user expects)
                if yes_node_id:
                    self._log_flow(lead_id, f"Switching original lead to YES path: {yes_node_id}", level="info")
                    
                    # Update the original lead to continue with YES path
                    lead.current_node = yes_node_id
                    lead.execution_path.append(yes_node_id)
                    await lead.save()
                    
                    # Execute the YES path with the original lead
                    logger.info(f"=== EXECUTING YES PATH ===")
                    logger.info(f"Lead ID: {lead_id}")
                    logger.info(f"YES Node ID: {yes_node_id}")
                    await self._execute_flow_from_current_node(lead)
                    self._log_flow(lead_id, f"Original lead now executing YES path", level="info")
                    logger.info(f"=== YES PATH EXECUTION COMPLETE ===")
                else:
                    self._log_flow(lead_id, f"No YES path found for condition node", level="warning")
                    await self._update_lead_status(lead, "completed", "No YES path found")
            else:
                # This shouldn't happen in normal flow, but handle gracefully
                self._log_flow(lead_id, f"Condition not met but event occurred - this is unexpected", level="warning")
                next_node_id = self._get_next_node_id(condition_node_id, "no")
                
                if next_node_id:
                    lead.current_node = next_node_id
                    await lead.save()
                    await self._execute_flow_from_current_node(lead)
                else:
                    await self._update_lead_status(lead, "completed", "No next node for condition branch: no")

            await self._check_campaign_completion()
            
        except Exception as e:
            self._log_flow(lead_id, f"Resume from condition failed: {str(e)}", level="error")
            if 'lead' in locals() and lead:
                await self._update_lead_status(lead, "failed", f"Resume from condition failed: {str(e)}")

    async def _execute_parallel_path(self, lead: LeadModel, start_node_id: str, path_name: str):
        """Execute a parallel path starting from a specific node"""
        try:
            self._log_flow(lead.lead_id, f"Starting parallel {path_name} path from node {start_node_id}", level="info")
            
            # Check if parallel lead already exists to prevent duplicates
            parallel_lead_id = f"{lead.lead_id}_{path_name.lower()}"
            existing_parallel_lead = await LeadModel.find_one({"lead_id": parallel_lead_id})
            
            if existing_parallel_lead:
                self._log_flow(lead.lead_id, f"Parallel {path_name} path already exists: {parallel_lead_id}", level="warning")
                return
            
            # Create a copy of the lead for this parallel path
            parallel_lead = LeadModel(
                lead_id=parallel_lead_id,
                campaign_id=lead.campaign_id,
                name=lead.name,
                email=lead.email,
                status="running",
                current_node=start_node_id,
                execution_path=[start_node_id],
                created_at=lead.created_at,
                updated_at=datetime.now(timezone.utc),
                completed_tasks=[],
                sent_emails=[],
                completed_waits=[],
                email_sent_count=lead.email_sent_count
            )
            
            await parallel_lead.insert()
            await self._add_journal_entry(parallel_lead.lead_id, f"Started parallel {path_name} path", node_id=start_node_id)
            
            # Execute the parallel path
            try:
                await self._execute_flow_from_current_node(parallel_lead)
                
                # Log path completion for campaign tracking
                if path_name == "NO":
                    self._log_flow(parallel_lead.lead_id, f"NO branch path completed - this affects campaign completion", level="info")
                    # Trigger campaign completion check since a NO branch finished
                    await self._check_campaign_completion()
                else:
                    self._log_flow(parallel_lead.lead_id, f"YES branch path completed - does not affect campaign completion", level="info")
            except Exception as execution_error:
                self._log_flow(parallel_lead.lead_id, f"Parallel path execution failed: {execution_error}", level="error")
                # Don't raise - let the original lead continue
            
        except Exception as e:
            self._log_flow(lead.lead_id, f"Failed to execute parallel {path_name} path: {str(e)}", level="error")
            raise



    async def _check_campaign_completion(self):
        """✅ FIXED: Campaign completes when all timeout mechanisms (NO branches) finish"""
        try:
            # Get all leads for this campaign
            all_leads = await LeadModel.find({"campaign_id": self.campaign_id}).to_list()
            logger.info(f"[CAMPAIGN_CHECK_DEBUG] Found {len(all_leads)} total leads for campaign {self.campaign_id}")
            
            # ✅ FIXED: Simplified lead counting since we no longer use parallel leads
            active_leads = [lead for lead in all_leads if lead.status in ["running", "paused", "pending"]]
            
            logger.info(f"[CAMPAIGN_CHECK_DEBUG] Active leads: {len(active_leads)}")
            
            # Log all leads for debugging
            for lead in all_leads:
                logger.info(f"[CAMPAIGN_CHECK_DEBUG] Lead {lead.lead_id}: status={lead.status}, current_node={lead.current_node}")
            
            if len(active_leads) == 0:
                total_leads_count = len(all_leads)
                if total_leads_count > 0 and self.campaign.status != "completed":
                    try:
                        self.campaign.status = "completed"
                        self.campaign.completed_at = datetime.now(timezone.utc)
                        await self.campaign.save()
                        logger.info(f"[CAMPAIGN_COMPLETE] Campaign {self.campaign_id} completed with {total_leads_count} total leads")
                        logger.info(f"[CAMPAIGN_COMPLETE] All leads have finished execution")
                    except Exception as save_error:
                        logger.error(f"[CAMPAIGN_COMPLETE] Failed to save campaign completion: {save_error}")
                else:
                    logger.info(f"[CAMPAIGN_CHECK] Campaign {self.campaign_id} already completed")
            else:
                logger.info(f"[CAMPAIGN_CHECK] Campaign {self.campaign_id} - {len(active_leads)} active leads remaining")
                
        except Exception as e:
            logger.error(f"[CAMPAIGN_CHECK] Error checking campaign completion: {e}", exc_info=True)