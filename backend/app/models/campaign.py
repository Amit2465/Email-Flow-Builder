from beanie import Document
from pydantic import Field
from typing import List, Optional, Literal
from datetime import datetime, timezone


class CampaignModel(Document):
    campaign_id: str = Field(..., example="campaign_1754062199795")
    name: str = Field(..., example="Welcome Campaign")
    status: Literal["ready", "running", "paused", "completed"] = "ready"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    nodes: List[dict]  # Flexible dict structure for frontend data
    connections: List[dict]  # Flexible dict structure for frontend data
    workflow: dict  # Flexible dict structure for frontend data
    contact_file: Optional[dict] = None

    class Settings:
        name = "campaigns"

    class Config:
        json_schema_extra = {
            "example": {
                "campaign_id": "campaign_1754062199795",
                "name": "Welcome Campaign",
                "status": "ready",
                "created_at": "2025-08-01T19:30:00.000Z",
                "updated_at": "2025-08-01T19:30:00.000Z",
                "nodes": [],
                "connections": [],
                "workflow": {
                    "start_node": "start-1",
                    "total_nodes": 1,
                    "total_connections": 0
                },
                "contact_file": None
            }
        }
