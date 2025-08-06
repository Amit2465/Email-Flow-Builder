from beanie import Document
from pydantic import Field
from datetime import datetime, timezone
from typing import Optional, List
from typing import Literal

class LeadEvent(Document):
    event_id: str = Field(..., index=True)
    lead_id: str = Field(..., index=True)
    campaign_id: str = Field(..., index=True)
    event_type: Literal["email_open", "link_click"] = Field(..., example="email_open")
    condition_node_id: str = Field(..., example="condition-1")
    target_url: Optional[str] = Field(default=None, example="https://example.com/signup")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed: bool = Field(default=False)
    processed_at: Optional[datetime] = None
    # ✅ NEW: Enhanced event context for proper mapping
    email_node_id: Optional[str] = Field(default=None, example="email-1")  # Which email this event belongs to
    email_subject: Optional[str] = Field(default=None, example="Welcome Email")  # For debugging and tracking
    condition_chain: List[str] = Field(default_factory=list)  # Chain of conditions for chained flows
    email_links: List[dict] = Field(default_factory=list)  # Available links in email
    event_context: dict = Field(default_factory=dict)  # Additional context for complex flows

    class Settings:
        name = "lead_events" 