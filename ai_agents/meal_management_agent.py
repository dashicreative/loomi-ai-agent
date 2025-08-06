"""
Meal Management Agent - Phase 1: Basic Meal Scheduling

Handles in-app changes like:
- "Schedule [Meal Name] for Tuesday"
- "Create a new meal titled turkey bowl"

Built with LangChain for clear, understandable agent architecture.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from services.llm_service import llm_service
from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage


class MealScheduleAction(BaseModel):
    """Parsed action for scheduling a meal"""
    meal_name: str = Field(..., description="Name of the meal to schedule")
    target_date: str = Field(..., description="Target date in YYYY-MM-DD format")  
    meal_type: str = Field(default="dinner", description="Type of meal: breakfast, lunch, dinner, or snack")


class MealManagementAgent:
    """
    Phase 1: Basic meal scheduling agent
    
    Focuses on single query: "Schedule [Meal Name] for Tuesday"
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Simple, focused prompt for meal scheduling
        self.schedule_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a meal scheduling assistant. Your job is to extract meal scheduling information from user requests.

Current context:
- Today is {today}
- Available meals in user's collection: {available_meals}

Parse the user's request and extract:
1. meal_name: The exact name of the


















 meal (must match available meals)
2. target_date: Convert day names to YYYY-MM-DD format
3. meal_type: breakfast, lunch, dinner, or snack (default: dinner)

Day conversion examples:
- "Tuesday" → next Tuesday's date
- "tomorrow" → tomorrow's date  
- "today" → today's date

