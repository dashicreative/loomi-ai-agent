"""
Tool-Based Batch Executor - Executes multiple scheduling operations using tools

This replaces the original batch_executor.py with a tool-based version.
"""

from typing import Dict, Any, List

from storage.local_storage import LocalStorage
from ..parsers.parser_models import BatchScheduleAction
from ..tools.tool_orchestrator import ToolOrchestrator


class ToolBatchExecutor:
    """
    Executes batch scheduling operations using tools instead of direct storage calls
    """
    
    def __init__(self, storage: LocalStorage):
        self.storage = storage
        self.orchestrator = ToolOrchestrator(storage)
    
    async def execute_batch_schedule(
        self, 
        batch_action: BatchScheduleAction, 
        available_meals: List[str]
    ) -> Dict[str, Any]:
        """
        Execute multiple scheduling tasks using tools
        
        Args:
            batch_action: The batch of tasks to execute
            available_meals: List of available meal names
            
        Returns:
            Dictionary with execution results
        """
        # Convert BatchScheduleAction tasks to dicts for the orchestrator
        tasks = []
        for task in batch_action.tasks:
            tasks.append({
                "meal_name": task.meal_name,
                "target_date": task.target_date,
                "meal_type": task.meal_type,
                "is_random": task.is_random
            })
        
        # Use the orchestrator to execute all tasks
        result = await self.orchestrator.execute_batch_schedule(tasks, available_meals)
        
        # Add request type to the result
        result["request_type"] = batch_action.request_type
        
        return result