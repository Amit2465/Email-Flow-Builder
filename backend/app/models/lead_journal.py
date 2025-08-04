from beanie import Document
from pydantic import Field
from datetime import datetime, timezone
from typing import Optional

class LeadJournal(Document):
    """
    Represents a single event or state transition in a lead's journey.
    Used for auditing and debugging campaign flows.
    """
    lead_id: str = Field(..., index=True)
    campaign_id: str = Field(..., index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    details: Optional[dict] = None

    class Settings:
        name = "lead_journal"
