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
from datetime import date, datetime, timedelta
from uuid import uuid4
import random

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from models.scheduled_meal import ScheduledMeal, MealOccasion
from models.meal import Meal
from storage.local_storage import LocalStorage
from ..core.llm_intent_processor import LLMIntentProcessor, LLMRequestContext, IntentType
from ..utils.response_utils import ResponseBuilder
from ..utils.meal_utils import MealUtils
from ..utils.task_queue import TaskQueueManager, TaskDetails, TaskType, TaskStatus


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
        self.task_queue = TaskQueueManager()  # LLM-first task persistence
    
    async def process(
        self, 
        message: ChatMessage, 
        available_meals: List[str],
        conversation_history: Optional[List[Dict]] = None,
        user_id: str = "default"
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
            # STEP 1: Check if this is a new multi-task request and parse it FIRST
            if self._is_new_multi_task_request(message.content, user_id):
                # Parse and store individual tasks in queue immediately
                self._parse_and_queue_multi_task_request(user_id, message.content, available_meals)
            
            # STEP 2: Get current task context (either new or existing)
            task_queue_summary = self.task_queue.get_queue_summary(user_id)
            current_task = self.task_queue.get_current_task(user_id)
            
            # STEP 3: Get current schedule for context
            current_schedule = self._get_schedule_context()
            
            # Process the user's message with task queue context
            context = await self.llm_intent.understand_request(
                message.content, 
                available_meals,
                current_schedule=current_schedule,
                conversation_history=conversation_history,
                task_queue_state=task_queue_summary
            )
            
            # Handle requests based on LLM analysis - Direct execution
            if context.needs_clarification:
                return self._create_clarification_response(context, user_id)
            
            # Route to appropriate direct handler with user_id
            if context.intent_type == IntentType.DIRECT_SCHEDULE:
                return await self._direct_schedule_meal(context, available_meals, conversation_history, user_id)
            elif context.intent_type == IntentType.BATCH_SCHEDULE:
                return await self._direct_batch_schedule(context, available_meals)
            elif context.intent_type == IntentType.FILL_SCHEDULE:
                return await self._direct_fill_schedule(context, available_meals)
            elif context.intent_type == IntentType.AUTONOMOUS_SCHEDULE:
                return await self._direct_autonomous_schedule(context, available_meals)
            elif context.intent_type == IntentType.RESCHEDULE_MEAL:
                return await self._direct_reschedule_meal(context, available_meals)
            elif context.intent_type == IntentType.CLEAR_SCHEDULE:
                return await self._direct_clear_schedule(context)
            elif context.intent_type == IntentType.VIEW_SCHEDULE:
                return await self._direct_view_schedule(context)
            elif context.intent_type == IntentType.LIST_MEALS:
                return await self._direct_list_meals(conversation_history, context, user_id)
            elif context.intent_type == IntentType.CONVERSATION_CLOSURE:
                return self._create_closure_response(context)
            else:
                return self._create_unknown_response(context)
                
        except Exception as e:
            return self.response_builder.unexpected_error(str(e))
    
    def _create_clarification_response(self, context: LLMRequestContext, user_id: str = "default") -> AIResponse:
        """Create response requesting clarification"""
        
        # Check if clarification includes suggestions that should be stored for follow-up
        clarification_msg = context.clarification_question or ""
        
        # Check for meal suggestions in clarification messages
        suggestions_found = False
        
        # Pattern 1: "How about X or Y instead?" (original scheduling suggestions)
        if "how about" in clarification_msg.lower() and "instead" in clarification_msg.lower():
            suggestions = self._extract_suggestions_from_clarification(clarification_msg)
            suggestions_found = True
        
        # Pattern 2: "Here are some options: X, Y, Z!" (LIST_MEALS responses)
        elif "here are" in clarification_msg.lower() and "options" in clarification_msg.lower():
            suggestions = self._extract_suggestions_from_clarification(clarification_msg)
            suggestions_found = True
        
        else:
            suggestions = []
        
        # Suggestions are now handled via conversation history instead of context manager
        
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
    
    def _create_closure_response(self, context: LLMRequestContext) -> AIResponse:
        """Create response for conversation closure"""
        closure_msg = context.clarification_question or "Awesome! I'm always here to help!"
        
        return AIResponse(
            conversational_response=closure_msg,
            actions=[],
            model_used="enhanced_meal_agent",
            # Signal to clear conversation history
            metadata={"clear_conversation": True}
        )
    
    async def _direct_schedule_meal(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str],
        conversation_history: Optional[List[Dict]] = None,
        user_id: str = "default"
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
                # Generate context-aware suggestions with 7-meal maximum
                occasion_context = self._determine_occasion_context(conversation_history)
                
                # Filter suggestions by context if available
                suggestion_meals = meals
                if occasion_context:
                    context_filtered = [m for m in meals if m.occasion.value == occasion_context]
                    if context_filtered:
                        suggestion_meals = context_filtered
                
                # Apply 7-meal maximum and get suggestions
                max_suggestions = min(3, len(suggestion_meals))
                suggestions = [m.name for m in suggestion_meals[:max_suggestions]]
                
                error_msg = f"You don't have {meal_name} saved."
                
                if suggestions:
                    if len(suggestions) > 1:
                        error_msg += f" How about {', '.join(suggestions[:-1])} or {suggestions[-1]} instead?"
                    else:
                        error_msg += f" How about {suggestions[0]} instead?"
                    
                    # Suggestions are now handled via conversation history instead of context manager
                
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
        
        # Build response - check for task queue continuation first
        task_queue_summary = self.task_queue.get_queue_summary(user_id)
        if task_queue_summary.get('has_active_request', False):
            # Use task queue completion logic for systematic multi-task handling
            response = self._complete_current_task_and_continue(
                user_id, meal_obj.name, target_date, meal_type
            )
        elif context.clarification_question:
            # Use LLM's response for other clarification scenarios
            response = context.clarification_question
        else:
            # Default single-task response
            natural_date = self.response_builder.format_natural_date(target_date)
            response = f"I've scheduled {meal_obj.name} for {meal_type} {natural_date}!"
            
            # Add closure question for single operations
            response += "\n\nDo you need any other schedule-related assistance?"
        
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
    
    async def _direct_autonomous_schedule(
        self, 
        context: LLMRequestContext, 
        available_meals: List[str]
    ) -> AIResponse:
        """Direct autonomous meal scheduling based on user preferences"""
        entities = context.entities
        dates = entities.get("dates", [date.today().isoformat()])
        meal_types = entities.get("meal_types", ["dinner"])
        
        # Load meals - Direct storage call
        meals = self.storage.load_meals()
        
        if not meals:
            return AIResponse(
                conversational_response="No meals available to choose from.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        scheduled_meals = []
        
        # Use preference-based recommendations for autonomous scheduling
        for i, target_date in enumerate(dates):
            meal_type = meal_types[i % len(meal_types)]
            
            # Get recommended meals based on user preferences
            recommended_meals = self.storage.get_recommended_meals(occasion=meal_type, count=1)
            
            if recommended_meals:
                meal_name = recommended_meals[0]
                # Find the actual meal object
                meal_obj = None
                for meal in meals:
                    if meal.name == meal_name:
                        meal_obj = meal
                        break
                
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
        
        # Build response for autonomous scheduling
        if not scheduled_meals:
            return AIResponse(
                conversational_response="I couldn't schedule any meals autonomously.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        if len(scheduled_meals) == 1:
            schedule = scheduled_meals[0]
            natural_date = self.response_builder.format_natural_date(schedule['date'])
            response = f"I've chosen {schedule['meal_name']} for your {schedule['meal_type']} {natural_date}!"
        else:
            response = f"I've chosen {len(scheduled_meals)} meals for you:\n"
            for schedule in scheduled_meals:
                natural_date = self.response_builder.format_natural_date(schedule['date'])
                response += f"• {schedule['meal_name']} ({schedule['meal_type']}) {natural_date}\n"
        
        # Add closure question
        response += "\n\nDo you need any other schedule-related assistance?"
        
        return AIResponse(
            conversational_response=response.strip(),
            actions=[],  # Actions already completed
            model_used="enhanced_meal_agent"
        )
    
    async def _direct_reschedule_meal(self, context: LLMRequestContext, available_meals: List[str]) -> AIResponse:
        """Direct meal rescheduling - move existing meal from one date to another"""
        entities = context.entities
        
        # If LLM needs clarification, return it directly
        if context.needs_clarification:
            return AIResponse(
                conversational_response=context.clarification_question or "I need more information to reschedule your meal.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        # Extract source and destination dates from entities
        dates = entities.get("dates", [])
        meal_types = entities.get("meal_types", ["dinner"])  # Default to dinner if not specified
        
        if len(dates) < 2:
            return AIResponse(
                conversational_response="I need both the source and destination dates to reschedule a meal. Please specify where to move the meal from and to.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        source_date = datetime.fromisoformat(dates[0]).date()
        dest_date = datetime.fromisoformat(dates[1]).date()
        meal_occasion = meal_types[0] if meal_types else "dinner"
        
        # Map meal_type to MealOccasion enum
        occasion_mapping = {
            "breakfast": MealOccasion.breakfast,
            "lunch": MealOccasion.lunch, 
            "dinner": MealOccasion.dinner,
            "snack": MealOccasion.snack
        }
        occasion = occasion_mapping.get(meal_occasion.lower(), MealOccasion.dinner)
        
        # Find the meal to reschedule on the source date
        scheduled_meals = self.storage.get_scheduled_meals_by_date(source_date)
        
        # Filter by occasion if specified
        target_meals = [meal for meal in scheduled_meals if meal.occasion == occasion]
        
        if not target_meals:
            # No meals found on source date for that occasion
            natural_source_date = self.response_builder.format_natural_date(source_date.isoformat())
            if len(scheduled_meals) > 0:
                # There are meals on that date, just not for that occasion
                return AIResponse(
                    conversational_response=f"You don't have any {meal_occasion} scheduled for {natural_source_date}. What meals would you like me to help you reschedule?",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
            else:
                # No meals at all on that date
                return AIResponse(
                    conversational_response=f"You don't have any meals scheduled for {natural_source_date}. What would you like me to help you with?",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
        
        elif len(target_meals) > 1:
            # Multiple meals found, need clarification
            meals = self.storage.load_meals()
            meal_lookup = {meal.id: meal for meal in meals}
            
            meal_list = []
            for scheduled_meal in target_meals:
                meal_obj = meal_lookup.get(scheduled_meal.meal_id)
                if meal_obj:
                    meal_list.append(meal_obj.name)
            
            natural_source_date = self.response_builder.format_natural_date(source_date.isoformat())
            meal_options = "\n".join(f"• {meal}" for meal in meal_list)
            
            return AIResponse(
                conversational_response=f"You have multiple {meal_occasion} meals scheduled for {natural_source_date}. Which one would you like to reschedule?\n{meal_options}",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        else:
            # Exactly one meal found - proceed with rescheduling
            meal_to_reschedule = target_meals[0]
            
            # Get meal details for response
            meals = self.storage.load_meals()
            meal_obj = None
            for meal in meals:
                if meal.id == meal_to_reschedule.meal_id:
                    meal_obj = meal
                    break
            
            if not meal_obj:
                return AIResponse(
                    conversational_response="I couldn't find the meal details. Something went wrong.",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
            
            # Check if destination date/occasion already has a meal
            dest_scheduled_meals = self.storage.get_scheduled_meals_by_date(dest_date)
            dest_conflict = [meal for meal in dest_scheduled_meals if meal.occasion == occasion]
            
            if dest_conflict:
                # There's already a meal scheduled at the destination
                conflict_meal = dest_conflict[0]
                conflict_meal_obj = None
                for meal in meals:
                    if meal.id == conflict_meal.meal_id:
                        conflict_meal_obj = meal
                        break
                
                natural_dest_date = self.response_builder.format_natural_date(dest_date.isoformat())
                conflict_name = conflict_meal_obj.name if conflict_meal_obj else "a meal"
                
                return AIResponse(
                    conversational_response=f"You already have {conflict_name} scheduled for {meal_occasion} on {natural_dest_date}. Would you like me to replace it with {meal_obj.name}?",
                    actions=[],
                    model_used="enhanced_meal_agent"
                )
            
            # Perform the rescheduling - remove from source and add to destination
            # Remove from source date
            self.storage.delete_scheduled_meal(meal_to_reschedule.id)
            
            # Add to destination date
            new_scheduled_meal = ScheduledMeal(
                meal_id=meal_obj.id,
                date=dest_date,
                occasion=occasion
            )
            saved_meal = self.storage.add_scheduled_meal(new_scheduled_meal)
            
            # Build success response
            natural_source_date = self.response_builder.format_natural_date(source_date.isoformat())
            natural_dest_date = self.response_builder.format_natural_date(dest_date.isoformat())
            
            response = f"I've rescheduled {meal_obj.name} from {natural_source_date}'s {meal_occasion} to {natural_dest_date}'s {meal_occasion}!"
            response += "\n\nDo you need any other schedule-related assistance?"
            
            return AIResponse(
                conversational_response=response,
                actions=[],  # Action already completed
                model_used="enhanced_meal_agent"
            )

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
        
        # Add closure question for action operations
        if cleared_count > 0:
            response += "\n\nDo you need any other schedule-related assistance?"
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _direct_view_schedule(self, context: LLMRequestContext) -> AIResponse:
        """Direct schedule viewing - no tool abstraction"""
        entities = context.entities
        
        # Check for temporal references first (month, week, etc.)
        temporal_refs = entities.get("temporal_references", [])
        
        if any("month" in ref.lower() for ref in temporal_refs):
            # View entire month
            from datetime import date as date_module
            today = date_module.today()
            start_date = today.replace(day=1)
            
            # Get last day of month
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            
            # Get all meals in the month range
            all_scheduled = self.storage.load_scheduled_meals()
            month_meals = []
            
            # Also load meal details for display
            meals = self.storage.load_meals()
            meal_lookup = {meal.id: meal for meal in meals}
            
            for scheduled_meal in all_scheduled:
                if start_date <= scheduled_meal.date <= end_date:
                    meal_obj = meal_lookup.get(scheduled_meal.meal_id)
                    if meal_obj:
                        month_meals.append({
                            'date': scheduled_meal.date.isoformat(),
                            'meal_name': meal_obj.name,
                            'meal_occasion': scheduled_meal.occasion
                        })
            
            if not month_meals:
                response = f"No meals scheduled for {today.strftime('%B %Y')}."
            else:
                response = f"Here's what's scheduled for {today.strftime('%B %Y')}:\n"
                # Group by date
                meals_by_date = {}
                for meal in month_meals:
                    meal_date = meal['date']
                    if meal_date not in meals_by_date:
                        meals_by_date[meal_date] = []
                    meals_by_date[meal_date].append(meal)
                
                # Sort dates and display
                for meal_date in sorted(meals_by_date.keys()):
                    date_obj = datetime.fromisoformat(meal_date).date()
                    response += f"\n{date_obj.strftime('%A, %B %d')}:\n"
                    for meal in meals_by_date[meal_date]:
                        # meal_occasion is already a MealOccasion enum
                        try:
                            occasion_name = meal['meal_occasion'].value.replace('_', ' ').title()
                        except AttributeError:
                            # If it's already a string, use it directly
                            occasion_name = str(meal['meal_occasion']).replace('_', ' ').title()
                        response += f"  • {meal['meal_name']} ({occasion_name})\n"
        
        elif any("week" in ref.lower() for ref in temporal_refs):
            # View current week
            from datetime import date as date_module
            today = date_module.today()
            
            # Calculate week boundaries (Sunday to Saturday)
            days_since_sunday = (today.weekday() + 1) % 7  # Convert Monday=0 to Sunday=0
            week_start = today - timedelta(days=days_since_sunday)
            week_end = week_start + timedelta(days=6)
            
            # Get all meals in the week range
            all_scheduled = self.storage.load_scheduled_meals()
            week_meals = []
            
            # Also load meal details for display
            meals = self.storage.load_meals()
            meal_lookup = {meal.id: meal for meal in meals}
            
            for scheduled_meal in all_scheduled:
                if week_start <= scheduled_meal.date <= week_end:
                    meal_obj = meal_lookup.get(scheduled_meal.meal_id)
                    if meal_obj:
                        week_meals.append({
                            'date': scheduled_meal.date.isoformat(),
                            'meal_name': meal_obj.name,
                            'meal_occasion': scheduled_meal.occasion,
                            'weekday': scheduled_meal.date.strftime('%A')
                        })
            
            if not week_meals:
                response = f"No meals scheduled for this week ({week_start.strftime('%B %d')} - {week_end.strftime('%B %d')})."
            else:
                response = f"Here's what's scheduled for this week ({week_start.strftime('%B %d')} - {week_end.strftime('%B %d')}):\n"
                
                # Group by date
                meals_by_date = {}
                for meal in week_meals:
                    meal_date = meal['date']
                    if meal_date not in meals_by_date:
                        meals_by_date[meal_date] = []
                    meals_by_date[meal_date].append(meal)
                
                # Sort dates and display
                for meal_date in sorted(meals_by_date.keys()):
                    date_obj = datetime.fromisoformat(meal_date).date()
                    response += f"\n{date_obj.strftime('%A, %B %d')}:\n"
                    for meal in meals_by_date[meal_date]:
                        # meal_occasion is already a MealOccasion enum value
                        occasion_name = str(meal['meal_occasion']).replace('_', ' ').title()
                        response += f"  • {meal['meal_name']} ({occasion_name})\n"
        
        else:
            # Get specific date from entities or default to today
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
                
                # Load meal details to get names
                meals = self.storage.load_meals()
                meal_lookup = {meal.id: meal for meal in meals}
                
                for scheduled_meal in scheduled_meals:
                    meal_obj = meal_lookup.get(scheduled_meal.meal_id)
                    if meal_obj:
                        # Handle both enum and string occasion types
                        if hasattr(scheduled_meal.occasion, 'value'):
                            occasion_name = scheduled_meal.occasion.value.replace('_', ' ').title()
                        else:
                            occasion_name = str(scheduled_meal.occasion).replace('_', ' ').title()
                        response += f"• {meal_obj.name} ({occasion_name})\n"
        
        return AIResponse(
            conversational_response=response.strip(),
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    async def _direct_list_meals(self, conversation_history: Optional[List[Dict]] = None, context: Optional[LLMRequestContext] = None, user_id: str = "default") -> AIResponse:
        """LLM-driven meal listing with intelligent suggestions"""
        
        # Check if LLM provided a clarification question (intelligent response)
        if context and context.clarification_question:
            # Extract suggestions from the LLM response and store them for follow-up
            suggestions = self._extract_suggestions_from_clarification(context.clarification_question)
            
            # Suggestions are now handled via conversation history instead of context manager
            
            # Use the LLM's intelligent response instead of hard-coded logic
            return AIResponse(
                conversational_response=context.clarification_question,
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        # Fallback: If LLM didn't provide response, use basic meal list
        meals = self.storage.load_meals()
        
        if not meals:
            return AIResponse(
                conversational_response="You don't have any saved meals yet.",
                actions=[],
                model_used="enhanced_meal_agent"
            )
        
        # Simple fallback response (should rarely be used)
        meal_names = [meal.name for meal in meals[:3]]  # Max 3 for fallback
        meal_list = ", ".join(meal_names)
        response = f"Here are some options: {meal_list}."
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    def _determine_occasion_context(self, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """Determine meal occasion context from conversation history"""
        if not conversation_history:
            return None
        
        # Look through recent conversation turns for occasion mentions
        occasions = ["breakfast", "lunch", "dinner", "snack"]
        
        # Check last few turns for occasion context
        for turn in conversation_history[-3:]:  # Check last 3 turns
            user_msg = turn.get("user", "").lower()
            agent_msg = turn.get("agent", "").lower()
            
            for occasion in occasions:
                if occasion in user_msg or occasion in agent_msg:
                    return occasion
        
        # If no explicit occasion found, try to infer from meal names mentioned
        # Common meal patterns that suggest dinner (most common default)
        dinner_indicators = ["pizza", "pasta", "steak", "chicken", "beef", "pork", "salmon", "lasagna"]
        breakfast_indicators = ["pancakes", "eggs", "cereal", "oatmeal", "bagel", "toast", "waffle"]
        lunch_indicators = ["sandwich", "salad", "soup", "wrap", "burger"]
        
        for turn in conversation_history[-2:]:  # Check last 2 turns for meal mentions
            user_msg = turn.get("user", "").lower()
            
            # Check for dinner indicators
            if any(indicator in user_msg for indicator in dinner_indicators):
                return "dinner"
            # Check for breakfast indicators  
            elif any(indicator in user_msg for indicator in breakfast_indicators):
                return "breakfast"
            # Check for lunch indicators
            elif any(indicator in user_msg for indicator in lunch_indicators):
                return "lunch"
        
        # Default to dinner as it's the most common meal people schedule
        # Only return default if there's been at least some meal-related conversation
        meal_related_words = ["schedule", "meal", "eat", "cook", "available"]
        for turn in conversation_history[-2:]:
            user_msg = turn.get("user", "").lower()
            if any(word in user_msg for word in meal_related_words):
                return "dinner"  # Default context
        
        return None
    
    def _get_previously_suggested_meals(self, conversation_history: Optional[List[Dict]] = None) -> List[str]:
        """Extract previously suggested meals from conversation history"""
        if not conversation_history:
            return []
        
        suggested_meals = []
        
        # Look for "How about" patterns in agent responses
        for turn in conversation_history[-3:]:  # Check last 3 turns
            agent_msg = turn.get("agent", "")
            
            # Pattern: "How about X or Y instead?" or "How about X instead?"
            if "how about" in agent_msg.lower():
                # Extract meal names between "How about" and "instead"
                import re
                pattern = r"how about (.+?)(?:instead|\?)"
                match = re.search(pattern, agent_msg.lower())
                if match:
                    suggestions_text = match.group(1)
                    # Split on "or", "and", and commas
                    suggestions = re.split(r'\s*(?:,\s*|\s+or\s+|\s+and\s+)\s*', suggestions_text)
                    # Clean up each suggestion (remove articles, punctuation)
                    for suggestion in suggestions:
                        cleaned = re.sub(r'^(a|an|the)\s+', '', suggestion.strip(' ,.?!'))
                        if cleaned and len(cleaned) > 1:  # Avoid single letters
                            # Capitalize properly for matching
                            cleaned = ' '.join(word.capitalize() for word in cleaned.split())
                            suggested_meals.append(cleaned)
        
        return list(set(suggested_meals))  # Remove duplicates
    
    def _extract_suggestions_from_clarification(self, clarification_msg: str) -> List[str]:
        """Extract meal suggestions from clarification message"""
        import re
        
        # Pattern 1: "How about X or Y instead?" (original format)
        pattern1 = r"how about (.+?)(?:instead|\?)"
        match1 = re.search(pattern1, clarification_msg.lower())
        
        if match1:
            suggestions_text = match1.group(1)
        else:
            # Pattern 2: "Here are some options: X, Y, Z!" (old LIST_MEALS format - still supported)
            pattern2 = r"here are (?:some )?(?:other )?options?: (.+?)(?:\!|\?|$)"
            match2 = re.search(pattern2, clarification_msg.lower())
            
            if match2:
                suggestions_text = match2.group(1)
            else:
                # Pattern 3: "We could also go with X, Y, or Z if you'd like?" (new conversational format)
                pattern3 = r"(?:we could (?:also )?go with|you (?:might|could) (?:enjoy|like|try)|how about trying) (.+?)(?:\?|!|if you|$)"
                match3 = re.search(pattern3, clarification_msg.lower())
                
                if match3:
                    suggestions_text = match3.group(1)
                else:
                    return []
        
        # Split on "or", "and", and commas, handling "maybe" and other conversational words
        suggestions = re.split(r'\s*(?:,\s*|\s+or\s+(?:maybe\s+)?|\s+and\s+|\s+maybe\s+)\s*', suggestions_text)
        
        # Clean up each suggestion (remove articles, punctuation)
        cleaned_suggestions = []
        for suggestion in suggestions:
            cleaned = re.sub(r'^(a|an|the)\s+', '', suggestion.strip(' ,.?!'))
            if cleaned and len(cleaned) > 1:  # Avoid single letters
                # Capitalize properly for matching
                cleaned = ' '.join(word.capitalize() for word in cleaned.split())
                cleaned_suggestions.append(cleaned)
        
        return cleaned_suggestions
    
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
        
        # Add closure question if any meals were scheduled
        if scheduled_count > 0:
            response += "\n\nDo you need any other schedule-related assistance?"
        
        return AIResponse(
            conversational_response=response.strip(),
            actions=actions,
            model_used="enhanced_meal_agent"
        )
    
    def _get_schedule_context(self) -> Dict[str, Any]:
        """Get current schedule context for LLM analysis"""
        try:
            # Get today's and next few days' schedules for context
            today = date.today()
            schedule_context = {}
            
            for days_ahead in range(7):  # Next 7 days
                check_date = today + timedelta(days=days_ahead)
                scheduled_meals = self.storage.get_scheduled_meals_by_date(check_date)
                
                if scheduled_meals:
                    # Load meal details
                    meals = self.storage.load_meals()
                    meal_lookup = {meal.id: meal for meal in meals}
                    
                    day_meals = []
                    for scheduled_meal in scheduled_meals:
                        meal_obj = meal_lookup.get(scheduled_meal.meal_id)
                        if meal_obj:
                            day_meals.append({
                                "meal_name": meal_obj.name,
                                "occasion": scheduled_meal.occasion.value if hasattr(scheduled_meal.occasion, 'value') else str(scheduled_meal.occasion)
                            })
                    
                    if day_meals:
                        schedule_context[check_date.isoformat()] = day_meals
            
            return schedule_context
            
        except Exception as e:
            # Return empty context if there's an error
            return {}

    # === TASK QUEUE MANAGEMENT METHODS ===
    
    def _is_new_multi_task_request(self, request_text: str, user_id: str) -> bool:
        """
        Check if this is a NEW multi-task request (not a clarification for existing tasks)
        
        Args:
            request_text: User's request text
            user_id: User identifier
            
        Returns:
            True if this is a new multi-task request
        """
        # Check if user already has pending tasks (then this is likely a clarification)
        existing_tasks = self.task_queue.get_pending_tasks(user_id)
        if existing_tasks:
            return False
        
        # Check for multi-task patterns in the request
        multi_task_indicators = [
            " and ", " then ", " also ", " plus ",
            "dinner.*breakfast", "breakfast.*lunch", "lunch.*dinner"
        ]
        
        request_lower = request_text.lower()
        return any(indicator in request_lower for indicator in multi_task_indicators)
    
    def _parse_and_queue_multi_task_request(self, user_id: str, request_text: str, available_meals: List[str]):
        """
        Parse multi-task request and create individual tasks in queue
        
        Args:
            user_id: User identifier
            request_text: Original multi-task request
            available_meals: Available meal names
        """
        # Simple parsing for common patterns
        # "Schedule dinner tomorrow and breakfast Tuesday" -> 
        # ["schedule dinner tomorrow", "schedule breakfast Tuesday"]
        
        tasks = []
        
        # Pattern: "Schedule X and Y"
        if " and " in request_text.lower():
            parts = request_text.lower().split(" and ")
            base_action = "schedule"
            
            for i, part in enumerate(parts):
                part = part.strip()
                if i == 0:
                    # First part: "Schedule dinner tomorrow" 
                    tasks.append(part)
                else:
                    # Subsequent parts: "breakfast Tuesday" -> "schedule breakfast Tuesday"
                    if not part.startswith("schedule"):
                        part = f"{base_action} {part}"
                    tasks.append(part)
        
        # Create TaskDetails for each parsed task
        for task_text in tasks:
            # Extract meal occasion and date from task text
            occasion = self._extract_meal_occasion(task_text)
            date_part = self._extract_date_reference(task_text)
            
            # Convert date reference to actual date
            actual_date = self._convert_date_reference_to_iso(date_part)
            
            task_details = TaskDetails(
                task_type=TaskType.SCHEDULE_MEAL,
                meal_occasion=occasion,
                date=actual_date,
                original_request_part=date_part,
                clarification_needed=True  # Always need meal selection
            )
            
            self.task_queue.add_task(user_id, task_details)
    
    def _extract_meal_occasion(self, task_text: str) -> str:
        """Extract meal occasion from task text"""
        occasions = ["breakfast", "lunch", "dinner", "snack"]
        task_lower = task_text.lower()
        
        for occasion in occasions:
            if occasion in task_lower:
                return occasion
        return "dinner"  # default
    
    def _extract_date_reference(self, task_text: str) -> str:
        """Extract date reference from task text"""
        # Simple extraction - look for common date patterns
        date_patterns = ["tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        task_lower = task_text.lower()
        
        for pattern in date_patterns:
            if pattern in task_lower:
                return pattern
        return "today"  # default
    
    def _convert_date_reference_to_iso(self, date_reference: str) -> str:
        """Convert date reference (like 'tuesday') to ISO date format"""
        from datetime import date, timedelta
        
        today = date.today()
        date_ref_lower = date_reference.lower()
        
        if date_ref_lower == "today":
            return today.isoformat()
        elif date_ref_lower == "tomorrow":
            return (today + timedelta(days=1)).isoformat()
        else:
            # Handle weekday names
            weekdays = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }
            
            if date_ref_lower in weekdays:
                target_weekday = weekdays[date_ref_lower]
                current_weekday = today.weekday()
                
                # Calculate days until target weekday
                days_ahead = (target_weekday - current_weekday) % 7
                if days_ahead == 0:  # If it's the same weekday, assume next week
                    days_ahead = 7
                
                target_date = today + timedelta(days=days_ahead)
                return target_date.isoformat()
        
        # Fallback to tomorrow
        return (today + timedelta(days=1)).isoformat()
    
    def _create_task_queue_from_context(self, user_id: str, original_request: str, context: LLMRequestContext):
        """
        Create task queue from LLM analysis of multi-task request
        
        Args:
            user_id: User identifier
            original_request: Original request text
            context: LLM analysis context
        """
        # Create task queue from entities
        task_ids = self.task_queue.parse_multi_task_request(
            user_id=user_id,
            request_text=original_request,
            entities=context.entities
        )
        
        return task_ids
    
    def _complete_current_task_and_continue(self, user_id: str, meal_name: str, date: str, meal_type: str) -> str:
        """
        Complete current task and get next task clarification
        
        Args:
            user_id: User identifier
            meal_name: Meal that was scheduled
            date: Date scheduled
            meal_type: Meal occasion
            
        Returns:
            Clarification question for next task or completion message
        """
        current_task = self.task_queue.get_current_task(user_id)
        if current_task:
            # Update and complete current task
            self.task_queue.update_task(
                user_id, 
                current_task.task_id,
                meal_name=meal_name,
                status=TaskStatus.COMPLETED
            )
            self.task_queue.complete_task(user_id, current_task.task_id)
        
        # Check for next pending task
        next_task = self.task_queue.get_current_task(user_id)
        if next_task:
            # Format natural date for next task
            natural_date = self.response_builder.format_natural_date(next_task.date)
            occasion = next_task.meal_occasion or "meal"
            
            # Get meal suggestions for next task occasion
            meals = self.storage.load_meals()
            if occasion != "meal":
                # Handle both enum and string occasion values
                filtered_meals = []
                for meal in meals:
                    meal_occasion = meal.occasion.value if hasattr(meal.occasion, 'value') else str(meal.occasion)
                    if meal_occasion == occasion:
                        filtered_meals.append(meal)
            else:
                filtered_meals = meals
            suggestions = [meal.name for meal in filtered_meals[:3]]
            
            suggestion_text = "\n".join(f"• {meal}" for meal in suggestions)
            
            return f"I've scheduled {meal_name} for {self.response_builder.format_natural_date(date)}'s {meal_type}! Now, what {occasion} would you like for {natural_date}? Here are some suggestions from your meals:\n{suggestion_text}"
        else:
            # All tasks complete
            return f"I've scheduled {meal_name} for {self.response_builder.format_natural_date(date)}'s {meal_type}! All your requested meals have been scheduled. Do you need any other assistance?"