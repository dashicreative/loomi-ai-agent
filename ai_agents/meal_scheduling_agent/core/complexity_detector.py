"""
Complexity Detection - Determines if request is simple or complex

This is now a thin wrapper around IntentClassifier for backward compatibility.
The real intelligence is in the IntentClassifier.
"""

from typing import List
from .intent_classifier import IntentClassifier, IntentType


class ComplexityDetector:
    """
    Analyzes user requests to determine processing complexity
    
    Simple requests: Direct meal + command + clear timeframe
    Complex requests: Multi-meal, batch operations, ambiguous requests
    """
    
    def __init__(self):
        # Use the new IntentClassifier for actual classification
        self.intent_classifier = IntentClassifier()
        
        # Define which intents are "simple" vs "complex"
        self.simple_intents = {
            IntentType.DIRECT_SCHEDULE,
            IntentType.VIEW_SCHEDULE,
            IntentType.LIST_MEALS
        }
        
        self.complex_intents = {
            IntentType.BATCH_SCHEDULE,
            IntentType.FILL_SCHEDULE,
            IntentType.CLEAR_SCHEDULE,
            IntentType.AMBIGUOUS_SCHEDULE,
            IntentType.NEEDS_CLARIFICATION,
            IntentType.UNKNOWN
        }
    
    async def detect(self, user_request: str, available_meals: List[str]) -> str:
        """
        Determine if this is a simple or complex request
        
        This method maintains backward compatibility while using
        the new IntentClassifier for intelligent classification.
        
        Args:
            user_request: The user's request string
            available_meals: List of available meal names
            
        Returns:
            "simple" or "complex"
        """
        # Use IntentClassifier for intelligent classification
        intent = await self.intent_classifier.classify(user_request, available_meals)
        
        # High confidence simple intents
        if intent.type in self.simple_intents and intent.confidence >= 0.8:
            return "simple"
        
        # Everything else is complex (safer default)
        return "complex"
    
    async def get_intent(self, user_request: str, available_meals: List[str]):
        """
        Get the full intent classification (new method for enhanced functionality)
        
        Returns the Intent object with confidence scores and entities.
        """
        return await self.intent_classifier.classify(user_request, available_meals)