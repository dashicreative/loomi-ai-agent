"""
Tool Orchestrator - Manages tool execution and coordination

This replaces direct function calls with tool-based operations,
providing a clean interface for the processors to use.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import date

from storage.local_storage import LocalStorage
from models.meal import Meal
from .production_tools import ToolRegistry
from .temporal_tool import TemporalExtractionTool


class ToolOrchestrator:
    """
    Orchestrates tool execution for meal scheduling operations
    
    This provides high-level methods that use tools internally,
    maintaining the same interface as the original direct calls.
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.tools = ToolRegistry(storage)
        self.temporal_tool = TemporalExtractionTool()
    
    async def get_available_meals(self) -> Tuple[List[str], List[Meal]]:
        """
        Get available meals using tools
        
        Returns:
            Tuple of (meal_names, meal_objects)
        """
        result = await self.tools.execute_tool("load_meals")
        
        if result["success"]:
            return result["meal_names"], result["meals"]
        else:
            return [], []
    
    async def find_and_schedule_meal(
        self,
        meal_name: str,
        target_date: str,
        meal_type: str,
        available_meals: List[str]
    ) -> Dict[str, Any]:
        """
        Find a meal and schedule it
        
        This combines multiple tool calls to accomplish the task.
        """
        # Step 1: Find the meal
        find_result = await self.tools.execute_tool(
            "find_meal_by_name",
            meal_name=meal_name,
            available_meals=available_meals
        )
        
        if not find_result["success"] or not find_result["found"]:
            # Suggest alternatives
            suggest_result = await self.tools.execute_tool(
                "suggest_alternatives",
                requested_meal=meal_name,
                available_meals=available_meals,
                max_suggestions=3
            )
            
            return {
                "success": False,
                "error": f"Meal '{meal_name}' not found",
                "suggestions": suggest_result.get("suggestions", [])
            }
        
        # Step 2: Schedule the meal
        schedule_result = await self.tools.execute_tool(
            "schedule_single_meal",
            meal=find_result["meal"],
            target_date=target_date,
            meal_type=meal_type
        )
        
        return schedule_result
    
    async def schedule_random_meal(
        self,
        available_meals: List[str],
        target_date: str,
        meal_type: str
    ) -> Dict[str, Any]:
        """
        Select a random meal and schedule it
        """
        # Step 1: Select random meal
        random_result = await self.tools.execute_tool(
            "select_random_meals",
            available_meals=available_meals,
            count=1
        )
        
        if not random_result["success"] or not random_result["selected_meals"]:
            return {
                "success": False,
                "error": "No meals available for random selection"
            }
        
        selected_meal_name = random_result["selected_meals"][0]
        
        # Step 2: Find and schedule the selected meal
        return await self.find_and_schedule_meal(
            meal_name=selected_meal_name,
            target_date=target_date,
            meal_type=meal_type,
            available_meals=available_meals
        )
    
    async def parse_date_string(self, date_string: str) -> Optional[str]:
        """
        Parse a natural language date to ISO format using temporal reasoning
        
        Returns:
            ISO date string or None if parsing fails
        """
        # Use the new temporal extraction tool
        result = await self.temporal_tool.execute(text=date_string)
        
        if result.success and result.data.get("success"):
            # For single day references, return the start date
            return result.data.get("start_date")
        else:
            # Fall back to legacy date parser if needed
            legacy_result = await self.tools.execute_tool(
                "parse_date",
                date_string=date_string
            )
            
            if legacy_result["success"]:
                return legacy_result["iso_date"]
            else:
                return None
    
    async def extract_temporal_context(self, text: str) -> Dict[str, Any]:
        """
        Extract full temporal context from natural language
        
        This provides richer temporal understanding than simple date parsing,
        including date ranges, confidence scores, and metadata.
        
        Args:
            text: Natural language text containing temporal references
            
        Returns:
            Dictionary with temporal context information
        """
        result = await self.temporal_tool.execute(text=text)
        
        if result.success:
            return result.data
        else:
            return {
                "success": False,
                "error": result.error or "Failed to extract temporal context"
            }
    
    async def get_batch_dates(self, pattern: str) -> List[str]:
        """
        Get a list of dates for batch scheduling
        
        Returns:
            List of ISO date strings
        """
        result = await self.tools.execute_tool(
            "get_date_range",
            pattern=pattern
        )
        
        if result["success"]:
            return result["dates"]
        return []
    
    async def extract_meal_type(self, request: str) -> str:
        """
        Extract meal type from request
        
        Returns:
            Meal type (defaults to "dinner")
        """
        result = await self.tools.execute_tool(
            "extract_meal_type",
            request=request
        )
        
        return result.get("meal_type", "dinner")
    
    async def execute_batch_schedule(
        self,
        tasks: List[Dict[str, Any]],
        available_meals: List[str]
    ) -> Dict[str, Any]:
        """
        Execute multiple scheduling tasks
        
        This replaces the batch executor's direct storage calls with tool usage.
        """
        successful_schedules = []
        errors = []
        
        for task in tasks:
            try:
                meal_name = task.get("meal_name")
                target_date = task.get("target_date")
                meal_type = task.get("meal_type", "dinner")
                is_random = task.get("is_random", False)
                
                if is_random or not meal_name:
                    # Schedule random meal
                    result = await self.schedule_random_meal(
                        available_meals=available_meals,
                        target_date=target_date,
                        meal_type=meal_type
                    )
                else:
                    # Schedule specific meal
                    result = await self.find_and_schedule_meal(
                        meal_name=meal_name,
                        target_date=target_date,
                        meal_type=meal_type,
                        available_meals=available_meals
                    )
                
                if result["success"]:
                    successful_schedules.append({
                        "meal_name": result.get("meal_name"),
                        "date": result.get("date"),
                        "meal_type": result.get("meal_type"),
                        "scheduled_meal_id": result.get("scheduled_meal_id")
                    })
                else:
                    errors.append({
                        "task": task,
                        "meal_name": meal_name,
                        "reason": result.get("error", "Unknown error"),
                        "suggestions": result.get("suggestions", [])
                    })
                    
            except Exception as e:
                errors.append({
                    "task": task,
                    "meal_name": task.get("meal_name", "Unknown"),
                    "reason": str(e)
                })
        
        return {
            "success": len(successful_schedules) > 0,
            "scheduled_count": len(successful_schedules),
            "schedules": successful_schedules,
            "errors": errors
        }
    
    async def clear_schedule(
        self,
        date_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear scheduled meals using the clear schedule tool"""
        clear_tool = self.tools.get_tool("clear_schedule")
        
        if not clear_tool:
            return {
                "success": False,
                "error": "Clear schedule tool not available",
                "cleared_count": 0
            }
        
        return await clear_tool.execute(
            date_range=date_range,
            start_date=start_date,
            end_date=end_date
        )