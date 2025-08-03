from beanie import Document
from pydantic import Field
from datetime import datetime, timezone
from typing import List, Optional


class LeadModel(Document):
    lead_id: str = Field(..., index=True)
    campaign_id: str = Field(..., index=True)
    name: str = Field(..., example="John Doe")
    email: str = Field(..., example="john@example.com")
    status: str = Field(default="pending", example="pending")
    current_node: str = Field(..., example="start-1")
    execution_path: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    email_sent_count: int = Field(default=0)
    last_email_sent_at: Optional[datetime] = None
    wait_until: Optional[datetime] = None
    scheduled_task_id: Optional[str] = None
    next_node: Optional[str] = None

    class Settings:
        name = "leads" 