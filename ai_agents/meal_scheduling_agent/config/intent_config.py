"""
Intent Configuration - Defines all possible intents for meal scheduling
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    """All possible intent types in meal scheduling domain"""
    # Direct actions
    DIRECT_SCHEDULE = "direct_schedule"
    BATCH_SCHEDULE = "batch_schedule"
    CLEAR_SCHEDULE = "clear_schedule"
    FILL_SCHEDULE = "fill_schedule"
    
    # Query intents
    VIEW_SCHEDULE = "view_schedule"
    LIST_MEALS = "list_meals"
    
    # Ambiguous/needs clarification
    AMBIGUOUS_SCHEDULE = "ambiguous_schedule"
    NEEDS_CLARIFICATION = "needs_clarification"
    
    # System intents
    UNKNOWN = "unknown"
    

@dataclass
class IntentDefinition:
    """Configuration for a specific intent type"""
    name: IntentType
    confidence_threshold: float
    required_entities: List[str]
    optional_entities: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)  # Keywords that trigger this intent
    examples: List[str] = field(default_factory=list)
    requires_llm: bool = False  # Whether this intent needs LLM parsing
    cache_friendly: bool = True  # Whether responses can be cached


class IntentConfig:
    """Complete intent configuration for meal scheduling"""
    
    def __init__(self):
        self.intents: Dict[IntentType, IntentDefinition] = {
            IntentType.DIRECT_SCHEDULE: IntentDefinition(
                name=IntentType.DIRECT_SCHEDULE,
                confidence_threshold=0.8,
                required_entities=["meal_name", "date"],
                optional_entities=["meal_type", "servings"],
                triggers=["schedule", "add", "plan"],
                examples=[
                    "Schedule pizza for tomorrow dinner",
                    "Add chicken to Tuesday lunch",
                    "Plan pasta for next Friday"
                ],
                requires_llm=False,
                cache_friendly=False
            ),
            
            IntentType.BATCH_SCHEDULE: IntentDefinition(
                name=IntentType.BATCH_SCHEDULE,
                confidence_threshold=0.7,
                required_entities=["date_range", "meal_type"],
                optional_entities=["meal_names"],
                triggers=["next 5 days", "this week", "rest of week", "multiple", "batch"],
                examples=[
                    "Schedule dinners for the next 5 days",
                    "Plan breakfast for this week",
                    "Add lunches for the rest of the week"
                ],
                requires_llm=True,
                cache_friendly=False
            ),
            
            IntentType.FILL_SCHEDULE: IntentDefinition(
                name=IntentType.FILL_SCHEDULE,
                confidence_threshold=0.7,
                required_entities=["action"],
                optional_entities=["date_range", "meal_types"],
                triggers=["fill", "populate", "random meals", "pick meals"],
                examples=[
                    "Fill my schedule with random meals",
                    "Pick some dinners for next week",
                    "Fill this week with breakfast and dinner"
                ],
                requires_llm=True,
                cache_friendly=False
            ),
            
            IntentType.CLEAR_SCHEDULE: IntentDefinition(
                name=IntentType.CLEAR_SCHEDULE,
                confidence_threshold=0.9,
                required_entities=["action"],
                optional_entities=["date_range"],
                triggers=["clear", "remove all", "delete all", "unschedule", "cancel"],
                examples=[
                    "Clear my schedule",
                    "Remove all meals this week",
                    "Delete everything for next month"
                ],
                requires_llm=False,
                cache_friendly=False
            ),
            
            IntentType.VIEW_SCHEDULE: IntentDefinition(
                name=IntentType.VIEW_SCHEDULE,
                confidence_threshold=0.8,
                required_entities=["action"],
                optional_entities=["date", "date_range"],
                triggers=["what's scheduled", "show schedule", "view meals", "scheduled for"],
                examples=[
                    "What's scheduled for tomorrow?",
                    "Show me this week's meals",
                    "What meals do I have planned?"
                ],
                requires_llm=False,
                cache_friendly=True
            ),
            
            IntentType.LIST_MEALS: IntentDefinition(
                name=IntentType.LIST_MEALS,
                confidence_threshold=0.9,
                required_entities=["action"],
                triggers=["available meals", "what meals", "list meals", "my meals", "saved meals"],
                examples=[
                    "What meals do I have available?",
                    "List my saved meals",
                    "Show me all meals"
                ],
                requires_llm=False,
                cache_friendly=True
            ),
            
            IntentType.AMBIGUOUS_SCHEDULE: IntentDefinition(
                name=IntentType.AMBIGUOUS_SCHEDULE,
                confidence_threshold=0.4,
                required_entities=["action"],
                triggers=["some", "a few", "help", "suggest", "pick", "choose"],
                examples=[
                    "Schedule some meals",
                    "Can you pick a meal for me?",
                    "Help me plan dinner"
                ],
                requires_llm=True,
                cache_friendly=False
            )
        }
    
    def get_intent_by_triggers(self, text: str) -> Optional[IntentType]:
        """Find intent type by matching trigger keywords"""
        text_lower = text.lower()
        
        # Check each intent's triggers
        for intent_type, definition in self.intents.items():
            for trigger in definition.triggers:
                if trigger in text_lower:
                    return intent_type
        
        return None
    
    def get_required_entities(self, intent_type: IntentType) -> List[str]:
        """Get required entities for an intent"""
        if intent_type in self.intents:
            return self.intents[intent_type].required_entities
        return []
    
    def get_confidence_threshold(self, intent_type: IntentType) -> float:
        """Get confidence threshold for an intent"""
        if intent_type in self.intents:
            return self.intents[intent_type].confidence_threshold
        return 0.5
    
    def requires_llm(self, intent_type: IntentType) -> bool:
        """Check if intent requires LLM processing"""
        if intent_type in self.intents:
            return self.intents[intent_type].requires_llm
        return True  # Default to LLM for unknown intents