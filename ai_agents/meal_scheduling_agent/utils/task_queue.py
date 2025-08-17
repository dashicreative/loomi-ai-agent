"""
Task Queue Management for Multi-Task Meal Scheduling

This module provides systematic task persistence and tracking for the meal scheduling agent,
following LLM-first philosophy where the LLM orchestrates task queue operations while 
the queue provides reliable state persistence.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TaskType(Enum):
    SCHEDULE_MEAL = "schedule_meal"
    CLEAR_SCHEDULE = "clear_schedule"
    VIEW_SCHEDULE = "view_schedule"

@dataclass
class TaskDetails:
    """Individual task within a multi-task request"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType = TaskType.SCHEDULE_MEAL
    status: TaskStatus = TaskStatus.PENDING
    
    # Scheduling details
    meal_name: Optional[str] = None
    date: Optional[str] = None  # ISO format YYYY-MM-DD
    meal_occasion: Optional[str] = None  # breakfast, lunch, dinner, snack
    
    # Context preservation
    original_request_part: str = ""  # "dinner tomorrow"
    clarification_needed: bool = False
    clarification_reason: str = ""
    
    # Lifecycle tracking
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def update(self, **kwargs):
        """Update task details and timestamp"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()

@dataclass 
class MultiTaskRequest:
    """Container for related tasks from a single user request"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_request: str = ""
    tasks: List[TaskDetails] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def pending_tasks(self) -> List[TaskDetails]:
        return [task for task in self.tasks if task.status == TaskStatus.PENDING]
    
    @property 
    def current_task(self) -> Optional[TaskDetails]:
        """Get the first pending task (queue-like processing)"""
        pending = self.pending_tasks
        return pending[0] if pending else None
    
    @property
    def is_complete(self) -> bool:
        return all(task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED] for task in self.tasks)

class TaskQueueManager:
    """
    LLM-First Task Queue Management
    
    Provides systematic task persistence while allowing LLM to make all 
    intelligent decisions about task creation, processing, and completion.
    """
    
    def __init__(self):
        # In-memory storage: user_id -> MultiTaskRequest
        # TODO: Could be enhanced with file-based persistence later
        self.user_requests: Dict[str, Optional[MultiTaskRequest]] = {}
    
    def create_multi_task_request(self, user_id: str, original_request: str) -> str:
        """
        Create new multi-task request container
        
        Args:
            user_id: User identifier
            original_request: Original user request text
            
        Returns:
            request_id: Unique identifier for this multi-task request
        """
        request = MultiTaskRequest(original_request=original_request)
        self.user_requests[user_id] = request
        return request.request_id
    
    def add_task(self, user_id: str, task_details: TaskDetails) -> str:
        """
        Add individual task to user's current multi-task request
        
        Args:
            user_id: User identifier  
            task_details: Task information
            
        Returns:
            task_id: Unique identifier for this task
        """
        if user_id not in self.user_requests or self.user_requests[user_id] is None:
            # Create new request if none exists
            self.create_multi_task_request(user_id, task_details.original_request_part)
        
        request = self.user_requests[user_id]
        request.tasks.append(task_details)
        return task_details.task_id
    
    def get_current_task(self, user_id: str) -> Optional[TaskDetails]:
        """
        Get the current task being processed (first pending task)
        
        Args:
            user_id: User identifier
            
        Returns:
            Current task or None if no pending tasks
        """
        if user_id not in self.user_requests or self.user_requests[user_id] is None:
            return None
        
        return self.user_requests[user_id].current_task
    
    def get_pending_tasks(self, user_id: str) -> List[TaskDetails]:
        """
        Get all pending tasks for user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of pending tasks
        """
        if user_id not in self.user_requests or self.user_requests[user_id] is None:
            return []
        
        return self.user_requests[user_id].pending_tasks
    
    def complete_task(self, user_id: str, task_id: str) -> bool:
        """
        Mark task as completed
        
        Args:
            user_id: User identifier
            task_id: Task to complete
            
        Returns:
            True if task was found and completed
        """
        request = self.user_requests.get(user_id)
        if not request:
            return False
        
        for task in request.tasks:
            if task.task_id == task_id:
                task.status = TaskStatus.COMPLETED
                task.updated_at = datetime.now()
                return True
        
        return False
    
    def update_task(self, user_id: str, task_id: str, **updates) -> bool:
        """
        Update task details
        
        Args:
            user_id: User identifier
            task_id: Task to update
            **updates: Field updates
            
        Returns:
            True if task was found and updated
        """
        request = self.user_requests.get(user_id)
        if not request:
            return False
        
        for task in request.tasks:
            if task.task_id == task_id:
                task.update(**updates)
                return True
        
        return False
    
    def clear_completed_tasks(self, user_id: str) -> int:
        """
        Remove completed tasks from queue
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of tasks cleared
        """
        request = self.user_requests.get(user_id)
        if not request:
            return 0
        
        initial_count = len(request.tasks)
        request.tasks = [task for task in request.tasks 
                        if task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]]
        
        return initial_count - len(request.tasks)
    
    def clear_all_tasks(self, user_id: str) -> bool:
        """
        Clear all tasks for user (conversation reset)
        
        Args:
            user_id: User identifier
            
        Returns:
            True if tasks were cleared
        """
        if user_id in self.user_requests:
            self.user_requests[user_id] = None
            return True
        return False
    
    def get_queue_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get summary of user's task queue state for LLM context
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with queue state information
        """
        request = self.user_requests.get(user_id)
        if not request:
            return {
                "has_active_request": False,
                "current_task": None,
                "pending_count": 0,
                "tasks": []
            }
        
        return {
            "has_active_request": True,
            "original_request": request.original_request,
            "current_task": request.current_task,
            "pending_count": len(request.pending_tasks),
            "total_tasks": len(request.tasks),
            "is_complete": request.is_complete,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "meal_name": task.meal_name,
                    "date": task.date,
                    "occasion": task.meal_occasion,
                    "original_part": task.original_request_part,
                    "needs_clarification": task.clarification_needed
                }
                for task in request.tasks
            ]
        }
    
    def parse_multi_task_request(self, user_id: str, request_text: str, entities: Dict[str, Any]) -> List[str]:
        """
        Helper method to parse multi-task request into individual tasks
        LLM will call this to break down complex requests
        
        Args:
            user_id: User identifier
            request_text: Original request text
            entities: Parsed entities from LLM (dates, meal_types, etc.)
            
        Returns:
            List of task_ids created
        """
        # Create new multi-task request
        request_id = self.create_multi_task_request(user_id, request_text)
        
        # Extract task components from entities
        dates = entities.get("dates", [])
        meal_types = entities.get("meal_types", [])
        meal_names = entities.get("meal_names", [])
        
        task_ids = []
        
        # Create individual tasks based on entity combinations
        for i, date in enumerate(dates):
            meal_type = meal_types[i] if i < len(meal_types) else "dinner"
            meal_name = meal_names[i] if i < len(meal_names) else None
            
            task = TaskDetails(
                task_type=TaskType.SCHEDULE_MEAL,
                meal_name=meal_name,
                date=date,
                meal_occasion=meal_type,
                original_request_part=f"{meal_type} {date}",
                clarification_needed=(meal_name is None)
            )
            
            task_id = self.add_task(user_id, task)
            task_ids.append(task_id)
        
        return task_ids