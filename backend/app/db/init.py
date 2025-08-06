import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models.campaign import CampaignModel
from app.models.lead import LeadModel
from app.models.lead_journal import LeadJournal
from app.models.lead_event import LeadEvent

MONGO_URI = "mongodb://admin:password123@mongodb:27017/emailbuilder?authSource=admin"
DB_NAME = "emailbuilder"

logger = logging.getLogger(__name__)

async def init_db():
    try:
        logger.info("Initializing database connection...")
        client = AsyncIOMotorClient(MONGO_URI)
        
        # Test the connection
        await client.admin.command('ping')
        logger.info("MongoDB connection test successful.")
        
        await init_beanie(
            database=client[DB_NAME], 
            document_models=[CampaignModel, LeadModel, LeadJournal, LeadEvent]
        )
        logger.info("MongoDB connection established and Beanie initialized.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise
