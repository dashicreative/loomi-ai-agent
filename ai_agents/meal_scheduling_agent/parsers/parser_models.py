"""
Parser Models - Pydantic models for structured parsing
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator, model_validator
from datetime import date


class ScheduleTask(BaseModel):
    """
    Represents a single scheduling task
    """
    meal_name: Optional[str] = Field(None, description="Exact meal name from available meals")
    target_date: str = Field(..., description="Target date in YYYY-MM-DD format")
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] = Field(
        default="dinner", 
        description="Type of meal"
    )
    is_random: bool = Field(False, description="Whether to pick a random meal")
    
    @validator('target_date')
    def validate_date_format(cls, v):
        """Ensure date is in correct format"""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD")
    
    @model_validator(mode='after')
    def validate_meal_name_or_random(self):
        """Ensure either meal_name is provided or is_random is True"""
        if not self.meal_name and not self.is_random:
            raise ValueError("Either meal_name must be provided or is_random must be True")
        return self


class BatchScheduleAction(BaseModel):
    """
    Represents a batch of scheduling tasks
    """
    tasks: List[ScheduleTask] = Field(..., description="List of scheduling tasks")
    request_type: Literal[
        "single", 
        "multi_meal", 
        "batch_days", 
        "random_selection",
        "mixed",
        "fallback_parsed"
    ] = Field(..., description="Type of scheduling request")
    
    @validator('tasks')
    def validate_tasks_not_empty(cls, v):
        """Ensure at least one task exists"""
        if not v:
            raise ValueError("At least one task is required")
        return v


class ParsedRequest(BaseModel):
    """
    Complete parsed request with metadata
    """
    action: BatchScheduleAction
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Parsing confidence score")
    parsing_method: Literal["llm", "fallback", "simple"] = Field(..., description="Method used for parsing")
    helpful_response: Optional[str] = Field(None, description="Helpful response for errors")


class AmbiguityInfo(BaseModel):
    """
    Information about request ambiguity
    """
    is_ambiguous: bool = Field(..., description="Whether request is ambiguous")
    missing: List[str] = Field(default_factory=list, description="Missing information elements")
    has_meals: bool = Field(..., description="Whether any meals were mentioned")
    has_time: bool = Field(..., description="Whether time/date was mentioned")
    vague_quantity: bool = Field(False, description="Whether quantity is vague")
    clarification_type: Optional[Literal[
        "no_meals",
        "no_time", 
        "vague_quantity",
        "multiple_missing"
    ]] = Field(None, description="Type of clarification needed")