# Tool-Based Architecture

This document explains the tool-based architecture implementation that follows AI SDK patterns like OpenAI and LangChain.

## Overview

The tool-based architecture replaces direct function calls with explicit tools that have:
- Standardized interfaces (name, description, execute)
- Clear separation of concerns
- Better testability and observability
- Easy extensibility

## Architecture Comparison

### Original Architecture
```python
# Direct storage calls
meals = self.storage.load_meals()
self.storage.add_scheduled_meal(scheduled_meal)

# Direct utility calls
selected = MealUtils.select_random_meals(available_meals, 1)
date = DateUtils.parse_relative_date("tomorrow")
```

### Tool-Based Architecture
```python
# Tool execution through orchestrator
result = await self.orchestrator.execute_tool("load_meals")
result = await self.orchestrator.execute_tool("schedule_single_meal", 
    meal=meal, 
    target_date=date, 
    meal_type="dinner"
)
```

## Available Tools

1. **LoadMealsTool** - Load all available meals from storage
2. **FindMealByNameTool** - Find a meal with fuzzy matching
3. **SelectRandomMealsTool** - Select random meals
4. **ScheduleSingleMealTool** - Schedule one meal
5. **ParseDateTool** - Convert natural language dates
6. **GetDateRangeTool** - Generate date ranges for batch scheduling
7. **SuggestAlternativeMealsTool** - Suggest meals when requested not found
8. **ExtractMealTypeTool** - Extract meal type from request

## Tool Structure

Each tool follows this pattern:

```python
class MyTool(BaseTool):
    def __init__(self, dependencies):
        super().__init__(
            name="my_tool",
            description="What this tool does"
        )
        self.dependencies = dependencies
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool operation"""
        try:
            # Tool logic here
            return {
                "success": True,
                "result": result_data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
```

## Benefits

1. **Modularity** - Each tool is self-contained
2. **Testability** - Tools can be tested independently
3. **Observability** - Easy to log/trace tool usage
4. **Extensibility** - Add new tools without changing core logic
5. **Reusability** - Tools can be used by different agents
6. **Standards** - Follows AI SDK patterns

## Usage

### Basic Tool Usage
```python
# Get tool registry
tools = ToolRegistry(storage)

# Execute a tool
result = await tools.execute_tool("parse_date", date_string="tomorrow")
if result["success"]:
    iso_date = result["iso_date"]
```

### Using the Orchestrator
```python
# High-level orchestration
orchestrator = ToolOrchestrator(storage)

# Complex operation using multiple tools
result = await orchestrator.find_and_schedule_meal(
    meal_name="Pizza",
    target_date="2024-03-15",
    meal_type="dinner",
    available_meals=["Pizza", "Tacos"]
)
```

### Using Tool-Based Agent
```python
from ai_agents.meal_scheduling_agent import ToolBasedMealAgent

# Same interface as original agent
agent = ToolBasedMealAgent()
response = await agent.process(message)

# Get tool information
tool_info = agent.get_tool_info()
```

## Migration Path

Both agents are available:

1. **EnhancedMealAgent** - Original with direct calls (backward compatible)
2. **ToolBasedMealAgent** - New tool-based architecture

You can gradually migrate by:
```python
# Use environment variable or config
USE_TOOL_BASED = os.getenv("USE_TOOL_BASED_AGENT", "false").lower() == "true"

if USE_TOOL_BASED:
    from ai_agents.meal_scheduling_agent import ToolBasedMealAgent as MealAgent
else:
    from ai_agents.meal_scheduling_agent import EnhancedMealAgent as MealAgent
```

## Future Enhancements

### LLM Tool Selection (Phase 4)
Enable the LLM to reason about which tools to use:

```python
# LLM decides: "I need to parse the date first, then find the meal"
tool_sequence = await llm_decide_tools(user_request)
# Returns: [("parse_date", {"date_string": "tomorrow"}), 
#          ("find_meal_by_name", {"meal_name": "pizza"})]
```

### Tool Composition
Create higher-level tools from basic tools:

```python
class WeeklyMealPlannerTool(ComposedTool):
    """Uses multiple basic tools to plan a week"""
    required_tools = ["get_date_range", "select_random_meals", "schedule_single_meal"]
```

### Tool Versioning
Support multiple versions of tools:

```python
tools.register("parse_date", ParseDateToolV2(), version="2.0")
result = await tools.execute_tool("parse_date", version="2.0", **kwargs)
```

## Conclusion

The tool-based architecture provides a professional, extensible foundation that:
- Maintains 100% backward compatibility
- Follows modern AI SDK patterns
- Enables future LLM reasoning capabilities
- Improves testing and maintenance

This positions the meal scheduling agent for growth while maintaining its current functionality.