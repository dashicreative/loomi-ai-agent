"""
Conversation Context Manager - Tracks conversation state and suggestions

Handles context for follow-up responses like "yes", "that one", "the first one", etc.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ContextType(Enum):
    """Types of conversation context"""
    MEAL_SUGGESTIONS = "meal_suggestions"
    DATE_CLARIFICATION = "date_clarification"
    MEAL_TYPE_CLARIFICATION = "meal_type_clarification"
    CONFIRMATION_PENDING = "confirmation_pending"


@dataclass
class ConversationContext:
    """Stores conversation context for a user session"""
    context_type: ContextType
    data: Dict[str, Any]
    timestamp: datetime
    expires_at: datetime
    user_request: str  # The original request that created this context
    
    def is_expired(self) -> bool:
        """Check if context has expired"""
        return datetime.now() > self.expires_at
    
    def get_suggestions(self) -> Optional[List[str]]:
        """Get meal suggestions if this is a meal suggestions context"""
        if self.context_type == ContextType.MEAL_SUGGESTIONS:
            return self.data.get("suggestions", [])
        return None


class ConversationContextManager:
    """
    Manages conversation context for handling follow-up responses
    
    Features:
    - Stores suggestions made to users
    - Tracks context for ambiguous responses
    - Handles timeout/expiration of context
    - Maps follow-up responses to previous suggestions
    """
    
    def __init__(self, context_ttl_minutes: int = 5):
        """
        Initialize context manager
        
        Args:
            context_ttl_minutes: How long to keep context alive (default 5 minutes)
        """
        self.contexts: Dict[str, ConversationContext] = {}  # user_id -> context
        self.context_ttl = timedelta(minutes=context_ttl_minutes)
    
    def store_suggestions(
        self, 
        user_id: str, 
        suggestions: List[str], 
        original_request: str,
        requested_meal: Optional[str] = None,
        date: Optional[str] = None,
        meal_type: Optional[str] = None
    ) -> None:
        """
        Store meal suggestions for a user
        
        Args:
            user_id: Unique user identifier
            suggestions: List of meal suggestions offered
            original_request: The user's original request
            requested_meal: The meal they originally asked for
            date: The date they wanted to schedule for
            meal_type: The meal type (breakfast/lunch/dinner)
        """
        context = ConversationContext(
            context_type=ContextType.MEAL_SUGGESTIONS,
            data={
                "suggestions": suggestions,
                "requested_meal": requested_meal,
                "date": date,
                "meal_type": meal_type
            },
            timestamp=datetime.now(),
            expires_at=datetime.now() + self.context_ttl,
            user_request=original_request
        )
        self.contexts[user_id] = context
    
    def get_context(self, user_id: str) -> Optional[ConversationContext]:
        """
        Get active context for a user
        
        Args:
            user_id: Unique user identifier
            
        Returns:
            Active context or None if expired/not found
        """
        context = self.contexts.get(user_id)
        
        if context and not context.is_expired():
            return context
        
        # Clean up expired context
        if context:
            del self.contexts[user_id]
        
        return None
    
    def resolve_affirmative_response(
        self, 
        user_id: str, 
        response: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve an affirmative response (yes, ok, sure) to previous context
        
        Args:
            user_id: Unique user identifier
            response: The user's response
            
        Returns:
            Resolved action data or None if no context
        """
        context = self.get_context(user_id)
        if not context:
            return None
        
        response_lower = response.lower().strip()
        
        # Check for affirmative responses
        affirmative_responses = {
            "yes", "yeah", "yep", "sure", "ok", "okay", 
            "sounds good", "that works", "perfect", "great"
        }
        
        if any(affirm in response_lower for affirm in affirmative_responses):
            if context.context_type == ContextType.MEAL_SUGGESTIONS:
                suggestions = context.get_suggestions()
                if suggestions:
                    # Default to first suggestion for simple affirmative
                    return {
                        "action": "schedule",
                        "meal_name": suggestions[0],
                        "date": context.data.get("date"),
                        "meal_type": context.data.get("meal_type"),
                        "original_request": context.user_request
                    }
        
        # Check for specific selection (e.g., "the first one", "pizza")
        return self._resolve_specific_selection(context, response)
    
    def _resolve_specific_selection(
        self, 
        context: ConversationContext, 
        response: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve specific selections like "the first one" or meal names
        
        Args:
            context: Active conversation context
            response: User's response
            
        Returns:
            Resolved action data or None
        """
        response_lower = response.lower().strip()
        suggestions = context.get_suggestions()
        
        if not suggestions:
            return None
        
        # Check for ordinal selections
        ordinal_map = {
            "first": 0, "1st": 0, "one": 0, "1": 0,
            "second": 1, "2nd": 1, "two": 1, "2": 1,
            "third": 2, "3rd": 2, "three": 2, "3": 2,
            "last": -1
        }
        
        for ordinal, index in ordinal_map.items():
            if ordinal in response_lower:
                try:
                    selected_meal = suggestions[index]
                    return {
                        "action": "schedule",
                        "meal_name": selected_meal,
                        "date": context.data.get("date"),
                        "meal_type": context.data.get("meal_type"),
                        "original_request": context.user_request
                    }
                except IndexError:
                    continue
        
        # Check if response contains one of the suggested meals
        for suggestion in suggestions:
            if suggestion.lower() in response_lower:
                return {
                    "action": "schedule",
                    "meal_name": suggestion,
                    "date": context.data.get("date"),
                    "meal_type": context.data.get("meal_type"),
                    "original_request": context.user_request
                }
        
        return None
    
    def clear_context(self, user_id: str) -> None:
        """Clear context for a user"""
        if user_id in self.contexts:
            del self.contexts[user_id]
    
    def clear_expired_contexts(self) -> None:
        """Remove all expired contexts"""
        expired_users = [
            user_id for user_id, context in self.contexts.items()
            if context.is_expired()
        ]
        for user_id in expired_users:
            del self.contexts[user_id]