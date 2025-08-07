"""
Enhanced Meal Agent - Main orchestrator with modular architecture

This is the main implementation using a modular, tool-based architecture.
"""

from typing import List

from models.ai_models import ChatMessage, AIResponse
from storage.local_storage import LocalStorage
from .core.complexity_detector import ComplexityDetector
from .processors.simple_processor import SimpleProcessor
from .processors.complex_processor import ComplexProcessor
from .tools.tool_orchestrator import ToolOrchestrator
from .utils.response_utils import ResponseBuilder
from .exceptions.meal_exceptions import MealAgentError


class EnhancedMealAgent:
    """
    Enhanced meal scheduling agent with modular architecture
    
    Handles complex meal scheduling requests with:
    - Multi-task scheduling: "Schedule pizza and egg tacos for tomorrow"
    - Batch operations: "Schedule breakfast for the next 5 days"
    - Random selection: "Pick some meals at random for Friday"
    - Smart clarification: Asks for help only when truly ambiguous
    
    Uses a modular, tool-based architecture for better maintainability and extensibility.
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        self.orchestrator = ToolOrchestrator(self.storage)
        
        # Initialize all components
        self.complexity_detector = ComplexityDetector()
        self.simple_processor = SimpleProcessor(self.storage)
        self.complex_processor = ComplexProcessor(self.storage)
        self.response_builder = ResponseBuilder()
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Main entry point - Process meal management requests using tools
        
        Args:
            message: The user's chat message
            
        Returns:
            AIResponse with conversational response and actions
        """
        try:
            # Get available meals using tools
            meal_names, meals = await self.orchestrator.get_available_meals()
            
            if not meal_names:
                return self.response_builder.no_meals_error()
            
            # Detect complexity and route request
            complexity = await self.complexity_detector.detect(
                message.content, meal_names
            )
            
            if complexity == "simple":
                return await self.simple_processor.process(message, meal_names)
            else:
                return await self.complex_processor.process(message, meal_names)
                
        except MealAgentError as e:
            return self.response_builder.error_response(str(e))
        except Exception as e:
            return self.response_builder.unexpected_error(str(e))
    
    def get_tool_info(self) -> dict:
        """
        Get information about available tools
        
        Returns:
            Dictionary with tool information
        """
        tools = self.orchestrator.tools.get_all_tools()
        tool_info = {}
        
        for name, tool in tools.items():
            tool_info[name] = {
                "name": tool.name,
                "description": tool.description
            }
        
        return {
            "total_tools": len(tools),
            "tools": tool_info
        }