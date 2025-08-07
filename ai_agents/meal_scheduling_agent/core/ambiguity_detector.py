"""
Ambiguity Detection - Identifies when requests need clarification
"""

from typing import List, Dict


class AmbiguityDetector:
    """
    Detects when user requests are too vague and generates clarification questions
    """
    
    def __init__(self):
        self.quantity_numbers = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        
        self.specific_quantity_phrases = [
            "next week", "this week", "rest of the week", "weekend", 
            "daily", "each day", "tomorrow", "today"
        ]
        
        self.vague_quantity_words = [
            "some", "a few", "several", "multiple", "pick", "choose", "select"
        ]
        
        self.timeframe_indicators = [
            "next", "this", "tomorrow", "today", "weekend", "rest of",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "week", "weekly", "days", "daily"
        ]
        
        self.random_indicators = ["random", "some", "pick", "choose", "saved meals"]
    
    def detect_ambiguity(self, user_request: str, available_meals: List[str]) -> Dict:
        """
        Detect if request is too ambiguous and needs clarification
        
        Args:
            user_request: The user's request
            available_meals: List of available meal names
            
        Returns:
            Dictionary with ambiguity information
        """
        request_lower = user_request.lower()
        
        # Check for specific quantity indicators (how many exactly)
        has_specific_quantity = (
            any(word in request_lower for word in self.quantity_numbers) or 
            any(phrase in request_lower for phrase in self.specific_quantity_phrases)
        )
        
        # Check for vague quantity words that need clarification
        has_vague_quantity = (
            any(word in request_lower for word in self.vague_quantity_words) and 
            not any(word in request_lower for word in self.quantity_numbers)
        )
        
        # Check for date/time indicators (when to schedule)
        has_timeframe = any(word in request_lower for word in self.timeframe_indicators)
        
        # Check for specific meal indicators
        has_specific_meals = (
            any(meal.lower() in request_lower for meal in available_meals) or 
            not any(word in request_lower for word in self.random_indicators)
        )
        
        # Determine ambiguity level
        missing_elements = []
        
        # If vague quantity without specific timeframe = ambiguous
        if has_vague_quantity and not has_specific_quantity:
            missing_elements.append("specific_quantity")
        if not has_timeframe:
            missing_elements.append("timeframe")
            
        # High ambiguity = vague quantity without specific count
        is_highly_ambiguous = has_vague_quantity and not has_specific_quantity
        
        return {
            "is_ambiguous": is_highly_ambiguous,
            "missing": missing_elements,
            "has_specific_quantity": has_specific_quantity,
            "has_vague_quantity": has_vague_quantity,
            "has_timeframe": has_timeframe,
            "has_specific_meals": has_specific_meals
        }
    
    def generate_clarification_response(self, ambiguity_info: dict, user_request: str) -> str:
        """
        Generate helpful clarification questions
        
        Args:
            ambiguity_info: Dictionary from detect_ambiguity
            user_request: Original user request
            
        Returns:
            Clarification message
        """
        missing = ambiguity_info["missing"]
        
        clarifications = []
        if "specific_quantity" in missing:
            clarifications.append("how many meals would you like me to schedule")
        if "timeframe" in missing:
            clarifications.append("which days or time period you'd prefer")
            
        if len(clarifications) == 1:
            return f"I'd be happy to help! Could you let me know {clarifications[0]}?"
        else:
            return f"I'd be happy to help! Could you let me know {' and '.join(clarifications)}?"