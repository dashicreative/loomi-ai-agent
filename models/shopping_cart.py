from datetime import datetime
from typing import List
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer
from .base import BaseEntity
import time

class CartItem(BaseEntity):
    """Individual cart item model"""
    name: str = Field(..., description="Name of the cart item", alias="ingredient")
    meal_id: UUID = Field(..., description="ID of the meal this ingredient is from", alias="mealId")
    meal_name: str = Field(..., description="Name of the meal this ingredient is from", alias="mealName")
    quantity: int = Field(default=1, description="Quantity of the item")
    is_completed: bool = Field(False, description="Whether item has been shopped", alias="isCompleted")
    date_added: datetime = Field(default_factory=datetime.now, description="When item was added to cart", alias="dateAdded")
    
    @field_serializer('date_added')
    def serialize_date_added(self, date_added: datetime) -> float:
        """Serialize datetime to Unix timestamp for iOS compatibility"""
        return date_added.timestamp()
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "ingredient": "Milk",
                "mealId": "550e8400-e29b-41d4-a716-446655440000",
                "mealName": "Chicken Parmesan",
                "quantity": 1,
                "isCompleted": False,
                "dateAdded": 1691240200.0
            }
        }
    }

class CartMeal(BaseEntity):
    """Meal in shopping cart model"""
    meal_id: UUID = Field(..., description="ID of the meal", alias="mealId")
    meal_name: str = Field(..., description="Name of the meal", alias="mealName")
    servings: int = Field(default=1, description="Number of servings needed")
    date_added: datetime = Field(default_factory=datetime.now, description="When meal was added to cart", alias="dateAdded")
    
    @field_serializer('date_added')
    def serialize_date_added(self, date_added: datetime) -> float:
        """Serialize datetime to Unix timestamp for iOS compatibility"""
        return date_added.timestamp()
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440003",
                "mealId": "550e8400-e29b-41d4-a716-446655440000",
                "mealName": "Chicken Parmesan",
                "servings": 4,
                "dateAdded": 1691240200.0
            }
        }
    }

class ShoppingCart(BaseModel):
    """Shopping cart model that exactly matches iOS app structure"""
    meals: List[CartMeal] = Field(default_factory=list, description="Meals in the cart")
    items: List[CartItem] = Field(default_factory=list, description="Individual items in the cart")
    
    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "meals": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440003",
                        "mealId": "550e8400-e29b-41d4-a716-446655440000",
                        "mealName": "Chicken Parmesan",
                        "servings": 4,
                        "dateAdded": 1691240200.0
                    }
                ],
                "items": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440002",
                        "ingredient": "Milk",
                        "quantity": 1,
                        "isCompleted": False,
                        "dateAdded": 1691240200.0
                    }
                ]
            }
        }
    }

class CartMealCreate(BaseModel):
    """Model for adding a meal to cart"""
    meal_id: UUID = Field(..., alias="mealId")
    meal_name: str = Field(..., alias="mealName")
    servings: int = Field(default=1)
    
    model_config = {
        "populate_by_name": True
    }

class CartItemCreate(BaseModel):
    """Model for adding an item to cart"""
    name: str = Field(..., alias="ingredient")
    meal_id: UUID = Field(..., alias="mealId")
    meal_name: str = Field(..., alias="mealName")
    quantity: int = Field(default=1)
    
    model_config = {
        "populate_by_name": True
    }