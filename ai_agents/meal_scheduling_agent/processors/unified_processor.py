"""
Unified Processor - Phase 2 Migration: Single processor using LLM-first architecture

This replaces:
- SimpleProcessor (123 lines)
- ComplexProcessor (285 lines)  
- BatchExecutor (52 lines)

Total replacement: ~460 lines → ~200 lines with better capability
"""

from typing import List, Dict, Any, Optional
from datetime import date

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..core.llm_intent_processor import LLMIntentProcessor, LLMRequestContext
from ..core.intent_classifier import IntentType
from ..tools.tool_orchestrator import ToolOrchestrator
from ..utils.response_utils import ResponseBuilder


class UnifiedProcessor:
    """
    Single processor that handles all meal scheduling requests using LLM-first architecture
    
    Replaces the artificial SimpleProcessor/ComplexProcessor distinction with 
    intelligent LLM-driven processing that adapts to any request complexity.
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.llm_intent = LLMIntentProcessor()
        self.orchestrator = ToolOrchestrator(storage)
        self.response_builder = ResponseBuilder()
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str]
    ) -> AIResponse:
        """
        Process any meal scheduling request using LLM understanding
        
        Args:
            message: The user's message
            available_meals: List of available meal names
            
        Returns:
            AIResponse with the result
        """
        try:
            # Use LLM to understand the request
            context = await self.llm_intent.understand_request(
                message.content, 
                available_meals
            )
            
            # Handle requests based on LLM analysis
            if context.needs_clarification:
                return self._create_clarification_response(context)
            
            # Route to appropriate handler based on intent
            if context.intent_type == IntentType.DIRECT_SCHEDULE:
                return await self._handle_direct_schedule(context, available_meals)
            elif context.intent_type == IntentType.BATCH_SCHEDULE:
                return await self._handle_batch_schedule(context, available_meals)
            elif context.intent_type == IntentType.FILL_SCHEDULE:
                return await self._handle_fill_schedule(context, available_meals)
            elif context.intent_type == IntentType.CLEAR_SCHEDULE:
                return await self._handle_clear_schedule(context)
            elif context.intent_type == IntentType.VIEW_SCHEDULE:
                return await self._handle_view_schedule(context)
            elif context.intent_type == IntentType.LIST_MEALS:
                return await self._handle_list_meals(available_meals)
            else:
                return self._create_unknown_response(context)
                
        except Exception as e:
            return self.response_builder.unexpected_error(str(e))
    
    def _create_clarification_response(self, context: LLMRequestContext) -> AIResponse:
        """Create response requesting clarification"""
        return AIResponse(
            conversational_response=context.clarification_question,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    def _create_unknown_response(self, context: LLMRequestContext) -> AIResponse:
        """Create response for unknown intents"""
        fallback_msg = ("I'm not sure what you'd like me to do. "
                       "Try asking me to schedule a meal, view your schedule, or clear meals.")
        
        return AIResponse(
            conversational_response=context.clarification_question or fallback_msg,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _handle_direct_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Handle direct single meal scheduling"""
        # Extract entities from LLM analysis
        entities = context.entities
        
        # Get meal name
        meal_name = None
        if entities.get("meal_names"):
            meal_name = entities["meal_names"][0]
        
        if not meal_name:
            return AIResponse(
                conversational_response="I couldn't identify which meal you want to schedule. Please specify a meal name.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        # Get date (use first date if multiple)
        target_date = None
        if entities.get("dates"):
            target_date = entities["dates"][0]
        else:
            # Default to today if no date specified
            target_date = date.today().isoformat()
        
        # Get meal type (default to dinner)
        meal_type = "dinner"
        if entities.get("meal_types"):
            meal_type = entities["meal_types"][0]
        
        # Execute using orchestrator
        result = await self.orchestrator.find_and_schedule_meal(
            meal_name=meal_name,
            target_date=target_date,
            meal_type=meal_type,
            available_meals=available_meals
        )
        
        if result["success"]:
            # Format natural date for response
            natural_date = self.response_builder.format_natural_date(result["date"])
            response = f"I've scheduled {result['meal_name']} for {result['meal_type']} {natural_date}!"
            
            action = AIAction(
                type=ActionType.SCHEDULE_MEAL,
                parameters={
                    "meal_name": result["meal_name"],
                    "date": result["date"],
                    "meal_type": result["meal_type"],
                    "scheduled_meal_id": result.get("scheduled_meal_id")
                }
            )
            
            return AIResponse(
                conversational_response=response,
                actions=[action],
                model_used="enhanced_meal_agent"
            )
        else:
            # Handle suggestions from orchestrator
            suggestions = result.get("suggestions", [])
            error_msg = f"I don't have {meal_name} available."
            
            if suggestions:
                if len(suggestions) > 1:
                    error_msg += f" How about {', '.join(suggestions[:-1])} or {suggestions[-1]} instead?"
                else:
                    error_msg += f" How about {suggestions[0]} instead?"
            
            return AIResponse(
                conversational_response=error_msg,
                actions=[],
                model_used="enhanced_meal_agent"
            )
    
    async def _handle_batch_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Handle batch/multiple meal scheduling"""
        # Build tasks from LLM execution plan
        tasks = []
        
        if context.execution_plan:
            # Use LLM-generated execution plan
            for action in context.execution_plan:
                if action.get("action") in ["schedule_meal", "schedule_random"]:
                    tasks.append({
                        "meal_name": action.get("meal_name"),
                        "target_date": action.get("date"),
                        "meal_type": action.get("meal_type", "dinner"),
                        "is_random": action.get("action") == "schedule_random" or not action.get("meal_name")
                    })
        else:
            # Fallback: generate tasks from entities
            entities = context.entities
            dates = entities.get("dates", [date.today().isoformat()])
            meal_types = entities.get("meal_types", ["dinner"])
            meal_names = entities.get("meal_names", [])
            
            # If no specific meals mentioned, use random selection
            if not meal_names:
                for target_date in dates:
                    for meal_type in meal_types:
                        tasks.append({
                            "meal_name": None,  # Will trigger random selection
                            "target_date": target_date,
                            "meal_type": meal_type,
                            "is_random": True
                        })
            else:
                # Distribute specified meals across dates/types
                for i, target_date in enumerate(dates):
                    meal_name = meal_names[i % len(meal_names)] if meal_names else None
                    meal_type = meal_types[i % len(meal_types)]
                    
                    tasks.append({
                        "meal_name": meal_name,
                        "target_date": target_date,
                        "meal_type": meal_type,
                        "is_random": not meal_name
                    })
        
        # Execute batch using orchestrator
        result = await self.orchestrator.execute_batch_schedule(tasks, available_meals)
        
        return self._build_batch_response(result, len(tasks))
    
    async def _handle_fill_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Handle fill schedule requests (random meal selection)"""
        entities = context.entities
        dates = entities.get("dates", [date.today().isoformat()])
        meal_types = entities.get("meal_types", ["dinner"])
        
        # Generate random scheduling tasks
        tasks = []
        for target_date in dates:
            for meal_type in meal_types:
                tasks.append({
                    "meal_name": None,  # Triggers random selection
                    "target_date": target_date,
                    "meal_type": meal_type,
                    "is_random": True
                })
        
        result = await self.orchestrator.execute_batch_schedule(tasks, available_meals)
        return self._build_batch_response(result, len(tasks))
    
    async def _handle_clear_schedule(self, context: LLMRequestContext) -> AIResponse:
        """Handle clear schedule requests"""
        entities = context.entities
        
        # Determine date range from entities
        if entities.get("dates"):
            if len(entities["dates"]) == 1:
                # Single date
                target_date = entities["dates"][0]
                result = await self.orchestrator.clear_schedule(
                    start_date=target_date,
                    end_date=target_date
                )
            else:
                # Date range
                start_date = min(entities["dates"])
                end_date = max(entities["dates"])
                result = await self.orchestrator.clear_schedule(
                    start_date=start_date,
                    end_date=end_date
                )
        else:
            # Check for temporal references
            temporal_refs = entities.get("temporal_references", [])
            if any("week" in ref.lower() for ref in temporal_refs):
                result = await self.orchestrator.clear_schedule(date_range="week")
            elif any("month" in ref.lower() for ref in temporal_refs):
                result = await self.orchestrator.clear_schedule(date_range="month")
            else:
                # Default to today
                today = date.today().isoformat()
                result = await self.orchestrator.clear_schedule(
                    start_date=today,
                    end_date=today
                )
        
        if result["success"]:
            cleared_count = result["cleared_count"]
            
            if cleared_count == 0:
                response = "Your schedule is already clear!"
            elif cleared_count == 1:
                response = "I've cleared 1 scheduled meal."
            else:
                response = f"I've cleared {cleared_count} scheduled meals."
            
            return AIResponse(
                conversational_response=response,
                actions=[],
                model_used="enhanced_meal_agent"
            )
        else:
            return AIResponse(
                conversational_response=f"Sorry, I couldn't clear your schedule: {result.get('error', 'Unknown error')}",
                actions=[],
                model_used="enhanced_meal_agent"
            )
    
    async def _handle_view_schedule(self, context: LLMRequestContext) -> AIResponse:
        """Handle view schedule requests"""
        # This would integrate with existing schedule viewing logic
        # For now, return a placeholder response
        return AIResponse(
            conversational_response="I'd show you your schedule here, but that feature needs integration with the existing view logic.",
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _handle_list_meals(self, available_meals: List[str]) -> AIResponse:
        """Handle list meals requests"""
        if not available_meals:
            return AIResponse(
                conversational_response="You don't have any saved meals yet.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        if len(available_meals) <= 10:
            meal_list = ", ".join(available_meals)
            response = f"Here are your saved meals: {meal_list}."
        else:
            # Show first 10 and indicate there are more
            meal_list = ", ".join(available_meals[:10])
            response = f"Here are some of your saved meals: {meal_list}... and {len(available_meals) - 10} more."
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    def _build_batch_response(self, result: Dict[str, Any], total_requested: int) -> AIResponse:
        """Build response for batch operations"""
        if result["success"] and result["schedules"]:
            scheduled_count = result["scheduled_count"]
            schedules = result["schedules"]
            
            if scheduled_count == 1:
                schedule = schedules[0]
                natural_date = self.response_builder.format_natural_date(schedule['date'])
                response = f"I've scheduled {schedule['meal_name']} for {schedule['meal_type']} {natural_date}!"
                
                # Include action for single schedule
                actions = [AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters=schedule
                )]
            else:
                # Multiple schedules - provide summary
                response = f"I've scheduled {scheduled_count} meals for you:\n"
                for schedule in schedules[:5]:  # Limit to first 5 for readability
                    natural_date = self.response_builder.format_natural_date(schedule['date'])
                    response += f"• {schedule['meal_name']} ({schedule['meal_type']}) {natural_date}\n"
                
                if len(schedules) > 5:
                    response += f"... and {len(schedules) - 5} more meals"
                
                # No individual actions for batch operations (per user feedback)
                actions = []
            
            # Add error information if some tasks failed
            if result["errors"]:
                response += f"\n\nNote: {len(result['errors'])} tasks had issues."
                for error in result["errors"][:2]:
                    if "meal_name" in error and "reason" in error:
                        response += f"\n• {error['meal_name']}: {error['reason']}"
            
            return AIResponse(
                conversational_response=response.strip(),
                actions=actions,
                model_used="enhanced_meal_agent"
            )
        else:
            # Handle complete failure
            error_msg = "I couldn't schedule any meals."
            if result["errors"]:
                first_error = result["errors"][0]
                error_msg += f" Issue: {first_error.get('reason', 'Unknown error')}"
            
            return AIResponse(
                conversational_response=error_msg,
                actions=[],
                model_used="enhanced_meal_agent"
            )