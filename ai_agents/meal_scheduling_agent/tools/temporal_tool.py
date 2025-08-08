"""
Temporal Tool - Universal date/time extraction tool using TemporalReasoner

This tool provides consistent temporal understanding across all agent operations.
"""

from typing import Dict, Any, Optional
from datetime import date, timedelta

from ..core.base_tool import BaseTool, ToolResult, ToolResultStatus
from ..core.temporal_reasoner import TemporalReasoner, TemporalReference


class TemporalExtractionTool(BaseTool):
    """
    Tool for extracting and interpreting temporal information from natural language
    
    This tool uses the TemporalReasoner to provide consistent date/time understanding
    across all agent functions.
    """
    
    def __init__(self):
        super().__init__(
            name="extract_temporal",
            description="Extract and interpret dates/times from natural language"
        )
        self.temporal_reasoner = TemporalReasoner()
    
    async def _execute_impl(self, **kwargs) -> ToolResult:
        """
        Extract temporal information from text
        
        Args:
            text: The text to extract temporal information from
            context_date: Optional reference date for relative calculations
            
        Returns:
            ToolResult with extracted temporal context
        """
        text = kwargs.get("text", "")
        context_date = kwargs.get("context_date")
        
        if not text:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="No text provided for temporal extraction"
            )
        
        # Use custom reference date if provided
        if context_date:
            self.temporal_reasoner = TemporalReasoner(reference_date=context_date)
        
        # Extract temporal context
        temporal_context = self.temporal_reasoner.interpret(text)
        
        # Convert to result format
        start_date, end_date = temporal_context.get_date_range()
        
        result_data = {
            "success": True,
            "reference_type": temporal_context.reference_type.value,
            "confidence": temporal_context.confidence,
            "start_date": start_date,
            "end_date": end_date,
            "is_single_day": temporal_context.is_single_day(),
            "description": self.temporal_reasoner.describe_context(temporal_context),
            "metadata": temporal_context.metadata,
            "original_phrase": temporal_context.original_phrase
        }
        
        # Add specific interpretations for common use cases
        if temporal_context.reference_type == TemporalReference.ALL_TIME:
            result_data["date_range"] = "all"
        elif temporal_context.reference_type == TemporalReference.RELATIVE_WEEK:
            if temporal_context.metadata.get("week") == "this":
                result_data["date_range"] = "week"
            elif temporal_context.metadata.get("week") == "next":
                result_data["date_range"] = "next_week"
        elif temporal_context.reference_type == TemporalReference.RELATIVE_MONTH:
            if temporal_context.metadata.get("month") == "this":
                result_data["date_range"] = "month"
        
        # Handle ambiguous cases
        if temporal_context.reference_type == TemporalReference.AMBIGUOUS:
            result_data["needs_clarification"] = True
            result_data["success"] = False
            result_data["error"] = f"Could not interpret temporal reference: '{text}'"
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data=result_data
        )
    
    def _validate_params(self, **kwargs) -> Optional[str]:
        """Validate input parameters"""
        if "text" not in kwargs:
            return "Missing required parameter: text"
        return None


class DateRangeTool(BaseTool):
    """
    Tool for working with date ranges and performing date calculations
    """
    
    def __init__(self):
        super().__init__(
            name="date_range",
            description="Calculate and manipulate date ranges"
        )
        self.temporal_reasoner = TemporalReasoner()
    
    async def _execute_impl(self, **kwargs) -> ToolResult:
        """
        Perform date range operations
        
        Args:
            operation: Type of operation (expand, contract, shift, etc.)
            start_date: Starting date
            end_date: Ending date
            days: Number of days for operations
            
        Returns:
            ToolResult with date range information
        """
        operation = kwargs.get("operation", "info")
        start_date_str = kwargs.get("start_date")
        end_date_str = kwargs.get("end_date")
        days = kwargs.get("days", 0)
        
        try:
            # Parse dates if provided
            start_date = date.fromisoformat(start_date_str) if start_date_str else None
            end_date = date.fromisoformat(end_date_str) if end_date_str else None
            
            result_data = {}
            
            if operation == "info":
                # Provide information about the date range
                if start_date and end_date:
                    delta = (end_date - start_date).days + 1
                    result_data = {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "days": delta,
                        "weeks": delta / 7,
                        "includes_weekend": self._includes_weekend(start_date, end_date)
                    }
            
            elif operation == "expand":
                # Expand the date range by specified days
                if start_date and end_date:
                    new_start = start_date - timedelta(days=days)
                    new_end = end_date + timedelta(days=days)
                    result_data = {
                        "start_date": new_start.isoformat(),
                        "end_date": new_end.isoformat(),
                        "expanded_by": days * 2
                    }
            
            elif operation == "shift":
                # Shift the entire range by specified days
                if start_date and end_date:
                    new_start = start_date + timedelta(days=days)
                    new_end = end_date + timedelta(days=days)
                    result_data = {
                        "start_date": new_start.isoformat(),
                        "end_date": new_end.isoformat(),
                        "shifted_by": days
                    }
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                data=result_data
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Date operation failed: {str(e)}"
            )
    
    def _includes_weekend(self, start_date: date, end_date: date) -> bool:
        """Check if date range includes weekend days"""
        current = start_date
        while current <= end_date:
            if current.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return True
            current += timedelta(days=1)
        return False
    
    def _validate_params(self, **kwargs) -> Optional[str]:
        """Validate input parameters"""
        operation = kwargs.get("operation")
        if operation not in ["info", "expand", "shift", None]:
            return f"Invalid operation: {operation}"
        return None