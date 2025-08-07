"""
Example: How to implement OpenAI-style function calling or LangChain-style tool usage

This shows how your agent could work more like ChatGPT with function calling
or LangChain agents that reason about tool usage.
"""

from typing import List, Dict, Any
import json
from langchain_core.prompts import ChatPromptTemplate
from services.llm_service import llm_service


class ToolCallingAgent:
    """
    Agent that uses LLM to decide which tools to call
    
    Similar to:
    - OpenAI's function calling
    - LangChain's tool-using agents
    - Anthropic's tool use
    """
    
    def __init__(self, tools: List[Dict[str, Any]]):
        self.tools = tools
        self.tool_descriptions = self._format_tool_descriptions()
        
        # Prompt that teaches the LLM about available tools
        self.tool_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a meal scheduling assistant with access to the following tools:

{tool_descriptions}

To use a tool, respond with a JSON object like this:
{{
    "thought": "I need to check available meals first",
    "tool": "get_available_meals",
    "parameters": {{}}
}}

Or for tools with parameters:
{{
    "thought": "I'll schedule Pizza for tomorrow's dinner",
    "tool": "schedule_meal",
    "parameters": {{
        "meal_name": "Pizza",
        "target_date": "2024-03-21",
        "meal_type": "dinner"
    }}
}}

Today is {today}. When the user says "tomorrow", that means {tomorrow}.

Analyze the user's request and decide which tool(s) to use."""),
            ("human", "{user_request}")
        ])
    
    def _format_tool_descriptions(self) -> str:
        """Format tools for the prompt"""
        descriptions = []
        for tool in self.tools:
            desc = f"- {tool['name']}: {tool['description']}"
            if tool.get('parameters'):
                desc += f"\n  Parameters: {json.dumps(tool['parameters'], indent=2)}"
            descriptions.append(desc)
        return "\n".join(descriptions)
    
    async def process_with_reasoning(self, user_request: str) -> Dict[str, Any]:
        """
        Process request by having LLM reason about tool usage
        
        This is how modern AI SDKs work:
        1. LLM analyzes the request
        2. LLM decides which tool to use
        3. LLM provides parameters
        4. System executes the tool
        5. LLM sees result and decides next step
        """
        from datetime import date, timedelta
        
        # Get LLM's decision on tool usage
        chain = self.tool_prompt | llm_service.claude
        
        response = await chain.ainvoke({
            "user_request": user_request,
            "tool_descriptions": self.tool_descriptions,
            "today": date.today().isoformat(),
            "tomorrow": (date.today() + timedelta(days=1)).isoformat()
        })
        
        # Parse LLM's tool decision
        try:
            tool_call = json.loads(response.content)
            return {
                "success": True,
                "thought": tool_call.get("thought"),
                "tool": tool_call.get("tool"),
                "parameters": tool_call.get("parameters", {})
            }
        except:
            return {
                "success": False,
                "error": "Failed to parse tool decision"
            }


# Example of how to define tools for the agent
MEAL_TOOLS_SCHEMA = [
    {
        "name": "get_available_meals",
        "description": "Get list of all meals that can be scheduled",
        "parameters": {}
    },
    {
        "name": "schedule_meal",
        "description": "Schedule a specific meal for a date",
        "parameters": {
            "meal_name": "string - Name of the meal",
            "target_date": "string - Date in YYYY-MM-DD format",
            "meal_type": "string - One of: breakfast, lunch, dinner, snack"
        }
    },
    {
        "name": "check_schedule_conflict",
        "description": "Check if a date/meal type is already scheduled",
        "parameters": {
            "target_date": "string - Date to check",
            "meal_type": "string - Meal type to check"
        }
    },
    {
        "name": "get_scheduled_meals",
        "description": "Get meals scheduled for a date range",
        "parameters": {
            "start_date": "string - Start date",
            "end_date": "string - Optional end date"
        }
    }
]


# Example usage showing the full flow
async def example_tool_calling_flow():
    """
    Example of how tool calling works in modern AI SDKs
    """
    # Initialize agent with tool schemas
    agent = ToolCallingAgent(MEAL_TOOLS_SCHEMA)
    
    # User request
    user_request = "Schedule pizza for tomorrow's dinner"
    
    # Step 1: LLM decides which tool to use
    decision = await agent.process_with_reasoning(user_request)
    print(f"LLM Thought: {decision['thought']}")
    print(f"Tool to use: {decision['tool']}")
    print(f"Parameters: {decision['parameters']}")
    
    # Step 2: Execute the actual tool (would be done by the system)
    # tool_result = execute_tool(decision['tool'], decision['parameters'])
    
    # Step 3: LLM could then see the result and decide if more tools are needed
    # This creates a reasoning loop similar to ReAct agents


# Comparison with your current approach:
"""
Current Approach:
- Direct method calls: self.storage.add_scheduled_meal(...)
- Logic is hardcoded in processors
- No explicit tool interface

Tool-Based Approach (AI SDK style):
- Explicit tool definitions with schemas
- LLM reasons about which tools to use
- Standardized tool interface
- Tools can be reused across different agents
- Easier to add new capabilities (just add new tools)
- Better observability (can log tool calls)
- More testable (can mock tools)

Benefits of Tools:
1. **Modularity**: Each tool is self-contained
2. **Reusability**: Tools can be used by different agents
3. **Extensibility**: Easy to add new tools
4. **Observability**: Can track what tools are being used
5. **Testing**: Can test tools independently
6. **Documentation**: Tools self-document their capabilities
"""