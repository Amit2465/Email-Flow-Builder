from beanie import Document
from pydantic import Field
from typing import Optional, Dict, Literal
from datetime import datetime, timezone


class LeadModel(Document):
    lead_id: str = Field(..., example="lead_1754062199795")
    campaign_id: str = Field(..., example="campaign_1754062199795")
    name: str = Field(..., example="John Doe")
    email: str = Field(..., example="john@example.com")
    
    # Flow execution state
    status: Literal["pending", "running", "paused", "completed", "failed"] = "pending"
    current_node: str = Field(..., example="start-1")
    next_node: Optional[str] = None
    
    # Condition tracking
    conditions_met: Dict[str, bool] = Field(default_factory=dict)  # node_id -> bool
    wait_until: Optional[datetime] = None  # For wait nodes
    
    # Execution history
    execution_path: list = Field(default_factory=list)  # List of visited nodes
    email_sent_count: int = Field(default=0)
    last_email_sent_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error tracking
    error_message: Optional[str] = None
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)

    class Settings:
        name = "leads"
        indexes = [
            "campaign_id",
            "email",
            "status",
            "current_node",
            ("campaign_id", "status"),
            ("campaign_id", "current_node"),
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "lead_1754062199795",
                "campaign_id": "campaign_1754062199795",
                "name": "John Doe",
                "email": "john@example.com",
                "status": "running",
                "current_node": "send-email-1",
                "next_node": "condition-1",
                "conditions_met": {"condition-1": False},
                "wait_until": None,
                "execution_path": ["start-1", "send-email-1"],
                "email_sent_count": 1,
                "last_email_sent_at": "2025-08-01T19:30:00.000Z",
                "created_at": "2025-08-01T19:30:00.000Z",
                "updated_at": "2025-08-01T19:30:00.000Z",
                "started_at": "2025-08-01T19:30:00.000Z",
                "completed_at": None,
                "error_message": None,
                "retry_count": 0,
                "max_retries": 3
            }
        } 