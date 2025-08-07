"""
Tool-Based Agent - Main orchestrator using tool architecture

This is the tool-based version of the agent that uses tools instead of direct calls.
"""

from typing import List

from models.ai_models import ChatMessage, AIResponse
from storage.local_storage import LocalStorage
from .core.complexity_detector import ComplexityDetector
from .processors.tool_simple_processor import ToolSimpleProcessor
from .processors.tool_complex_processor import ToolComplexProcessor
from .tools.tool_orchestrator import ToolOrchestrator
from .utils.response_utils import ResponseBuilder
from .exceptions.meal_exceptions import MealAgentError


class ToolBasedMealAgent:
    """
    Tool-based meal scheduling agent that uses explicit tools for all operations
    
    This is the same as EnhancedMealAgent but uses tools instead of direct calls:
    - All storage operations go through tools
    - Tool orchestrator manages tool execution
    - Same interface and functionality as original
    """
    
    def __init__(self):
        self.storage = LocalStorage()
        self.orchestrator = ToolOrchestrator(self.storage)
        
        # Initialize all components with tool-based versions
        self.complexity_detector = ComplexityDetector()
        self.simple_processor = ToolSimpleProcessor(self.storage)
        self.complex_processor = ToolComplexProcessor(self.storage)
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