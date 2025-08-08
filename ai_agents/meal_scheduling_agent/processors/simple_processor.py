"""
Simple Processor - Handles straightforward single-meal requests using tools
"""

from typing import List
from datetime import date, timedelta

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..parsers.parser_models import ScheduleTask, BatchScheduleAction
from ..tools.tool_orchestrator import ToolOrchestrator
from ..utils.response_utils import ResponseBuilder
from .batch_executor import BatchExecutor
from ..core.temporal_reasoner import TemporalReasoner


class SimpleProcessor:
    """
    Processes simple scheduling requests using tools
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.orchestrator = ToolOrchestrator(storage)
        self.response_builder = ResponseBuilder()
        self.batch_executor = BatchExecutor(storage)
        self.temporal_reasoner = TemporalReasoner()
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str]
    ) -> AIResponse:
        """
        Process simple single-meal scheduling requests using tools
        
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
            
            # Extract date from request using tools
            target_date = await self._extract_simple_date(message.content)
            
            # Extract meal type using tools
            meal_type = await self.orchestrator.extract_meal_type(message.content)
            
            # Execute the scheduling using batch logic for consistency
            task = ScheduleTask(
                meal_name=meal_name,
                target_date=target_date,
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
    
    async def _extract_simple_date(self, content: str) -> str:
        """
        Extract date from simple request using temporal reasoning
        
        Args:
            content: User request content
            
        Returns:
            ISO formatted date string
        """
        # Use temporal reasoner for consistent date extraction
        temporal_context = self.temporal_reasoner.interpret(content)
        
        # Get the start date (for single day references)
        start_date, _ = temporal_context.get_date_range()
        
        if start_date:
            return start_date
        else:
            # Default to today if no date could be extracted
            return date.today().isoformat()