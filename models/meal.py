from enum import Enum
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from .base import BaseEntity

class MealOccasion(str, Enum):
    """Meal occasion types that match iOS app exactly"""
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"

class Meal(BaseEntity):
    """Meal model that exactly matches iOS app structure"""
    name: str = Field(..., description="Name of the meal")
    ingredients: List[str] = Field(default_factory=list, description="List of ingredients")
    instructions: List[str] = Field(default_factory=list, description="Cooking instructions")
    prep_time: Optional[int] = Field(None, description="Preparation time in minutes", alias="prepTime")
    servings: Optional[int] = Field(None, description="Number of servings")
    occasion: MealOccasion = Field(..., description="Meal occasion (breakfast, lunch, dinner, snack)")
    is_favorite: bool = Field(False, description="Whether meal is marked as favorite", alias="isFavorite")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
        "alias_generator": None,  # Keep explicit aliases
        "by_alias": True,  # Use aliases in serialization
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Chicken Parmesan",
                "ingredients": ["chicken breast", "parmesan cheese", "breadcrumbs"],
                "instructions": ["Pound chicken thin", "Bread and season", "Cook until golden"],
                "prepTime": 30,
                "servings": 4,
                "occasion": "dinner",
                "isFavorite": True
            }
        }
    }

class MealCreate(BaseModel):
    """Model for creating a new meal (without ID)"""
    name: str
    ingredients: List[str] = Field(default_factory=list)
    instructions: List[str] = Field(default_factory=list)
    prep_time: Optional[int] = Field(None, alias="prepTime")
    servings: Optional[int] = None
    occasion: MealOccasion
    is_favorite: bool = Field(False, alias="isFavorite")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }

class MealUpdate(BaseModel):
    """Model for updating an existing meal"""
    name: Optional[str] = None
    ingredients: Optional[List[str]] = None
    instructions: Optional[List[str]] = None
    prep_time: Optional[int] = Field(None, alias="prepTime")
    servings: Optional[int] = None
    occasion: Optional[MealOccasion] = None
    is_favorite: Optional[bool] = Field(None, alias="isFavorite")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }