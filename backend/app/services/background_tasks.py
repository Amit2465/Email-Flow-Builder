import asyncio
import logging
from datetime import datetime
from typing import List, Dict
from app.models.lead import LeadModel
from app.services.flow_executor import FlowExecutor

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    """
    Manages automatic background tasks for campaign execution
    """
    
    def __init__(self):
        self.running = False
        self.task = None
        self.timeout_tasks: Dict[str, asyncio.Task] = {}  # lead_id -> timeout task
    
    async def start(self):
        """Start the background task manager"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._run_background_tasks())
            logger.info("=== BACKGROUND TASK MANAGER STARTED ===")
            logger.info(f"Background task manager running: {self.running}")
            logger.info(f"Background task created: {self.task is not None}")
        else:
            logger.warning("Background task manager is already running")
    
    async def stop(self):
        """Stop the background task manager"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        # Cancel all timeout tasks
        for task in self.timeout_tasks.values():
            task.cancel()
        self.timeout_tasks.clear()
        
        logger.info("=== BACKGROUND TASK MANAGER STOPPED ===")
    
    async def _run_background_tasks(self):
        """Main background task loop"""
        logger.info("=== BACKGROUND TASK LOOP STARTED ===")
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                logger.info(f"=== BACKGROUND TASK LOOP ITERATION {loop_count} ===")
                logger.info(f"Checking for waiting leads at {datetime.now()}")
                
                # Check for waiting leads and set up timeouts
                await self._check_and_setup_timeouts()
                
                logger.info(f"Background task loop iteration {loop_count} completed")
                logger.info(f"Waiting 30 seconds before next check...")
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in background task loop iteration {loop_count}: {e}")
                logger.info("Waiting 60 seconds before retry...")
                await asyncio.sleep(60)  # Wait longer on error
        
        logger.info("=== BACKGROUND TASK LOOP ENDED ===")
    
    async def _check_and_setup_timeouts(self):
        """Check for waiting leads and set up individual timeouts"""
        try:
            logger.info("=== CHECKING AND SETTING UP TIMEOUTS ===")
            current_time = datetime.now()
            logger.info(f"Current time: {current_time}")
            
            # Find all paused leads
            paused_leads = await LeadModel.find({
                "status": "paused"
            }).to_list()
            
            logger.info(f"Found {len(paused_leads)} paused leads")
            
            for lead in paused_leads:
                try:
                    # Check if this lead has a wait_until timestamp
                    if lead.wait_until:
                        # Calculate seconds until timeout
                        seconds_until_timeout = (lead.wait_until - current_time).total_seconds()
                        
                        if seconds_until_timeout <= 0:
                            # Timeout has passed - resume immediately
                            logger.info(f"Lead {lead.lead_id} timeout has passed, resuming immediately")
                            await self._resume_lead(lead.lead_id)
                        else:
                            # Set up timeout task if not already set
                            if lead.lead_id not in self.timeout_tasks:
                                logger.info(f"Setting up timeout for lead {lead.lead_id} in {seconds_until_timeout} seconds")
                                timeout_task = asyncio.create_task(
                                    self._timeout_lead(lead.lead_id, seconds_until_timeout)
                                )
                                self.timeout_tasks[lead.lead_id] = timeout_task
                            else:
                                logger.debug(f"Timeout task already exists for lead {lead.lead_id}")
                    else:
                        logger.info(f"Lead {lead.lead_id} has no wait_until timestamp")
                        
                except Exception as e:
                    logger.error(f"Error processing lead {lead.lead_id}: {e}")
                    
            logger.info("=== TIMEOUT SETUP COMPLETED ===")
                
        except Exception as e:
            logger.error(f"=== ERROR CHECKING TIMEOUTS ===")
            logger.error(f"Error: {e}")
    
    async def _timeout_lead(self, lead_id: str, seconds: float):
        """Timeout a specific lead after the given seconds"""
        try:
            logger.info(f"=== TIMEOUT TASK STARTED FOR LEAD {lead_id} ===")
            logger.info(f"Waiting {seconds} seconds before resuming lead {lead_id}")
            
            await asyncio.sleep(seconds)
            
            logger.info(f"=== TIMEOUT EXPIRED FOR LEAD {lead_id} ===")
            await self._resume_lead(lead_id)
            
            # Remove the task from tracking
            if lead_id in self.timeout_tasks:
                del self.timeout_tasks[lead_id]
                
        except asyncio.CancelledError:
            logger.info(f"Timeout task cancelled for lead {lead_id}")
        except Exception as e:
            logger.error(f"Error in timeout task for lead {lead_id}: {e}")
    
    async def _resume_lead(self, lead_id: str):
        """Resume a specific lead"""
        try:
            logger.info(f"=== RESUMING LEAD {lead_id} ===")
            
            lead = await LeadModel.find_one({"lead_id": lead_id})
            if not lead:
                logger.warning(f"Lead {lead_id} not found")
                return
                
            if lead.status != "paused":
                logger.warning(f"Lead {lead_id} is not paused (status: {lead.status})")
                return
                
            logger.info(f"Campaign ID: {lead.campaign_id}")
            logger.info(f"Current status: {lead.status}")
            logger.info(f"Wait until: {lead.wait_until}")
            logger.info(f"Next node: {lead.next_node}")
            
            # Check if this is a timeout scenario (email not opened)
            # Look for no_branch in conditions_met
            no_branch_node = None
            next_action_node = None
            for key, value in lead.conditions_met.items():
                if key.endswith("_no_branch") and value:
                    no_branch_node = value
                elif key.endswith("_next_action") and value:
                    next_action_node = value
            
            if no_branch_node and next_action_node:
                logger.info(f"Lead {lead_id} timed out - taking no branch to {next_action_node}")
                # This is a timeout - take the next action from no branch
                lead.next_node = next_action_node
                await lead.save()
            elif no_branch_node:
                logger.info(f"Lead {lead_id} timed out - taking no branch to {no_branch_node}")
                # Fallback to no branch node
                lead.next_node = no_branch_node
                await lead.save()
            
            # Resume execution
            executor = FlowExecutor(lead.campaign_id)
            await executor.load_campaign()
            await executor.resume_lead(lead_id)
            
            logger.info(f"=== SUCCESSFULLY RESUMED LEAD {lead_id} ===")
            
        except Exception as e:
            logger.error(f"=== FAILED TO RESUME LEAD {lead_id} ===")
            logger.error(f"Error: {e}")
            # Mark lead as failed if we can't resume it
            try:
                lead = await LeadModel.find_one({"lead_id": lead_id})
                if lead:
                    lead.status = "failed"
                    lead.error_message = f"Failed to resume: {str(e)}"
                    await lead.save()
                    logger.error(f"Lead {lead_id} marked as failed")
            except Exception as save_error:
                logger.error(f"Failed to mark lead {lead_id} as failed: {save_error}")
    
    async def _check_waiting_leads(self):
        """Legacy method - now uses timeout tasks instead"""
        logger.info("Legacy _check_waiting_leads called - using timeout tasks instead")
        await self._check_and_setup_timeouts()

# Global background task manager instance
background_manager = BackgroundTaskManager() 