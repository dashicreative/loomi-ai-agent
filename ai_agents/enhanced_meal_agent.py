"""
Enhanced Meal Management Agent - Multi-task Scheduling Support

Handles complex requests like:
- "Schedule pizza and egg tacos for tomorrow"  
- "Schedule breakfast for the next 5 days based on my saved meals"
- "Pick some meals at random to schedule for Friday"

Built with robustness while preserving existing functionality.
"""

import asyncio
import random
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser
from pydantic import BaseModel, Field

from services.llm_service import llm_service
from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage


class ScheduleTask(BaseModel):
    """Individual scheduling task parsed from complex requests"""
    meal_name: Optional[str] = Field(None, description="Specific meal name or 'random' for random selection")
    target_date: str = Field(..., description="Target date in YYYY-MM-DD format")
    meal_type: str = Field(default="dinner", description="breakfast, lunch, dinner, or snack")
    is_random: bool = Field(default=False, description="Whether to pick random meal")


class BatchScheduleAction(BaseModel):
    """Parsed action for batch scheduling requests"""
    tasks: List[ScheduleTask] = Field(..., description="List of scheduling tasks to execute")
    request_type: str = Field(..., description="Type: multi_meal, batch_days, random_selection")


class EnhancedMealAgent:
    """
    Enhanced meal scheduling agent with multi-task support
    
    Handles both simple and complex scheduling requests:
    - Single: "Schedule chicken for Tuesday" 
    - Multi: "Schedule pizza and tacos for tomorrow"
    - Batch: "Schedule breakfast for next 5 days"
    - Random: "Pick meals at random for Friday"
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Enhanced prompt for complex scheduling
        self.enhanced_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an advanced meal scheduling assistant that can handle complex multi-task scheduling requests.

Current context:
- Today is {today}
- Available meals: {available_meals}

Parse the user's request and identify the scheduling pattern:

1. **Multi-meal requests**: "Schedule pizza and egg tacos for tomorrow"
   → Create multiple tasks for same date

2. **Batch day requests**: "Schedule breakfast for the next 5 days" 
   → Create tasks for multiple consecutive days

3. **Random selection**: "Pick some meals at random to schedule for Friday"
   → Create tasks with is_random=true

4. **Mixed requests**: "Schedule pizza for tomorrow and pick random meals for Friday"
   → Combine different task types

For each task, extract:
- meal_name: Exact meal name from available meals, or null if random
- target_date: Convert to YYYY-MM-DD format
- meal_type: breakfast, lunch, dinner, snack
- is_random: true if should pick random meal

Date conversion rules:
- "tomorrow" → {tomorrow}
- "next 5 days" → 5 consecutive dates starting tomorrow
- "Friday" → next Friday's date
- "next week" → dates 7+ days ahead

Request classification:
- "multi_meal": Multiple specific meals for same date
- "batch_days": Same meal type across multiple days
- "random_selection": Random meal picking involved

{format_instructions}"""),
            ("human", "{user_request}")
        ])
        
        # Simple fallback prompt for basic requests
        self.simple_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a meal scheduling assistant. Parse this scheduling request:

Available meals: {available_meals}
Today is {today}

Extract:
- meal_name: Exact meal name (must match available meals)
- target_date: Convert to YYYY-MM-DD format  
- meal_type: breakfast, lunch, dinner, or snack

