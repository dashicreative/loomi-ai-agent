from pydantic import BaseModel, Field, model_validator
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, date

class BaseEntity(BaseModel):
    """Base entity class with common fields"""
    id: UUID = Field(default_factory=uuid4)
    
    model_config = {
        "validate_assignment": True,
        "use_enum_values": True,
        "extra": "forbid",
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }