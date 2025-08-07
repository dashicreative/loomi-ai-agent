"""
Intent Classifier - Enhanced intent classification with confidence scoring

Replaces the basic ComplexityDetector with a full intent classification system.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import date
import re

from ..config import IntentType, IntentConfig, get_config
from ..utils.date_utils import DateUtils
from ..utils.meal_utils import MealUtils


@dataclass
class Intent:
    """Classified intent with confidence and extracted entities"""
    type: IntentType
    confidence: float
    entities: Dict[str, Any]
    needs_clarification: bool
    raw_request: str
    
    # Additional metadata for efficiency
    cache_key: Optional[str] = None
    requires_llm: bool = False
    
    def __repr__(self) -> str:
        return f"Intent(type={self.type.value}, confidence={self.confidence:.2f}, entities={list(self.entities.keys())})"


@dataclass
class Entity:
    """Extracted entity with metadata"""
    name: str
    value: Any
    confidence: float
    source: str  # "rule" or "llm"


class IntentClassifier:
    """
    Enhanced intent classification with confidence scoring
    
    Features:
    - Rule-based classification for efficiency (reduces LLM calls)
    - Confidence scoring based on entity extraction
    - Clarification detection
    - Entity extraction with validation
    """
    
    def __init__(self):
        self.config = get_config()
        self.intent_config = IntentConfig()
        self.date_utils = DateUtils()
        self.meal_utils = MealUtils()
        
        # Compile regex patterns for efficiency
        self._compile_patterns()
        
    def _compile_patterns(self):
        """Compile regex patterns for entity extraction"""
        # Date patterns
        self.date_patterns = {
            "today": re.compile(r'\b(today|tonight)\b', re.I),
            "tomorrow": re.compile(r'\b(tomorrow)\b', re.I),
            "weekday": re.compile(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.I),
            "next_weekday": re.compile(r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.I),
            "date_range": re.compile(r'\b(next\s+\d+\s+days?|this\s+week|rest\s+of\s+week|next\s+week)\b', re.I)
        }
        
        # Meal type patterns
        self.meal_type_pattern = re.compile(r'\b(breakfast|lunch|dinner|snack)s?\b', re.I)
        
        # Action patterns
        self.action_patterns = {
            "schedule": re.compile(r'\b(schedule|add|plan|set)\b', re.I),
            "clear": re.compile(r'\b(clear|remove|delete|cancel|unschedule)\b', re.I),
            "view": re.compile(r'\b(view|show|what\'s|scheduled|planned)\b', re.I),
            "list": re.compile(r'\b(list|available|what meals|my meals|saved meals)\b', re.I)
        }
    
    async def classify(self, request: str, available_meals: List[str]) -> Intent:
        """
        Classify user request into intent with confidence scoring
        
        Process:
        1. Extract entities using rules (fast)
        2. Determine intent type based on entities and triggers
        3. Calculate confidence score
        4. Determine if clarification needed
        """
        # First, try rule-based classification
        entities = self._extract_entities(request, available_meals)
        intent_type = self._determine_intent_type(request, entities)
        confidence = self._calculate_confidence(intent_type, entities, request)
        
        # Check if clarification needed
        needs_clarification = self._needs_clarification(intent_type, entities, confidence)
        
        # Determine if LLM required
        requires_llm = self.intent_config.requires_llm(intent_type)
        
        return Intent(
            type=intent_type,
            confidence=confidence,
            entities=entities,
            needs_clarification=needs_clarification,
            raw_request=request,
            requires_llm=requires_llm
        )
    
    def _extract_entities(self, request: str, available_meals: List[str]) -> Dict[str, Any]:
        """Extract entities from request using rules"""
        entities = {}
        request_lower = request.lower()
        
        # Extract action
        for action_type, pattern in self.action_patterns.items():
            if pattern.search(request):
                entities["action"] = action_type
                break
        
        # Extract meal names
        found_meals = []
        for meal in available_meals:
            if meal.lower() in request_lower:
                found_meals.append(meal)
        
        if found_meals:
            if len(found_meals) == 1:
                entities["meal_name"] = found_meals[0]
            else:
                entities["meal_names"] = found_meals
        
        # Extract dates
        date_info = self._extract_date_info(request)
        if date_info:
            entities.update(date_info)
        
        # Extract meal type
        meal_type_match = self.meal_type_pattern.search(request)
        if meal_type_match:
            entities["meal_type"] = meal_type_match.group(1).lower()
        
        # Extract quantities/counts
        count_match = re.search(r'\b(\d+)\s+(meals?|dinners?|lunches?|breakfasts?)\b', request, re.I)
        if count_match:
            entities["count"] = int(count_match.group(1))
        
        # Check for random/selection indicators
        if any(word in request_lower for word in ["random", "pick", "choose", "select", "some"]):
            entities["is_random"] = True
        
        return entities
    
    def _extract_date_info(self, request: str) -> Dict[str, Any]:
        """Extract date-related entities"""
        date_info = {}
        
        # Check for specific dates
        if self.date_patterns["today"].search(request):
            date_info["date"] = date.today().isoformat()
        elif self.date_patterns["tomorrow"].search(request):
            date_info["date"] = self.date_utils.get_tomorrow()
        elif match := self.date_patterns["next_weekday"].search(request):
            weekday = match.group(1)
            date_info["date"] = self.date_utils.get_next_weekday(weekday)
        elif match := self.date_patterns["weekday"].search(request):
            weekday = match.group(1)
            date_info["date"] = self.date_utils.get_upcoming_weekday(weekday)
        
        # Check for date ranges
        if match := self.date_patterns["date_range"].search(request):
            range_text = match.group(0)
            date_info["date_range"] = range_text
            
            # Parse specific ranges
            if "next" in range_text and "days" in range_text:
                days_match = re.search(r'(\d+)', range_text)
                if days_match:
                    date_info["days_count"] = int(days_match.group(1))
            elif "this week" in range_text:
                date_info["range_type"] = "current_week"
            elif "next week" in range_text:
                date_info["range_type"] = "next_week"
            elif "rest of week" in range_text:
                date_info["range_type"] = "rest_of_week"
        
        return date_info
    
    def _determine_intent_type(self, request: str, entities: Dict[str, Any]) -> IntentType:
        """Determine intent type based on entities and triggers"""
        request_lower = request.lower()
        
        # First check by triggers (most reliable)
        intent_type = self.intent_config.get_intent_by_triggers(request)
        if intent_type:
            return intent_type
        
        # Then check by entity combinations
        action = entities.get("action", "")
        
        # Clear operations
        if action == "clear":
            return IntentType.CLEAR_SCHEDULE
        
        # View operations
        if action == "view" or "what's scheduled" in request_lower:
            return IntentType.VIEW_SCHEDULE
        
        # List operations
        if action == "list" or "available meals" in request_lower:
            return IntentType.LIST_MEALS
        
        # Fill operations
        if "fill" in request_lower and ("schedule" in request_lower or "week" in request_lower):
            return IntentType.FILL_SCHEDULE
        
        # Scheduling operations
        if action == "schedule" or not action:
            # Check for batch indicators
            if "date_range" in entities or "days_count" in entities:
                return IntentType.BATCH_SCHEDULE
            
            # Check for direct scheduling
            if "meal_name" in entities and "date" in entities:
                return IntentType.DIRECT_SCHEDULE
            
            # Check for ambiguous scheduling
            if entities.get("is_random") or any(word in request_lower for word in ["some", "help", "suggest"]):
                return IntentType.AMBIGUOUS_SCHEDULE
        
        # Default to unknown
        return IntentType.UNKNOWN
    
    def _calculate_confidence(self, intent_type: IntentType, entities: Dict[str, Any], request: str) -> float:
        """Calculate confidence score for the classification"""
        # Start with base confidence
        confidence = 0.5
        
        # Get required entities for this intent
        required_entities = self.intent_config.get_required_entities(intent_type)
        
        # Check how many required entities we found
        if required_entities:
            found_required = sum(1 for entity in required_entities if entity in entities)
            entity_coverage = found_required / len(required_entities)
            confidence = 0.3 + (entity_coverage * 0.5)  # 30% base + up to 50% for entities
        
        # Boost confidence for exact trigger matches
        if self.intent_config.get_intent_by_triggers(request) == intent_type:
            confidence += 0.2
        
        # Reduce confidence for ambiguous indicators
        ambiguous_words = ["some", "help", "maybe", "could", "might", "suggest"]
        if any(word in request.lower() for word in ambiguous_words):
            confidence *= 0.8
        
        # Cap confidence at 0.95 (never 100% certain)
        return min(confidence, 0.95)
    
    def _needs_clarification(self, intent_type: IntentType, entities: Dict[str, Any], confidence: float) -> bool:
        """Determine if clarification is needed"""
        # Always need clarification for ambiguous intents
        if intent_type in [IntentType.AMBIGUOUS_SCHEDULE, IntentType.NEEDS_CLARIFICATION]:
            return True
        
        # Need clarification if confidence below threshold
        threshold = self.intent_config.get_confidence_threshold(intent_type)
        if confidence < threshold:
            return True
        
        # Check for missing required entities
        required_entities = self.intent_config.get_required_entities(intent_type)
        missing_required = [e for e in required_entities if e not in entities]
        if missing_required:
            return True
        
        return False
    
    def get_intent_examples(self, intent_type: IntentType) -> List[str]:
        """Get examples for an intent type (useful for testing/documentation)"""
        if intent_type in self.intent_config.intents:
            return self.intent_config.intents[intent_type].examples
        return []