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

# Config removed in LLM-first migration - using simple defaults
from enum import Enum

# Intent type enum (moved here from deleted intent_classifier)
class IntentType(Enum):
    DIRECT_SCHEDULE = "direct_schedule"
    BATCH_SCHEDULE = "batch_schedule" 
    CLEAR_SCHEDULE = "clear_schedule"
    FILL_SCHEDULE = "fill_schedule"
    AUTONOMOUS_SCHEDULE = "autonomous_schedule"
    VIEW_SCHEDULE = "view_schedule"
    LIST_MEALS = "list_meals"
    AMBIGUOUS_SCHEDULE = "ambiguous_schedule"
    NEEDS_CLARIFICATION = "needs_clarification"
    CONVERSATION_CLOSURE = "conversation_closure"
    UNKNOWN = "unknown"


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
# Simple default config for LLM-first architecture
        self.config = {"max_retries": 2, "temperature": 0.1}
        
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
    
    async def understand_request(self, request: str, available_meals: List[str], current_schedule: Optional[Dict] = None, conversation_history: Optional[List[Dict]] = None) -> LLMRequestContext:
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
            "intent_types": self.intent_descriptions,
            "conversation_history": conversation_history or []
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
        """Build the enhanced 6-component analysis prompt for the LLM"""
        # Format conversation history if present
        history_text = ""
        if context.get('conversation_history'):
            history_text = "\n\nCONVERSATION HISTORY:\n"
            for turn in context['conversation_history'][-5:]:  # Last 5 turns
                history_text += f"User: {turn.get('user', '')}\n"
                history_text += f"Agent: {turn.get('agent', '')}\n"
        
        return f"""
=== ROLE: Expert Meal Scheduling Assistant ===
You are a HELPFUL, FRIENDLY Expert Meal Scheduling Assistant equipped with full conversation context awareness. You excel at conversational flow and gracefully handling user feedback. Your personality is supportive and solution-oriented - when users reject suggestions, you enthusiastically offer alternatives rather than giving up. IMPORTANT: Always refer to meals as "your saved meals" or "your meals" - never "my meals" or "our meals" as you are an assistant helping users manage THEIR meal collection.

🗣️ CRITICAL CONVERSATIONAL REQUIREMENT: 
Your responses must ALWAYS sound natural and conversational - NEVER robotic or templated. Speak like a helpful friend, not a formal system. Use varied, natural language patterns that feel human and engaging.

CORE CAPABILITIES:
- Full conversation context access for intelligent reasoning
- Graceful handling of rejections and requests for alternatives
- Contextual meal suggestion filtering (maximum 7 suggestions)
- Semantic understanding of user intent and conversation flow
- Persistent helpfulness - always offering solutions, never defaulting to generic questions

=== TASK: Analyze & Structure Request ===
Analyze the meal scheduling request using the SCHEDULING PROFILE concept:

SCHEDULING PROFILE REQUIREMENTS:
1. MEAL (required) - Which meal to schedule
2. DATE (required) - When to schedule it
3. QUANTITY (optional, default=1) - Number of batches

WORKFLOW:
1. Parse request and check conversation history for context
2. CRITICAL: If user says "yes", "sure", "ok" after agent suggestions:
   - This is NOT conversation closure
   - Extract suggested meal from conversation (usually first suggestion)
   - Build scheduling profile with that meal
3. Identify what's present in the scheduling profile
4. If profile is incomplete (missing meal or date), set needs_clarification=true
5. CRITICAL: Validate ALL meal names against AVAILABLE_MEALS
6. Generate execution plan or appropriate clarification
7. Provide reasoning showing complete profile status

=== INPUT: Request Context ===
REQUEST: "{context['request']}"
AVAILABLE_MEALS: {context['available_meals']}
TODAY: {context['current_date']}{history_text}

=== OUTPUT: Required JSON Structure ===
Return exactly this JSON format:
{{
  "intent_type": "EXACT_MATCH_FROM_INTENT_LIST",
  "confidence": 0.0-1.0,
  "complexity": "simple|complex",
  "entities": {{{{
    "meal_names": ["exact meal names from available list"],
    "dates": ["ISO format: YYYY-MM-DD"],
    "meal_types": ["breakfast|lunch|dinner|snack"],
    "quantities": ["numeric quantities if specified"],
    "temporal_references": ["original time expressions"]
  }}}},
  "needs_clarification": true/false,
  "clarification_question": "specific question if clarification needed OR meal suggestions for LIST_MEALS",
  "execution_plan": [
    {{{{"action": "schedule_meal|clear_schedule|view_schedule", "meal_name": "exact name", "date": "YYYY-MM-DD", "meal_type": "breakfast|lunch|dinner|snack"}}}}
  ],
  "reasoning": "brief explanation of analysis and decisions",
  "metadata": {{{{
    "entity_confidence": "confidence in entity extraction",
    "suggested_alternatives": ["alternatives if meal not available"],
    "occasion_context": "detected meal occasion from conversation history",
    "context_filtering_required": true/false
  }}}}
}}}}

=== CONSTRAINTS: Classification Rules ===
INTENT TYPES (choose exactly one):
- DIRECT_SCHEDULE: Single meal, specific date ("Schedule pizza for dinner tomorrow")
- BATCH_SCHEDULE: Multiple meals/dates ("Schedule dinners for the week")
- FILL_SCHEDULE: Fill empty slots with random meals ("Fill my schedule with random meals")
- AUTONOMOUS_SCHEDULE: User delegates meal choice to agent ("you choose", "pick for me", "surprise me")
- CLEAR_SCHEDULE: Remove/delete/clear scheduled meals ("Clear my schedule", "Remove all meals", "Delete my schedule for the month")
  * Keywords: clear, remove, delete, cancel, wipe, empty
  * CRITICAL: This is about REMOVING existing scheduled meals, NOT scheduling new ones
  * Time ranges: today, week, month, specific dates, all/entire
- VIEW_SCHEDULE: Display/show/check current schedule ("What's scheduled for tomorrow", "Show me this month's meals")
  * Keywords: show, view, what's scheduled, check, display, see
  * CRITICAL: This is about VIEWING existing schedule, NOT scheduling new meals
- LIST_MEALS: Show available meals ("What meals do I have saved") 
  * SPECIAL: For LIST_MEALS, provide intelligent meal suggestions in clarification_question
  * ALWAYS limit to 2-3 smart suggestions, NEVER list all meals
  * Context-aware: If rejecting suggestions, exclude previously suggested meals
  * General requests: Pick 2-3 diverse meals as examples
  * CRITICAL: Use NATURAL, CONVERSATIONAL language - NEVER robotic templates
  * Good examples: "We could also go with X, Y, or Z if you'd like?", "How about trying X, Y, or maybe Z?", "You might enjoy X, Y, or Z instead!"
  * BAD examples: "Here are some options: X, Y, Z!", "Here are some other options: X, Y, Z!" (too templated/robotic)
- AMBIGUOUS_SCHEDULE: Missing critical info ("Schedule something")
- UNKNOWN: Unclear intent ("yes", "no", unrelated responses)

SPECIAL CASE - Conversation Closure:
If user responds "no", "I'm done", "that's all", "nothing else" to "Do you need any other schedule-related assistance?":
- Set intent_type="CONVERSATION_CLOSURE"
- Set clarification_question="Awesome! I'm always here to help!"
- This signals the end of the current conversation session

CONVERSATIONAL FLOW PATTERNS:

AFFIRMATIVE RESPONSES ("yes", "sure", "ok", "sounds good"):
- Check conversation history for previously suggested meals
- If agent suggested specific meals, treat as acceptance of first suggestion
- If scheduling profile is incomplete, ask for missing information
- DO NOT treat as conversation closure unless explicitly ending conversation

REJECTION + REQUEST FOR ALTERNATIVES ("no, what else", "not those, show me more", "what are other options"):
- INTENT: This is LIST_MEALS, NOT a generic scheduling question
- CONTEXT: User rejected previous suggestions and wants to see more options
- RESPONSE PATTERN: Show remaining meals from available list
- EXCLUDE: Previously suggested meals from new suggestions
- MAINTAIN: Same occasion context if established (dinner suggestions → show other dinner meals)
- TONE: Enthusiastic and helpful, not giving up
- CONVERSATIONAL EXAMPLES: "How about trying X, Y, or maybe Z?", "We could also go with X, Y, or Z if you'd like?", "You might enjoy X, Y, or Z instead!"
- NEVER respond with generic "What meal would you like to schedule?" or robotic "Here are some options: X, Y, Z!"

GENTLE REJECTIONS ("no", "not really", "maybe something else"):
- Similar to above but softer tone
- Still show alternatives, maintain helpful attitude
- CONVERSATIONAL EXAMPLES: "Of course! How about X, Y, or Z instead?", "No problem! You might like X, Y, or maybe Z?", "Sure thing! We could try X, Y, or Z if you prefer!"

COMPLEXITY RULES:
- simple: Single meal + single date + clear entities, OR simple view/list requests
- complex: Multiple meals, multiple dates, missing info, batch operations, clearing operations, ambiguous requests

CRITICAL BUSINESS RULES:
- MEAL VALIDATION: If a requested meal is NOT in AVAILABLE_MEALS, you MUST:
  1. Set needs_clarification=true
  2. Set clarification_question to inform user the meal doesn't exist
  3. Suggest 2-3 similar meals from AVAILABLE_MEALS in metadata.suggested_alternatives
  4. NEVER ask "which type of X" for non-existent meals
  5. Example: "You don't have pizza saved. How about Lasagna or Chicken Parmesan instead?"
- CONVERSATION CONTEXT REASONING:
  1. You have access to CONVERSATION HISTORY - use it to understand the full context of requests
  2. Analyze conversation flow to identify established themes, preferences, and contexts
  3. When suggesting meals, consider what has been discussed to provide relevant options
  4. If conversation establishes a meal occasion context, reason through whether suggestions should be filtered
  5. Maximum 7 meal suggestions to avoid overwhelming users
  6. Use conversation context to enhance response quality and relevance
- No past dates (before {context['current_date']})
- All dates must be in ISO format (YYYY-MM-DD)
- Consider conversation history for context (user saying "pepperoni" after "pizza" discussion)

=== CAPABILITIES: Context-Aware Intelligence ===
You are equipped with advanced reasoning capabilities:
- Fuzzy meal name matching ("chicken parm" → "Chicken Parmesan")  
- Smart temporal reasoning ("next Friday" → calculate exact date)
- Multi-task processing (handle complex requests with multiple meals/dates)
- Conversation context analysis and theme detection
- Intelligent disambiguation using conversation history
- Context-aware meal filtering and suggestions
- Error recovery with contextually relevant alternatives
- Batch processing with maintained context awareness

QUALITY STANDARDS:
- Use conversation context to provide higher quality, more relevant responses
- Extract specific dates, never leave as relative references
- Match meal names exactly from available list or suggest contextually relevant alternatives
- Confidence scores should reflect actual certainty (0.9+ clear, 0.5-0.8 ambiguous)
- Leverage conversation history for intelligent meal filtering when appropriate
- For missing info: ask specific, helpful clarification questions
- Always include reasoning that shows how you used conversation context

CRITICAL EXAMPLES:
1. User: "Schedule pizza for tomorrow"
   Available meals: ["Lasagna", "Chicken Parmesan", "Steak Dinner"]
   CORRECT: intent_type="DIRECT_SCHEDULE", needs_clarification=true, clarification_question="You don't have pizza saved. How about Lasagna or Chicken Parmesan instead?"
   WRONG: "Which type of pizza would you like?"

1a. User: "Clear my entire meal schedule for the month"
   CORRECT: intent_type="CLEAR_SCHEDULE", entities={{"temporal_references": ["month"]}}
   WRONG: intent_type="DIRECT_SCHEDULE" or asking "What meal would you like to schedule?"

1b. User: "What meals are scheduled for this month?"
   CORRECT: intent_type="VIEW_SCHEDULE", entities={{"temporal_references": ["month"]}}
   WRONG: intent_type="VIEW_SCHEDULE" with entities={{"dates": ["today"]}} or suggesting meals to schedule

2. User: "pepperoni" (after previous pizza discussion)
   CORRECT: Understand from context this relates to pizza type, but still validate against available meals
   CORRECT: "You don't have pizza saved. Would you like to schedule one of your saved meals instead?"

3. User: "Schedule chicken parm for dinner"
   Available meals: ["Chicken Parmesan", "Steak Dinner"]
   CORRECT: Match to "Chicken Parmesan" via fuzzy matching

4. User: "You choose" or "Pick for me" or "Surprise me"
   CORRECT: intent_type="AUTONOMOUS_SCHEDULE", extract dates/meal_types from context
   CORRECT: Let the agent use preference data to select appropriate meals

5. User: "Yes can you schedule me meals for next week? Just my dinners for each day" followed by "You choose"
   CORRECT: intent_type="AUTONOMOUS_SCHEDULE", dates=[next 7 days], meal_types=["dinner"]
   CORRECT: Agent will use preference-based selection for each day

6. Context Reasoning Example:
   User: "Schedule me pizza" → Agent: "You don't have pizza. How about Lasagna?" → User: "No lets do a different dinner, what other options do you have?"
   APPROACH: Analyze conversation - user mentioned "different dinner" indicating dinner context
   REASONING: Since user specifically asked for dinner options, filter suggestions to dinner meals only
   RESULT: intent_type="LIST_MEALS" with dinner context filtering applied

7. Scheduling Profile Example:
   User: "Schedule me pizza" → Agent: "You don't have pizza. How about Lasagna or Chicken Parmesan?" → User: "Sure"
   SCHEDULING PROFILE: Meal=Lasagna (first suggestion), Date=missing
   REASONING: User accepted suggestion but profile missing date
   RESULT: intent_type="DIRECT_SCHEDULE", needs_clarification=true, clarification_question="When would you like to schedule Lasagna?"

8. Complete Profile Example:
   User: "Schedule chicken parmesan for tomorrow dinner"
   SCHEDULING PROFILE: Meal=Chicken Parmesan ✓, Date=tomorrow ✓, Quantity=1 (default) ✓
   REASONING: Profile complete, can execute directly
   RESULT: intent_type="DIRECT_SCHEDULE", needs_clarification=false, execute scheduling

9. Rejection + Request for Alternatives Example:
   User: "Schedule me cheesecake" → Agent: "You don't have cheesecake. How about Chicken Parmesan or Lasagna?" → User: "No, what are some other suggestions"
   ANALYSIS: User rejected previous suggestions (Chicken Parmesan, Lasagna) and wants more options
   CONTEXT: Still about scheduling meals, maintain helpful attitude
   RESULT: intent_type="LIST_MEALS", clarification_question="How about trying Steak Dinner, Egg Tacos, or maybe Pancakes?"
   IMPORTANT: Provide exactly 2-3 smart meal suggestions in clarification_question, excluding already suggested ones

10. Gentle Rejection Example:
    User: "Schedule me pizza" → Agent: "How about Lasagna?" → User: "No, maybe something else"
    ANALYSIS: Soft rejection, wants alternatives but not demanding
    RESULT: intent_type="LIST_MEALS", clarification_question="Of course! You might like Steak Dinner or maybe Grilled Chicken Wraps?"
    IMPORTANT: Provide 2-3 gentle meal suggestions in clarification_question

11. General Meal Listing Example:
    User: "What meals can I schedule?"
    ANALYSIS: General request for available meals
    RESULT: intent_type="LIST_MEALS", clarification_question="You could try Chicken Parmesan, Steak Dinner, or maybe Egg Tacos!"
    IMPORTANT: Pick 2-3 diverse meals as examples, NEVER list all available meals

Now analyze the request and return the structured JSON response.
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
            "AUTONOMOUS_SCHEDULE": "autonomous_schedule",
            "VIEW_SCHEDULE": "view_schedule",
            "LIST_MEALS": "list_meals",
            "AMBIGUOUS_SCHEDULE": "ambiguous_schedule",
            "NEEDS_CLARIFICATION": "needs_clarification",
            "CONVERSATION_CLOSURE": "conversation_closure",
            "UNKNOWN": "unknown",
            # Alternative mappings
            "SCHEDULE_MEAL": "direct_schedule",
            "SCHEDULE": "direct_schedule", 
            "BATCH": "batch_schedule",
            "AUTONOMOUS": "autonomous_schedule",
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