"""
Simple Processor - Handles straightforward single-meal requests
"""

from typing import List
from datetime import date, timedelta

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..parsers.parser_models import ScheduleTask, BatchScheduleAction
from ..utils.date_utils import DateUtils
from ..utils.response_utils import ResponseBuilder
from .batch_executor import BatchExecutor


class SimpleProcessor:
    """
    Processes simple scheduling requests
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.date_utils = DateUtils()
        self.response_builder = ResponseBuilder()
        self.batch_executor = BatchExecutor(storage)
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str]
    ) -> AIResponse:
        """
        Process simple single-meal scheduling requests directly
        
        Args:
            message: The user's message
            available_meals: List of available meal names
            
        Returns:
            AIResponse with the result
        """
        try:
            # Find meal name in request
            meal_name = None
            for meal in available_meals:
                if meal.lower() in message.content.lower():
                    meal_name = meal
                    break
            
            if not meal_name:
                return AIResponse(
                    conversational_response="I couldn't find that meal in your saved meals. Please try with one of your saved meals.",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
            
            # Extract date from request
            target_date = self._extract_simple_date(message.content)
            
            # Determine meal type
            meal_type = self._extract_meal_type(message.content)
            
            # Execute the scheduling using batch logic for consistency
            task = ScheduleTask(
                meal_name=meal_name,
                target_date=target_date.isoformat(),
                meal_type=meal_type,
                is_random=False
            )
            batch_action = BatchScheduleAction(tasks=[task], request_type="single")
            batch_result = await self.batch_executor.execute_batch_schedule(batch_action, available_meals)
            
            if batch_result["success"] and batch_result["schedules"]:
                schedule_result = batch_result["schedules"][0]
                
                # Format natural date
                natural_date = self.response_builder.format_natural_date(schedule_result['date'])
                response = f"I've scheduled {schedule_result['meal_name']} for {schedule_result['meal_type']} {natural_date}!"
                
                action = AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters=schedule_result
                )
                
                return AIResponse(
                    conversational_response=response,
                    actions=[action],
                    model_used="enhanced_meal_agent"
                )
            else:
                error_msg = batch_result["errors"][0]["reason"] if batch_result["errors"] else "Unknown error"
                return AIResponse(
                    conversational_response=f"Sorry, I couldn't schedule that meal: {error_msg}",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
                
        except Exception as e:
            return self.response_builder.unexpected_error(str(e))
    
    def _extract_simple_date(self, content: str) -> date:
        """
        Extract date from simple request
        
        Args:
            content: User request content
            
        Returns:
            Extracted date (defaults to today)
        """
        content_lower = content.lower()
        
        # Check for tomorrow first
        if "tomorrow" in content_lower:
            return date.today() + timedelta(days=1)
        
        # Check for "next" weekday patterns
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
        for weekday in weekdays:
            if f"next {weekday}" in content_lower:
                iso_date = self.date_utils.get_next_weekday_date(weekday, date.today())
                return date.fromisoformat(iso_date)
        
        # Check for regular weekday patterns
        for weekday in weekdays:
            if weekday in content_lower:
                iso_date = self.date_utils.get_next_weekday_date(weekday, date.today())
                return date.fromisoformat(iso_date)
        
        # Default to today
        return date.today()
    
    def _extract_meal_type(self, content: str) -> str:
        """
        Extract meal type from request
        
        Args:
            content: User request content
            
        Returns:
            Meal type (defaults to dinner)
        """
        content_lower = content.lower()
        
        if "breakfast" in content_lower:
            return "breakfast"
        elif "lunch" in content_lower:
            return "lunch"
        elif "dinner" in content_lower:
            return "dinner"
        elif "snack" in content_lower:
            return "snack"
        else:
            # Default to dinner
            return "dinner"