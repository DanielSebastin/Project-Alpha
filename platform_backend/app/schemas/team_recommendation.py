from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

class TeamRecommendationOut(BaseModel):
    id: UUID
    user_id: UUID
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
