"""
Main Agent Orchestrator - The conductor that coordinates all components
"""

from typing import List

from models.ai_models import ChatMessage, AIResponse
from storage.local_storage import LocalStorage
from .core.complexity_detector import ComplexityDetector
from .processors.simple_processor import SimpleProcessor
from .processors.complex_processor import ComplexProcessor
from .utils.response_utils import ResponseBuilder
from .exceptions.meal_exceptions import MealAgentError


class EnhancedMealAgent:
    """
    Main meal scheduling agent that orchestrates all components
    
    Handles both simple and complex scheduling patterns:
    - Single: "Schedule chicken for Tuesday" 
    - Multi: "Schedule pizza and tacos for tomorrow"
    - Batch: "Schedule breakfast for next 5 days"
    - Random: "Pick meals at random for Friday"
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        
        # Initialize all components
        self.complexity_detector = ComplexityDetector()
        self.simple_processor = SimpleProcessor(self.storage)
        self.complex_processor = ComplexProcessor(self.storage)
        self.response_builder = ResponseBuilder()
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Main entry point - Process meal management requests
        
        Args:
            message: The user's chat message
            
        Returns:
            AIResponse with conversational response and actions
        """
        try:
            # Get available meals
            meals = self.storage.load_meals()
            available_meals = [meal.name for meal in meals]
            
            if not available_meals:
                return self.response_builder.no_meals_error()
            
            # Detect complexity and route request
            complexity = await self.complexity_detector.detect(
                message.content, available_meals
            )
            
            if complexity == "simple":
                return await self.simple_processor.process(message, available_meals)
            else:
                return await self.complex_processor.process(message, available_meals)
                
        except MealAgentError as e:
            return self.response_builder.error_response(str(e))
        except Exception as e:
            return self.response_builder.unexpected_error(str(e))