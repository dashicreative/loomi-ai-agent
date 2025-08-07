"""
Meal Scheduling Agent - Main public API

This modular agent handles complex meal scheduling requests with:
- Multi-task scheduling: "Schedule pizza and egg tacos for tomorrow"
- Batch operations: "Schedule breakfast for the next 5 days"
- Random selection: "Pick some meals at random for Friday"
- Smart clarification: Asks for help only when truly ambiguous

Uses a modular architecture with tools for better maintainability and extensibility.
"""

from .agent import EnhancedMealAgent
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
__version__ = "2.0.0"  # Modular architecture with tools