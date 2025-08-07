"""
Response Utilities - AIResponse creation helpers
"""

from typing import List, Optional, Dict
from datetime import date, timedelta

from models.ai_models import AIResponse, AIAction, ActionType


class ResponseBuilder:
    """
    Utilities for building consistent AIResponse objects
    """
    
    @staticmethod
    def no_meals_error() -> AIResponse:
        """Create response when no meals are available"""
        return AIResponse(
            conversational_response="I don't see any saved meals. Please add some meals first before scheduling.",
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    @staticmethod
    def error_response(error_message: str) -> AIResponse:
        """Create error response"""
        return AIResponse(
            conversational_response=f"I encountered an error: {error_message}",
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    @staticmethod
    def unexpected_error(error: str) -> AIResponse:
        """Create unexpected error response"""
        return AIResponse(
            conversational_response=f"I had trouble processing your request. Error: {error}",
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    @staticmethod
    def clarification_response(clarification_message: str) -> AIResponse:
        """Create clarification request response"""
        return AIResponse(
            conversational_response=clarification_message,
            actions=[],
            model_used="enhanced_meal_agent"
        )
    
    @staticmethod
    def format_natural_date(iso_date: str) -> str:
        """
        Convert ISO date to natural language
        
        Args:
            iso_date: ISO formatted date string
            
        Returns:
            Natural language date (e.g., "tomorrow", "Friday")
        """
        try:
            target_date = date.fromisoformat(iso_date)
            today = date.today()
            days_diff = (target_date - today).days
            
            if days_diff == 0:
                return "today"
            elif days_diff == 1:
                return "tomorrow"
            elif days_diff == -1:
                return "yesterday"
            elif 2 <= days_diff <= 7:
                return target_date.strftime("%A")  # Weekday name
            else:
                return target_date.strftime("%B %d")  # Month day
        except:
            return iso_date
    
    @staticmethod
    def format_meal_confirmation(meal_name: str, target_date: str, meal_type: str) -> str:
        """
        Format a single meal scheduling confirmation
        
        Args:
            meal_name: Name of the scheduled meal
            target_date: ISO date string
            meal_type: Type of meal (breakfast, lunch, etc.)
            
        Returns:
            Formatted confirmation string
        """
        natural_date = ResponseBuilder.format_natural_date(target_date)
        return f"{meal_name} for {meal_type} {natural_date}"
    
    @staticmethod
    def build_success_response(scheduled_meals: List[Dict], 
                             failed_meals: Optional[List[Dict]] = None) -> AIResponse:
        """
        Build a success response with scheduled meals
        
        Args:
            scheduled_meals: List of successfully scheduled meals
            failed_meals: Optional list of failed scheduling attempts
            
        Returns:
            Complete AIResponse object
        """
        actions = []
        confirmations = []
        
        # Process successful meals
        for meal in scheduled_meals:
            actions.append(AIAction(
                type=ActionType.SCHEDULE_MEAL,
                parameters={
                    "meal_name": meal["meal_name"],
                    "date": meal["date"],
                    "meal_type": meal.get("meal_type", "dinner"),
                    "scheduled_meal_id": meal.get("scheduled_meal_id")
                }
            ))
            
            confirmation = ResponseBuilder.format_meal_confirmation(
                meal["meal_name"],
                meal["date"],
                meal.get("meal_type", "dinner")
            )
            confirmations.append(confirmation)
        
        # Build response message
        if len(confirmations) == 1:
            response = f"I've scheduled {confirmations[0]}."
        elif len(confirmations) > 1:
            response = "I've scheduled:\n" + "\n".join(f"• {conf}" for conf in confirmations)
        else:
            response = "I couldn't schedule any meals."
        
        # Add failed meal information if any
        if failed_meals:
            failed_messages = []
            for fail in failed_meals:
                if "reason" in fail:
                    failed_messages.append(f"• {fail['meal_name']}: {fail['reason']}")
            
            if failed_messages:
                response += "\n\nNote: " + "\n".join(failed_messages)
        
        return AIResponse(
            conversational_response=response,
            actions=actions,
            model_used="enhanced_meal_agent"
        )