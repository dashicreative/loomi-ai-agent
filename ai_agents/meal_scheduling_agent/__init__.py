"""
Meal Scheduling Agent - LLM-First Architecture

This simplified agent handles complex meal scheduling requests with:
- Multi-task scheduling: "Schedule pizza and egg tacos for tomorrow"
- Batch operations: "Schedule breakfast for the next 5 days"
- Random selection: "Pick some meals at random for Friday"
- Smart clarification: Asks for help only when truly ambiguous

Uses LLM-first architecture with direct storage operations for optimal performance.
"""

from .agent import EnhancedMealAgent
from .exceptions.meal_exceptions import (
    MealNotFoundError, 
    InvalidDateError,
    SchedulingConflictError,
    AmbiguousRequestError,
    LLMParsingError
)

# Public API - what external code imports
__all__ = [
    'EnhancedMealAgent',
    'MealNotFoundError',
    'InvalidDateError',
    'SchedulingConflictError',
    'AmbiguousRequestError',
    'LLMParsingError'
]

# Version info
__version__ = "3.0.0"  # LLM-first architecture with direct storage