{format_instructions}"""),
            ("human", "{user_request}")
        ])
        
        # Output parser for structured data
        self.output_parser = PydanticOutputParser(pydantic_object=MealScheduleAction)
    
    def _get_next_weekday_date(self, weekday_name: str, today: date) -> str:
        """Convert weekday name to next occurrence date (this week or next week)"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return today.isoformat()
        
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
            
        target_date = today + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    def _get_next_week_weekday_date(self, weekday_name: str, today: date) -> str:
        """Convert weekday name to NEXT WEEK's occurrence (always 7+ days ahead)"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return today.isoformat()
        
        # Always go to next week
        days_ahead = target_weekday - today.weekday() + 7
        target_date = today + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    async def parse_schedule_request(self, user_request: str) -> MealScheduleAction:
        """Parse a meal scheduling request using LangChain"""
        
        # Get available meals from storage
        meals = self.storage.load_meals()
        available_meals = [meal.name for meal in meals]
        
        # Build the prompt
        chain = self.schedule_prompt | llm_service.claude | self.output_parser
        
        # Execute the chain
        try:
            result = await chain.ainvoke({
                "user_request": user_request,
                "today": date.today().isoformat(),
                "available_meals": ", ".join(available_meals),
                "format_instructions": self.output_parser.get_format_instructions()
            })
            return result
        except Exception as e:
            # Fallback parsing if LLM fails
            print(f"LLM parsing failed: {e}")
            return self._fallback_parse(user_request, available_meals)
    
    def _fallback_parse(self, user_request: str, available_meals: List[str]) -> MealScheduleAction:
        """Simple fallback parsing without LLM"""
        # Find meal name
        meal_name = "Unknown Meal"
        for meal in available_meals:
            if meal.lower() in user_request.lower():
                meal_name = meal
                break
        
        # Enhanced day detection
        target_date = date.today().isoformat()
        request_lower = user_request.lower()
        
        # Handle "next" + weekday (always next week)
        if "next wednesday" in request_lower:
            target_date = self._get_next_week_weekday_date("wednesday", date.today())
        elif "next tuesday" in request_lower:
            target_date = self._get_next_week_weekday_date("tuesday", date.today())
        elif "next monday" in request_lower:
            target_date = self._get_next_week_weekday_date("monday", date.today())
        elif "next thursday" in request_lower:
            target_date = self._get_next_week_weekday_date("thursday", date.today())
        elif "next friday" in request_lower:
            target_date = self._get_next_week_weekday_date("friday", date.today())
        elif "next saturday" in request_lower:
            target_date = self._get_next_week_weekday_date("saturday", date.today())
        elif "next sunday" in request_lower:
            target_date = self._get_next_week_weekday_date("sunday", date.today())
        # Handle standalone weekdays
        elif "wednesday" in request_lower:
            target_date = self._get_next_weekday_date("wednesday", date.today())
        elif "tuesday" in request_lower:
            target_date = self._get_next_weekday_date("tuesday", date.today())
        elif "monday" in request_lower:
            target_date = self._get_next_weekday_date("monday", date.today())
        elif "thursday" in request_lower:
            target_date = self._get_next_weekday_date("thursday", date.today())
        elif "friday" in request_lower:
            target_date = self._get_next_weekday_date("friday", date.today())
        elif "saturday" in request_lower:
            target_date = self._get_next_weekday_date("saturday", date.today())
        elif "sunday" in request_lower:
            target_date = self._get_next_weekday_date("sunday", date.today())
        elif "tomorrow" in request_lower:
            target_date = (date.today() + timedelta(days=1)).isoformat()
        
        return MealScheduleAction(
            meal_name=meal_name,
            target_date=target_date,
            meal_type="dinner"
        )
    
    async def execute_schedule_action(self, action: MealScheduleAction) -> Dict[str, Any]:
        """Execute the meal scheduling action"""
        try:
            # Find the meal in storage
            meals = self.storage.load_meals()
            target_meal = None
            
            for meal in meals:
                if meal.name.lower() == action.meal_name.lower():
                    target_meal = meal
                    break
            
            if not target_meal:
                return {
                    "success": False,
                    "error": f"Meal '{action.meal_name}' not found in your collection"
                }
            
            # Create scheduled meal
            from models.scheduled_meal import ScheduledMeal, MealOccasion
            from uuid import uuid4
            
            # Convert string to date
            target_date = date.fromisoformat(action.target_date)
            meal_occasion = MealOccasion(action.meal_type)
            
            scheduled_meal = ScheduledMeal(
                id=uuid4(),
                meal_id=target_meal.id,
                date=target_date,
                occasion=meal_occasion
            )
            
            # Save to storage
            self.storage.add_scheduled_meal(scheduled_meal)
            
            return {
                "success": True,
                "scheduled_meal_id": str(scheduled_meal.id),
                "meal_name": target_meal.name,
                "date": action.target_date,
                "meal_type": action.meal_type
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to schedule meal: {str(e)}"
            }
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process a meal management request
        
        Phase 1: Focus on "Schedule [Meal Name] for Tuesday" pattern
        """
        try:
            # Parse the scheduling request
            schedule_action = await self.parse_schedule_request(message.content)
            
            # Execute the action
            result = await self.execute_schedule_action(schedule_action)
            
            if result["success"]:
                # Success response
                conversational_response = f"✅ I've scheduled {result['meal_name']} for {result['meal_type']} on {result['date']}!"
                
                # Create AI action for consistency
                ai_action = AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters={
                        "meal_name": result["meal_name"],
                        "date": result["date"],
                        "meal_type": result["meal_type"],
                        "scheduled_meal_id": result["scheduled_meal_id"]
                    }
                )
                
                return AIResponse(
                    conversational_response=conversational_response,
                    actions=[ai_action],
                    model_used="claude"
                )
            else:
                # Error response
                return AIResponse(
                    conversational_response=f"❌ Sorry, I couldn't schedule that meal. {result['error']}",
                    actions=[],
                    model_used="claude"
                )
                
        except Exception as e:
            return AIResponse(
                conversational_response=f"❌ I encountered an error processing your request: {str(e)}",
                actions=[],
                model_used="claude"
            )


# Test function for development
async def test_meal_management_agent():
    """Test the basic meal scheduling functionality"""
    agent = MealManagementAgent()
    
    # Test message
    test_message = ChatMessage(
        content="Schedule chicken parmesan for Tuesday",
        user_context={}
    )
    
    print("🧪 Testing Meal Management Agent")
    print(f"Input: {test_message.content}")
    
    result = await agent.process(test_message)
    
    print(f"Response: {result.conversational_response}")
    print(f"Actions: {len(result.actions)}")
    if result.actions:
        action = result.actions[0]
        print(f"Action Type: {action.type}")
        print(f"Parameters: {action.parameters}")


if __name__ == "__main__":
    asyncio.run(test_meal_management_agent())