import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.init import init_db
from app.api.campaign import router as campaign_router
from app.api.tracking import router as tracking_router
from app.services.background_tasks import background_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== APPLICATION STARTUP ===")
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")
    
    # Start background task manager
    logger.info("Starting background task manager...")
    await background_manager.start()
    logger.info("Background task manager started successfully")
    logger.info("=== APPLICATION STARTUP COMPLETE ===")
    
    yield
    
    # Stop background task manager
    logger.info("=== APPLICATION SHUTDOWN ===")
    logger.info("Stopping background task manager...")
    await background_manager.stop()
    logger.info("Background task manager stopped")
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

# Simple CORS for Docker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "EmailBuilder API - Automatic Campaign System"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "EmailBuilder API is running"}

@app.post("/debug/test-wait-resume")
async def test_wait_resume():
    """Manual test endpoint to trigger background task check"""
    try:
        logger.info("=== MANUAL BACKGROUND TASK TEST ===")
        await background_manager._check_waiting_leads()
        logger.info("=== MANUAL BACKGROUND TASK TEST COMPLETE ===")
        return {"message": "Background task check completed", "status": "success"}
    except Exception as e:
        logger.error(f"Manual background task test failed: {e}")
        return {"message": f"Background task check failed: {str(e)}", "status": "error"}

@app.get("/debug/background-tasks")
async def debug_background_tasks():
    """Debug endpoint to check background task status"""
    return {
        "background_manager_running": background_manager.running,
        "task_active": background_manager.task is not None,
        "message": "Check logs for background task activity"
    }

@app.post("/debug/create-test-wait-lead")
async def create_test_wait_lead():
    """Create a test lead with a wait node for testing"""
    try:
        logger.info("=== CREATING TEST WAIT LEAD ===")
        
        from app.models.lead import LeadModel
        from datetime import datetime, timedelta
        
        # Create a test lead that will wait for 10 seconds
        test_lead = LeadModel(
            lead_id=f"test_wait_lead_{int(datetime.now().timestamp())}",
            campaign_id="test_campaign",
            name="Test Lead",
            email="test@example.com",
            status="paused",
            current_node="wait-1",
            next_node="send-email-1",
            wait_until=datetime.now() + timedelta(seconds=10),  # Wait 10 seconds
            execution_path=["start-1", "wait-1"]
        )
        
        await test_lead.save()
        
        logger.info(f"Created test lead: {test_lead.lead_id}")
        logger.info(f"Wait until: {test_lead.wait_until}")
        logger.info(f"Next node: {test_lead.next_node}")
        
        return {
            "message": "Test wait lead created",
            "lead_id": test_lead.lead_id,
            "wait_until": test_lead.wait_until.isoformat(),
            "next_node": test_lead.next_node
        }
        
    except Exception as e:
        logger.error(f"Failed to create test wait lead: {e}")
        return {"message": f"Failed to create test lead: {str(e)}", "status": "error"}

@app.get("/debug/leads")
async def debug_leads():
    """Debug endpoint to check all leads in database"""
    try:
        from app.models.lead import LeadModel
        
        all_leads = await LeadModel.find_all().to_list()
        
        leads_info = []
        for lead in all_leads:
            leads_info.append({
                "lead_id": lead.lead_id,
                "campaign_id": lead.campaign_id,
                "status": lead.status,
                "current_node": lead.current_node,
                "next_node": lead.next_node,
                "wait_until": lead.wait_until.isoformat() if lead.wait_until else None,
                "conditions_met": lead.conditions_met,
                "created_at": lead.created_at.isoformat(),
                "updated_at": lead.updated_at.isoformat()
            })
        
        return {
            "total_leads": len(leads_info),
            "leads": leads_info
        }
        
    except Exception as e:
        logger.error(f"Failed to get leads: {e}")
        return {"message": f"Failed to get leads: {str(e)}", "status": "error"}

@app.get("/debug/campaign/{campaign_id}")
async def debug_campaign(campaign_id: str):
    """Debug endpoint to check a specific campaign"""
    try:
        from app.models.campaign import CampaignModel
        
        campaign = await CampaignModel.find_one({"campaign_id": campaign_id})
        if not campaign:
            return {"message": "Campaign not found", "status": "error"}
        
        return {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status,
            "nodes": campaign.nodes,
            "connections": campaign.connections,
            "workflow": campaign.workflow
        }
        
    except Exception as e:
        logger.error(f"Failed to get campaign: {e}")
        return {"message": f"Failed to get campaign: {str(e)}", "status": "error"}

# Only essential endpoints for automatic system

# Include routers
app.include_router(campaign_router, prefix="/api", tags=["campaigns"])
app.include_router(tracking_router, prefix="/api", tags=["tracking"])
