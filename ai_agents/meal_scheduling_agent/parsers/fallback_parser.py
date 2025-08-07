"""
Fallback Parser - Rule-based parsing when LLM fails
"""

from typing import List
from datetime import date, timedelta

from .parser_models import BatchScheduleAction, ScheduleTask
from ..utils.date_utils import DateUtils


class FallbackParser:
    """
    Manual parsing logic for when LLM parsing fails
    """
    
    def __init__(self):
        self.date_utils = DateUtils()
    
    def parse_complex_request(
        self, 
        user_request: str, 
        available_meals: List[str]
    ) -> BatchScheduleAction:
        """
        Fallback parsing for complex requests without LLM
        
        Args:
            user_request: The user's request
            available_meals: List of available meal names
            
        Returns:
            BatchScheduleAction with parsed tasks
        """
        request_lower = user_request.lower()
        tasks = []
        
        # Detect batch day patterns
        if "next 5 days" in request_lower or "rest of the week" in request_lower or "this week" in request_lower:
            # Calculate dates based on pattern
            if "rest of the week" in request_lower:
                # Rest of the week = tomorrow through Sunday
                today = date.today()
                tomorrow = today + timedelta(days=1)
                days_until_end_of_week = 6 - today.weekday()  # 0=Monday, 6=Sunday
                
                if days_until_end_of_week > 0:
                    dates = self.date_utils.get_date_range(tomorrow, days_until_end_of_week)
                else:
                    # Today is Sunday, so no "rest of week"
                    dates = []
            elif "this week" in request_lower:
                # This week = today through Sunday
                today = date.today()
                days_until_sunday = (6 - today.weekday()) % 7
                if days_until_sunday == 0 and today.weekday() == 6:  # Today is Sunday
                    days_until_sunday = 7
                dates = self.date_utils.get_date_range(today, days_until_sunday + 1)
            else:
                # Next 5 days
                dates = self.date_utils.get_date_range(date.today() + timedelta(days=1), 5)
            
            # Determine meal type - default to dinner
            meal_type = "dinner"  # Default
            if "breakfast" in request_lower:
                meal_type = "breakfast"
            elif "lunch" in request_lower:
                meal_type = "lunch"
            elif "dinner" in request_lower or "dinners" in request_lower:
                meal_type = "dinner"
            
            for target_date in dates:
                if "random" in request_lower or "saved meals" in request_lower or not any(meal.lower() in request_lower for meal in available_meals):
                    # Use random selection if explicitly requested, mentions "saved meals", or no specific meal found
                    tasks.append(ScheduleTask(
                        meal_name=None,
                        target_date=target_date,
                        meal_type=meal_type,
                        is_random=True
                    ))
                else:
                    # Find specific meal mentioned
                    found_meal = None
                    for meal in available_meals:
                        if meal.lower() in request_lower:
                            found_meal = meal
                            break
                    
                    tasks.append(ScheduleTask(
                        meal_name=found_meal,
                        target_date=target_date,
                        meal_type=meal_type,
                        is_random=found_meal is None
                    ))
            
            return BatchScheduleAction(tasks=tasks, request_type="batch_days")
        
        # Detect random selection (including "pick" variants) - check before multi-meal
        elif any(word in request_lower for word in ["random", "pick", "choose", "select"]) and not any(meal.lower() in request_lower for meal in available_meals):
            target_date = date.today().isoformat()
            if "tomorrow" in request_lower:
                target_date = (date.today() + timedelta(days=1)).isoformat()
            elif "friday" in request_lower:
                target_date = self.date_utils.get_next_weekday_date("friday", date.today())
            
            # Detect meal type
            meal_type = "dinner"  # default
            if "breakfast" in request_lower:
                meal_type = "breakfast"
            elif "lunch" in request_lower:
                meal_type = "lunch"
            elif "dinner" in request_lower:
                meal_type = "dinner"
            elif "snack" in request_lower:
                meal_type = "snack"
            
            tasks.append(ScheduleTask(
                meal_name=None,
                target_date=target_date,
                meal_type=meal_type,
                is_random=True
            ))
            
            return BatchScheduleAction(tasks=tasks, request_type="random_selection")
        
        # Detect multi-meal patterns (pizza and tacos)
        elif " and " in request_lower and any(meal.lower() in request_lower for meal in available_meals):
            # Find target date
            target_date = date.today().isoformat()
            if "tomorrow" in request_lower:
                target_date = (date.today() + timedelta(days=1)).isoformat()
            elif "friday" in request_lower:
                target_date = self.date_utils.get_next_weekday_date("friday", date.today())
            
            # Find meals mentioned
            mentioned_meals = []
            for meal in available_meals:
                if meal.lower() in request_lower:
                    mentioned_meals.append(meal)
            
            # Create tasks for each meal
            meal_type = "dinner"  # default
            if "breakfast" in request_lower:
                meal_type = "breakfast"
            elif "lunch" in request_lower:
                meal_type = "lunch"
            
            for meal in mentioned_meals:
                tasks.append(ScheduleTask(
                    meal_name=meal,
                    target_date=target_date,
                    meal_type=meal_type,
                    is_random=False
                ))
            
            return BatchScheduleAction(tasks=tasks, request_type="multi_meal")
        
        # Default to single task (fallback)
        # Extract what meal was requested even if not found
        requested_meal = None
        for word in user_request.split():
            if len(word) > 3 and word.lower() not in ["schedule", "tomorrow", "today", "for", "the"]:
                requested_meal = word
                break
        
        if not requested_meal:
            requested_meal = "requested meal"
        
        default_date = date.today().isoformat()
        return BatchScheduleAction(
            tasks=[ScheduleTask(meal_name=requested_meal, target_date=default_date, meal_type="dinner")],
            request_type="single"
        )