"""
Direct Processor - Phase 3 Migration: LLM + Direct Storage Architecture

This eliminates the entire tool abstraction layer:
- BaseTool (296 lines)
- ToolOrchestrator (281 lines)  
- Production Tools (460 lines)
- Tool registry, caching, metrics, retry logic

Total elimination: ~1037 lines of abstraction for simple CRUD operations
Result: Direct, efficient storage calls with LLM intelligence
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime
from uuid import uuid4
import random

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from models.scheduled_meal import ScheduledMeal, MealOccasion
from models.meal import Meal
from storage.local_storage import LocalStorage
from ..core.llm_intent_processor import LLMIntentProcessor, LLMRequestContext, IntentType
from ..utils.response_utils import ResponseBuilder
from ..utils.meal_utils import MealUtils


class DirectProcessor:
    """
    Phase 3: Direct storage processor - No tool abstractions, just LLM + Storage
    
    Eliminates 1000+ lines of tool abstraction overhead and directly calls
    storage methods based on LLM understanding.
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.llm_intent = LLMIntentProcessor()
        self.response_builder = ResponseBuilder()
        self.meal_utils = MealUtils()
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str]
    ) -> AIResponse:
        """
        Process any meal scheduling request using LLM + Direct Storage
        
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
            
            # Handle requests based on LLM analysis - Direct execution
            if context.needs_clarification:
                return self._create_clarification_response(context)
            
            # Route to appropriate direct handler
            if context.intent_type == IntentType.DIRECT_SCHEDULE:
                return await self._direct_schedule_meal(context, available_meals)
            elif context.intent_type == IntentType.BATCH_SCHEDULE:
                return await self._direct_batch_schedule(context, available_meals)
            elif context.intent_type == IntentType.FILL_SCHEDULE:
                return await self._direct_fill_schedule(context, available_meals)
            elif context.intent_type == IntentType.CLEAR_SCHEDULE:
                return await self._direct_clear_schedule(context)
            elif context.intent_type == IntentType.VIEW_SCHEDULE:
                return await self._direct_view_schedule(context)
            elif context.intent_type == IntentType.LIST_MEALS:
                return await self._direct_list_meals()
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
    
    async def _direct_schedule_meal(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Direct meal scheduling - no tool abstraction"""
        entities = context.entities
        
        # Get meal name from LLM analysis
        meal_name = None
        if entities.get("meal_names"):
            meal_name = entities["meal_names"][0]
        
        if not meal_name:
            return AIResponse(
                conversational_response="I couldn't identify which meal you want to schedule. Please specify a meal name.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        # Find exact meal match - Direct storage call
        meals = self.storage.load_meals()
        meal_obj = None
        
        for meal in meals:
            if meal.name.lower() == meal_name.lower():
                meal_obj = meal
                break
        
        if not meal_obj:
            # Try fuzzy matching
            meal_obj = self.meal_utils.find_meal_by_fuzzy_name(meal_name, meals)
            
            if not meal_obj:
                # Generate suggestions - Direct approach
                suggestions = [m.name for m in meals[:3]]  # Simple first 3
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
        
        # Get date and meal type from LLM entities
        target_date = entities.get("dates", [date.today().isoformat()])[0]
        meal_type = entities.get("meal_types", ["dinner"])[0]
        
        # Convert meal_type to MealOccasion enum
        occasion_mapping = {
            "breakfast": MealOccasion.breakfast,
            "lunch": MealOccasion.lunch, 
            "dinner": MealOccasion.dinner,
            "snack": MealOccasion.snack
        }
        occasion = occasion_mapping.get(meal_type.lower(), MealOccasion.dinner)
        
        # Create and save scheduled meal - Direct storage call
        scheduled_meal = ScheduledMeal(
            meal_id=meal_obj.id,
            date=datetime.fromisoformat(target_date).date(),
            occasion=occasion
        )
        
        # Direct storage save
        saved_meal = self.storage.add_scheduled_meal(scheduled_meal)
        
        # Build response
        natural_date = self.response_builder.format_natural_date(target_date)
        response = f"I've scheduled {meal_obj.name} for {meal_type} {natural_date}!"
        
        # Action already completed by direct storage - no need for iOS to process it
        # Keep action for debugging but mark as completed
        action = AIAction(
            type=ActionType.SCHEDULE_MEAL,
            parameters={
                "meal_name": meal_obj.name,
                "date": target_date,
                "meal_type": meal_type,
                "scheduled_meal_id": str(saved_meal.id),
                "status": "completed"  # Indicates action is already done
            }
        )
        
        return AIResponse(
            conversational_response=response,
            actions=[],  # Empty actions - meal already scheduled directly
            model_used="enhanced_meal_agent"
        )
    
    async def _direct_batch_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Direct batch scheduling - no tool orchestration"""
        entities = context.entities
        dates = entities.get("dates", [date.today().isoformat()])
        meal_types = entities.get("meal_types", ["dinner"])
        meal_names = entities.get("meal_names", [])
        
        # Load meals once - Direct storage call
        meals = self.storage.load_meals()
        
        scheduled_meals = []
        errors = []
        
        # Direct scheduling logic
        for i, target_date in enumerate(dates):
            meal_type = meal_types[i % len(meal_types)]
            
            # Determine meal to schedule
            if meal_names and i < len(meal_names):
                # Specific meal requested
                meal_name = meal_names[i]
                meal_obj = self._find_meal_direct(meal_name, meals)
            else:
                # Random meal selection - Direct approach
                meal_obj = random.choice(meals) if meals else None
            
            if meal_obj:
                # Create scheduled meal - Direct creation
                occasion_mapping = {
                    "breakfast": MealOccasion.breakfast,
                    "lunch": MealOccasion.lunch,
                    "dinner": MealOccasion.dinner,
                    "snack": MealOccasion.snack
                }
                occasion = occasion_mapping.get(meal_type.lower(), MealOccasion.dinner)
                
                scheduled_meal = ScheduledMeal(
                    meal_id=meal_obj.id,
                    date=datetime.fromisoformat(target_date).date(),
                    occasion=occasion
                )
                
                # Direct storage save
                saved_meal = self.storage.add_scheduled_meal(scheduled_meal)
                scheduled_meals.append({
                    "meal_name": meal_obj.name,
                    "date": target_date,
                    "meal_type": meal_type,
                    "scheduled_meal_id": str(saved_meal.id)
                })
            else:
                errors.append({
                    "meal_name": meal_names[i] if i < len(meal_names) else "Random",
                    "date": target_date,
                    "reason": f"Meal not found: {meal_names[i]}" if i < len(meal_names) else "No meals available"
                })
        
        # Build response
        return self._build_batch_response_direct(scheduled_meals, errors)
    
    async def _direct_fill_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Direct schedule filling with random meals"""
        entities = context.entities
        dates = entities.get("dates", [date.today().isoformat()])
        meal_types = entities.get("meal_types", ["dinner"])
        
        # Load meals - Direct storage call
        meals = self.storage.load_meals()
        
        if not meals:
            return AIResponse(
                conversational_response="No meals available to fill your schedule.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        scheduled_meals = []
        
        # Fill with random meals - Direct approach
        for target_date in dates:
            for meal_type in meal_types:
                meal_obj = random.choice(meals)
                
                # Map meal type to occasion
                occasion_mapping = {
                    "breakfast": MealOccasion.breakfast,
                    "lunch": MealOccasion.lunch,
                    "dinner": MealOccasion.dinner,
                    "snack": MealOccasion.snack
                }
                occasion = occasion_mapping.get(meal_type.lower(), MealOccasion.dinner)
                
                # Create and save - Direct storage
                scheduled_meal = ScheduledMeal(
                    meal_id=meal_obj.id,
                    date=datetime.fromisoformat(target_date).date(),
                    occasion=occasion
                )
                
                saved_meal = self.storage.add_scheduled_meal(scheduled_meal)
                scheduled_meals.append({
                    "meal_name": meal_obj.name,
                    "date": target_date,
                    "meal_type": meal_type,
                    "scheduled_meal_id": str(saved_meal.id)
                })
        
        return self._build_batch_response_direct(scheduled_meals, [])
    
    async def _direct_clear_schedule(self, context: LLMRequestContext) -> AIResponse:
        """Direct schedule clearing - no tool abstraction"""
        entities = context.entities
        
        # Determine date range from LLM entities - Direct approach
        start_date = None
        end_date = None
        date_range = None
        
        if entities.get("dates"):
            dates = entities["dates"]
            if len(dates) == 1:
                # Single date
                start_date = datetime.fromisoformat(dates[0]).date()
                end_date = start_date
            else:
                # Date range
                start_date = datetime.fromisoformat(min(dates)).date()
                end_date = datetime.fromisoformat(max(dates)).date()
        else:
            # Check temporal references for patterns
            temporal_refs = entities.get("temporal_references", [])
            if any("week" in ref.lower() for ref in temporal_refs):
                date_range = "week"
            elif any("month" in ref.lower() for ref in temporal_refs):
                date_range = "month"
            else:
                # Default to today
                start_date = date.today()
                end_date = start_date
        
        # Direct storage clear call
        cleared_count = self.storage.clear_schedule(
            date_range=date_range,
            start_date=start_date,
            end_date=end_date
        )
        
        # Build response
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
    
    async def _direct_view_schedule(self, context: LLMRequestContext) -> AIResponse:
        """Direct schedule viewing - no tool abstraction"""
        entities = context.entities
        
        # Get date from entities
        if entities.get("dates"):
            target_date_str = entities["dates"][0]
            target_date = datetime.fromisoformat(target_date_str).date()
        else:
            target_date = date.today()
        
        # Direct storage call to get scheduled meals
        scheduled_meals = self.storage.get_scheduled_meals_by_date(target_date)
        
        if not scheduled_meals:
            natural_date = self.response_builder.format_natural_date(target_date.isoformat())
            response = f"No meals scheduled for {natural_date}."
        else:
            natural_date = self.response_builder.format_natural_date(target_date.isoformat())
            response = f"Here's what's scheduled for {natural_date}:\n"
            
            for meal in scheduled_meals:
                occasion_name = meal.meal_occasion.value.replace('_', ' ').title()
                response += f"• {meal.meal_name} ({occasion_name})\n"
        
        return AIResponse(
            conversational_response=response.strip(),
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _direct_list_meals(self) -> AIResponse:
        """Direct meal listing - no tool abstraction"""
        # Direct storage call
        meals = self.storage.load_meals()
        
        if not meals:
            return AIResponse(
                conversational_response="You don't have any saved meals yet.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        meal_names = [meal.name for meal in meals]
        
        if len(meal_names) <= 10:
            meal_list = ", ".join(meal_names)
            response = f"Here are your saved meals: {meal_list}."
        else:
            # Show first 10 and indicate there are more
            meal_list = ", ".join(meal_names[:10])
            response = f"Here are some of your saved meals: {meal_list}... and {len(meal_names) - 10} more."
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    def _find_meal_direct(self, meal_name: str, meals: List[Meal]) -> Optional[Meal]:
        """Direct meal finding - no tool utilities"""
        # Exact match first
        for meal in meals:
            if meal.name.lower() == meal_name.lower():
                return meal
        
        # Simple fuzzy match
        for meal in meals:
            if meal_name.lower() in meal.name.lower() or meal.name.lower() in meal_name.lower():
                return meal
        
        return None
    
    def _build_batch_response_direct(self, scheduled_meals: List[Dict], errors: List[Dict]) -> AIResponse:
        """Build response for batch operations - direct approach"""
        scheduled_count = len(scheduled_meals)
        
        if scheduled_count == 0:
            error_msg = "I couldn't schedule any meals."
            if errors:
                error_msg += f" Issue: {errors[0]['reason']}"
            
            return AIResponse(
                conversational_response=error_msg,
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        if scheduled_count == 1:
            schedule = scheduled_meals[0]
            natural_date = self.response_builder.format_natural_date(schedule['date'])
            response = f"I've scheduled {schedule['meal_name']} for {schedule['meal_type']} {natural_date}!"
            
            # Meals already scheduled directly - no actions needed
            actions = []
        else:
            # Multiple schedules - provide summary
            response = f"I've scheduled {scheduled_count} meals for you:\n"
            for schedule in scheduled_meals[:5]:  # Limit to first 5 for readability
                natural_date = self.response_builder.format_natural_date(schedule['date'])
                response += f"• {schedule['meal_name']} ({schedule['meal_type']}) {natural_date}\n"
            
            if len(scheduled_meals) > 5:
                response += f"... and {len(scheduled_meals) - 5} more meals"
            
            # No individual actions for batch operations
            actions = []
        
        # Add error information if some tasks failed
        if errors:
            response += f"\n\nNote: {len(errors)} tasks had issues."
            for error in errors[:2]:
                response += f"\n• {error['meal_name']}: {error['reason']}"
        
        return AIResponse(
            conversational_response=response.strip(),
            actions=actions,
            model_used="enhanced_meal_agent"
        )