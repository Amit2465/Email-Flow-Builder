import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models.campaign import CampaignModel
from app.models.lead import LeadModel
from app.models.lead_journal import LeadJournal

MONGO_URI = "mongodb://admin:password123@mongodb:27017/emailbuilder?authSource=admin"
DB_NAME = "emailbuilder"

logger = logging.getLogger(__name__)

async def init_db():
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        await init_beanie(
            database=client[DB_NAME], 
            document_models=[CampaignModel, LeadModel, LeadJournal]
        )
        logger.info("MongoDB connection established and Beanie initialized.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
