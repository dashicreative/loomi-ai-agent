"""
Complex Processor - Handles multi-task, batch, and ambiguous requests using tools
"""

from typing import List
from datetime import date, timedelta

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..core.ambiguity_detector import AmbiguityDetector
from ..parsers.llm_parser import LLMParser
from ..parsers.fallback_parser import FallbackParser
from ..tools.tool_orchestrator import ToolOrchestrator
from .batch_executor import BatchExecutor
from ..utils.response_utils import ResponseBuilder
from ..utils.date_utils import DateUtils


class ComplexProcessor:
    """
    Processes complex scheduling requests using tools
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.orchestrator = ToolOrchestrator(storage)
        self.ambiguity_detector = AmbiguityDetector()
        self.llm_parser = LLMParser()
        self.fallback_parser = FallbackParser()
        self.batch_executor = BatchExecutor(storage)
        self.response_builder = ResponseBuilder()
        self.date_utils = DateUtils()
        self.temporal_reasoner = TemporalReasoner()
        self.context_manager = None  # Will be set by the main agent
    
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
        # Store message for context access
        self._current_message = message
        
        # Check for clear schedule requests first
        request_lower = message.content.lower()
        if any(keyword in request_lower for keyword in ["clear", "remove all", "delete all", "unschedule"]):
            return await self._handle_clear_schedule(message)
        
        # Check for ambiguity
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
        # Store the original request for context tracking
        result["original_request"] = message.content
        
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
        # For batch operations, we don't need individual actions
        # The summary message is sufficient for user experience
        actions = []
        
        # Only include actions if it's a single schedule (for backward compatibility)
        if scheduled_count == 1:
            actions.append(AIAction(
                type=ActionType.SCHEDULE_MEAL,
                parameters=schedules[0]
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
                
                # Store context for follow-up responses if we have suggestions
                if suggestions and hasattr(self, 'context_manager') and self.context_manager:
                    # Extract date and meal_type from the error task info
                    task_info = first_error.get("task", {})
                    original_date = task_info.get("target_date") or first_error.get("date")
                    original_meal_type = task_info.get("meal_type") or first_error.get("meal_type", "dinner")
                    
                    # Extract user_id from message context
                    user_id = self._current_message.user_context.get("user_id", "default") if hasattr(self, '_current_message') else "default"
                    
                    self.context_manager.store_suggestions(
                        user_id=user_id,
                        suggestions=suggestions,
                        original_request=result.get("original_request", ""),
                        requested_meal=unavailable_meal,
                        date=original_date,
                        meal_type=original_meal_type
                    )
            else:
                # Other types of errors
                error_reasons = [e.get("reason", "Unknown error") for e in result["errors"][:3]]
                error_msg += f"Issues: {'; '.join(error_reasons)}"
        
        return AIResponse(
            conversational_response=error_msg,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _handle_clear_schedule(self, message: ChatMessage) -> AIResponse:
        """Handle clear schedule requests using universal temporal reasoning"""
        # Use temporal reasoner to understand the time reference
        temporal_context = self.temporal_reasoner.interpret(message.content)
        
        # Determine date range based on temporal context
        date_range = None
        start_date = None
        end_date = None
        
        if temporal_context.reference_type == TemporalReference.ALL_TIME:
            date_range = "all"
        elif temporal_context.reference_type == TemporalReference.RELATIVE_WEEK:
            # For "this week", use the legacy date_range parameter for backward compatibility
            if temporal_context.metadata.get("week") == "this":
                date_range = "week"
            else:
                # For other week references (next week, last week), use specific dates
                start_date, end_date = temporal_context.get_date_range()
        elif temporal_context.reference_type == TemporalReference.RELATIVE_MONTH:
            # For "this month", use the legacy date_range parameter
            if temporal_context.metadata.get("month") == "this":
                date_range = "month"
            else:
                # For other month references, use specific dates
                start_date, end_date = temporal_context.get_date_range()
        elif temporal_context.reference_type == TemporalReference.AMBIGUOUS:
            # If ambiguous, default to today for safety
            today = date.today().isoformat()
            start_date = today
            end_date = today
        else:
            # For all other cases (specific dates, relative days, etc.), use the resolved dates
            start_date, end_date = temporal_context.get_date_range()
        
        # Execute clear operation
        result = await self.orchestrator.clear_schedule(
            date_range=date_range,
            start_date=start_date,
            end_date=end_date
        )
        
        if result["success"]:
            cleared_count = result["cleared_count"]
            
            if cleared_count == 0:
                response = "Your schedule is already clear!"
            elif cleared_count == 1:
                response = "I've cleared 1 scheduled meal."
            else:
                # Use temporal reasoner to generate natural description
                time_description = self.temporal_reasoner.describe_context(temporal_context)
                
                # Format the response based on what was cleared
                if temporal_context.reference_type == TemporalReference.ALL_TIME:
                    response = f"I've cleared all {cleared_count} scheduled meals."
                else:
                    response = f"I've cleared {cleared_count} scheduled meals for {time_description}."
            
            return AIResponse(
                conversational_response=response.strip(),
                actions=[],
                model_used="enhanced_meal_agent"
            )
        else:
            return AIResponse(
                conversational_response=f"Sorry, I couldn't clear your schedule: {result.get('error', 'Unknown error')}",
                actions=[],
                model_used="enhanced_meal_agent"
            )