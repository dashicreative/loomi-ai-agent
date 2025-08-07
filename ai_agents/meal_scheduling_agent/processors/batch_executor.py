"""
Batch Executor - Executes multiple scheduling operations
"""

from typing import Dict, Any, List
from datetime import date
from uuid import uuid4

from models.scheduled_meal import ScheduledMeal, MealOccasion
from storage.local_storage import LocalStorage
from ..parsers.parser_models import BatchScheduleAction, ScheduleTask
from ..utils.meal_utils import MealUtils


class BatchExecutor:
    """
    Executes batch scheduling operations
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.meal_utils = MealUtils()
    
    async def execute_batch_schedule(
        self, 
        batch_action: BatchScheduleAction, 
        available_meals: List[str]
    ) -> Dict[str, Any]:
        """
        Execute multiple scheduling tasks
        
        Args:
            batch_action: The batch of tasks to execute
            available_meals: List of available meal names
            
        Returns:
            Dictionary with execution results
        """
        results = []
        successful_schedules = []
        errors = []
        
        for task in batch_action.tasks:
            try:
                # Handle random meal selection
                if task.is_random or not task.meal_name:
                    selected_meals = self.meal_utils.select_random_meals(available_meals, 1)
                    if not selected_meals:
                        errors.append({
                            "task": task,
                            "reason": "No meals available for random selection"
                        })
                        continue
                    task.meal_name = selected_meals[0]
                
                # Find the meal
                meals = self.storage.load_meals()
                target_meal = None
                
                for meal in meals:
                    if meal.name.lower() == task.meal_name.lower():
                        target_meal = meal
                        break
                
                if not target_meal:
                    # Try fuzzy matching
                    fuzzy_match = self.meal_utils.find_meal_by_name(
                        task.meal_name, 
                        [m.name for m in meals]
                    )
                    if fuzzy_match:
                        for meal in meals:
                            if meal.name == fuzzy_match:
                                target_meal = meal
                                break
                
                if not target_meal:
                    errors.append({
                        "task": task,
                        "meal_name": task.meal_name,
                        "reason": f"Meal '{task.meal_name}' not found"
                    })
                    continue
                
                # Create scheduled meal
                target_date = date.fromisoformat(task.target_date)
                meal_occasion = MealOccasion(task.meal_type)
                
                scheduled_meal = ScheduledMeal(
                    id=uuid4(),
                    meal_id=target_meal.id,
                    date=target_date,
                    occasion=meal_occasion
                )
                
                # Save to storage
                self.storage.add_scheduled_meal(scheduled_meal)
                
                successful_schedules.append({
                    "meal_name": target_meal.name,
                    "date": task.target_date,
                    "meal_type": task.meal_type,
                    "scheduled_meal_id": str(scheduled_meal.id)
                })
                
            except Exception as e:
                errors.append({
                    "task": task,
                    "meal_name": getattr(task, 'meal_name', 'Unknown'),
                    "reason": str(e)
                })
        
        return {
            "success": len(successful_schedules) > 0,
            "scheduled_count": len(successful_schedules),
            "schedules": successful_schedules,
            "errors": errors,
            "request_type": batch_action.request_type
        }