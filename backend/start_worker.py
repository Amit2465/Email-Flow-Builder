#!/usr/bin/env python3
"""
Simple script to start the Celery worker with proper error handling.
This can be used to manually start the worker if it's not running.
"""

import os
import sys
import subprocess
import time
import logging

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.celery_config import celery_app
from app.db.init import init_db
import asyncio

logger = logging.getLogger(__name__)

def check_celery_worker():
    """Check if Celery worker is running"""
    try:
        # Try to inspect active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            logger.info("Celery worker is running")
            return True
        else:
            logger.warning("No active Celery workers found")
            return False
    except Exception as e:
        logger.error(f"Failed to check Celery worker status: {e}")
        return False

def start_celery_worker():
    """Start the Celery worker"""
    try:
        logger.info("Starting Celery worker...")
        
        # Initialize database connection
        asyncio.run(init_db())
        logger.info("Database connection initialized")
        
        # Start the worker
        cmd = [
            "celery", 
            "-A", "app.celery_worker.celery", 
            "worker", 
            "--loglevel=info",
            "--concurrency=1"
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
        
        logger.info(f"Celery worker started with PID: {process.pid}")
        return process
        
    except Exception as e:
        logger.error(f"Failed to start Celery worker: {e}")
        return None

def main():
    """Main function to check and start worker if needed"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=== CELERY WORKER CHECK ===")
    
    # Check if worker is already running
    if check_celery_worker():
        logger.info("Worker is already running, no action needed")
        return
    
    # Start the worker
    process = start_celery_worker()
    if process:
        logger.info("Worker started successfully")
        logger.info("Press Ctrl+C to stop the worker")
        
        try:
            # Keep the script running
            while True:
                time.sleep(1)
                if process.poll() is not None:
                    logger.error("Worker process died unexpectedly")
                    break
        except KeyboardInterrupt:
            logger.info("Stopping worker...")
            process.terminate()
            process.wait()
            logger.info("Worker stopped")
    else:
        logger.error("Failed to start worker")
        sys.exit(1)

if __name__ == "__main__":
    main() 