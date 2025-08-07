"""
Tool-Based Processor - Uses explicit tools like LangChain/OpenAI agents

This shows how your agent could work with explicit tools instead of
direct function calls, following AI SDK patterns.
"""

from typing import List, Dict, Any
from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from ..tools.meal_tools import get_all_tools
from ..utils.response_utils import ResponseBuilder


class ToolBasedProcessor:
    """
    Processor that uses explicit tools for operations
    
    This follows the pattern of AI SDKs where the agent:
    1. Analyzes the request
    2. Decides which tools to use
    3. Calls tools with parameters
    4. Processes tool results
    5. Generates response
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.tools = {tool.name: tool for tool in get_all_tools(storage)}
        self.response_builder = ResponseBuilder()
    
    async def process_with_tools(self, message: ChatMessage) -> AIResponse:
        """
        Process request using explicit tool calls
        
        This demonstrates how an agent would work with tools:
        1. Parse intent
        2. Select appropriate tools
        3. Execute tools in sequence
        4. Build response from results
        """
        request = message.content.lower()
        
        # Example: "Schedule pizza for tomorrow"
        if "schedule" in request:
            return await self._handle_scheduling_with_tools(message)
        
        # Example: "What meals do I have?"
        elif any(phrase in request for phrase in ["what meals", "available meals", "my meals"]):
            return await self._handle_list_meals_with_tools()
        
        # Example: "What's scheduled for tomorrow?"
        elif "scheduled" in request and not "schedule" in request:
            return await self._handle_view_schedule_with_tools(message)
        
        else:
            return self.response_builder.error_response("I'm not sure how to help with that.")
    
    async def _handle_scheduling_with_tools(self, message: ChatMessage) -> AIResponse:
        """Handle scheduling using explicit tool calls"""
        
        # Tool 1: Get available meals
        meals_result = self.tools["get_available_meals"].run()
        
        if not meals_result["success"] or meals_result["count"] == 0:
            return self.response_builder.no_meals_error()
        
        available_meals = [m["name"] for m in meals_result["meals"]]
        
        # Parse request to find meal name
        meal_name = None
        request_lower = message.content.lower()
        for meal in available_meals:
            if meal.lower() in request_lower:
                meal_name = meal
                break
        
        if not meal_name:
            return AIResponse(
                conversational_response=f"I don't see that meal. You have: {', '.join(available_meals[:3])}",
                actions=[],
                model_used="tool_based"
            )
        
        # Parse date (simplified for demo)
        from datetime import date, timedelta
        if "tomorrow" in request_lower:
            target_date = (date.today() + timedelta(days=1)).isoformat()
        else:
            target_date = date.today().isoformat()
        
        # Tool 2: Check for conflicts
        conflict_result = self.tools["check_schedule_conflict"].run(
            target_date=target_date,
            meal_type="dinner"
        )
        
        if conflict_result.get("has_conflict"):
            existing = conflict_result.get("existing_meal", "a meal")
            return AIResponse(
                conversational_response=f"You already have {existing} scheduled for dinner that day. Would you like to replace it?",
                actions=[],
                model_used="tool_based"
            )
        
        # Tool 3: Schedule the meal
        schedule_result = self.tools["schedule_meal"].run(
            meal_name=meal_name,
            target_date=target_date,
            meal_type="dinner"
        )
        
        if schedule_result["success"]:
            scheduled = schedule_result["scheduled_meal"]
            natural_date = self.response_builder.format_natural_date(scheduled["date"])
            
            return AIResponse(
                conversational_response=f"I've scheduled {scheduled['meal_name']} for {scheduled['meal_type']} {natural_date}!",
                actions=[AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters=scheduled
                )],
                model_used="tool_based"
            )
        else:
            return self.response_builder.error_response(schedule_result.get("error", "Scheduling failed"))
    
    async def _handle_list_meals_with_tools(self) -> AIResponse:
        """Handle listing meals using tools"""
        
        # Use tool to get meals
        result = self.tools["get_available_meals"].run()
        
        if result["success"] and result["count"] > 0:
            meal_names = [m["name"] for m in result["meals"]]
            response = f"You have {result['count']} meals available: {', '.join(meal_names)}"
        else:
            response = "You don't have any meals saved yet."
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="tool_based"
        )
    
    async def _handle_view_schedule_with_tools(self, message: ChatMessage) -> AIResponse:
        """Handle viewing schedule using tools"""
        
        from datetime import date, timedelta
        
        # Parse date from request
        request_lower = message.content.lower()
        if "tomorrow" in request_lower:
            check_date = (date.today() + timedelta(days=1)).isoformat()
        elif "today" in request_lower:
            check_date = date.today().isoformat()
        else:
            check_date = date.today().isoformat()
        
        # Use tool to get scheduled meals
        result = self.tools["get_scheduled_meals"].run(start_date=check_date)
        
        if result["success"] and result["count"] > 0:
            meals = result["scheduled_meals"]
            response = f"Here's what's scheduled:\n"
            for meal in meals:
                response += f"• {meal['meal_name']} for {meal['meal_type']}\n"
        else:
            response = "Nothing scheduled for that day."
        
        return AIResponse(
            conversational_response=response,
            actions=[],
            model_used="tool_based"
        )