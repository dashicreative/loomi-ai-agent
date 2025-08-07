"""
Simplified LangChain meal agent implementation
"""

import json
from typing import Dict, Any, List
from datetime import date, timedelta

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain.tools import Tool

from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage
from services.llm_service import llm_service
from .tools import (
    GetAvailableMealsTool,
    DateParserTool,
    ScheduleSingleMealTool,
    RandomMealSelectorTool,
    AmbiguityDetectorTool
)


# Simple ReAct prompt
REACT_PROMPT = """Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

You are a meal scheduling assistant. Be concise and friendly. Today is {current_date}.

Begin!

Question: {input}
Thought: {agent_scratchpad}"""


class SimpleLangChainAgent:
    """Simplified LangChain agent for meal scheduling"""
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Create tools
        self.tools = [
            Tool(
                name="get_meals",
                description="Get list of available meals",
                func=lambda x: GetAvailableMealsTool(self.storage)._run(x)
            ),
            Tool(
                name="parse_date",
                description="Convert date like 'tomorrow' to YYYY-MM-DD",
                func=lambda x: DateParserTool()._run(x)
            ),
            Tool(
                name="schedule_meal",
                description="Schedule a meal. Input format: 'meal_name|date|meal_type'",
                func=self._schedule_meal_wrapper
            ),
            Tool(
                name="select_random",
                description="Select N random meals. Input format: 'count|available_meals_json'",
                func=lambda x: RandomMealSelectorTool()._run(*x.split('|', 1))
            ),
            Tool(
                name="check_ambiguity",
                description="Check if request is ambiguous",
                func=lambda x: AmbiguityDetectorTool()._run(x)
            )
        ]
        
        # Create prompt
        self.prompt = PromptTemplate.from_template(REACT_PROMPT)
        
        # Create agent
        self.agent = create_react_agent(
            llm=llm_service.claude,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Create executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5
        )
    
    def _schedule_meal_wrapper(self, input_str: str) -> str:
        """Wrapper for schedule meal tool"""
        try:
            parts = input_str.split('|')
            if len(parts) >= 2:
                meal_name = parts[0]
                target_date = parts[1]
                meal_type = parts[2] if len(parts) > 2 else "dinner"
                
                tool = ScheduleSingleMealTool(self.storage)
                return tool._run(meal_name, target_date, meal_type)
            else:
                return "Error: Invalid input format. Use: meal_name|date|meal_type"
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """Process user message"""
        try:
            # Run agent
            result = await self.agent_executor.ainvoke({
                "input": message.content,
                "current_date": date.today().isoformat()
            })
            
            # Extract response
            response = result.get("output", "I couldn't process your request.")
            
            # Extract actions from tool calls (simplified)
            actions = []
            if "scheduled" in response.lower():
                # Try to extract scheduled meal info
                actions.append(AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters={"message": response}
                ))
            
            return AIResponse(
                conversational_response=response,
                actions=actions,
                model_used="simple_langchain"
            )
            
        except Exception as e:
            return AIResponse(
                conversational_response=f"Error: {str(e)}",
                actions=[],
                model_used="simple_langchain"
            )


# Test function
async def test_simple_agent():
    """Test the simplified agent"""
    agent = SimpleLangChainAgent()
    
    test_cases = [
        "Schedule Pizza for tomorrow",
        "Can you pick a meal for me?",
        "What meals do I have?"
    ]
    
    for test_msg in test_cases:
        print(f"\n🧪 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_simple_agent())