{format_instructions}"""),
            ("human", "{user_request}")
        ])
        
        # Output parsers  
        self.batch_parser = JsonOutputParser()
        self.json_parser = JsonOutputParser()
    
    def _get_date_range(self, start_date: date, num_days: int) -> List[str]:
        """Generate consecutive dates starting from start_date"""
        dates = []
        for i in range(num_days):
            target_date = start_date + timedelta(days=i)
            dates.append(target_date.isoformat())
        return dates
    
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
    
    def _select_random_meals(self, available_meals: List[str], count: int = 1) -> List[str]:
        """Select random meals from available collection"""
        if not available_meals:
            return []
        
        # Ensure we don't select more meals than available
        count = min(count, len(available_meals))
        return random.sample(available_meals, count)
    
    async def _detect_request_complexity(self, user_request: str) -> str:
        """Determine if this is a simple or complex request"""
        request_lower = user_request.lower()
        
        # Complex patterns
        complex_indicators = [
            " and ",  # "pizza and tacos"
            "next 5 days", "next 3 days", "next week",  # batch scheduling
            "rest of the week", "this week", "the week",  # week-based scheduling
            "random", "pick some", "choose some", "saved meals",  # random selection
            "breakfast for", "lunch for", "dinner for",  # batch meal types
            "dinners for", "meals for"  # plural meal planning
        ]
        
        for indicator in complex_indicators:
            if indicator in request_lower:
                return "complex"
        
        return "simple"
    
    async def _parse_complex_request(self, user_request: str, available_meals: List[str]) -> BatchScheduleAction:
        """Parse complex multi-task scheduling requests"""
        try:
            # Build the enhanced prompt
            chain = self.enhanced_prompt | llm_service.claude | self.batch_parser
            
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            
            result_dict = await chain.ainvoke({
                "user_request": user_request,
                "today": date.today().isoformat(),
                "tomorrow": tomorrow,
                "available_meals": ", ".join(available_meals),
                "format_instructions": "Return a JSON object with 'tasks' array and 'request_type' string"
            })
            
            # Convert dict result to BatchScheduleAction
            tasks = []
            for task_dict in result_dict.get('tasks', []):
                tasks.append(ScheduleTask(**task_dict))
            
            return BatchScheduleAction(
                tasks=tasks,
                request_type=result_dict.get('request_type', 'unknown')
            )
            
        except Exception as e:
            print(f"Complex parsing failed, using fallback: {e}")
            return self._fallback_complex_parse(user_request, available_meals)
    
    def _fallback_complex_parse(self, user_request: str, available_meals: List[str]) -> BatchScheduleAction:
        """Fallback parsing for complex requests without LLM"""
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
                    dates = self._get_date_range(tomorrow, days_until_end_of_week)
                else:
                    # Today is Sunday, so no "rest of week"
                    dates = []
            elif "this week" in request_lower:
                # This week = today through Sunday
                today = date.today()
                days_until_sunday = (6 - today.weekday()) % 7
                if days_until_sunday == 0 and today.weekday() == 6:  # Today is Sunday
                    days_until_sunday = 7
                dates = self._get_date_range(today, days_until_sunday + 1)
            else:
                # Next 5 days
                dates = self._get_date_range(date.today() + timedelta(days=1), 5)
            
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
        
        # Detect multi-meal patterns (pizza and tacos)
        elif " and " in request_lower:
            # Find target date
            target_date = date.today().isoformat()
            if "tomorrow" in request_lower:
                target_date = (date.today() + timedelta(days=1)).isoformat()
            elif "friday" in request_lower:
                target_date = self._get_next_weekday_date("friday", date.today())
            
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
        
        # Detect random selection
        elif "random" in request_lower or "pick some" in request_lower:
            target_date = date.today().isoformat()
            if "tomorrow" in request_lower:
                target_date = (date.today() + timedelta(days=1)).isoformat()
            elif "friday" in request_lower:
                target_date = self._get_next_weekday_date("friday", date.today())
            
            tasks.append(ScheduleTask(
                meal_name=None,
                target_date=target_date,
                meal_type="dinner",
                is_random=True
            ))
            
            return BatchScheduleAction(tasks=tasks, request_type="random_selection")
        
        # Default to single task (fallback)
        default_date = date.today().isoformat()
        return BatchScheduleAction(
            tasks=[ScheduleTask(meal_name="Unknown", target_date=default_date, meal_type="dinner")],
            request_type="single"
        )
    
    async def _execute_batch_schedule(self, batch_action: BatchScheduleAction, available_meals: List[str]) -> Dict[str, Any]:
        """Execute multiple scheduling tasks"""
        results = []
        successful_schedules = []
        errors = []
        
        for task in batch_action.tasks:
            try:
                # Handle random meal selection
                if task.is_random or not task.meal_name:
                    selected_meals = self._select_random_meals(available_meals, 1)
                    if not selected_meals:
                        errors.append("No meals available for random selection")
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
                    errors.append(f"Meal '{task.meal_name}' not found")
                    continue
                
                # Create scheduled meal
                from models.scheduled_meal import ScheduledMeal, MealOccasion
                from uuid import uuid4
                
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
                errors.append(f"Failed to schedule {task.meal_name}: {str(e)}")
        
        return {
            "success": len(successful_schedules) > 0,
            "scheduled_count": len(successful_schedules),
            "schedules": successful_schedules,
            "errors": errors,
            "request_type": batch_action.request_type
        }
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process meal management requests with enhanced multi-task support
        
        Handles both simple and complex scheduling patterns
        """
        try:
            # Get available meals
            meals = self.storage.load_meals()
            available_meals = [meal.name for meal in meals]
            
            if not available_meals:
                return AIResponse(
                    conversational_response="❌ No meals found in your collection. Please add some meals first.",
                    actions=[],
                    model_used="enhanced"
                )
            
            # Detect request complexity
            complexity = await self._detect_request_complexity(message.content)
            
            if complexity == "simple":
                # Use existing simple logic for basic requests
                return await self._process_simple_request(message, available_meals)
            else:
                # Use enhanced logic for complex requests
                return await self._process_complex_request(message, available_meals)
                
        except Exception as e:
            return AIResponse(
                conversational_response=f"❌ I encountered an error: {str(e)}",
                actions=[],
                model_used="enhanced"
            )
    
    async def _process_simple_request(self, message: ChatMessage, available_meals: List[str]) -> AIResponse:
        """Process simple single-meal scheduling requests directly"""
        try:
            # Use the existing fallback logic for simple requests
            meal_name = None
            for meal in available_meals:
                if meal.lower() in message.content.lower():
                    meal_name = meal
                    break
            
            if not meal_name:
                return AIResponse(
                    conversational_response="I couldn't find that meal in your saved meals. Please try with one of your saved meals.",
                    actions=[],
                    model_used="enhanced"
                )
            
            # Simple date extraction - default to today
            target_date = date.today()
            content_lower = message.content.lower()
            
            if "tomorrow" in content_lower:
                target_date = date.today() + timedelta(days=1)
            elif "next wednesday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("wednesday", date.today()))
            elif "next tuesday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("tuesday", date.today()))
            elif "next monday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("monday", date.today()))
            elif "next thursday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("thursday", date.today()))
            elif "next friday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("friday", date.today()))
            elif "next saturday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("saturday", date.today()))
            elif "next sunday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("sunday", date.today()))
            elif "tuesday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("tuesday", date.today()))
            elif "monday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("monday", date.today()))
            elif "wednesday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("wednesday", date.today()))
            elif "thursday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("thursday", date.today()))
            elif "friday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("friday", date.today()))
            elif "saturday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("saturday", date.today()))
            elif "sunday" in content_lower:
                target_date = date.fromisoformat(self._get_next_weekday_date("sunday", date.today()))
            
            # Execute the scheduling using existing batch logic
            task = ScheduleTask(
                meal_name=meal_name,
                target_date=target_date.isoformat(),
                meal_type="dinner",
                is_random=False
            )
            batch_action = BatchScheduleAction(tasks=[task], request_type="single")
            batch_result = await self._execute_batch_schedule(batch_action, available_meals)
            
            if batch_result["success"] and batch_result["schedules"]:
                schedule_result = batch_result["schedules"][0]
                response = f"✅ I've scheduled {schedule_result['meal_name']} for {schedule_result['meal_type']} on {schedule_result['date']}!"
                action = AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters=schedule_result
                )
                return AIResponse(
                    conversational_response=response,
                    actions=[action],
                    model_used="enhanced"
                )
            else:
                error_msg = batch_result["errors"][0] if batch_result["errors"] else "Unknown error"
                return AIResponse(
                    conversational_response=f"❌ Sorry, I couldn't schedule that meal: {error_msg}",
                    actions=[],
                    model_used="enhanced"
                )
                
        except Exception as e:
            return AIResponse(
                conversational_response=f"❌ I encountered an error: {str(e)}",
                actions=[],
                model_used="enhanced"
            )
    
    async def _process_complex_request(self, message: ChatMessage, available_meals: List[str]) -> AIResponse:
        """Process complex multi-task scheduling requests"""
        
        # Parse the complex request
        batch_action = await self._parse_complex_request(message.content, available_meals)
        
        # Execute batch scheduling
        result = await self._execute_batch_schedule(batch_action, available_meals)
        
        if result["success"]:
            # Create success response
            scheduled_count = result["scheduled_count"]
            schedules = result["schedules"]
            
            if scheduled_count == 1:
                schedule = schedules[0]
                response = f"✅ I've scheduled {schedule['meal_name']} for {schedule['meal_type']} on {schedule['date']}!"
            else:
                response = f"✅ I've scheduled {scheduled_count} meals for you:\n"
                for schedule in schedules[:5]:  # Limit to first 5 for readability
                    response += f"• {schedule['meal_name']} ({schedule['meal_type']}) on {schedule['date']}\n"
                
                if len(schedules) > 5:
                    response += f"... and {len(schedules) - 5} more meals"
            
            # Add error information if some tasks failed
            if result["errors"]:
                response += f"\n\n⚠️ Note: {len(result['errors'])} tasks had issues."
            
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
                model_used="enhanced"
            )
        
        else:
            # Error response
            error_msg = "❌ I couldn't schedule any meals. "
            if result["errors"]:
                error_msg += f"Issues: {'; '.join(result['errors'][:3])}"
            
            return AIResponse(
                conversational_response=error_msg,
                actions=[],
                model_used="enhanced"
            )


# Test function
async def test_enhanced_agent():
    """Test the enhanced agent with complex requests"""
    agent = EnhancedMealAgent()
    
    test_cases = [
        "Schedule pizza and egg tacos for tomorrow",
        "Schedule breakfast for the next 5 days based on my saved meals",
        "Pick some meals at random to schedule for Friday",
        "Schedule chicken for Tuesday",  # Simple case
    ]
    
    for test_msg in test_cases:
        print(f"\n🧪 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")


if __name__ == "__main__":
    asyncio.run(test_enhanced_agent())