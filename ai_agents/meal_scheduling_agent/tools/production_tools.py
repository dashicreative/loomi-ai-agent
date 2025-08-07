"""
Production Tools - All tools needed for the meal scheduling agent

These replace direct function calls with standardized tool interfaces.
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import date, timedelta, datetime
from uuid import uuid4
import random
from abc import ABC, abstractmethod

from storage.local_storage import LocalStorage
from models.scheduled_meal import ScheduledMeal, MealOccasion
from models.meal import Meal
from ..utils.meal_utils import MealUtils
from ..utils.date_utils import DateUtils


class BaseTool(ABC):
    """Base class for all tools"""
    
    def __init__(self, name: str, description: str):
        self._name = name
        self._description = description
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters"""
        pass


class LoadMealsTool(BaseTool):
    """Load all available meals from storage"""
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="load_meals",
            description="Load all available meals from storage"
        )
        self.storage = storage
    
    async def execute(self) -> Dict[str, Any]:
        """Load meals and return meal names"""
        try:
            meals = self.storage.load_meals()
            return {
                "success": True,
                "meals": meals,
                "meal_names": [meal.name for meal in meals],
                "count": len(meals)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meals": [],
                "meal_names": []
            }


class FindMealByNameTool(BaseTool):
    """Find a specific meal by name with fuzzy matching"""
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="find_meal_by_name",
            description="Find a meal by name with fuzzy matching support"
        )
        self.storage = storage
        self.meal_utils = MealUtils()
    
    async def execute(self, meal_name: str, available_meals: List[str]) -> Dict[str, Any]:
        """Find meal by name"""
        try:
            # Try exact match first
            meals = self.storage.load_meals()
            for meal in meals:
                if meal.name.lower() == meal_name.lower():
                    return {
                        "success": True,
                        "found": True,
                        "meal": meal,
                        "meal_name": meal.name
                    }
            
            # Try fuzzy match
            fuzzy_match = self.meal_utils.find_meal_by_name(meal_name, available_meals)
            if fuzzy_match:
                for meal in meals:
                    if meal.name == fuzzy_match:
                        return {
                            "success": True,
                            "found": True,
                            "meal": meal,
                            "meal_name": meal.name
                        }
            
            return {
                "success": True,
                "found": False,
                "meal": None,
                "meal_name": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "found": False
            }


class SelectRandomMealsTool(BaseTool):
    """Select random meals from available options"""
    
    def __init__(self):
        super().__init__(
            name="select_random_meals",
            description="Select one or more random meals from available options"
        )
        self.meal_utils = MealUtils()
    
    async def execute(self, available_meals: List[str], count: int = 1) -> Dict[str, Any]:
        """Select random meals"""
        try:
            selected = self.meal_utils.select_random_meals(available_meals, count)
            return {
                "success": True,
                "selected_meals": selected,
                "count": len(selected)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "selected_meals": []
            }


