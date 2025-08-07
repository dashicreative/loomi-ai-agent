"""
LangChain tools for meal scheduling operations
"""

import json
import random
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from storage.local_storage import LocalStorage
from models.scheduled_meal import ScheduledMeal, MealOccasion
from uuid import uuid4


class GetAvailableMealsTool(BaseTool):
    """Tool to get list of user's saved meals"""
    name: str = "get_available_meals"
    description: str = "Get list of user's saved meals with their names and default occasions"
    storage: LocalStorage
    
    def __init__(self, storage: LocalStorage, **kwargs):
        super().__init__(storage=storage, **kwargs)
    
    def _run(self, query: str = "") -> str:
        """Get available meals"""
        try:
            meals = self.storage.load_meals()
            meal_list = [
                {
                    "name": meal.name,
                    "id": str(meal.id),
                    "occasion": meal.occasion
                }
                for meal in meals
            ]
            return json.dumps(meal_list)
        except Exception as e:
            return f"Error getting meals: {str(e)}"
    
    async def _arun(self, query: str = "") -> str:
        """Async version"""
        return self._run(query)


class DateParserTool(BaseTool):
    """Tool to parse relative dates to absolute dates"""
    name: str = "parse_date"
    description: str = "Convert relative dates (tomorrow, next Friday) to YYYY-MM-DD format"
    
    def _get_next_weekday_date(self, weekday_name: str, from_date: date) -> str:
        """Convert weekday name to next occurrence"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return from_date.isoformat()
        
        days_ahead = target_weekday - from_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
            
        target_date = from_date + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    def _run(self, date_expression: str) -> str:
        """Parse date expression"""
        try:
            expr_lower = date_expression.lower().strip()
            today = date.today()
            
            # Direct date mappings
            if expr_lower == "today":
                return today.isoformat()
            elif expr_lower == "tomorrow":
                return (today + timedelta(days=1)).isoformat()
            elif "next" in expr_lower:
                # Extract weekday from "next Monday" etc
                parts = expr_lower.split()
                if len(parts) >= 2:
                    weekday = parts[-1]
                    return self._get_next_weekday_date(weekday, today)
            elif expr_lower in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                return self._get_next_weekday_date(expr_lower, today)
            else:
                # Try to parse as ISO date
                try:
                    parsed_date = date.fromisoformat(date_expression)
                    return parsed_date.isoformat()
                except:
                    return f"Could not parse date: {date_expression}"
                    
        except Exception as e:
            return f"Error parsing date: {str(e)}"
    
    async def _arun(self, date_expression: str) -> str:
        """Async version"""
        return self._run(date_expression)


class ScheduleSingleMealTool(BaseTool):
    """Tool to schedule a single meal"""
    name: str = "schedule_single_meal"
    description: str = "Schedule one specific meal to a date and meal type (breakfast/lunch/dinner/snack)"
    storage: LocalStorage
    
    def __init__(self, storage: LocalStorage, **kwargs):
        super().__init__(storage=storage, **kwargs)
    
    def _run(self, meal_name: str, target_date: str, meal_type: str = "dinner") -> str:
        """Schedule a single meal"""
        try:
            # Find the meal
            meals = self.storage.load_meals()
            target_meal = None
            
            for meal in meals:
                if meal.name.lower() == meal_name.lower():
                    target_meal = meal
                    break
            
            if not target_meal:
                return f"Meal '{meal_name}' not found in saved meals"
            
            # Create scheduled meal
            meal_occasion = MealOccasion(meal_type.lower())
            scheduled_meal = ScheduledMeal(
                id=uuid4(),
                meal_id=target_meal.id,
                date=date.fromisoformat(target_date),
                occasion=meal_occasion
            )
            
            # Save to storage
            self.storage.add_scheduled_meal(scheduled_meal)
            
            return json.dumps({
                "success": True,
                "scheduled_meal_id": str(scheduled_meal.id),
                "meal_name": target_meal.name,
                "date": target_date,
                "meal_type": meal_type
            })
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e)
            })
    
    async def _arun(self, meal_name: str, target_date: str, meal_type: str = "dinner") -> str:
        """Async version"""
        return self._run(meal_name, target_date, meal_type)


class BatchMealSchedulerTool(BaseTool):
    """Tool to schedule multiple meals at once"""
    name: str = "schedule_multiple_meals"
    description: str = "Schedule multiple meals across multiple dates. Accepts JSON array of scheduling tasks"
    storage: LocalStorage
    
    def __init__(self, storage: LocalStorage, **kwargs):
        super().__init__(storage=storage, **kwargs)
    
    def _run(self, schedule_plan: str) -> str:
        """Execute batch scheduling"""
        try:
            # Parse the schedule plan
            tasks = json.loads(schedule_plan)
            if not isinstance(tasks, list):
                tasks = [tasks]
            
            results = []
            for task in tasks:
                meal_name = task.get("meal_name")
                target_date = task.get("date")
                meal_type = task.get("meal_type", "dinner")
                
                # Use inline scheduling logic instead of calling another tool
                single_scheduler = ScheduleSingleMealTool(self.storage)
                result = single_scheduler._run(meal_name, target_date, meal_type)
                result_data = json.loads(result)
                results.append(result_data)
            
            # Summarize results
            successful = [r for r in results if r.get("success")]
            failed = [r for r in results if not r.get("success")]
            
            return json.dumps({
                "total_scheduled": len(successful),
                "total_failed": len(failed),
                "successful_meals": successful,
                "failed_meals": failed
            })
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to parse schedule plan: {str(e)}"
            })
    
    async def _arun(self, schedule_plan: str) -> str:
        """Async version"""
        return self._run(schedule_plan)


class RandomMealSelectorTool(BaseTool):
    """Tool to select random meals"""
    name: str = "select_random_meals"
    description: str = "Pick random meals from available meals. Specify count and available meals JSON"
    
    def _run(self, count: str = "1", available_meals: str = "[]") -> str:
        """Select random meals"""
        try:
            num_meals = int(count)
            meals = json.loads(available_meals)
            
            if not meals:
                return json.dumps([])
            
            # Get meal names
            meal_names = [m.get("name") if isinstance(m, dict) else m for m in meals]
            
            # Ensure we don't select more than available
            num_meals = min(num_meals, len(meal_names))
            
            selected = random.sample(meal_names, num_meals)
            return json.dumps(selected)
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to select random meals: {str(e)}"
            })
    
    async def _arun(self, count: str = "1", available_meals: str = "[]") -> str:
        """Async version"""
        return self._run(count, available_meals)


class ConflictDetectorTool(BaseTool):
    """Tool to check for scheduling conflicts"""
    name: str = "check_scheduling_conflicts"
    description: str = "Check if a date/meal_type slot already has a scheduled meal"
    storage: LocalStorage
    
    def __init__(self, storage: LocalStorage, **kwargs):
        super().__init__(storage=storage, **kwargs)
    
    def _run(self, target_date: str, meal_type: str) -> str:
        """Check for conflicts"""
        try:
            scheduled_meals = self.storage.load_scheduled_meals()
            target_date_obj = date.fromisoformat(target_date)
            
            conflicts = []
            for scheduled in scheduled_meals:
                if (scheduled.date == target_date_obj and 
                    scheduled.occasion == meal_type):
                    # Find meal name
                    meals = self.storage.load_meals()
                    meal_name = "Unknown"
                    for meal in meals:
                        if meal.id == scheduled.meal_id:
                            meal_name = meal.name
                            break
                    
                    conflicts.append({
                        "meal_name": meal_name,
                        "scheduled_id": str(scheduled.id)
                    })
            
            if conflicts:
                return json.dumps({
                    "has_conflict": True,
                    "conflicts": conflicts
                })
            else:
                return json.dumps({
                    "has_conflict": False
                })
                
        except Exception as e:
            return json.dumps({
                "error": f"Failed to check conflicts: {str(e)}"
            })
    
    async def _arun(self, target_date: str, meal_type: str) -> str:
        """Async version"""
        return self._run(target_date, meal_type)


class AmbiguityDetectorTool(BaseTool):
    """Tool to detect ambiguous requests"""
    name: str = "detect_request_ambiguity"
    description: str = "Analyze if a meal scheduling request needs clarification"
    
    def _run(self, user_request: str) -> str:
        """Detect ambiguity"""
        try:
            request_lower = user_request.lower()
            
            # Check for vague quantities
            has_vague_quantity = any(word in request_lower for word in [
                "some", "a few", "several", "multiple", "pick", "choose", "select"
            ]) and not any(word in request_lower for word in ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
            
            # Check for timeframe
            has_timeframe = any(word in request_lower for word in [
                "next", "this", "tomorrow", "today", "weekend",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "week", "weekly", "days", "daily"
            ])
            
            # Missing elements
            missing_elements = []
            if has_vague_quantity and not has_timeframe:
                missing_elements.append("specific_timeframe")
            if has_vague_quantity:
                missing_elements.append("specific_quantity")
                
            is_ambiguous = len(missing_elements) > 0
            
            clarifications = []
            if "specific_quantity" in missing_elements:
                clarifications.append("how many meals would you like me to schedule")
            if "specific_timeframe" in missing_elements:
                clarifications.append("which days or time period you'd prefer")
            
            clarification_msg = ""
            if clarifications:
                if len(clarifications) == 1:
                    clarification_msg = f"Could you let me know {clarifications[0]}?"
                else:
                    clarification_msg = f"Could you let me know {' and '.join(clarifications)}?"
            
            return json.dumps({
                "is_ambiguous": is_ambiguous,
                "missing_elements": missing_elements,
                "clarification_message": clarification_msg
            })
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to detect ambiguity: {str(e)}"
            })
    
    async def _arun(self, user_request: str) -> str:
        """Async version"""
        return self._run(user_request)