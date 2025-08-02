import logging
import io
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.models.campaign import CampaignModel
from app.models.lead import LeadModel
from app.services.email import send_email_with_tracking
import pandas as pd

logger = logging.getLogger(__name__)


class FlowExecutor:
    """
    Handles execution of campaign flows for individual leads
    """
    
    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id
        self.campaign = None
        self.nodes = {}
        self.connections = {}
        self.start_node = None
        
    async def load_campaign(self):
        """Load campaign data and build execution graph"""
        self.campaign = await CampaignModel.find_one({"campaign_id": self.campaign_id})
        if not self.campaign:
            raise ValueError(f"Campaign {self.campaign_id} not found")
            
        # Build node lookup
        for node in self.campaign.nodes:
            self.nodes[node["id"]] = node
            
        # Build connection lookup
        for conn in self.campaign.connections:
            source = conn["from_node"]
            if source not in self.connections:
                self.connections[source] = []
            self.connections[source].append(conn)
            
        self.start_node = self.campaign.workflow.get("start_node", "start-1")
        logger.info(f"Loaded campaign {self.campaign_id} with {len(self.nodes)} nodes")
        
        # Analyze flow structure
        self._analyze_flow_structure()
    
    def _analyze_flow_structure(self):
        """Analyze the flow structure to determine if it's linear or conditional"""
        has_condition_nodes = False
        has_branching = False
        
        for node in self.campaign.nodes:
            if node.get("type") == "condition":
                has_condition_nodes = True
                # Check if condition node has proper yes/no branches
                connections = self.connections.get(node["id"], [])
                has_yes = any(conn.get("connection_type") == "yes" for conn in connections)
                has_no = any(conn.get("connection_type") == "no" for conn in connections)
                
                if has_yes and has_no:
                    has_branching = True
                    logger.info(f"Found conditional node {node['id']} with proper yes/no branches")
                else:
                    logger.info(f"Found condition node {node['id']} without proper branches (treating as linear)")
        
        if has_condition_nodes and has_branching:
            logger.info("=== FLOW ANALYSIS: CONDITIONAL FLOW ===")
            logger.info("This campaign contains conditional logic with email open tracking")
        else:
            logger.info("=== FLOW ANALYSIS: LINEAR FLOW ===")
            logger.info("This campaign is a linear flow without conditional branching")
        
        logger.info(f"Total nodes: {len(self.campaign.nodes)}")
        logger.info(f"Total connections: {len(self.campaign.connections)}")
        logger.info(f"Has condition nodes: {has_condition_nodes}")
        logger.info(f"Has proper branching: {has_branching}")
            
    async def parse_contact_file(self, contact_file_data: dict) -> List[Dict[str, str]]:
        """Parse uploaded contact file into leads"""
        try:
            # For now, assume CSV format
            file_content = contact_file_data.get("content", "")
            if not file_content:
                raise ValueError("No file content provided")
                
            logger.info(f"Parsing contact file content: {len(file_content)} characters")
            logger.info(f"First 200 characters: {file_content[:200]}")
                
            # Parse CSV content - handle headers properly
            # First try with headers
            try:
                df = pd.read_csv(io.StringIO(file_content))
                logger.info("CSV parsed with headers")
            except Exception as header_error:
                logger.info(f"Failed to parse with headers: {header_error}")
                # Try without headers (first row is data)
                try:
                    df = pd.read_csv(io.StringIO(file_content), header=None)
                    # Create default column names
                    if len(df.columns) >= 2:
                        df.columns = ['Name', 'Email'] + [f'Col_{i}' for i in range(2, len(df.columns))]
                    else:
                        df.columns = ['Name']
                    logger.info("CSV parsed without headers, using default column names")
                except Exception as no_header_error:
                    raise ValueError(f"Failed to parse CSV: {no_header_error}")
            
            logger.info(f"CSV columns found: {list(df.columns)}")
            logger.info(f"CSV shape: {df.shape}")
            logger.info(f"First few rows: {df.head().to_dict()}")
            
            # Try to find email column (case insensitive)
            email_column = None
            name_column = None
            
            for col in df.columns:
                col_lower = str(col).lower().strip()
                if col_lower in ['email', 'e-mail', 'mail', 'e_mail']:
                    email_column = col
                elif col_lower in ['name', 'fullname', 'full_name', 'firstname', 'first_name', 'contact_name']:
                    name_column = col
            
            # If no name column found, use first column or create default
            if not name_column:
                if len(df.columns) > 1:
                    name_column = df.columns[0]  # Use first column as name
                else:
                    # Create default names
                    df['Name'] = [f'Contact {i+1}' for i in range(len(df))]
                    name_column = 'Name'
            
            # If no email column found, use second column or raise error
            if not email_column:
                if len(df.columns) > 1:
                    email_column = df.columns[1]  # Use second column as email
                else:
                    raise ValueError("No email column found in CSV")
            
            logger.info(f"Using name column: {name_column}")
            logger.info(f"Using email column: {email_column}")
            
            # Convert to list of dictionaries
            leads = []
            for index, row in df.iterrows():
                try:
                    name = str(row[name_column]).strip()
                    email = str(row[email_column]).strip().lower()
                    
                    # Skip empty rows or invalid emails
                    if not email or email == 'nan' or email == '':
                        logger.debug(f"Skipping row {index}: empty email")
                        continue
                    
                    # Basic email validation
                    if '@' not in email or '.' not in email:
                        logger.debug(f"Skipping row {index}: invalid email format: {email}")
                        continue
                    
                    # Clean up name
                    if not name or name == 'nan' or name == '':
                        name = f"Contact {index+1}"
                    
                    lead = {
                        "name": name,
                        "email": email,
                    }
                    leads.append(lead)
                    logger.debug(f"Added lead: {name} <{email}>")
                    
                except Exception as row_error:
                    logger.warning(f"Error processing row {index}: {row_error}")
                    continue
                
            logger.info(f"Parsed {len(leads)} valid leads from contact file")
            if len(leads) == 0:
                raise ValueError("No valid leads found in CSV file")
            return leads
            
        except Exception as e:
            logger.error(f"Failed to parse contact file: {e}")
            raise
            
    async def create_leads(self, leads_data: List[Dict[str, str]]) -> List[LeadModel]:
        """Create LeadModel instances for all leads"""
        leads = []
        for i, lead_data in enumerate(leads_data):
            lead = LeadModel(
                lead_id=f"lead_{self.campaign_id}_{i}_{int(datetime.now().timestamp())}",
                campaign_id=self.campaign_id,
                name=lead_data["name"],
                email=lead_data["email"],
                current_node=self.start_node,
                status="pending"
            )
            leads.append(lead)
            
        # Bulk insert
        await LeadModel.insert_many(leads)
        logger.info(f"Created {len(leads)} leads for campaign {self.campaign_id}")
        return leads
        
    async def start_campaign(self, contact_file_data: dict):
        """Start campaign execution for all leads"""
        try:
            logger.info("=" * 50)
            logger.info("=== FLOW EXECUTOR: STARTING CAMPAIGN ===")
            logger.info(f"Campaign ID: {self.campaign_id}")
            logger.info("=" * 50)
            
            logger.info("Step 1: Loading campaign data...")
            await self.load_campaign()
            logger.info(f"Campaign loaded successfully with {len(self.nodes)} nodes")
            
            logger.info("Step 2: Parsing contact file...")
            leads_data = await self.parse_contact_file(contact_file_data)
            logger.info(f"Parsed {len(leads_data)} leads from contact file")
            
            logger.info("Step 3: Creating lead records...")
            leads = await self.create_leads(leads_data)
            logger.info(f"Created {len(leads)} lead records in database")
            
            logger.info("Step 4: Updating campaign status...")
            self.campaign.status = "running"
            await self.campaign.save()
            logger.info("Campaign status updated to 'running'")
            
            logger.info("Step 5: Starting execution for all leads...")
            execution_count = 0
            for i, lead in enumerate(leads):
                logger.info(f"Executing lead {i+1}/{len(leads)}: {lead.lead_id}")
                await self.execute_lead(lead)
                execution_count += 1
                logger.info(f"Lead {lead.lead_id} execution completed")
                
            logger.info("=" * 50)
            logger.info("=== FLOW EXECUTOR: CAMPAIGN COMPLETED ===")
            logger.info(f"Campaign ID: {self.campaign_id}")
            logger.info(f"Total leads processed: {execution_count}")
            logger.info("=" * 50)
            
            return {"status": "started", "leads_count": len(leads)}
            
        except Exception as e:
            logger.error("=" * 50)
            logger.error("=== FLOW EXECUTOR: CAMPAIGN FAILED ===")
            logger.error(f"Campaign ID: {self.campaign_id}")
            logger.error(f"Error: {str(e)}")
            logger.error("=" * 50)
            raise
            
    async def execute_lead(self, lead: LeadModel):
        """Execute flow for a single lead"""
        try:
            if lead.status in ["completed", "failed"]:
                return
                
            # Update lead status
            lead.status = "running"
            if not lead.started_at:
                lead.started_at = datetime.now()
            lead.updated_at = datetime.now()
            await lead.save()
            
            # Execute current node
            await self._execute_node(lead)
            
        except Exception as e:
            logger.error(f"Failed to execute lead {lead.lead_id}: {e}")
            lead.status = "failed"
            lead.error_message = str(e)
            lead.updated_at = datetime.now()
            await lead.save()
            
    async def _execute_node(self, lead: LeadModel):
        """Execute the current node for a lead"""
        node_id = lead.current_node
        node = self.nodes.get(node_id)
        
        if not node:
            logger.error(f"Node {node_id} not found for lead {lead.lead_id}")
            lead.status = "failed"
            lead.error_message = f"Node {node_id} not found"
            await lead.save()
            return
            
        node_type = node.get("type", "unknown")
        logger.info(f"Executing {node_type} node {node_id} for lead {lead.lead_id}")
        
        # Add to execution path
        if node_id not in lead.execution_path:
            lead.execution_path.append(node_id)
            
        # Execute based on node type
        if node_type == "start":
            await self._execute_start_node(lead, node)
        elif node_type == "sendEmail":
            await self._execute_send_email_node(lead, node)
        elif node_type == "condition":
            await self._execute_condition_node(lead, node)
        elif node_type == "wait":
            await self._execute_wait_node(lead, node)
        elif node_type == "end":
            await self._execute_end_node(lead, node)
        else:
            logger.warning(f"Unknown node type: {node_type}")
            await self._move_to_next_node(lead, node_id)
    
    def _get_next_node_id(self, current_node_id: str, branch: str = "default") -> str:
        """Get the next node ID based on current node and branch"""
        connections = self.connections.get(current_node_id, [])
        logger.info(f"Available connections from {current_node_id}: {connections}")
        logger.info(f"Looking for branch: {branch}")
        
        # Find the appropriate connection based on branch
        next_connection = None
        for conn in connections:
            logger.info(f"Checking connection: {conn}")
            if branch == "default" or conn.get("connection_type") == branch:
                next_connection = conn
                logger.info(f"Found matching connection: {conn}")
                break
        
        if next_connection:
            return next_connection["to_node"]
        return None
            
    async def _execute_start_node(self, lead: LeadModel, node: dict):
        """Execute start node - just move to next node"""
        logger.info(f"Executing start node {node['id']} for lead {lead.lead_id}")
        await self._move_to_next_node(lead, node["id"])
        
    async def _execute_send_email_node(self, lead: LeadModel, node: dict):
        """Execute send email node"""
        try:
            logger.info(f"=== EXECUTING SEND EMAIL NODE ===")
            logger.info(f"Lead ID: {lead.lead_id}")
            logger.info(f"Lead Email: {lead.email}")
            logger.info(f"Node ID: {node['id']}")
            
            # Get email configuration from frontend
            config = node.get("configuration", {})
            logger.info(f"Email node configuration: {config}")
            logger.info(f"Available config keys: {list(config.keys())}")
            
            # Read subject and body from configuration (no hardcoded fallbacks)
            subject = config.get("subject", "")
            body = config.get("body", "")
            
            logger.info(f"Extracted subject: '{subject}'")
            logger.info(f"Extracted body length: {len(body)} characters")
            
            # Validate that we have content
            if not subject or not body:
                logger.error(f"Missing email content for lead {lead.lead_id}")
                logger.error(f"Subject: '{subject}', Body: '{body}'")
                raise ValueError("Email node missing subject or body content")
            
            # Send email with tracking
            logger.info("Calling send_email_with_tracking...")
            send_email_with_tracking(
                subject=subject,
                body=body,
                recipient_email=lead.email,
                lead_id=lead.lead_id,
                campaign_id=lead.campaign_id
            )
            
            # Update lead stats
            lead.email_sent_count += 1
            lead.last_email_sent_at = datetime.now()
            await lead.save()
            
            logger.info(f"Lead stats updated - emails sent: {lead.email_sent_count}")
            logger.info(f"Email sent successfully to {lead.email} for lead {lead.lead_id}")
            
            # Move to next node
            logger.info("Moving to next node...")
            await self._move_to_next_node(lead, node["id"])
            
        except Exception as e:
            logger.error(f"Failed to send email for lead {lead.lead_id}: {e}")
            raise
            
    async def _execute_condition_node(self, lead: LeadModel, node: dict):
        """Execute condition node - check if condition is met"""
        config = node.get("configuration", {})
        logger.info(f"Condition node configuration: {config}")
        logger.info(f"Available config keys: {list(config.keys())}")
        
        # Read condition type from frontend configuration
        condition_type = config.get("conditionType", "open")
        logger.info(f"Condition type: {condition_type}")
        
        # Check if condition is already met
        if lead.conditions_met.get(node["id"], False) or lead.conditions_met.get("email_open", False):
            logger.info(f"Condition {node['id']} already met for lead {lead.lead_id}")
            await self._move_to_next_node(lead, node["id"], branch="yes")
        else:
            # Check if this condition node has proper yes/no branches
            connections = self.connections.get(node["id"], [])
            has_yes_branch = any(conn.get("connection_type") == "yes" for conn in connections)
            has_no_branch = any(conn.get("connection_type") == "no" for conn in connections)
            
            logger.info(f"Condition node branches - Yes: {has_yes_branch}, No: {has_no_branch}")
            
            if has_yes_branch and has_no_branch:
                # This is a proper conditional flow - pause and wait for email open
                logger.info(f"Condition {node['id']} not met for lead {lead.lead_id}, pausing lead")
                
                # Find the next node for when condition is met (yes branch)
                next_node_id = self._get_next_node_id(node["id"], "yes")
                
                # Also find the "no" branch for timeout
                no_branch_node_id = self._get_next_node_id(node["id"], "no")
                
                # Calculate timeout based on the "no" branch path
                timeout_minutes = self._calculate_timeout_from_no_branch(no_branch_node_id)
                wait_until = datetime.now() + timedelta(minutes=timeout_minutes)
                
                # Get the next action from the no branch path
                next_action_node = self._get_next_action_from_no_branch(no_branch_node_id)
                
                # Pause the lead and wait for email open with timeout
                lead.status = "paused"
                lead.next_node = next_node_id  # Resume here if email opened
                lead.wait_until = wait_until   # Timeout for background task
                lead.updated_at = datetime.now()
                await lead.save()
                
                logger.info(f"Lead {lead.lead_id} paused waiting for email open condition")
                logger.info(f"Lead will resume at node: {next_node_id} when condition is met")
                logger.info(f"Lead will timeout at: {wait_until} (after {timeout_minutes} minutes)")
                logger.info(f"No branch node: {no_branch_node_id}")
                logger.info(f"Next action after timeout: {next_action_node}")
                
                # Store the no branch node and next action for timeout handling
                lead.conditions_met[f"{node['id']}_no_branch"] = no_branch_node_id
                lead.conditions_met[f"{node['id']}_next_action"] = next_action_node
                await lead.save()
            else:
                # This is a linear flow with a condition node that doesn't have proper branches
                # Just continue to the next node (treat as linear)
                logger.info(f"Condition node {node['id']} has no proper branches, treating as linear flow")
                await self._move_to_next_node(lead, node["id"], branch="default")
    
    def _calculate_timeout_from_no_branch(self, no_branch_node_id: str) -> int:
        """Calculate timeout by following the no branch path and finding wait nodes"""
        if not no_branch_node_id:
            return 1  # Default 1 minute if no branch found
        
        try:
            # Follow the no branch path to find wait nodes
            current_node_id = no_branch_node_id
            total_timeout_minutes = 0
            visited_nodes = set()
            
            # Follow the path up to 10 nodes to avoid infinite loops
            for _ in range(10):
                if current_node_id in visited_nodes:
                    break
                visited_nodes.add(current_node_id)
                
                current_node = self.nodes.get(current_node_id)
                if not current_node:
                    break
                
                node_type = current_node.get("type", "")
                logger.info(f"Following no branch path: {current_node_id} (type: {node_type})")
                
                if node_type == "wait":
                    # Found a wait node - get its duration
                    config = current_node.get("configuration", {})
                    wait_duration = config.get("waitDuration", config.get("duration", 1))
                    wait_unit = config.get("waitUnit", config.get("unit", "days"))
                    
                    # Convert to minutes
                    if wait_unit == "days":
                        total_timeout_minutes += wait_duration * 24 * 60
                    elif wait_unit == "hours":
                        total_timeout_minutes += wait_duration * 60
                    elif wait_unit == "minutes":
                        total_timeout_minutes += wait_duration
                    elif wait_unit == "seconds":
                        total_timeout_minutes += wait_duration / 60
                    else:
                        total_timeout_minutes += wait_duration * 24 * 60  # Default to days
                    
                    logger.info(f"Found wait node: {wait_duration} {wait_unit} = {total_timeout_minutes} minutes")
                    break  # Stop after first wait node
                
                elif node_type == "sendEmail":
                    # Found send email node - this is the action after timeout
                    logger.info(f"Found send email node after timeout: {current_node_id}")
                    break
                
                elif node_type == "end":
                    # Reached end node
                    logger.info(f"Reached end node in no branch: {current_node_id}")
                    break
                
                # Move to next node in the path
                connections = self.connections.get(current_node_id, [])
                if connections:
                    current_node_id = connections[0]["to_node"]  # Take first connection
                else:
                    break
            
            # Return calculated timeout, minimum 1 minute
            timeout = max(1, total_timeout_minutes)
            logger.info(f"Calculated timeout from no branch: {timeout} minutes")
            return timeout
            
        except Exception as e:
            logger.error(f"Error calculating timeout from no branch: {e}")
            return 1  # Default 1 minute on error
    
    def _get_next_action_from_no_branch(self, no_branch_node_id: str) -> str:
        """Get the next action node from the no branch path"""
        if not no_branch_node_id:
            return None
        
        try:
            # Follow the no branch path to find the next action
            current_node_id = no_branch_node_id
            visited_nodes = set()
            
            # Follow the path up to 10 nodes to avoid infinite loops
            for _ in range(10):
                if current_node_id in visited_nodes:
                    break
                visited_nodes.add(current_node_id)
                
                current_node = self.nodes.get(current_node_id)
                if not current_node:
                    break
                
                node_type = current_node.get("type", "")
                logger.info(f"Following no branch path for next action: {current_node_id} (type: {node_type})")
                
                if node_type in ["sendEmail", "wait", "condition", "end"]:
                    # Found an action node - return it
                    logger.info(f"Found next action node: {current_node_id} (type: {node_type})")
                    return current_node_id
                
                # Move to next node in the path
                connections = self.connections.get(current_node_id, [])
                if connections:
                    current_node_id = connections[0]["to_node"]  # Take first connection
                else:
                    break
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting next action from no branch: {e}")
            return None
            
    async def _execute_wait_node(self, lead: LeadModel, node: dict):
        """Execute wait node - schedule next execution"""
        try:
            logger.info(f"=== EXECUTING WAIT NODE ===")
            logger.info(f"Lead ID: {lead.lead_id}")
            logger.info(f"Node ID: {node['id']}")
            
            # Get wait configuration from node
            config = node.get("configuration", {})
            logger.info(f"Wait node configuration: {config}")
            logger.info(f"Available config keys: {list(config.keys())}")
            
            # Read wait duration and unit from configuration
            # Frontend sends waitDuration and waitUnit, backend expects duration and unit
            wait_duration = config.get("waitDuration", config.get("duration", 1))
            wait_unit = config.get("waitUnit", config.get("unit", "days"))
            
            logger.info(f"Extracted wait_duration: {wait_duration}")
            logger.info(f"Extracted wait_unit: {wait_unit}")
            
            logger.info(f"Wait duration: {wait_duration} {wait_unit}")
            
            # Calculate wait time based on unit
            if wait_unit == "days":
                wait_until = datetime.now() + timedelta(days=wait_duration)
            elif wait_unit == "hours":
                wait_until = datetime.now() + timedelta(hours=wait_duration)
            elif wait_unit == "minutes":
                wait_until = datetime.now() + timedelta(minutes=wait_duration)
            elif wait_unit == "seconds":
                wait_until = datetime.now() + timedelta(seconds=wait_duration)
            else:
                # Default to days if unit is not recognized
                logger.warning(f"Unknown wait unit '{wait_unit}', defaulting to days")
                wait_until = datetime.now() + timedelta(days=wait_duration)
            
            logger.info(f"Calculated wait until: {wait_until}")
            
            # Find the next node after this wait node
            next_node_id = None
            connections = self.connections.get(node["id"], [])
            if connections:
                next_node_id = connections[0]["to_node"]  # Take first connection
            
            # Update lead with wait information
            lead.wait_until = wait_until
            lead.status = "paused"
            lead.next_node = next_node_id  # Set the next node to resume at
            lead.updated_at = datetime.now()
            await lead.save()
            
            logger.info(f"Lead {lead.lead_id} paused at wait node {node['id']}")
            logger.info(f"Lead will resume at node: {next_node_id}")
            logger.info(f"Lead will resume at time: {wait_until}")
            logger.info(f"Wait duration: {wait_duration} {wait_unit}")
            logger.info("=== WAIT NODE EXECUTION COMPLETED ===")
            
        except Exception as e:
            logger.error(f"Failed to execute wait node for lead {lead.lead_id}: {e}")
            raise
        
    async def _execute_end_node(self, lead: LeadModel, node: dict):
        """Execute end node - mark lead as completed"""
        lead.status = "completed"
        lead.completed_at = datetime.now()
        lead.updated_at = datetime.now()
        await lead.save()
        
        logger.info(f"Lead {lead.lead_id} completed campaign")
        
    async def _move_to_next_node(self, lead: LeadModel, current_node_id: str, branch: str = "default"):
        """Move lead to the next node in the flow"""
        # Get next node ID using helper function
        next_node_id = self._get_next_node_id(current_node_id, branch)
        
        if not next_node_id:
            # No next node - mark as completed
            lead.status = "completed"
            lead.completed_at = datetime.now()
            lead.updated_at = datetime.now()
            await lead.save()
            logger.info(f"Lead {lead.lead_id} reached end of flow (no next connection found)")
            return
            
        # Move to next node
        logger.info(f"Moving lead {lead.lead_id} from {current_node_id} to {next_node_id}")
        lead.current_node = next_node_id
        lead.next_node = None
        lead.updated_at = datetime.now()
        await lead.save()
        
        # Continue execution
        await self._execute_node(lead)
        
    async def resume_lead(self, lead_id: str, condition_met: bool = False, condition_node_id: str = None):
        """Resume execution for a paused lead"""
        try:
            logger.info(f"=== RESUMING LEAD ===")
            logger.info(f"Lead ID: {lead_id}")
            logger.info(f"Condition met: {condition_met}")
            logger.info(f"Condition node ID: {condition_node_id}")
            
            lead = await LeadModel.find_one({"lead_id": lead_id})
            if not lead:
                raise ValueError(f"Lead {lead_id} not found")
                
            if lead.status != "paused":
                logger.warning(f"Lead {lead_id} is not paused (status: {lead.status})")
                return
                
            # Clear wait state if this was a wait node
            if lead.wait_until:
                logger.info(f"Clearing wait state for lead {lead_id}")
                lead.wait_until = None
                
            # Update condition if provided
            if condition_met:
                logger.info(f"Email open condition met for lead {lead_id}")
                # Mark all conditions as met since we're resuming from email open
                # This will allow the condition node to take the "yes" branch
                lead.conditions_met = {**lead.conditions_met, "email_open": True}
                
            # Resume execution
            lead.status = "running"
            lead.updated_at = datetime.now()
            await lead.save()
            
            logger.info(f"Lead {lead_id} status updated to running")
            
            # If we have a next_node set (from wait/condition), move to it first
            if lead.next_node:
                logger.info(f"Moving lead {lead_id} to next node: {lead.next_node}")
                lead.current_node = lead.next_node
                lead.next_node = None
                await lead.save()
            
            logger.info(f"Executing current node for lead {lead_id}: {lead.current_node}")
            
            # Continue execution from current node
            await self._execute_node(lead)
            
        except Exception as e:
            logger.error(f"Error resuming lead {lead_id}: {e}")
            raise
        
    async def get_campaign_stats(self) -> Dict[str, Any]:
        """Get campaign execution statistics"""
        total_leads = await LeadModel.count({"campaign_id": self.campaign_id})
        running_leads = await LeadModel.count({"campaign_id": self.campaign_id, "status": "running"})
        paused_leads = await LeadModel.count({"campaign_id": self.campaign_id, "status": "paused"})
        completed_leads = await LeadModel.count({"campaign_id": self.campaign_id, "status": "completed"})
        failed_leads = await LeadModel.count({"campaign_id": self.campaign_id, "status": "failed"})
        
        return {
            "campaign_id": self.campaign_id,
            "total_leads": total_leads,
            "running_leads": running_leads,
            "paused_leads": paused_leads,
            "completed_leads": completed_leads,
            "failed_leads": failed_leads,
            "completion_rate": (completed_leads / total_leads * 100) if total_leads > 0 else 0
        } 