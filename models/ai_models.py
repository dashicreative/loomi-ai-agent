from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from uuid import UUID

class ActionType(str, Enum):
    """AI action types"""
    SCHEDULE_MEAL = "schedule_meal"
    DELETE_SCHEDULED_MEAL = "delete_scheduled_meal"
    CLEAR_SCHEDULE = "clear_schedule"
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    DELETE_MEAL = "delete_meal"
    FIND_RECIPE = "find_recipe"
    SAVE_RECIPE = "save_recipe"
    GENERATE_SHOPPING_LIST = "generate_shopping_list"

class AIAction(BaseModel):
    """Individual AI action"""
    type: ActionType = Field(..., description="Type of action to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    
    model_config = {
        "use_enum_values": True,
        "json_schema_extra": {
            "example": {
                "type": "schedule_meal",
                "parameters": {
                    "meal_name": "Chicken Parmesan",
                    "date": "2025-08-10",
                    "meal_type": "dinner"
                }
            }
        }
    }

class AIResponse(BaseModel):
    """AI agent response format"""
    conversational_response: str = Field(..., description="Human-readable response", alias="conversationalResponse")
    actions: List[AIAction] = Field(default_factory=list, description="Actions to execute")
    model_used: str = Field(..., description="AI model that generated response", alias="modelUsed")
    preview_message: Optional[str] = Field(None, description="Preview of actions", alias="previewMessage")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata for internal processing")
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "conversationalResponse": "I'll add chicken parmesan to Tuesday dinner!",
                "actions": [
                    {
                        "type": "schedule_meal",
                        "parameters": {
                            "meal_name": "chicken parmesan",
                            "date": "2025-08-10",
                            "meal_type": "dinner"
                        }
                    }
                ],
                "modelUsed": "claude",
                "previewMessage": "Adding 1 meal to your dinner schedule"
            }
        }
    }

class ChatResponse(BaseModel):
    """Response from the AI chat endpoint - iOS compatible"""
    conversational_response: str = Field(..., description="Natural language response to user", alias="response")
    actions: List[AIAction] = Field(default_factory=list, description="Actions to perform")
    model_used: str = Field(..., description="Which AI model was used", alias="modelUsed")
    preview_message: Optional[str] = Field(None, description="Preview of what actions will do", alias="previewMessage")
    debug_chat_log: Optional[str] = Field(None, description="Clean chat log for debugging", alias="debugChatLog")
    
    model_config = {
        "populate_by_name": True
    }


class ChatMessage(BaseModel):
    """Chat message from user"""
    content: str = Field(..., description="Message content")
    user_context: Dict[str, Any] = Field(default_factory=dict, description="User context and preferences", alias="userContext")
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "content": "Add chicken parmesan to Tuesday dinner",
                "userContext": {
                    "saved_meals": ["chicken parmesan", "pasta", "salad"],
                    "dietary_preferences": ["healthy"],
                    "scheduled_meals": []
                }
            }
        }
    }

class Recipe(BaseModel):
    """Recipe model for API responses"""
    id: Optional[int] = Field(None, description="Spoonacular recipe ID")
    title: str = Field(..., description="Recipe title")
    image: Optional[str] = Field(None, description="Recipe image URL")
    ready_in_minutes: Optional[int] = Field(None, description="Total preparation time", alias="readyInMinutes")
    servings: Optional[int] = Field(None, description="Number of servings")
    source_url: Optional[str] = Field(None, description="Original recipe URL", alias="sourceUrl")
    summary: Optional[str] = Field(None, description="Recipe summary")
    ingredients: List[str] = Field(default_factory=list, description="Recipe ingredients")
    instructions: List[str] = Field(default_factory=list, description="Cooking instructions")
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "id": 12345,
                "title": "Chicken Parmesan",
                "image": "https://example.com/image.jpg",
                "readyInMinutes": 45,
                "servings": 4,
                "sourceUrl": "https://example.com/recipe",
                "summary": "Delicious breaded chicken with parmesan cheese",
                "ingredients": ["chicken breast", "parmesan cheese", "breadcrumbs"],
                "instructions": ["Pound chicken thin", "Bread and season", "Cook until golden"]
            }
        }
    }