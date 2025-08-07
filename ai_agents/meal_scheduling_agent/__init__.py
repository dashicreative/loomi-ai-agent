"""
Meal Scheduling Agent - Main public API

This modular agent handles complex meal scheduling requests with:
- Multi-task scheduling: "Schedule pizza and egg tacos for tomorrow"
- Batch operations: "Schedule breakfast for the next 5 days"
- Random selection: "Pick some meals at random for Friday"
- Smart clarification: Asks for help only when truly ambiguous

Now available in two versions:
- EnhancedMealAgent: Original with direct function calls
- ToolBasedMealAgent: Tool-based architecture following AI SDK patterns
"""

from .agent import EnhancedMealAgent
from .tool_agent import ToolBasedMealAgent
from .core.complexity_detector import ComplexityDetector
from .parsers.parser_models import ScheduleTask, BatchScheduleAction
from .exceptions.meal_exceptions import (
    MealNotFoundError, 
    InvalidDateError,
    SchedulingConflictError,
    AmbiguousRequestError,
    LLMParsingError
)
from .tools import ToolRegistry, ToolOrchestrator

# Public API - what external code imports
__all__ = [
    'EnhancedMealAgent',
    'ToolBasedMealAgent',
    'ScheduleTask', 
    'BatchScheduleAction',
    'ComplexityDetector',
    'MealNotFoundError',
    'InvalidDateError',
    'SchedulingConflictError',
    'AmbiguousRequestError',
    'LLMParsingError',
    'ToolRegistry',
    'ToolOrchestrator'
]

# Version info
__version__ = "2.0.0"  # Bumped for tool-based architecture