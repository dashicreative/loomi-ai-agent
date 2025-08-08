"""
LLM Intent Processor - Replaces rule-based intent classification with LLM understanding

This is Phase 1 of the architecture simplification. This single component replaces:
- IntentClassifier (288 lines of rules)  
- ComplexityDetector (70 lines wrapper)
- AmbiguityDetector (160 lines of logic)
- IntentConfig (180 lines of config)

Total replacement: ~700 lines → ~150 lines with better flexibility
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import asyncio

# For now, we'll use OpenAI - can be swapped for Claude later
import openai
from openai import AsyncOpenAI

from ..config import get_config
from .intent_classifier import IntentType  # Keep enum for compatibility


@dataclass
class LLMRequestContext:
    """Enhanced request context from LLM analysis"""
    intent_type: IntentType
    confidence: float
    complexity: str  # "simple" or "complex" for backward compatibility
    entities: Dict[str, Any]
    needs_clarification: bool
    execution_plan: Optional[List[Dict[str, Any]]] = None
    clarification_question: Optional[str] = None
    reasoning: Optional[str] = None


class LLMIntentProcessor:
    """
    LLM-powered intent processing that replaces multiple rule-based components
    
    Handles:
    - Intent classification (replaces IntentClassifier)
    - Complexity detection (replaces ComplexityDetector) 
    - Ambiguity detection (replaces AmbiguityDetector)
    - Entity extraction with semantic understanding
    - Basic execution planning
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LLM intent processor
        
        Args:
            api_key: OpenAI API key (if not provided, will use env var)
        """
        self.config = get_config()
        
        # Initialize OpenAI client
        self.client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        
        # Intent type mapping for LLM
        self.intent_descriptions = {
            "DIRECT_SCHEDULE": "Schedule a specific meal for a specific date/time",
            "BATCH_SCHEDULE": "Schedule multiple meals or meals for multiple days",
            "FILL_SCHEDULE": "Fill empty slots in schedule with random/suggested meals", 
            "CLEAR_SCHEDULE": "Remove/clear scheduled meals from calendar",
            "VIEW_SCHEDULE": "Show what's currently scheduled",
            "LIST_MEALS": "Show available meals to choose from",
            "AMBIGUOUS_SCHEDULE": "Intent is unclear, missing key information",
            "UNKNOWN": "Cannot determine what user wants to do"
        }
    
    async def understand_request(self, request: str, available_meals: List[str], current_schedule: Optional[Dict] = None) -> LLMRequestContext:
        """
        Analyze user request with LLM to understand intent, extract entities, and determine complexity
        
        Args:
            request: User's natural language request
            available_meals: List of available meal names
            current_schedule: Optional current schedule context
            
        Returns:
            LLMRequestContext with full analysis
        """
        # Build context for LLM
        context = {
            "request": request,
            "available_meals": available_meals[:20],  # Limit to prevent token overflow
            "current_date": datetime.now().isoformat()[:10],
            "intent_types": self.intent_descriptions
        }
        
        if current_schedule:
            context["current_schedule_sample"] = current_schedule
        
        # Create the analysis prompt
        prompt = self._build_analysis_prompt(context)
        
        try:
            # Call LLM for analysis
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cost-effective
                messages=[
                    {"role": "system", "content": "You are a meal scheduling assistant that analyzes user requests."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent analysis
                max_tokens=1000
            )
            
            # Parse LLM response
            analysis_text = response.choices[0].message.content
            analysis = self._parse_llm_response(analysis_text)
            
            # Convert to LLMRequestContext
            return self._build_request_context(analysis, request)
            
        except Exception as e:
            # Fallback to basic analysis if LLM fails
            return self._fallback_analysis(request, available_meals)
    
    def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """Build the analysis prompt for the LLM"""
        return f"""
Analyze this meal scheduling request and return a JSON response:

REQUEST: "{context['request']}"
AVAILABLE_MEALS: {context['available_meals']}
TODAY: {context['current_date']}

INTENT TYPES (choose exactly one):
- DIRECT_SCHEDULE: Schedule a specific meal for a specific date/time
- BATCH_SCHEDULE: Schedule multiple meals or meals for multiple days
- FILL_SCHEDULE: Fill empty slots in schedule with random/suggested meals
- CLEAR_SCHEDULE: Remove/clear scheduled meals from calendar
- VIEW_SCHEDULE: Show what's currently scheduled
- LIST_MEALS: Show available meals to choose from
- AMBIGUOUS_SCHEDULE: Intent is unclear, missing key information
- UNKNOWN: Cannot determine what user wants to do

