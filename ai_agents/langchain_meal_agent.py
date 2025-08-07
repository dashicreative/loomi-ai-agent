"""
Enhanced Meal Scheduling Agent using LangChain's agent framework
"""

import json
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

from langchain.agents import create_structured_chat_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import AIMessage, HumanMessage
from langchain.tools import Tool
from langchain_core.messages import SystemMessage

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from services.llm_service import llm_service
from .tools import (
    GetAvailableMealsTool,
    DateParserTool,
    ScheduleSingleMealTool,
    BatchMealSchedulerTool,
    RandomMealSelectorTool,
    ConflictDetectorTool,
    AmbiguityDetectorTool
)


# Agent system prompt
SYSTEM_PROMPT = """You are a meal scheduling specialist. You help users schedule, reschedule, and manage their meal planning.

You have access to the following tools:
{tools}

Tool names: {tool_names}

PROCESS:
1. First, detect if the request is ambiguous and needs clarification
2. If ambiguous, ask for clarification and stop
3. Get available meals to validate meal names
4. Parse any relative dates to absolute YYYY-MM-DD format
5. For random selection requests, use select_random_meals tool
6. Execute appropriate scheduling tool(s)
7. Provide friendly confirmation with what was scheduled

EXAMPLES:
- "Schedule pizza for tomorrow" → Use tools: parse_date, then schedule_single_meal
- "Pick a random meal for Friday" → Use tools: parse_date, get_available_meals, select_random_meals, schedule_single_meal

IMPORTANT:
- Be concise and friendly
- When meals aren't found, suggest 2-3 alternatives, not the full list
- Use natural language in responses
- Default meal type is "dinner" unless specified
- Current date: {current_date}"""


class LangChainMealAgent:
    """
    Meal scheduling agent using LangChain's agent framework and tools
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Create tool instances
        self.tool_instances = {
            'get_available_meals': GetAvailableMealsTool(storage=self.storage),
            'parse_date': DateParserTool(),
            'schedule_single_meal': ScheduleSingleMealTool(storage=self.storage),
            'schedule_multiple_meals': BatchMealSchedulerTool(storage=self.storage),
            'select_random_meals': RandomMealSelectorTool(),
            'check_scheduling_conflicts': ConflictDetectorTool(storage=self.storage),
            'detect_request_ambiguity': AmbiguityDetectorTool()
        }
        
        # Convert to LangChain Tool format
        self.tools = []
        for name, tool_instance in self.tool_instances.items():
            self.tools.append(Tool(
                name=tool_instance.name,
                description=tool_instance.description,
                func=tool_instance._run,
                coroutine=tool_instance._arun
            ))
        
        # Create prompt with proper format for structured chat agent
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Create structured chat agent
        self.agent = create_structured_chat_agent(
            llm=llm_service.claude,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Create executor with error handling
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,  # Set to False in production
            handle_parsing_errors=True,
            max_iterations=10,
            return_intermediate_steps=True
        )
    
    def _extract_actions_from_result(self, result: Dict[str, Any]) -> List[AIAction]:
        """Extract structured actions from agent execution result"""
        actions = []
        
        # Look through intermediate steps for tool calls
        intermediate_steps = result.get("intermediate_steps", [])
        
        for step in intermediate_steps:
            if len(step) >= 2:
                agent_action, tool_output = step
                
                # Check if it's a scheduling action
                if agent_action.tool == "schedule_single_meal":
                    try:
                        output_data = json.loads(tool_output)
                        if output_data.get("success"):
                            actions.append(AIAction(
                                type=ActionType.SCHEDULE_MEAL,
                                parameters={
                                    "meal_name": output_data.get("meal_name"),
                                    "date": output_data.get("date"),
                                    "meal_type": output_data.get("meal_type"),
                                    "scheduled_meal_id": output_data.get("scheduled_meal_id")
                                }
                            ))
                    except:
                        pass
                
                elif agent_action.tool == "schedule_multiple_meals":
                    try:
                        output_data = json.loads(tool_output)
                        successful_meals = output_data.get("successful_meals", [])
                        for meal in successful_meals:
                            actions.append(AIAction(
                                type=ActionType.SCHEDULE_MEAL,
                                parameters={
                                    "meal_name": meal.get("meal_name"),
                                    "date": meal.get("date"),
                                    "meal_type": meal.get("meal_type"),
                                    "scheduled_meal_id": meal.get("scheduled_meal_id")
                                }
                            ))
                    except:
                        pass
        
        return actions
    
    def _format_response_with_natural_dates(self, response: str) -> str:
        """Convert ISO dates in response to natural language"""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Replace common date patterns
        response = response.replace(today.isoformat(), "today")
        response = response.replace(tomorrow.isoformat(), "tomorrow")
        
        # Replace next week dates with weekday names
        for i in range(2, 8):
            future_date = today + timedelta(days=i)
            weekday = future_date.strftime("%A")
            response = response.replace(future_date.isoformat(), weekday)
        
        return response
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process user message using LangChain agent
        """
        try:
            # Execute agent with current date context
            result = await self.agent_executor.ainvoke({
                "input": message.content,
                "current_date": date.today().isoformat(),
                "chat_history": []  # Empty for now, can add memory later
            })
            
            # Extract response and actions
            response = result.get("output", "I encountered an issue processing your request.")
            actions = self._extract_actions_from_result(result)
            
            # Format response with natural dates
            response = self._format_response_with_natural_dates(response)
            
            return AIResponse(
                conversational_response=response,
                actions=actions,
                model_used="langchain_agent"
            )
            
        except Exception as e:
            print(f"Agent execution error: {str(e)}")
            return AIResponse(
                conversational_response=f"I encountered an error: {str(e)}. Please try rephrasing your request.",
                actions=[],
                model_used="langchain_agent"
            )
    
    def clear_memory(self):
        """Clear conversation memory (placeholder for future implementation)"""
        pass  # Memory will be added in next phase


# Test function
async def test_langchain_agent():
    """Test the LangChain-based agent"""
    agent = LangChainMealAgent()
    
    test_cases = [
        "Schedule pizza for tomorrow",
        "Pick a random meal for dinner on Friday",
        "Schedule breakfast for the next 3 days",
        "Can you just pick a meal for me",
        "Schedule chicken for tomorrow"  # Non-existent meal
    ]
    
    for test_msg in test_cases:
        print(f"\n🧪 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")
        
        # Clear memory between tests to avoid context pollution
        agent.clear_memory()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_langchain_agent())