"""
Tool-Based Complex Processor - Handles multi-task, batch, and ambiguous requests using tools

This replaces the original complex_processor.py with a tool-based version.
"""

from typing import List

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..core.ambiguity_detector import AmbiguityDetector
from ..parsers.llm_parser import LLMParser
from ..parsers.fallback_parser import FallbackParser
from ..tools.tool_orchestrator import ToolOrchestrator
from .tool_batch_executor import ToolBatchExecutor
from ..utils.response_utils import ResponseBuilder


class ToolComplexProcessor:
    """
    Processes complex scheduling requests using tools
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.orchestrator = ToolOrchestrator(storage)
        self.ambiguity_detector = AmbiguityDetector()
        self.llm_parser = LLMParser()
        self.fallback_parser = FallbackParser()
        self.batch_executor = ToolBatchExecutor(storage)
        self.response_builder = ResponseBuilder()
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str]
    ) -> AIResponse:
        """
        Process complex multi-task scheduling requests using tools
        
        Args:
            message: The user's message
            available_meals: List of available meal names
            
        Returns:
            AIResponse with the result
        """
        # Check for ambiguity first
        ambiguity_info = self.ambiguity_detector.detect_ambiguity(
            message.content, available_meals
        )
        
        if ambiguity_info["is_ambiguous"]:
            clarification_msg = self.ambiguity_detector.generate_clarification_response(
                ambiguity_info, message.content
            )
            return self.response_builder.clarification_response(clarification_msg)
        
        # Parse the complex request
        batch_action = None
        llm_response_text = None
        
        try:
            # Try LLM parsing first
            batch_action, llm_response_text = await self.llm_parser.parse_complex_request(
                message.content, available_meals
            )
            
            # If LLM returned None but gave us a helpful message, use it directly
            if batch_action is None and llm_response_text:
                return AIResponse(
                    conversational_response=llm_response_text,
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
        except Exception as e:
            print(f"LLM parsing failed, using fallback: {e}")
        
        # Fall back to rule-based parsing if needed
        if batch_action is None:
            batch_action = self.fallback_parser.parse_complex_request(
                message.content, available_meals
            )
        
        # Execute batch scheduling using tools
        result = await self.batch_executor.execute_batch_schedule(batch_action, available_meals)
        
        # If execution failed but we have helpful LLM response, use that instead
        if not result["success"] and llm_response_text:
            return AIResponse(
                conversational_response=llm_response_text,
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        if result["success"]:
            # Create success response
            return self._build_success_response(result)
        else:
            # Create error response
            return self._build_error_response(result)
    
    def _build_success_response(self, result: dict) -> AIResponse:
        """Build success response from execution result"""
        scheduled_count = result["scheduled_count"]
        schedules = result["schedules"]
        
        if scheduled_count == 1:
            schedule = schedules[0]
            natural_date = self.response_builder.format_natural_date(schedule['date'])
            response = f"I've scheduled {schedule['meal_name']} for {schedule['meal_type']} {natural_date}!"
        else:
            response = f"I've scheduled {scheduled_count} meals for you:\n"
            for schedule in schedules[:5]:  # Limit to first 5 for readability
                natural_date = self.response_builder.format_natural_date(schedule['date'])
                response += f"• {schedule['meal_name']} ({schedule['meal_type']}) {natural_date}\n"
            
            if len(schedules) > 5:
                response += f"... and {len(schedules) - 5} more meals"
        
        # Add error information if some tasks failed
        if result["errors"]:
            response += f"\n\nNote: {len(result['errors'])} tasks had issues."
            # Add first few error details
            for error in result["errors"][:2]:
                if "meal_name" in error and "reason" in error:
                    response += f"\n• {error['meal_name']}: {error['reason']}"
        
        # Create AI actions
        actions = []
        for schedule in schedules:
            actions.append(AIAction(
                type=ActionType.SCHEDULE_MEAL,
                parameters=schedule
            ))
        
        return AIResponse(
            conversational_response=response,
            actions=actions,
            model_used="enhanced_meal_agent"
        )
    
    def _build_error_response(self, result: dict) -> AIResponse:
        """Build error response from execution result"""
        error_msg = "I couldn't schedule any meals. "
        
        if result["errors"]:
            # Group errors by type for better messaging
            meal_not_found_errors = [e for e in result["errors"] if "not found" in e.get("reason", "")]
            
            if meal_not_found_errors:
                # Use suggestions from tools if available
                first_error = meal_not_found_errors[0]
                unavailable_meal = first_error.get("meal_name", "Unknown")
                suggestions = first_error.get("suggestions", [])
                
                error_msg = f"I don't have {unavailable_meal} available. "
                if suggestions:
                    if len(suggestions) > 1:
                        error_msg += f"How about {', '.join(suggestions[:-1])} or {suggestions[-1]} instead?"
                    else:
                        error_msg += f"How about {suggestions[0]} instead?"
                else:
                    # Fall back to loading meals for suggestions
                    meal_names, _ = self.orchestrator.get_available_meals()
                    if meal_names:
                        suggestions = meal_names[:3]
                        error_msg += f"How about {', '.join(suggestions[:-1])} or {suggestions[-1]} instead?"
            else:
                # Other types of errors
                error_reasons = [e.get("reason", "Unknown error") for e in result["errors"][:3]]
                error_msg += f"Issues: {'; '.join(error_reasons)}"
        
        return AIResponse(
            conversational_response=error_msg,
            actions=[],
            model_used="enhanced_meal_agent"
        )