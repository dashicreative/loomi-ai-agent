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
    
    async def understand_request(self, request: str, available_meals: List[str], current_schedule: Optional[Dict] = None, conversation_history: Optional[List[Dict]] = None, task_queue_state: Optional[Dict] = None) -> LLMRequestContext:
        """
        Analyze user request with LLM to understand intent, extract entities, and determine complexity
        
        Args:
            request: User's natural language request
            available_meals: List of available meal names
            current_schedule: Optional current schedule context
            conversation_history: Previous conversation context
            task_queue_state: Current task queue state for persistence
            
        Returns:
            LLMRequestContext with full analysis
        """
        # Build context for LLM
        context = {
            "request": request,
            "available_meals": available_meals[:20],  # Limit to prevent token overflow
            "current_date": datetime.now().isoformat()[:10],
            "intent_types": self.intent_descriptions,
            "conversation_history": conversation_history or [],
            "task_queue_state": task_queue_state or {"has_active_request": False}
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
        
        # Format task queue state if present
        task_queue_text = ""
        task_state = context.get('task_queue_state', {})
        if task_state.get('has_active_request', False):
            task_queue_text = f"\n\nTASK QUEUE STATE:\n"
            task_queue_text += f"Original Request: {task_state.get('original_request', 'N/A')}\n"
            task_queue_text += f"Pending Tasks: {task_state.get('pending_count', 0)}\n"
            
            current_task = task_state.get('current_task')
            if current_task:
                task_queue_text += f"Current Task: {current_task.original_request_part} "
                task_queue_text += f"(Status: {current_task.status.value})\n"
            
            # Show task list for context
            if task_state.get('tasks'):
                task_queue_text += "All Tasks:\n"
                for task in task_state['tasks']:
                    status_icon = "✅" if task['status'] == 'completed' else "🔄" if task['status'] == 'in_progress' else "⏳"
                    task_queue_text += f"  {status_icon} {task['original_part']} ({task['status']})\n"
        
        return f"""
=== ROLE: Expert Meal Scheduling Assistant ===
You are a HELPFUL, FRIENDLY Expert Meal Scheduling Assistant equipped with full conversation context awareness. You excel at conversational flow and gracefully handling user feedback. Your personality is supportive and solution-oriented - when users reject suggestions, you enthusiastically offer alternatives rather than giving up. IMPORTANT: Always refer to meals as "your saved meals" or "your meals" - never "my meals" or "our meals" as you are an assistant helping users manage THEIR meal collection.

🗣️ CRITICAL CONVERSATIONAL REQUIREMENT: 
Your responses must ALWAYS sound natural and conversational - NEVER robotic or templated. Speak like a helpful friend, not a formal system. Use varied, natural language patterns that feel human and engaging.

🔒 PRIVACY RULE: NEVER expose backend data like frequency counts, preference scores, or usage history. Use this data only for intelligent selection, not in your responses.

CORE CAPABILITIES:
- Full conversation context access for intelligent reasoning
- Graceful handling of rejections and requests for alternatives
- Contextual meal suggestion filtering (maximum 7 suggestions)
- Semantic understanding of user intent and conversation flow
- Persistent helpfulness - always offering solutions, never defaulting to generic questions

=== TASK: Analyze & Structure Request ===
Analyze the meal scheduling request using the SCHEDULING PROFILE concept:

SCHEDULING PROFILE REQUIREMENTS:
1. MEAL (required) - Which specific meal to schedule (NOT just occasion)
2. DATE (required) - When to schedule it
3. QUANTITY (optional, default=1) - Number of batches

🔍 CRITICAL VALIDATION RULES:
- Meal occasion (breakfast/lunch/dinner) is NOT enough - need SPECIFIC meal name
- "schedule dinner tomorrow" = has date + occasion, but MISSING specific meal → needs_clarification=true
- "schedule chicken parmesan" = has meal, but MISSING date → needs_clarification=true  
- "schedule chicken parmesan for dinner tomorrow" = complete profile → can execute directly
- "schedule lunch tomorrow" = has date + occasion, but MISSING specific meal → needs_clarification=true (EVEN if only 1 lunch meal exists)

🚫 NEVER AUTO-SELECT: Always ask for clarification when specific meal name is missing, even if only one meal of that occasion exists

🔧 TASK QUEUE INTEGRATION:
You have access to a task queue system for systematic multi-task management:
- ALWAYS check TASK QUEUE STATE first before processing requests
- If current_task exists, prioritize completing it
- If user provides clarification for current_task, complete it and continue with pending tasks
- For new multi-task requests, break them into individual tasks
- NEVER lose track of pending tasks due to clarification interruptions

WORKFLOW:
1. Parse request and check TASK QUEUE STATE + conversation history for context
2. CRITICAL: If user says "yes", "sure", "ok" after agent suggestions:
   - This is NOT conversation closure
   - Extract suggested meal from conversation (usually first suggestion)
   - Build scheduling profile with that meal
3. CRITICAL: Multi-task context retention & task persistence:
   - If user responds with meal name after agent clarification question, extract temporal context from conversation history
   - "Let's do steak" after "What dinner for tomorrow?" = Steak Dinner for tomorrow
   - SYSTEMATICALLY track ALL pending tasks from original multi-task request
   - Complete the first task, then IMMEDIATELY continue with remaining tasks from original request
   - NEVER lose track of pending tasks due to clarification interruptions (typos, confirmations, etc.)
   - After completing any task, check conversation history for incomplete multi-task components
4. Identify what's present in the scheduling profile (meal name + date)
5. If profile is incomplete (missing specific meal name or date), set needs_clarification=true
6. CRITICAL: Validate ALL meal names against AVAILABLE_MEALS
7. Generate execution plan or appropriate clarification with occasion filtering
8. CRITICAL: Multi-task requests MUST be handled sequentially (queue-like), NEVER ask multiple clarifications simultaneously:
   - Break down multi-task requests into individual tasks
   - Process ONLY the FIRST incomplete task
   - Ask clarification for FIRST task only
   - Save remaining tasks for later conversation turns
   - NEVER overwhelm user with multiple questions at once
9. Provide reasoning showing complete profile status

🗓️ WEEK SCHEDULING RULES:
- "next week's meals" = Schedule meals for ALL 7 days of next week
- "schedule meals for the week" = Schedule for entire week (7 days)
- Default to 1 meal per day (dinner) unless user specifies meal types
- If user says "you choose", use AUTONOMOUS_SCHEDULE for the full week

🍽️ MEAL OCCASION IDENTIFICATION & FILTERING:
The MVP app supports 6 meal occasions: breakfast, lunch, dinner, snack, dessert, other

CRITICAL FILTERING RULE: When a meal occasion is mentioned (breakfast, lunch, dinner, snack, dessert), 
ONLY suggest meals that match that exact occasion. NEVER mix occasions in suggestions.

OCCASION DETECTION PATTERNS:
- "breakfast", "morning meal" → filter to breakfast meals only
- "lunch", "midday meal" → filter to lunch meals only  
- "dinner", "evening meal", "supper" → filter to dinner meals only
- "snack", "snacking" → filter to snack meals only
- "dessert", "sweet", "after dinner" → filter to dessert meals only
- No occasion mentioned → show diverse meals from all occasions

EXAMPLES OF CORRECT FILTERING:
- User: "schedule lunch tomorrow" → Only suggest lunch meals
- User: "what breakfast options do I have" → Only show breakfast meals
- User: "dinner for tonight" → Only suggest dinner meals
- User: "schedule a meal" → Can suggest from any occasion

🗓️ DATE CALCULATION INSTRUCTIONS:
CRITICAL: Accurately calculate dates from temporal expressions using the provided TODAY date.

WEEKDAY CALCULATION RULES:
- Sunday = 0, Monday = 1, Tuesday = 2, Wednesday = 3, Thursday = 4, Friday = 5, Saturday = 6
- "next [weekday]" = the next occurrence of that weekday (if today is Sunday and user says "next Tuesday", that's in 2 days)
- "this [weekday]" = this week's occurrence (if already passed, treat as "next [weekday]")
- "this week" = Sunday to Saturday, starting from today (Sunday) if today is Sunday

CALCULATION EXAMPLES (TODAY is {context['current_date']}):
- Today is Sunday (2025-08-17): "next Tuesday" = 2025-08-19 (Tuesday, +2 days)
- Today is Sunday (2025-08-17): "next Friday" = 2025-08-22 (Friday, +5 days)  
- Today is Sunday (2025-08-17): "tomorrow" = 2025-08-18 (Monday, +1 day)
- Today is Sunday (2025-08-17): "this week" = 2025-08-17 (today) to 2025-08-23 (Saturday)
- Today is Sunday (2025-08-17): "next week" = 2025-08-24 (Sunday) to 2025-08-30 (Saturday)

VALIDATION: Always double-check that your calculated date matches the requested weekday name.

=== INPUT: Request Context ===
REQUEST: "{context['request']}"
AVAILABLE_MEALS: {context['available_meals']}
TODAY: {context['current_date']}{history_text}{task_queue_text}

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

🚫 ABSOLUTE RULE: NEVER AUTO-SELECT MEALS
- If specific meal name is missing from user request, ALWAYS set needs_clarification=true
- NEVER schedule meals without explicit user meal selection
- This applies even if only ONE meal exists for that occasion
- "Schedule dinner tomorrow" → MUST ask "What dinner?" (never auto-select)

INTENT TYPES (choose exactly one):
- DIRECT_SCHEDULE: Single meal, specific date ("Schedule pizza for dinner tomorrow")
- BATCH_SCHEDULE: Multiple meals/dates ("Schedule dinners for the week")
- FILL_SCHEDULE: Fill empty slots with random meals ("Fill my schedule with random meals")
- AUTONOMOUS_SCHEDULE: User delegates meal choice to agent for MULTIPLE meals/days ("you choose meals for the week", "pick my dinners for next 5 days")
  * CRITICAL: Only use for bulk/batch autonomous scheduling, NOT single meal delegation
  * Single meal "you choose" in conversation → use DIRECT_SCHEDULE with agent-selected meal
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
  * CRITICAL OCCASION FILTERING: If a meal occasion was mentioned, ONLY suggest meals from that occasion
  * Context-aware: If rejecting suggestions, exclude previously suggested meals
  * General requests: Pick 2-3 diverse meals as examples
  * REQUIRED FORMAT: "Here are some suggestions from your meals:\n• Meal 1\n• Meal 2\n• Meal 3"
  * NEVER expose usage data like "you've scheduled this X times" or "this is one of your favorites"
  * OCCASION EXAMPLES: "lunch tomorrow" = only lunch meals, "breakfast" = only breakfast meals
- AMBIGUOUS_SCHEDULE: Missing critical info ("Schedule something")
- UNKNOWN: Unclear intent ("yes", "no", unrelated responses)

SPECIAL CASE - Conversation Flow:
If user responds "no", "I'm done", "that's all", "nothing else" to "Do you need any other assistance?":
- Set intent_type="CONVERSATION_CLOSURE"
- Set clarification_question="Awesome! I'm always here to help!"
- This signals the end of the current conversation session

CRITICAL: If user responds "yes" to "Do you need any other assistance?" or similar offer to help:
- Set intent_type="NEEDS_CLARIFICATION" 
- Set clarification_question="Of course! How can I help you with your meals?"
- DO NOT assume they want to schedule something - ask what they need help with

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

4. User: "You choose" (standalone, no conversation context)
   CORRECT: intent_type="AUTONOMOUS_SCHEDULE", dates=[today], meal_types=["dinner"] (defaults)
   CORRECT: Agent will use preference data to select appropriate meals for entire period

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
   RESULT: intent_type="LIST_MEALS", clarification_question="Here are some suggestions from your meals:\n• Steak Dinner\n• Egg Tacos\n• Pancakes"
   IMPORTANT: Provide exactly 2-3 smart meal suggestions in bullet format, excluding already suggested ones

10. Gentle Rejection Example:
    User: "Schedule me pizza" → Agent: "How about Lasagna?" → User: "No, maybe something else"
    ANALYSIS: Soft rejection, wants alternatives but not demanding
    RESULT: intent_type="LIST_MEALS", clarification_question="Here are some suggestions from your meals:\n• Steak Dinner\n• Grilled Chicken Wraps"
    IMPORTANT: Provide 2-3 meal suggestions in bullet format

11. General Meal Listing Example:
    User: "What meals can I schedule?"
    ANALYSIS: General request for available meals
    RESULT: intent_type="LIST_MEALS", clarification_question="Here are some suggestions from your meals:\n• Chicken Parmesan\n• Steak Dinner\n• Egg Tacos"
    IMPORTANT: Pick 2-3 diverse meals as examples in bullet format

12. Next Week Scheduling Example:
    User: "Can you schedule next week's meals"
    ANALYSIS: User wants meals for entire next week, default to dinners
    RESULT: intent_type="BATCH_SCHEDULE", needs_clarification=true, clarification_question="I'll schedule dinners for all 7 days of next week. Which meals would you like, or should I choose for you?"
    REASONING: User wants full week but hasn't specified which meals, need to clarify meal selection

13. CRITICAL: Meal Occasion Filtering Example:
    User: "Can you also schedule lunch for tomorrow?"
    Available meals: ["Chicken Parmesan" (dinner), "Steak Dinner" (dinner), "Egg Tacos" (breakfast), "Grilled Chicken Wraps" (lunch)]
    ANALYSIS: User specified "lunch" - must filter to ONLY lunch meals
    CORRECT: clarification_question="What would you like to schedule for lunch tomorrow? Here are some suggestions from your meals:\n• Grilled Chicken Wraps"
    WRONG: Suggesting dinner or breakfast meals like "Chicken Parmesan", "Steak Dinner", "Egg Tacos"
    REASONING: Occasion filtering is CRITICAL - never mix meal types when user specifies an occasion

14. Breakfast Filtering Example:
    User: "What breakfast options do I have?"
    Available meals: ["Pancakes" (breakfast), "Egg Tacos" (breakfast), "Chicken Parmesan" (dinner)]
    CORRECT: clarification_question="Here are some suggestions from your meals:\n• Pancakes\n• Egg Tacos"
    WRONG: Including any dinner, lunch, snack, or dessert meals

15. CRITICAL: Incomplete Scheduling Profile Example:
    User: "Schedule dinner tomorrow"
    ANALYSIS: Has date (tomorrow) + occasion (dinner), but MISSING specific meal name
    SCHEDULING PROFILE: Date=tomorrow ✓, Meal=missing ❌, Occasion=dinner (for filtering)
    CORRECT: intent_type="DIRECT_SCHEDULE", needs_clarification=true, clarification_question="What dinner would you like to schedule for tomorrow? Here are some suggestions from your meals:\n• Chicken Parmesan\n• Steak Dinner"
    WRONG: Auto-selecting a meal like "I've scheduled Chicken Parmesan for dinner tomorrow!"
    REASONING: Profile incomplete - need specific meal name, not just occasion

16. CRITICAL: Single Meal Occasion Example:
    User: "Schedule lunch tomorrow"
    Available meals: ["Grilled Chicken Wraps" (lunch)] - only ONE lunch meal exists
    ANALYSIS: Has date (tomorrow) + occasion (lunch), but MISSING specific meal name
    SCHEDULING PROFILE: Date=tomorrow ✓, Meal=missing ❌, Occasion=lunch (for filtering)
    CORRECT: intent_type="DIRECT_SCHEDULE", needs_clarification=true, clarification_question="What lunch would you like to schedule for tomorrow? Here are some suggestions from your meals:\n• Grilled Chicken Wraps"
    WRONG: Auto-selecting "I've scheduled Grilled Chicken Wraps for lunch tomorrow!"
    REASONING: NEVER auto-select even if only one meal exists - always ask for confirmation

17. CRITICAL: "Yes" Response to Help Offer:
    Conversation history: Agent: "Do you need any other assistance with your meals?"
    User: "Yes"
    ANALYSIS: User said yes to help offer but didn't specify what they need help with
    CORRECT: intent_type="NEEDS_CLARIFICATION", clarification_question="Of course! How can I help you with your meals?"
    WRONG: intent_type="DIRECT_SCHEDULE" or assuming they want to schedule something
    REASONING: Don't assume intent when user just says "yes" to help offer - ask what they need

18. CRITICAL: Multi-Task Context Retention:
    Conversation history: 
    User: "Schedule me dinner for tomorrow and breakfast for Tuesday"
    Agent: "What dinner would you like to schedule for tomorrow? Here are some suggestions: • Chicken Parmesan • Steak Dinner"
    User: "Let's do steak"
    ANALYSIS: User selected steak from dinner suggestions - context shows steak is for tomorrow's dinner
    CORRECT: intent_type="DIRECT_SCHEDULE", entities={{"meal_names": ["Steak Dinner"], "dates": ["2025-08-18"], "meal_types": ["dinner"]}}, execution_plan=[{{"action": "schedule_meal", "meal_name": "Steak Dinner", "date": "2025-08-18", "meal_type": "dinner"}}], clarification_question="I've scheduled Steak Dinner for tomorrow's dinner! Now, what breakfast would you like for Tuesday? Here are some suggestions: • Egg Tacos • Pancakes"
    WRONG: asking "When would you like to schedule your Steak Dinner?" (forgetting tomorrow context)
    REASONING: Must remember multi-task context - steak was chosen for tomorrow's dinner, now ask about Tuesday's breakfast

19. CRITICAL: Multi-Task "You Choose" Context:
    Conversation history:
    User: "Schedule me dinner for tomorrow and breakfast for Tuesday"
    Agent: "What dinner would you like to schedule for tomorrow? Here are some suggestions: • Chicken Parmesan • Steak Dinner"
    User: "Chicken"
    Agent: "I've scheduled Chicken Parmesan for tomorrow's dinner! Now, what breakfast would you like for Tuesday? Here are some suggestions: • Egg Tacos • Pancakes"
    User: "You choose"
    ANALYSIS: "You choose" in multi-task context applies ONLY to the current question (Tuesday breakfast), NOT the entire week
    CORRECT: intent_type="DIRECT_SCHEDULE", entities={{"meal_names": ["Egg Tacos"], "dates": ["2025-08-20"], "meal_types": ["breakfast"]}}, execution_plan=[{{"action": "schedule_meal", "meal_name": "Egg Tacos", "date": "2025-08-20", "meal_type": "breakfast"}}], reasoning="User delegated choice for Tuesday breakfast only - selecting Egg Tacos based on preferences"
    WRONG: intent_type="AUTONOMOUS_SCHEDULE" with dates=[next 7 days] (scheduling entire week)
    REASONING: In multi-task context, "you choose" applies only to the specific task being discussed (Tuesday breakfast), not globally

20. CRITICAL: Multi-Task Sequential Processing Example:
    User: "Schedule Dinner Thursday and breakfast Friday and lunch Saturday"
    ANALYSIS: Multi-task request with 3 incomplete tasks (all missing specific meal names)
    CORRECT: Process ONLY the first task - ask for Thursday dinner clarification only
    CORRECT: intent_type="DIRECT_SCHEDULE", entities={{"dates": ["2025-08-21"], "meal_types": ["dinner"]}}, needs_clarification=true, clarification_question="What dinner would you like to schedule for Thursday? Here are some suggestions from your meals:\n• Chicken Parmesan\n• Steak Dinner"
    WRONG: Asking for all 3 clarifications simultaneously: "What dinner for Thursday? And what breakfast for Friday? Lastly, what lunch for Saturday?"
    REASONING: Queue-like processing prevents overwhelming user experience - handle one task at a time
    NEXT_STEP: After user selects Thursday dinner, then ask about Friday breakfast

21. CRITICAL: Task Persistence Through Clarification Interruptions:
    Conversation history:
    User: "Schedule dinner tomorrow and breakfast Tuesday"
    Agent: "What dinner would you like to schedule for tomorrow? Here are some suggestions: • Chicken Parmesan • Steak Dinner"
    User: "Steal" (typo for "Steak")
    Agent: "It seems like you meant to say 'steak.' Could you please confirm if you want to schedule Steak Dinner?"
    User: "Yes"
    ANALYSIS: User confirmed Steak Dinner for tomorrow. CRITICAL: Original request had TWO tasks - dinner tomorrow AND breakfast Tuesday
    CORRECT: intent_type="DIRECT_SCHEDULE", entities={{"meal_names": ["Steak Dinner"], "dates": ["2025-08-18"], "meal_types": ["dinner"]}}, execution_plan=[{{"action": "schedule_meal", "meal_name": "Steak Dinner", "date": "2025-08-18", "meal_type": "dinner"}}], clarification_question="I've scheduled Steak Dinner for tomorrow! Now, what breakfast would you like for Tuesday? Here are some suggestions: • Egg Tacos • Pancakes"
    WRONG: Treating "Yes" as general help request: "How can I help you with your meals?" (loses track of pending Tuesday breakfast)
    REASONING: Must systematically track and complete ALL tasks from original multi-task request, even through clarification interruptions

22. CRITICAL: Task Queue Integration Example:
    TASK QUEUE STATE:
    Original Request: "Schedule dinner tomorrow and breakfast Tuesday"
    Current Task: dinner tomorrow (Status: pending)
    All Tasks:
      ⏳ dinner tomorrow (pending)
      ⏳ breakfast Tuesday (pending)
    
    User: "Yes" (confirming Steak Dinner)
    ANALYSIS: User confirmed meal for current_task. Check task queue - there's a pending breakfast Tuesday task
    CORRECT: Complete current task (dinner tomorrow) + continue with next pending task (breakfast Tuesday)
    CORRECT: intent_type="DIRECT_SCHEDULE", execution_plan=[{{"action": "schedule_meal", "meal_name": "Steak Dinner", "date": "2025-08-18", "meal_type": "dinner"}}], clarification_question="I've scheduled Steak Dinner for tomorrow! Now, what breakfast would you like for Tuesday? Here are some suggestions: • Egg Tacos • Pancakes"
    WRONG: Ignoring task queue and treating as standalone "Yes": "How can I help you with your meals?"
    REASONING: Task queue ensures systematic completion of all tasks from original multi-task request

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