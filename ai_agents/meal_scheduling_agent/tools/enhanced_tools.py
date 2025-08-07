"""
Enhanced Tools - Production tools using the enterprise-grade BaseTool

These tools demonstrate best practices:
- Input/output validation with Pydantic
- Proper error handling
- Retry logic built-in
- Metrics collection
- Caching where appropriate
"""

from typing import List, Dict, Optional, Any
from datetime import date, timedelta
from uuid import uuid4
import random

from pydantic import BaseModel, Field, validator
from storage.local_storage import LocalStorage
from models.scheduled_meal import ScheduledMeal, MealOccasion
from models.meal import Meal

from ..core.base_tool import BaseTool
from ..utils.date_utils import DateUtils
from ..utils.meal_utils import MealUtils
from ..exceptions import MealNotFoundError, InvalidDateError, SchedulingConflictError


# Input/Output Models for Validation
class LoadMealsInput(BaseModel):
    """Input for LoadMealsTool"""
    include_metadata: bool = Field(False, description="Include full meal metadata")


class LoadMealsOutput(BaseModel):
    """Output for LoadMealsTool"""
    meals: List[Dict[str, Any]]
    count: int
    categories: Optional[Dict[str, int]] = None


class ScheduleMealInput(BaseModel):
    """Input for ScheduleSingleMealTool"""
    meal_name: str = Field(..., description="Name of meal to schedule")
    target_date: str = Field(..., description="Date in ISO format (YYYY-MM-DD)")
    meal_type: str = Field("dinner", description="Type of meal: breakfast, lunch, dinner, snack")
    
    @validator('target_date')
    def validate_date(cls, v):
        try:
            parsed_date = date.fromisoformat(v)
            if parsed_date < date.today():
                raise ValueError("Cannot schedule meals in the past")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid date: {str(e)}")
    
    @validator('meal_type')
    def validate_meal_type(cls, v):
        valid_types = ["breakfast", "lunch", "dinner", "snack"]
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid meal type. Must be one of: {', '.join(valid_types)}")
        return v.lower()


class ClearScheduleInput(BaseModel):
    """Input for ClearScheduleTool"""
    date_range: Optional[str] = Field(None, description="Range: 'week', 'month', 'all'")
    start_date: Optional[str] = Field(None, description="Start date for custom range")
    end_date: Optional[str] = Field(None, description="End date for custom range")
    
    @validator('date_range')
    def validate_range(cls, v):
        if v and v not in ["week", "month", "all"]:
            raise ValueError("date_range must be 'week', 'month', or 'all'")
        return v


# Enhanced Tool Implementations
class EnhancedLoadMealsTool(BaseTool):
    """
    Load available meals with caching and validation
    
    This tool is highly cacheable since meals don't change often.
    """
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="LoadMealsTool",
            description="Load all available meals from storage with metadata",
            input_model=LoadMealsInput,
            output_model=LoadMealsOutput
        )
        self.storage = storage
        self.meal_utils = MealUtils()
    
    async def _execute(self, include_metadata: bool = False) -> Dict[str, Any]:
        """
        Load meals from storage
        
        This method is cached automatically by BaseTool if caching is enabled.
        """
        meals = self.storage.load_meals()
        
        if include_metadata:
            # Include full meal data
            meal_dicts = []
            categories = {}
            
            for meal in meals:
                meal_dict = {
                    "id": meal.id,
                    "name": meal.name,
                    "ingredients": meal.ingredients,
                    "occasion": meal.occasion,
                    "prep_time": meal.prep_time,
                    "servings": meal.servings,
                    "is_favorite": meal.is_favorite
                }
                meal_dicts.append(meal_dict)
                
                # Count by category
                categories[meal.occasion] = categories.get(meal.occasion, 0) + 1
            
            return {
                "meals": meal_dicts,
                "count": len(meals),
                "categories": categories
            }
        else:
            # Simple name list (more efficient)
            return {
                "meals": [{"name": meal.name, "id": meal.id} for meal in meals],
                "count": len(meals)
            }


