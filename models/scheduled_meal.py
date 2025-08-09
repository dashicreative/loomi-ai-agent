from datetime import date as DateType, datetime
from uuid import UUID
from pydantic import BaseModel, Field
from .base import BaseEntity
from .meal import MealOccasion

class ScheduledMeal(BaseEntity):
    """Scheduled meal model that exactly matches iOS app structure"""
    meal_id: UUID = Field(..., description="ID of the meal being scheduled", alias="mealId")
    date: DateType = Field(..., description="Date when meal is scheduled")
    occasion: MealOccasion = Field(..., description="Meal occasion (breakfast, lunch, dinner, snack)")
    created_at: datetime = Field(default_factory=datetime.now, description="When this meal was scheduled (for preference tracking)", alias="createdAt")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "mealId": "550e8400-e29b-41d4-a716-446655440000",
                "date": "2025-08-10",
                "occasion": "dinner"
            }
        }
    }

class ScheduledMealCreate(BaseModel):
    """Model for creating a new scheduled meal (without ID)"""
    meal_id: UUID = Field(..., alias="mealId")
    date: DateType
    occasion: MealOccasion
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }

class ScheduledMealUpdate(BaseModel):
    """Model for updating an existing scheduled meal"""
    meal_id: UUID = Field(None, alias="mealId")
    date: DateType = None
    occasion: MealOccasion = None
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }

class ScheduledMealWithMeal(ScheduledMeal):
    """Scheduled meal with embedded meal details for UI display"""
    meal_name: str = Field(..., description="Name of the scheduled meal")
    meal_prep_time: int = Field(None, description="Preparation time of the meal", alias="mealPrepTime")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }