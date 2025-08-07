# Meal Scheduling Agent - Modular Architecture

This is a modular implementation of the Enhanced Meal Agent, broken down into smaller, focused components following SDK best practices.

## Tool-Based Architecture

The Enhanced Meal Agent uses a modular, tool-based architecture following AI SDK patterns (similar to OpenAI and LangChain). This provides better separation of concerns and easier extensibility.

## Architecture Overview

```
meal_scheduling_agent/
├── agent.py                    # Main orchestrator
├── core/                       # Core decision logic
│   ├── complexity_detector.py  # Routes simple vs complex
│   └── ambiguity_detector.py   # Identifies unclear requests
├── parsers/                    # Request parsing
│   ├── llm_parser.py          # AI-powered parsing
│   ├── fallback_parser.py     # Rule-based fallback
│   └── parser_models.py       # Pydantic data models
├── processors/                 # Request processing
│   ├── simple_processor.py    # Single-meal scheduling
│   ├── complex_processor.py   # Multi-task handling  
│   └── batch_executor.py      # Batch operations
├── prompts/                    # Prompt management
│   └── templates.py           # LLM prompt templates
├── tools/                      # Tool-based operations
│   ├── production_tools.py    # Production-ready tools
│   ├── tool_registry.py       # Tool management
│   └── tool_orchestrator.py   # Tool execution
├── utils/                      # Utilities
│   ├── date_utils.py          # Date parsing
│   ├── meal_utils.py          # Meal selection
│   └── response_utils.py      # Response building
└── exceptions/                 # Custom exceptions
    └── meal_exceptions.py     # Error types
```

## Key Components

### 1. **Agent** (`agent.py`)
The main orchestrator that:
- Loads available meals
- Detects request complexity
- Routes to appropriate processor
- Handles errors gracefully

### 2. **Core Logic** (`core/`)
- **ComplexityDetector**: Analyzes requests to determine if they're simple or complex
- **AmbiguityDetector**: Identifies vague requests that need clarification

### 3. **Parsers** (`parsers/`)
- **LLMParser**: Uses Claude to parse complex multi-task requests
- **FallbackParser**: Rule-based parsing when LLM fails
- **ParserModels**: Pydantic models for type safety

### 4. **Processors** (`processors/`)
- **SimpleProcessor**: Handles single-meal scheduling directly
- **ComplexProcessor**: Manages multi-task, batch, and ambiguous requests
- **BatchExecutor**: Executes multiple scheduling operations

### 5. **Tools** (`tools/`)
- **ProductionTools**: 8 specialized tools for meal operations
- **ToolRegistry**: Manages and provides access to all tools
- **ToolOrchestrator**: Executes tools and handles batch operations

### 6. **Utilities** (`utils/`)
- **DateUtils**: Parse relative dates ("tomorrow", "next Friday")
- **MealUtils**: Random selection, fuzzy matching
- **ResponseBuilder**: Create consistent AIResponse objects

## Usage

```python
from ai_agents.meal_scheduling_agent import EnhancedMealAgent
from models.ai_models import ChatMessage

# Initialize agent
agent = EnhancedMealAgent()

# Process a request
message = ChatMessage(
    content="Schedule pizza and tacos for tomorrow",
    user_context={}
)
response = await agent.process(message)

print(response.conversational_response)
# "I've scheduled 2 meals for you:
#  • Pizza (dinner) tomorrow
#  • Egg Tacos (dinner) tomorrow"
```

## Request Types Supported

1. **Simple Requests**
   - "Schedule Pizza for tomorrow"
   - "Add chicken for dinner on Friday"

2. **Multi-Meal Requests**
   - "Schedule pizza and egg tacos for tomorrow"
   - "Add pasta and salad for lunch"

3. **Batch Scheduling**
   - "Schedule breakfast for the next 5 days"
   - "Schedule dinners for the rest of the week"

4. **Random Selection**
   - "Pick some meals at random for Friday"
   - "Choose a few meals for next week"

5. **Ambiguous Requests** (triggers clarification)
   - "Can you pick a meal for me"
   - "Schedule some meals"

## Benefits of Modular Design

1. **Single Responsibility**: Each component has one clear purpose
2. **Easy Testing**: Test components independently
3. **Better Debugging**: Smaller files are easier to understand
4. **Reusability**: Components can be used in other agents
5. **Professional Structure**: Follows SDK patterns
6. **Easy Extension**: Add new parsers/processors without touching core logic

## Adding New Features

To add a new feature:

1. **New Parser**: Add to `parsers/` if you need new parsing logic
2. **New Processor**: Add to `processors/` for new request types
3. **New Utils**: Add to `utils/` for shared functionality
4. **New Exceptions**: Add to `exceptions/` for specific error cases

The modular structure makes it easy to extend without breaking existing functionality.