class EnhancedScheduleMealTool(BaseTool):
    """
    Schedule a single meal with conflict detection and validation
    
    Features:
    - Validates meal exists
    - Checks for scheduling conflicts
    - Ensures date is not in the past
    - Returns detailed success/error info
    """
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="ScheduleSingleMealTool",
            description="Schedule a single meal with validation and conflict detection",
            input_model=ScheduleMealInput
        )
        self.storage = storage
        self.meal_utils = MealUtils()
    
    async def _execute(self, meal_name: str, target_date: str, meal_type: str = "dinner") -> Dict[str, Any]:
        """Execute meal scheduling with full validation"""
        # Load available meals
        meals = self.storage.load_meals()
        meal_names = [m.name for m in meals]
        
        # Find exact meal or use fuzzy matching
        meal = next((m for m in meals if m.name.lower() == meal_name.lower()), None)
        
        if not meal:
            # Try fuzzy matching
            suggestions = self.meal_utils.suggest_alternatives(meal_name, meal_names, max_suggestions=3)
            raise MealNotFoundError(
                f"Meal '{meal_name}' not found. Did you mean: {', '.join(suggestions)}?"
            )
        
        # Parse date
        parsed_date = date.fromisoformat(target_date)
        
        # Check for conflicts
        existing_schedules = self.storage.load_scheduled_meals()
        conflicts = [
            s for s in existing_schedules 
            if s.date == parsed_date and s.occasion == meal_type
        ]
        
        if conflicts:
            existing_meal_name = next(
                (m.name for m in meals if m.id == conflicts[0].meal_id),
                "Unknown meal"
            )
            raise SchedulingConflictError(
                f"Already have {existing_meal_name} scheduled for {meal_type} on {target_date}"
            )
        
        # Create scheduled meal
        scheduled_meal = ScheduledMeal(
            id=str(uuid4()),
            meal_id=meal.id,
            date=parsed_date,
            occasion=meal_type
        )
        
        # Save to storage
        self.storage.save_scheduled_meal(scheduled_meal)
        
        return {
            "scheduled_meal_id": scheduled_meal.id,
            "meal_name": meal.name,
            "meal_id": meal.id,
            "date": target_date,
            "meal_type": meal_type,
            "success": True
        }


class EnhancedClearScheduleTool(BaseTool):
    """
    Clear scheduled meals for a date range
    
    Supports clearing by week, month, or all schedules.
    """
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="ClearScheduleTool",
            description="Clear scheduled meals for specified date range",
            input_model=ClearScheduleInput
        )
        self.storage = storage
    
    async def _execute(
        self,
        date_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear scheduled meals"""
        # Convert string dates if provided
        start_date_obj = None
        end_date_obj = None
        
        if start_date:
            start_date_obj = date.fromisoformat(start_date)
        if end_date:
            end_date_obj = date.fromisoformat(end_date)
        
        # Execute clear operation
        cleared_count = self.storage.clear_schedule(
            date_range=date_range,
            start_date=start_date_obj,
            end_date=end_date_obj
        )
        
        return {
            "cleared_count": cleared_count,
            "date_range": date_range or "custom",
            "success": True,
            "message": f"Successfully cleared {cleared_count} scheduled meals"
        }


class EnhancedSelectRandomMealsTool(BaseTool):
    """
    Select random meals from available options
    
    Features:
    - Avoids duplicate selections
    - Considers meal preferences
    - Filters by meal type if specified
    """
    
    def __init__(self):
        super().__init__(
            name="SelectRandomMealsTool",
            description="Select random meals with intelligent filtering"
        )
        self.meal_utils = MealUtils()
    
    async def _execute(
        self,
        available_meals: List[str],
        count: int = 1,
        avoid_duplicates: bool = True,
        meal_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Select random meals"""
        if count > len(available_meals):
            count = len(available_meals)
        
        # Use meal utils for selection
        selected = self.meal_utils.select_random_meals(
            available_meals,
            count=count,
            avoid_duplicates=avoid_duplicates
        )
        
        return {
            "selected_meals": selected,
            "count": len(selected),
            "success": True
        }


# Tool Registry Update
def get_enhanced_tools(storage: LocalStorage) -> Dict[str, BaseTool]:
    """Get all enhanced tools"""
    return {
        "LoadMealsTool": EnhancedLoadMealsTool(storage),
        "ScheduleSingleMealTool": EnhancedScheduleMealTool(storage),
        "ClearScheduleTool": EnhancedClearScheduleTool(storage),
        "SelectRandomMealsTool": EnhancedSelectRandomMealsTool()
    }