Return JSON with:
{{
  "intent_type": "EXACT_MATCH_FROM_LIST_ABOVE",
  "confidence": 0.0-1.0,
  "complexity": "simple or complex",
  "entities": {{
    "meal_names": ["extracted meal names"],
    "dates": ["extracted dates/time references"], 
    "meal_types": ["breakfast/lunch/dinner/snack"],
    "quantities": ["number of meals if specified"],
    "temporal_references": ["time expressions like 'next week'"]
  }},
  "needs_clarification": true/false,
  "clarification_question": "question if clarification needed",
  "execution_plan": [
    {{"action": "schedule_meal", "meal_name": "Pizza", "date": "tomorrow", "meal_type": "dinner"}}
  ],
  "reasoning": "brief explanation of analysis"
}}

INTENT CLASSIFICATION RULES:
- DIRECT_SCHEDULE: "Schedule pizza for dinner tomorrow" (specific meal + date)
- BATCH_SCHEDULE: "Schedule dinners for the week" (multiple meals/dates)
- CLEAR_SCHEDULE: "Clear next week's meals" (removing scheduled items)
- VIEW_SCHEDULE: "What's scheduled for tomorrow" (viewing existing schedule)
- AMBIGUOUS_SCHEDULE: "Schedule something" (missing critical info)
- UNKNOWN: "yes", "no", unclear responses

COMPLEXITY RULES:
- simple: Single meal for single date/time with clear entities, or simple view requests
- complex: Multiple meals, multiple dates, ambiguous requests (missing info), clearing operations, batch operations, unknown intents

SPECIFIC COMPLEXITY EXAMPLES:
- "Schedule pizza for dinner tomorrow" → simple (specific meal + date)
- "What's scheduled for tomorrow" → simple (specific query)
- "Schedule dinners for the week" → complex (multiple dates)
- "Clear next week's meals" → complex (clearing operation)
- "Schedule something for dinner" → complex (missing meal info)
- "yes" → complex (ambiguous/unknown)

ENTITY EXTRACTION:
- Match meal names flexibly (e.g., "chicken parm" → "Chicken Parmesan")
- Extract temporal references naturally ("next week", "tomorrow", etc.)
- Identify meal types from context if not explicit

