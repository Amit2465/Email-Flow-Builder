import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.db.init import init_db
from app.api.campaign import router as campaign_router
from app.api.tracking import router as tracking_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== APPLICATION STARTUP ===")
    logger.info("Starting EmailBuilder API with Celery integration")
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise
    logger.info("Celery worker should be running in a separate process.")
    logger.info("API endpoints available:")
    logger.info("  - /api/campaigns: Campaign management")
    logger.info("  - /api/track/open: Email open tracking")
    logger.info("  - /api/track/click: Link click tracking")
    logger.info("=== APPLICATION STARTUP COMPLETE ===")
    
    yield
    
    logger.info("=== APPLICATION SHUTDOWN ===")
    logger.info("Shutting down EmailBuilder API...")
    logger.info("=== APPLICATION SHUTDOWN COMPLETE ===")

app = FastAPI(lifespan=lifespan)

# Add CORS middleware
# For development, allowing all origins is convenient.
# For production, you would restrict this to your frontend's domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

@app.get("/")
async def root():
    return {"message": "EmailBuilder API - Celery Edition"}

@app.get("/test-cors")
async def test_cors():
    """Test endpoint for CORS verification"""
    return {"message": "CORS test successful", "status": "ok"}

@app.get("/health")
async def health_check():
    """Enhanced health check with system status"""
    try:
        # Check database connection
        from app.db.init import get_database
        db = get_database()
        await db.command("ping")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Celery connection
    try:
        from app.celery_config import celery_app
        from celery.task.control import inspect
        
        i = inspect()
        active_workers = i.active()
        celery_status = "healthy" if active_workers else "no_workers"
    except Exception as e:
        celery_status = f"unhealthy: {str(e)}"
    
    # Get system statistics
    try:
        from app.models.lead import LeadModel
        from app.models.lead_event import LeadEvent
        
        total_leads = await LeadModel.count_documents({})
        total_events = await LeadEvent.count_documents({})
        
        # Count active campaigns
        from app.models.campaign import CampaignModel
        active_campaigns = await CampaignModel.count_documents({"status": {"$in": ["running", "paused"]}})
        completed_campaigns = await CampaignModel.count_documents({"status": "completed"})
        
    except Exception as e:
        total_leads = 0
        total_events = 0
        active_campaigns = 0
        completed_campaigns = 0
    
    return {
        "status": "healthy" if db_status == "healthy" and celery_status == "healthy" else "degraded",
        "database": db_status,
        "celery": celery_status,
        "statistics": {
            "total_leads": total_leads,
            "total_events": total_events,
            "active_campaigns": active_campaigns,
            "completed_campaigns": completed_campaigns
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# Include API routers
app.include_router(campaign_router, prefix="/api", tags=["campaigns"])
app.include_router(tracking_router, prefix="/api", tags=["tracking"])
