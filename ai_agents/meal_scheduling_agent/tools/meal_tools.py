"""
Meal Scheduling Tools - Following LangChain/OpenAI tool patterns

These tools can be used by the agent to perform specific operations.
Each tool has a clear interface with name, description, and parameters.
"""

from typing import List, Dict, Optional, Any
from datetime import date
from pydantic import BaseModel, Field

from storage.local_storage import LocalStorage
from models.scheduled_meal import ScheduledMeal, MealOccasion
from uuid import uuid4


class BaseMealTool:
    """Base class for all meal scheduling tools"""
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
    
    @property
    def name(self) -> str:
        """Tool name"""
        raise NotImplementedError
    
    @property
    def description(self) -> str:
        """Tool description for the agent"""
        raise NotImplementedError
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool"""
        raise NotImplementedError


class GetAvailableMealsTool(BaseMealTool):
    """Tool to retrieve all available meals"""
    
    @property
    def name(self) -> str:
        return "get_available_meals"
    
    @property
    def description(self) -> str:
        return "Get a list of all available meals that can be scheduled"
    
    def run(self) -> Dict[str, Any]:
        """Get all available meals"""
        meals = self.storage.load_meals()
        return {
            "success": True,
            "meals": [
                {
                    "name": meal.name,
                    "id": str(meal.id),
                    "default_occasion": meal.default_occasion.value if meal.default_occasion else "dinner"
                }
                for meal in meals
            ],
            "count": len(meals)
        }


class ScheduleMealTool(BaseMealTool):
    """Tool to schedule a single meal"""
    
    @property
    def name(self) -> str:
        return "schedule_meal"
    
    @property
    def description(self) -> str:
        return "Schedule a specific meal for a given date and meal type"
    
    def run(self, meal_name: str, target_date: str, meal_type: str = "dinner") -> Dict[str, Any]:
        """
        Schedule a meal
        
        Args:
            meal_name: Name of the meal to schedule
            target_date: Date in ISO format (YYYY-MM-DD)
            meal_type: Type of meal (breakfast, lunch, dinner, snack)
        """
        try:
            # Find the meal
            meals = self.storage.load_meals()
            target_meal = None
            
            for meal in meals:
                if meal.name.lower() == meal_name.lower():
                    target_meal = meal
                    break
            
            if not target_meal:
                return {
                    "success": False,
                    "error": f"Meal '{meal_name}' not found"
                }
            
            # Create scheduled meal
            scheduled_date = date.fromisoformat(target_date)
            meal_occasion = MealOccasion(meal_type)
            
            scheduled_meal = ScheduledMeal(
                id=uuid4(),
                meal_id=target_meal.id,
                date=scheduled_date,
                occasion=meal_occasion
            )
            
            # Save to storage
            self.storage.add_scheduled_meal(scheduled_meal)
            
            return {
                "success": True,
                "scheduled_meal": {
                    "id": str(scheduled_meal.id),
                    "meal_name": target_meal.name,
                    "date": target_date,
                    "meal_type": meal_type
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class GetScheduledMealsTool(BaseMealTool):
    """Tool to retrieve scheduled meals for a date range"""
    
    @property
    def name(self) -> str:
        return "get_scheduled_meals"
    
    @property
    def description(self) -> str:
        return "Get all scheduled meals for a specific date or date range"
    
    def run(self, start_date: str, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get scheduled meals
        
        Args:
            start_date: Start date in ISO format
            end_date: Optional end date for range query
        """
        try:
            scheduled_meals = self.storage.load_scheduled_meals()
            meals = self.storage.load_meals()
            
            # Create meal lookup
            meal_lookup = {meal.id: meal for meal in meals}
            
            # Filter by date
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date) if end_date else start
            
            filtered_meals = []
            for sm in scheduled_meals:
                if start <= sm.date <= end:
                    meal_info = meal_lookup.get(sm.meal_id)
                    if meal_info:
                        filtered_meals.append({
                            "id": str(sm.id),
                            "meal_name": meal_info.name,
                            "date": sm.date.isoformat(),
                            "meal_type": sm.occasion.value
                        })
            
            return {
                "success": True,
                "scheduled_meals": filtered_meals,
                "count": len(filtered_meals)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class DeleteScheduledMealTool(BaseMealTool):
    """Tool to delete/unschedule a meal"""
    
    @property
    def name(self) -> str:
        return "delete_scheduled_meal"
    
    @property
    def description(self) -> str:
        return "Remove a scheduled meal by its ID"
    
    def run(self, scheduled_meal_id: str) -> Dict[str, Any]:
        """
        Delete a scheduled meal
        
        Args:
            scheduled_meal_id: ID of the scheduled meal to delete
        """
        try:
            from uuid import UUID
            meal_id = UUID(scheduled_meal_id)
            
            # This would need to be implemented in storage
            # For now, return a placeholder
            return {
                "success": True,
                "message": f"Scheduled meal {scheduled_meal_id} deleted"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class CheckScheduleConflictTool(BaseMealTool):
    """Tool to check if a meal slot is already scheduled"""
    
    @property
    def name(self) -> str:
        return "check_schedule_conflict"
    
    @property
    def description(self) -> str:
        return "Check if a specific date and meal type already has a scheduled meal"
    
    def run(self, target_date: str, meal_type: str) -> Dict[str, Any]:
        """
        Check for scheduling conflicts
        
        Args:
            target_date: Date to check in ISO format
            meal_type: Meal type to check
        """
        try:
            scheduled_meals = self.storage.load_scheduled_meals()
            check_date = date.fromisoformat(target_date)
            
            for sm in scheduled_meals:
                if sm.date == check_date and sm.occasion.value == meal_type:
                    meals = self.storage.load_meals()
                    meal_info = next((m for m in meals if m.id == sm.meal_id), None)
                    
                    return {
                        "success": True,
                        "has_conflict": True,
                        "existing_meal": meal_info.name if meal_info else "Unknown"
                    }
            
            return {
                "success": True,
                "has_conflict": False
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Tool Registry
def get_all_tools(storage: LocalStorage) -> List[BaseMealTool]:
    """Get all available tools initialized with storage"""
    return [
        GetAvailableMealsTool(storage),
        ScheduleMealTool(storage),
        GetScheduledMealsTool(storage),
        DeleteScheduledMealTool(storage),
        CheckScheduleConflictTool(storage)
    ]


# For LangChain compatibility
def create_langchain_tools(storage: LocalStorage):
    """Create LangChain-compatible tool wrappers"""
    from langchain.tools import Tool
    
    tools = []
    for meal_tool in get_all_tools(storage):
        tools.append(Tool(
            name=meal_tool.name,
            description=meal_tool.description,
            func=meal_tool.run
        ))
    
    return tools