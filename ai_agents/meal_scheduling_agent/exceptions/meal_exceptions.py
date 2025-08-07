"""
Custom exception classes for meal scheduling agent
"""


class MealAgentError(Exception):
    """Base exception for meal scheduling agent"""
    pass


class MealNotFoundError(MealAgentError):
    """Raised when a requested meal is not found"""
    def __init__(self, meal_name: str, available_meals: list = None):
        self.meal_name = meal_name
        self.available_meals = available_meals
        super().__init__(f"Meal '{meal_name}' not found in available meals")


class InvalidDateError(MealAgentError):
    """Raised when date parsing fails"""
    def __init__(self, date_string: str):
        self.date_string = date_string
        super().__init__(f"Could not parse date: '{date_string}'")


class SchedulingConflictError(MealAgentError):
    """Raised when there's a scheduling conflict"""
    def __init__(self, date: str, meal_type: str, existing_meal: str):
        self.date = date
        self.meal_type = meal_type
        self.existing_meal = existing_meal
        super().__init__(
            f"Scheduling conflict: {existing_meal} already scheduled for {meal_type} on {date}"
        )


class AmbiguousRequestError(MealAgentError):
    """Raised when request is too ambiguous to process"""
    def __init__(self, missing_info: list):
        self.missing_info = missing_info
        super().__init__(f"Request is ambiguous. Missing: {', '.join(missing_info)}")


class LLMParsingError(MealAgentError):
    """Raised when LLM fails to parse request"""
    def __init__(self, original_error: str):
        self.original_error = original_error
        super().__init__(f"LLM parsing failed: {original_error}")


class ToolExecutionError(MealAgentError):
    """Raised when a tool execution fails"""
    def __init__(self, tool_name: str, error: str):
        self.tool_name = tool_name
        self.error = error
        super().__init__(f"Tool '{tool_name}' execution failed: {error}")