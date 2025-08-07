"""
Complexity Detection - Determines if request is simple or complex
"""

from typing import List


class ComplexityDetector:
    """
    Analyzes user requests to determine processing complexity
    
    Simple requests: Direct meal + command + clear timeframe
    Complex requests: Multi-meal, batch operations, ambiguous requests
    """
    
    def __init__(self):
        self.simple_timeframes = [
            "today", "tomorrow", "tonight",
            "monday", "tuesday", "wednesday", "thursday", 
            "friday", "saturday", "sunday",
            "next monday", "next tuesday", "next wednesday", "next thursday", 
            "next friday", "next saturday", "next sunday"
        ]
        
        self.basic_commands = ["schedule", "reschedule", "add"]
        
        self.complexity_markers = [
            " and ",  # multiple items
            "pick", "choose", "select", "random",  # ambiguous selection
            "some", "a few", "several", "multiple",  # vague quantities
            "next 5 days", "next week", "rest of week", "this week",  # batch operations
            "meals for", "dinners for", "breakfasts for"  # plural operations
        ]
    
    async def detect(self, user_request: str, available_meals: List[str]) -> str:
        """
        Determine if this is a simple or complex request
        
        Simple requests have:
        - A specific meal name from saved meals
        - Basic scheduling commands (schedule, reschedule)  
        - Clear date/time specification
        - Single action intent
        
        Everything else defaults to complex for robust handling
        
        Args:
            user_request: The user's request string
            available_meals: List of available meal names
            
        Returns:
            "simple" or "complex"
        """
        request_lower = user_request.lower()
        
        # Check for simple request criteria
        has_specific_meal = any(meal.lower() in request_lower for meal in available_meals)
        has_basic_command = any(cmd in request_lower for cmd in self.basic_commands)
        has_clear_timeframe = any(time in request_lower for time in self.simple_timeframes)
        
        # Simple request indicators
        simple_indicators = [
            # Single meal scheduling patterns
            has_specific_meal and has_basic_command and has_clear_timeframe,
            # Very clear single-action patterns
            "schedule" in request_lower and has_specific_meal and ("today" in request_lower or "tomorrow" in request_lower),
        ]
        
        # If it clearly matches simple patterns, classify as simple
        if any(simple_indicators):
            # But exclude if it has complexity markers
            has_complexity_markers = any(marker in request_lower for marker in self.complexity_markers)
            
            if not has_complexity_markers:
                return "simple"
        
        # Default to complex for robust handling
        return "complex"