CLARIFICATION:
- Set needs_clarification=true if missing critical information
- Generate helpful question to gather missing details
"""
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        try:
            # Try to extract JSON from response
            response_text = response_text.strip()
            
            # Handle markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, try to extract key information
            return {
                "intent_type": "UNKNOWN",
                "confidence": 0.3,
                "complexity": "complex",
                "entities": {},
                "needs_clarification": True,
                "clarification_question": "Could you please clarify your meal scheduling request?",
                "reasoning": f"Failed to parse LLM response: {e}"
            }
    
    def _build_request_context(self, analysis: Dict[str, Any], original_request: str) -> LLMRequestContext:
        """Build LLMRequestContext from LLM analysis"""
        # Map uppercase LLM response to lowercase enum values
        intent_string = analysis.get("intent_type", "UNKNOWN").upper()
        
        # Map uppercase intent names to lowercase enum values
        intent_mapping = {
            "DIRECT_SCHEDULE": "direct_schedule",
            "BATCH_SCHEDULE": "batch_schedule", 
            "CLEAR_SCHEDULE": "clear_schedule",
            "FILL_SCHEDULE": "fill_schedule",
            "VIEW_SCHEDULE": "view_schedule",
            "LIST_MEALS": "list_meals",
            "AMBIGUOUS_SCHEDULE": "ambiguous_schedule",
            "NEEDS_CLARIFICATION": "needs_clarification",
            "UNKNOWN": "unknown",
            # Alternative mappings
            "SCHEDULE_MEAL": "direct_schedule",
            "SCHEDULE": "direct_schedule", 
            "BATCH": "batch_schedule",
            "CLEAR": "clear_schedule",
            "VIEW": "view_schedule",
            "SHOW": "view_schedule",
            "LIST": "list_meals",
            "AMBIGUOUS": "ambiguous_schedule"
        }
        
        enum_value = intent_mapping.get(intent_string, "unknown")
        
        try:
            intent_type = IntentType(enum_value)
        except ValueError:
            intent_type = IntentType.UNKNOWN
        
        return LLMRequestContext(
            intent_type=intent_type,
            confidence=float(analysis.get("confidence", 0.5)),
            complexity=analysis.get("complexity", "complex"),
            entities=analysis.get("entities", {}),
            needs_clarification=analysis.get("needs_clarification", False),
            execution_plan=analysis.get("execution_plan"),
            clarification_question=analysis.get("clarification_question"),
            reasoning=analysis.get("reasoning")
        )
    
    def _fallback_analysis(self, request: str, available_meals: List[str]) -> LLMRequestContext:
        """Fallback analysis if LLM fails"""
        request_lower = request.lower()
        
        # Basic intent detection
        if any(word in request_lower for word in ["schedule", "add", "plan"]):
            intent_type = IntentType.DIRECT_SCHEDULE
            complexity = "simple" if len(request.split()) < 10 else "complex"
        elif any(word in request_lower for word in ["clear", "remove", "delete"]):
            intent_type = IntentType.CLEAR_SCHEDULE
            complexity = "complex"
        elif any(word in request_lower for word in ["show", "what", "view"]):
            intent_type = IntentType.VIEW_SCHEDULE
            complexity = "simple"
        else:
            intent_type = IntentType.UNKNOWN
            complexity = "complex"
        
        # Basic entity extraction
        entities = {"meal_names": [], "dates": [], "meal_types": []}
        for meal in available_meals:
            if meal.lower() in request_lower:
                entities["meal_names"].append(meal)
        
        return LLMRequestContext(
            intent_type=intent_type,
            confidence=0.6,
            complexity=complexity,
            entities=entities,
            needs_clarification=len(entities["meal_names"]) == 0 and intent_type in [IntentType.DIRECT_SCHEDULE, IntentType.BATCH_SCHEDULE],
            clarification_question="What meal would you like to schedule?" if intent_type == IntentType.DIRECT_SCHEDULE else None,
            reasoning="Fallback analysis due to LLM error"
        )
    
    # Backward compatibility methods
    async def classify(self, request: str, available_meals: List[str]) -> 'LLMRequestContext':
        """Compatibility method for existing IntentClassifier interface"""
        return await self.understand_request(request, available_meals)
    
    async def detect(self, request: str, available_meals: List[str]) -> str:
        """Compatibility method for existing ComplexityDetector interface"""
        context = await self.understand_request(request, available_meals)
        return context.complexity
    
    def detect_ambiguity(self, request: str, available_meals: List[str]) -> Dict[str, Any]:
        """Compatibility method for existing AmbiguityDetector interface"""
        # This would need to be async in real implementation, but keeping sync for compatibility
        # In practice, we'd run this through the LLM analysis
        return {
            "is_ambiguous": len(request.strip()) < 10 or request.lower() in ["yes", "no", "ok", "sure"],
            "confidence": 0.5,
            "missing_info": ["clarification needed"],
            "analysis": "Quick ambiguity check - use full LLM analysis for better results"
        }


class LLMIntentProcessorTester:
    """DELETE_LATER: Testing utility for LLM intent processor"""
    
    def __init__(self, processor: LLMIntentProcessor):
        self.processor = processor
    
    async def test_scenarios(self, test_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Test multiple scenarios and compare results"""
        results = {
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        for scenario in test_scenarios:
            try:
                context = await self.processor.understand_request(
                    scenario["request"], 
                    scenario.get("available_meals", ["Pizza", "Chicken Parmesan", "Salad"])
                )
                
                # Check if results match expectations
                passed = (
                    context.intent_type.value == scenario.get("expected_intent", "UNKNOWN") and
                    context.complexity == scenario.get("expected_complexity", "complex")
                )
                
                if passed:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                
                results["details"].append({
                    "scenario": scenario["name"],
                    "request": scenario["request"],
                    "expected_intent": scenario.get("expected_intent"),
                    "actual_intent": context.intent_type.value,
                    "expected_complexity": scenario.get("expected_complexity"),
                    "actual_complexity": context.complexity,
                    "confidence": context.confidence,
                    "needs_clarification": context.needs_clarification,
                    "passed": passed,
                    "reasoning": context.reasoning
                })
                
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "scenario": scenario["name"],
                    "request": scenario["request"],
                    "error": str(e),
                    "passed": False
                })
        
        return results