class ScheduleSingleMealTool(BaseTool):
    """Schedule a single meal"""
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="schedule_single_meal",
            description="Schedule a single meal for a specific date and meal type"
        )
        self.storage = storage
    
    async def execute(
        self, 
        meal: Meal, 
        target_date: str, 
        meal_type: str = "dinner"
    ) -> Dict[str, Any]:
        """Schedule the meal"""
        try:
            # Create scheduled meal
            scheduled_date = date.fromisoformat(target_date)
            meal_occasion = MealOccasion(meal_type)
            
            scheduled_meal = ScheduledMeal(
                id=uuid4(),
                meal_id=meal.id,
                date=scheduled_date,
                occasion=meal_occasion
            )
            
            # Save to storage
            self.storage.add_scheduled_meal(scheduled_meal)
            
            return {
                "success": True,
                "scheduled_meal_id": str(scheduled_meal.id),
                "meal_name": meal.name,
                "date": target_date,
                "meal_type": meal_type
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class ParseDateTool(BaseTool):
    """Parse natural language dates to ISO format"""
    
    def __init__(self):
        super().__init__(
            name="parse_date",
            description="Convert natural language dates to ISO format"
        )
        self.date_utils = DateUtils()
    
    async def execute(self, date_string: str, from_date: Optional[date] = None) -> Dict[str, Any]:
        """Parse date string"""
        try:
            # Handle special cases
            if from_date is None:
                from_date = date.today()
            
            date_lower = date_string.lower().strip()
            
            # Tomorrow
            if date_lower == "tomorrow":
                result_date = from_date + timedelta(days=1)
            # Today
            elif date_lower == "today":
                result_date = from_date
            # Weekday names
            elif date_lower in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                result_date = date.fromisoformat(
                    self.date_utils.get_next_weekday_date(date_lower, from_date)
                )
            else:
                # Try to parse other formats
                parsed = self.date_utils.parse_relative_date(date_string, from_date)
                if parsed:
                    result_date = date.fromisoformat(parsed)
                else:
                    return {
                        "success": False,
                        "error": f"Could not parse date: {date_string}"
                    }
            
            return {
                "success": True,
                "iso_date": result_date.isoformat(),
                "parsed_date": result_date
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class GetDateRangeTool(BaseTool):
    """Generate a date range for batch scheduling"""
    
    def __init__(self):
        super().__init__(
            name="get_date_range",
            description="Generate consecutive dates for batch scheduling"
        )
        self.date_utils = DateUtils()
    
    async def execute(
        self, 
        pattern: str,
        from_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Get date range based on pattern"""
        try:
            if from_date is None:
                from_date = date.today()
            
            pattern_lower = pattern.lower()
            
            if "next 5 days" in pattern_lower:
                start = from_date + timedelta(days=1)
                dates = self.date_utils.get_date_range(start, 5)
            
            elif "rest of the week" in pattern_lower or "rest of week" in pattern_lower:
                tomorrow = from_date + timedelta(days=1)
                days_until_sunday = 6 - from_date.weekday()
                if days_until_sunday > 0:
                    dates = self.date_utils.get_date_range(tomorrow, days_until_sunday)
                else:
                    dates = []
            
            elif "this week" in pattern_lower:
                days_until_sunday = (6 - from_date.weekday()) % 7
                if days_until_sunday == 0 and from_date.weekday() == 6:
                    days_until_sunday = 7
                dates = self.date_utils.get_date_range(from_date, days_until_sunday + 1)
            
            else:
                # Default to single date
                dates = [from_date.isoformat()]
            
            return {
                "success": True,
                "dates": dates,
                "count": len(dates)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "dates": []
            }


class SuggestAlternativeMealsTool(BaseTool):
    """Suggest alternative meals when requested meal not found"""
    
    def __init__(self):
        super().__init__(
            name="suggest_alternatives",
            description="Suggest alternative meals when requested meal is not available"
        )
        self.meal_utils = MealUtils()
    
    async def execute(
        self, 
        requested_meal: str,
        available_meals: List[str],
        max_suggestions: int = 3
    ) -> Dict[str, Any]:
        """Suggest alternatives"""
        try:
            suggestions = self.meal_utils.suggest_alternatives(
                requested_meal, 
                available_meals, 
                max_suggestions
            )
            
            return {
                "success": True,
                "requested_meal": requested_meal,
                "suggestions": suggestions,
                "count": len(suggestions)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "suggestions": []
            }


class ExtractMealTypeTool(BaseTool):
    """Extract meal type from user request"""
    
    def __init__(self):
        super().__init__(
            name="extract_meal_type",
            description="Extract meal type (breakfast, lunch, dinner, snack) from request"
        )
        self.meal_utils = MealUtils()
    
    async def execute(self, request: str) -> Dict[str, Any]:
        """Extract meal type"""
        try:
            meal_type = self.meal_utils.extract_meal_type(request)
            return {
                "success": True,
                "meal_type": meal_type
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meal_type": "dinner"  # Default
            }


# Tool Registry
class ClearScheduleTool(BaseTool):
    """Clear scheduled meals for a date range"""
    
    def __init__(self, storage: LocalStorage):
        super().__init__(
            name="clear_schedule",
            description="Clear scheduled meals for a specified date range (week, month, or custom)"
        )
        self.storage = storage
    
    async def execute(
        self,
        date_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear scheduled meals"""
        try:
            # Convert string dates to date objects if provided
            start_date_obj = None
            end_date_obj = None
            
            if start_date:
                start_date_obj = datetime.fromisoformat(start_date).date()
            if end_date:
                end_date_obj = datetime.fromisoformat(end_date).date()
            
            # Clear schedule
            cleared_count = self.storage.clear_schedule(
                date_range=date_range,
                start_date=start_date_obj,
                end_date=end_date_obj
            )
            
            return {
                "success": True,
                "cleared_count": cleared_count,
                "date_range": date_range or "custom",
                "message": f"Cleared {cleared_count} scheduled meals"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "cleared_count": 0
            }


class ToolRegistry:
    """Registry of all available tools"""
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self._tools = self._initialize_tools()
    
    def _initialize_tools(self) -> Dict[str, BaseTool]:
        """Initialize all tools"""
        return {
            "load_meals": LoadMealsTool(self.storage),
            "find_meal_by_name": FindMealByNameTool(self.storage),
            "select_random_meals": SelectRandomMealsTool(),
            "schedule_single_meal": ScheduleSingleMealTool(self.storage),
            "parse_date": ParseDateTool(),
            "get_date_range": GetDateRangeTool(),
            "suggest_alternatives": SuggestAlternativeMealsTool(),
            "extract_meal_type": ExtractMealTypeTool(),
            "clear_schedule": ClearScheduleTool(self.storage)
        }
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a specific tool by name"""
        return self._tools.get(name)
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all tools"""
        return self._tools
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name"""
        tool = self.get_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found"
            }
        
        return await tool.execute(**kwargs)