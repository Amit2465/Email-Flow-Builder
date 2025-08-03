import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.init import init_db
from app.api.campaign import router as campaign_router
from app.api.tracking import router as tracking_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== APPLICATION STARTUP ===")
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")
    logger.info("Celery worker should be running in a separate process.")
    logger.info("=== APPLICATION STARTUP COMPLETE ===")
    
    yield
    
    logger.info("=== APPLICATION SHUTDOWN ===")
    logger.info("Shutting down...")

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

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Include API routers
app.include_router(campaign_router, prefix="/api", tags=["campaigns"])
app.include_router(tracking_router, prefix="/api", tags=["tracking"])
