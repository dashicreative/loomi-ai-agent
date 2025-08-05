"""
Meal Management Agent - Enhanced with comprehensive prompt template

Handles meal scheduling with clarifications, conflict resolution, and edge cases.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from services.llm_service import llm_service
from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage


# Pydantic models for structured outputs
class ScheduleMealParameters(BaseModel):
    meal_name: str
    date: str
    occasion: str = Field(default="dinner")
    servings: Optional[int] = Field(default=4)
    notes: Optional[str] = None


class Conflict(BaseModel):
    date: str
    occasion: str
    existing_meal: str
    action: Optional[str] = Field(default="skip")


class ClarificationOption(BaseModel):
    option: str
    description: str
    date: Optional[str] = None
    meal_name: Optional[str] = None
    action: Optional[str] = None


class ScheduleAction(BaseModel):
    type: str
    parameters: Dict[str, Any]


class AgentResponse(BaseModel):
    status: str = Field(..., description="success, needs_clarification, or error")
    conversational_response: str
    actions: Optional[List[ScheduleAction]] = Field(default_factory=list)
    clarification_type: Optional[str] = None
    pending_actions: Optional[List[ScheduleAction]] = None
    clarification_options: Optional[List[ClarificationOption]] = None
    conflicts: Optional[List[Conflict]] = None
    validation_errors: Optional[List[str]] = None


class MealManagementAgent:
    """
    Enhanced meal scheduling agent with comprehensive prompt template
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Comprehensive prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """# Meal Scheduling Sub-Agent Prompt Template

## System Role
You are a specialized meal scheduling sub-agent within an AI meal planning app. Your primary responsibility is to understand meal scheduling requests and convert them into precise scheduling actions. You handle conversational clarifications when needed but do NOT handle recipe discovery - you focus exclusively on scheduling operations and related clarifications.

## Your Capabilities
- Schedule single or multiple meals to specific dates and meal occasions
- Reschedule existing meals to new dates/occasions
- Handle relative dates (today, tomorrow, Monday, next week, etc.)
- Process batch scheduling requests
- Validate scheduling conflicts and constraints
- Generate precise action parameters for the execution engine

## Input Context
Current context:
- Today's date: {current_date}
- Available meals: {available_meals}
- Currently scheduled meals: {scheduled_meals}
- User preferences: {user_preferences}

## Output Format
You must respond with ONLY a JSON object in one of these formats:

### Successful Scheduling (No clarification needed)
```json
{{
  "status": "success",
  "conversational_response": "I've scheduled [meal details] for you!",
  "actions": [
    {{
      "type": "schedule_meal",
      "parameters": {{
        "meal_name": "exact meal name from saved_meals",
        "date": "YYYY-MM-DD",
        "occasion": "breakfast|lunch|dinner|snack",
        "servings": number,
        "notes": "optional notes"
      }}
    }}
  ],
  "conflicts": []
}}
```

### Needs Clarification
```json
{{
  "status": "needs_clarification",
  "conversational_response": "I need clarification: [specific question]",
  "clarification_type": "date_ambiguity|conflict_resolution|meal_not_found|serving_size",
  "pending_actions": [...],
  "clarification_options": [...]
}}
```

### Error
```json
{{
  "status": "error",
  "conversational_response": "I couldn't complete that request: [explanation]",
  "validation_errors": ["error messages"]
}}
```

## Date Processing Rules
1. Convert relative dates to absolute YYYY-MM-DD format:
   - "today" → {current_date}
   - "tomorrow" → current_date + 1 day
   - Weekday names → next occurrence
   - "next [weekday]" → that weekday of next week (7+ days ahead)

2. Only schedule for current date or future dates

3. Default to "dinner" if occasion not specified

## Conflict Handling
Check if date + occasion already has a scheduled meal. If so, note in conflicts array.

## Critical Rules
1. Always respond with valid JSON in the specified format
2. Use exact meal names from available_meals list
3. Convert all dates to YYYY-MM-DD format
4. Be conversational but concise
5. Handle ambiguity by requesting clarification"""),
            ("human", "{user_request}")
        ])
        
        # JSON output parser
        self.output_parser = JsonOutputParser()
    
    def _get_next_weekday_date(self, weekday_name: str, from_date: date) -> str:
        """Convert weekday name to next occurrence date"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return from_date.isoformat()
        
        days_ahead = target_weekday - from_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
            
        target_date = from_date + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    def _format_scheduled_meals(self, scheduled_meals) -> str:
        """Format scheduled meals for the prompt"""
        if not scheduled_meals:
            return "No meals currently scheduled"
        
        formatted = []
        for sm in scheduled_meals:
            meal = self.storage.get_meal_by_id(str(sm.meal_id))
            meal_name = meal.name if meal else "Unknown Meal"
            formatted.append(f"- {sm.date}: {meal_name} ({sm.occasion})")
        
        return "\n".join(formatted)
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process a meal management request with the enhanced prompt
        """
        try:
            # Load current data
            meals = self.storage.load_meals()
            available_meals = [meal.name for meal in meals]
            scheduled_meals = self.storage.load_scheduled_meals()
            
            # Format context
            user_preferences = message.user_context.get("preferences", {"default_servings": 4})
            
            # Build the prompt with context
            chain = self.prompt | llm_service.claude | self.output_parser
            
            # Execute the chain
            response_dict = await chain.ainvoke({
                "user_request": message.content,
                "current_date": date.today().isoformat(),
                "available_meals": ", ".join(available_meals),
                "scheduled_meals": self._format_scheduled_meals(scheduled_meals),
                "user_preferences": str(user_preferences)
            })
            
            # Convert dict to AgentResponse object
            agent_response = AgentResponse(**response_dict)
            
            # Process based on status
            if agent_response.status == "success":
                # Execute the actions
                executed_actions = []
                for action in agent_response.actions:
                    if action.type == "schedule_meal":
                        result = await self._execute_schedule_action(action.parameters)
                        if result["success"]:
                            executed_actions.append(AIAction(
                                type=ActionType.SCHEDULE_MEAL,
                                parameters=result
                            ))
                
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=executed_actions,
                    model_used="claude"
                )
            
            elif agent_response.status == "needs_clarification":
                # Return clarification request
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="claude"
                )
            
            else:  # error
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="claude"
                )
                
        except Exception as e:
            print(f"Agent processing error: {e}")
            # Fallback to simple scheduling
            return await self._fallback_process(message)
    
    async def _execute_schedule_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the meal scheduling action"""
        try:
            # Find the meal
            meals = self.storage.load_meals()
            target_meal = None
            
            for meal in meals:
                if meal.name.lower() == parameters["meal_name"].lower():
                    target_meal = meal
                    break
            
            if not target_meal:
                return {
                    "success": False,
                    "error": f"Meal '{parameters['meal_name']}' not found"
                }
            
            # Create scheduled meal
            from models.scheduled_meal import ScheduledMeal, MealOccasion
            from uuid import uuid4
            
            target_date = date.fromisoformat(parameters["date"])
            meal_occasion = MealOccasion(parameters["occasion"])
            
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
                "date": parameters["date"],
                "meal_type": parameters["occasion"]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _fallback_process(self, message: ChatMessage) -> AIResponse:
        """Simple fallback processing"""
        # Use the existing simple logic from V1
        meals = self.storage.load_meals()
        meal_names = [m.name for m in meals]
        
        # Find a meal name in the message
        meal_name = None
        for name in meal_names:
            if name.lower() in message.content.lower():
                meal_name = name
                break
        
        if not meal_name:
            return AIResponse(
                conversational_response="I couldn't find that meal in your saved meals. Please try with one of your saved meals.",
                actions=[],
                model_used="fallback"
            )
        
        # Simple date extraction
        target_date = date.today()
        content_lower = message.content.lower()
        
        if "tomorrow" in content_lower:
            target_date = date.today() + timedelta(days=1)
        elif "next wednesday" in content_lower:
            # Calculate next Wednesday (always 7+ days ahead)
            days_until_wednesday = (2 - date.today().weekday()) % 7
            if days_until_wednesday == 0:
                days_until_wednesday = 7
            target_date = date.today() + timedelta(days=days_until_wednesday + 7)
        elif "next" in content_lower:
            # Handle other "next [weekday]" patterns
            for day_name, day_num in [("monday", 0), ("tuesday", 1), ("thursday", 3), 
                                     ("friday", 4), ("saturday", 5), ("sunday", 6)]:
                if f"next {day_name}" in content_lower:
                    days_ahead = (day_num - date.today().weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_date = date.today() + timedelta(days=days_ahead + 7)
                    break
        else:
            # Handle simple weekday names (this week)
            for day_name, day_num in [("monday", 0), ("tuesday", 1), ("wednesday", 2),
                                     ("thursday", 3), ("friday", 4), ("saturday", 5), ("sunday", 6)]:
                if day_name in content_lower:
                    days_ahead = (day_num - date.today().weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_date = date.today() + timedelta(days=days_ahead)
                    break
        
        # Schedule the meal
        result = await self._execute_schedule_action({
            "meal_name": meal_name,
            "date": target_date.isoformat(),
            "occasion": "dinner"
        })
        
        if result["success"]:
            response = f"✅ I've scheduled {meal_name} for {result['meal_type']} on {result['date']}!"
            action = AIAction(
                type=ActionType.SCHEDULE_MEAL,
                parameters=result
            )
            return AIResponse(
                conversational_response=response,
                actions=[action],
                model_used="fallback"
            )
        else:
            return AIResponse(
                conversational_response=f"❌ Sorry, I couldn't schedule that meal: {result['error']}",
                actions=[],
                model_used="fallback"
            )


# Test function
async def test_meal_management():
    """Test the enhanced meal management agent"""
    agent = MealManagementAgent()
    
    test_cases = [
        "Schedule chicken parmesan for next Wednesday",
        "Add pasta to Tuesday", 
        "Schedule salmon for dinner tomorrow",
        "Put chicken on Friday"  # Should handle existing meal conflict if any
    ]
    
    for test_msg in test_cases:
        print(f"\n🧪 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")


if __name__ == "__main__":
    asyncio.run(test_meal_management())