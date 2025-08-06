"""
Schedule Agent - Enhanced with fuzzy matching for meal names

Handles meal scheduling with fuzzy string matching to handle typos,
case variations, and partial matches.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from difflib import SequenceMatcher

from services.llm_service import llm_service
from models.ai_models import ChatMessage, AIResponse, AIAction, ActionType
from storage.local_storage import LocalStorage


# Pydantic models for structured outputs
class ScheduleMealParameters(BaseModel):
    meal_name: str
    date: str
    occasion: Optional[str] = Field(default=None)  # No default occasion
    servings: Optional[int] = Field(default=4)
    notes: Optional[str] = None


class Conflict(BaseModel):
    date: str
    occasion: str
    existing_meal: str
    action: Optional[str] = Field(default="skip")


class ClarificationOption(BaseModel):
    option: str
    description: str
    date: Optional[str] = None
    meal_name: Optional[str] = None
    action: Optional[str] = None


class ScheduleAction(BaseModel):
    type: str
    parameters: Dict[str, Any]


class AgentResponse(BaseModel):
    status: str = Field(..., description="success, needs_clarification, or error")
    conversational_response: str
    actions: Optional[List[ScheduleAction]] = Field(default_factory=list)
    clarification_type: Optional[str] = None
    pending_actions: Optional[List[ScheduleAction]] = None
    clarification_options: Optional[List[ClarificationOption]] = None
    conflicts: Optional[List[Conflict]] = None
    validation_errors: Optional[List[str]] = None


class ScheduleAgent:
    """
    Enhanced meal scheduling agent with fuzzy string matching for meal names
    """
    
    def __init__(self, fuzzy_threshold: float = 0.6):
        self.storage = LocalStorage()
        self.fuzzy_threshold = fuzzy_threshold  # Minimum similarity score (0.0 to 1.0)
        
        # Enhanced prompt template with fuzzy matching guidance
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """# Meal Scheduling Sub-Agent Prompt Template

## System Role
You are a specialized meal scheduling sub-agent within an AI meal planning app. Your primary responsibility is to understand meal scheduling requests and convert them into precise scheduling actions. You handle conversational clarifications when needed but do NOT handle recipe discovery - you focus exclusively on scheduling operations and related clarifications.

## Your Capabilities
- Schedule single or multiple meals to specific dates and meal occasions
- Reschedule existing meals to new dates/occasions
- Handle relative dates (today, tomorrow, Monday, next week, etc.)
- Process batch scheduling requests
- Validate scheduling conflicts and constraints
- Generate precise action parameters for the execution engine
- **Handle meal name variations, typos, and fuzzy matches**

## Input Context
Current context:
- Today's date: {current_date}
- Available meals: {available_meals}
- Fuzzy matched meals (if any): {fuzzy_matches}
- Currently scheduled meals: {scheduled_meals}
- User preferences: {user_preferences}

## Fuzzy Matching Information
When fuzzy_matches is provided, it means the user's input didn't exactly match any meal name, but we found similar meals. You should:
1. Use the best fuzzy match if confidence is high
2. Ask for clarification if multiple good matches exist
3. Suggest the closest match if you're unsure

## Output Format
You must respond with ONLY a JSON object in one of these formats:

### Successful Scheduling (No clarification needed)
```json
{{
  "status": "success",
  "conversational_response": "I've scheduled [meal details] for you! (I matched '[user_input]' to '[actual_meal_name]')",
  "actions": [
    {{
      "type": "schedule_meal",
      "parameters": {{
        "meal_name": "exact meal name from saved_meals",
        "date": "YYYY-MM-DD",
        "occasion": "breakfast|lunch|dinner|snack|null (use meal's default)",
        "servings": number,
        "notes": "optional notes"
      }}
    }}
  ],
  "conflicts": []
}}
```

### Needs Clarification (Multiple fuzzy matches or ambiguous)
```json
{{
  "status": "needs_clarification",
  "conversational_response": "I found a few meals that might match '[user_input]'. Did you mean: [list options]?",
  "clarification_type": "fuzzy_match_ambiguity|date_ambiguity|conflict_resolution|meal_not_found|serving_size",
  "pending_actions": [...],
  "clarification_options": [
    {{
      "option": "Option 1: Schedule 'Chicken Parmesan'",
      "description": "Close match to your input",
      "meal_name": "Chicken Parmesan"
    }}
  ]
}}
```

### Error
```json
{{
  "status": "error",
  "conversational_response": "I couldn't find any meals similar to '[user_input]'. Available meals are: [list]",
  "validation_errors": ["No fuzzy matches found"]
}}
```

## Date Processing Rules
1. Convert relative dates to absolute YYYY-MM-DD format:
   - "today" → {current_date}
   - "tomorrow" → current_date + 1 day
   - Weekday names → next occurrence
   - "next [weekday]" → that weekday of next week (7+ days ahead)

2. Only schedule for current date or future dates

3. If occasion not specified by user, use the meal's default occasion
4. If meal has no default occasion, don't mention occasion in response

## Conflict Handling
Check if date + occasion already has a scheduled meal. If so, note in conflicts array.

## Critical Rules
1. Always respond with valid JSON in the specified format
2. Use exact meal names from available_meals list (after fuzzy matching)
3. Convert all dates to YYYY-MM-DD format
4. Be conversational but concise - use natural date words (today, tomorrow, Monday) instead of exact dates
5. Handle ambiguity by requesting clarification
6. **When using fuzzy matches, acknowledge the match in your response**
7. **Prefer exact matches over fuzzy matches when available**
8. **If no occasion specified, set occasion to null - the system will use meal's default**
9. **Use natural date language in responses: today, tomorrow, Monday, etc.**"""),
            ("human", "{user_request}")
        ])
        
        # JSON output parser
        self.output_parser = JsonOutputParser()
    
    def _fuzzy_match_meal_name(self, user_input: str, available_meals: List[str]) -> List[Tuple[str, float]]:
        """
        Find fuzzy matches for meal names using multiple strategies
        Returns list of (meal_name, confidence_score) tuples sorted by confidence
        """
        if not user_input or not available_meals:
            return []
        
        matches = []
        user_input_lower = user_input.lower().strip()
        
        for meal_name in available_meals:
            meal_name_lower = meal_name.lower().strip()
            
            # Strategy 1: Exact match (highest priority)
            if user_input_lower == meal_name_lower:
                matches.append((meal_name, 1.0))
                continue
            
            # Strategy 2: Substring match (high priority)
            if user_input_lower in meal_name_lower or meal_name_lower in user_input_lower:
                # Calculate overlap ratio
                overlap = min(len(user_input_lower), len(meal_name_lower)) / max(len(user_input_lower), len(meal_name_lower))
                matches.append((meal_name, 0.85 + (overlap * 0.1)))  # 0.85-0.95 range
                continue
            
            # Strategy 3: Sequence matching (handles typos and rearrangement)
            sequence_ratio = SequenceMatcher(None, user_input_lower, meal_name_lower).ratio()
            if sequence_ratio >= self.fuzzy_threshold:
                matches.append((meal_name, sequence_ratio))
                continue
            
            # Strategy 4: Word-based matching (handles missing/extra words)
            user_words = set(user_input_lower.split())
            meal_words = set(meal_name_lower.split())
            
            if user_words and meal_words:
                # Calculate Jaccard similarity
                intersection = len(user_words.intersection(meal_words))
                union = len(user_words.union(meal_words))
                jaccard_score = intersection / union if union > 0 else 0
                
                # Also check if any significant words match
                word_match_score = intersection / len(meal_words) if meal_words else 0
                
                combined_score = max(jaccard_score, word_match_score * 0.8)
                if combined_score >= self.fuzzy_threshold:
                    matches.append((meal_name, combined_score))
        
        # Sort by confidence score (descending) and return top matches
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]  # Return top 5 matches
    
    def _get_next_weekday_date(self, weekday_name: str, from_date: date) -> str:
        """Convert weekday name to next occurrence date"""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekdays.get(weekday_name.lower())
        if target_weekday is None:
            return from_date.isoformat()
        
        days_ahead = target_weekday - from_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
            
        target_date = from_date + timedelta(days=days_ahead)
        return target_date.isoformat()
    
    def _format_scheduled_meals(self, scheduled_meals) -> str:
        """Format scheduled meals for the prompt"""
        if not scheduled_meals:
            return "No meals currently scheduled"
        
        formatted = []
        for sm in scheduled_meals:
            meal = self.storage.get_meal_by_id(str(sm.meal_id))
            meal_name = meal.name if meal else "Unknown Meal"
            formatted.append(f"- {sm.date}: {meal_name} ({sm.occasion})")
        
        return "\n".join(formatted)
    
    def _format_date_naturally(self, target_date: date) -> str:
        """Convert date to natural language (today, tomorrow, Monday, etc.)"""
        today = date.today()
        
        if target_date == today:
            return "today"
        elif target_date == today + timedelta(days=1):
            return "tomorrow"
        elif target_date == today - timedelta(days=1):
            return "yesterday"
        else:
            # Check if it's within this week
            days_diff = (target_date - today).days
            if 0 < days_diff <= 7:
                weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                return weekday_names[target_date.weekday()]
            elif -7 <= days_diff < 0:
                weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                return f"last {weekday_names[target_date.weekday()]}"
            elif 7 < days_diff <= 14:
                weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                return f"next {weekday_names[target_date.weekday()]}"
            else:
                # Use month and day for further dates
                return target_date.strftime("%B %d")
    
    def _get_meal_default_occasion(self, meal_name: str) -> Optional[str]:
        """Get the default occasion for a meal"""
        meals = self.storage.load_meals()
        for meal in meals:
            if meal.name.lower() == meal_name.lower():
                if hasattr(meal.occasion, 'value'):
                    return meal.occasion.value
                else:
                    return meal.occasion if meal.occasion else None
        return None
    
    def _extract_meal_name_from_request(self, user_request: str) -> str:
        """
        Extract potential meal name from user request
        This is a simple extraction - could be enhanced with NLP
        """
        # Remove common scheduling words to isolate meal name
        scheduling_words = [
            'schedule', 'add', 'put', 'plan', 'book', 'set',
            'for', 'on', 'to', 'at', 'tomorrow', 'today',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'next', 'this', 'breakfast', 'lunch', 'dinner', 'snack'
        ]
        
        words = user_request.lower().split()
        meal_words = []
        
        for word in words:
            # Remove punctuation
            clean_word = ''.join(c for c in word if c.isalnum())
            if clean_word and clean_word not in scheduling_words:
                meal_words.append(clean_word)
        
        # Join remaining words - this is our best guess at the meal name
        return ' '.join(meal_words) if meal_words else user_request
    
    def _format_fuzzy_matches(self, fuzzy_matches: List[Tuple[str, float]]) -> str:
        """Format fuzzy matches for the prompt"""
        if not fuzzy_matches:
            return "No fuzzy matches found"
        
        formatted = []
        for meal_name, confidence in fuzzy_matches:
            confidence_pct = int(confidence * 100)
            formatted.append(f"- {meal_name} ({confidence_pct}% match)")
        
        return "\n".join(formatted)
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process a meal scheduling request with fuzzy matching
        """
        try:
            # Load current data
            meals = self.storage.load_meals()
            available_meals = [meal.name for meal in meals]
            scheduled_meals = self.storage.load_scheduled_meals()
            
            # Extract potential meal name and find fuzzy matches
            potential_meal_name = self._extract_meal_name_from_request(message.content)
            fuzzy_matches = self._fuzzy_match_meal_name(potential_meal_name, available_meals)
            
            # Format context
            user_preferences = message.user_context.get("preferences", {"default_servings": 4})
            
            # Build the prompt with context and fuzzy matches
            chain = self.prompt | llm_service.claude | self.output_parser
            
            # Execute the chain
            response_dict = await chain.ainvoke({
                "user_request": message.content,
                "current_date": date.today().isoformat(),
                "available_meals": ", ".join(available_meals),
                "fuzzy_matches": self._format_fuzzy_matches(fuzzy_matches),
                "scheduled_meals": self._format_scheduled_meals(scheduled_meals),
                "user_preferences": str(user_preferences)
            })
            
            # Convert dict to AgentResponse object
            agent_response = AgentResponse(**response_dict)
            
            # Process based on status
            if agent_response.status == "success":
                # Execute the actions
                executed_actions = []
                for action in agent_response.actions:
                    if action.type == "schedule_meal":
                        result = await self._execute_schedule_action(action.parameters)
                        if result["success"]:
                            executed_actions.append(AIAction(
                                type=ActionType.SCHEDULE_MEAL,
                                parameters=result
                            ))
                
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=executed_actions,
                    model_used="claude"
                )
            
            elif agent_response.status == "needs_clarification":
                # Return clarification request
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="claude"
                )
            
            else:  # error
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="claude"
                )
                
        except Exception as e:
            print(f"Agent processing error: {e}")
            # Fallback to fuzzy matching process
            return await self._fallback_process_with_fuzzy(message)
    
    async def _execute_schedule_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the meal scheduling action with fuzzy matching"""
        try:
            # Find the meal using fuzzy matching
            meals = self.storage.load_meals()
            target_meal = None
            
            # First try exact match
            for meal in meals:
                if meal.name.lower() == parameters["meal_name"].lower():
                    target_meal = meal
                    break
            
            # If no exact match, try fuzzy matching
            if not target_meal:
                meal_names = [meal.name for meal in meals]
                fuzzy_matches = self._fuzzy_match_meal_name(parameters["meal_name"], meal_names)
                
                if fuzzy_matches and fuzzy_matches[0][1] >= self.fuzzy_threshold:
                    # Use the best fuzzy match
                    best_match_name = fuzzy_matches[0][0]
                    for meal in meals:
                        if meal.name == best_match_name:
                            target_meal = meal
                            break
            
            if not target_meal:
                return {
                    "success": False,
                    "error": f"Meal '{parameters['meal_name']}' not found even with fuzzy matching"
                }
            
            # Determine the occasion to use
            from models.scheduled_meal import ScheduledMeal, MealOccasion
            from uuid import uuid4
            
            target_date = date.fromisoformat(parameters["date"])
            
            # Use provided occasion, or meal's default, or dinner as final fallback
            if parameters.get("occasion"):
                occasion_str = parameters["occasion"]
            else:
                # Use meal's default occasion (it's already a string in our current model)
                if hasattr(target_meal.occasion, 'value'):
                    meal_default_occasion = target_meal.occasion.value
                else:
                    meal_default_occasion = target_meal.occasion if target_meal.occasion else "dinner"
                occasion_str = meal_default_occasion
            
            meal_occasion = MealOccasion(occasion_str)
            
            scheduled_meal = ScheduledMeal(
                id=uuid4(),
                meal_id=target_meal.id,
                date=target_date,
                occasion=meal_occasion
            )
            
            # Save to storage
            self.storage.add_scheduled_meal(scheduled_meal)
            
            # Format natural date for response
            natural_date = self._format_date_naturally(target_date)
            
            return {
                "success": True,
                "scheduled_meal_id": str(scheduled_meal.id),
                "meal_name": target_meal.name,
                "date": parameters["date"],
                "natural_date": natural_date,
                "meal_type": occasion_str,
                "occasion_specified": bool(parameters.get("occasion"))  # Track if user specified occasion
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _fallback_process_with_fuzzy(self, message: ChatMessage) -> AIResponse:
        """Enhanced fallback processing with fuzzy matching"""
        try:
            meals = self.storage.load_meals()
            meal_names = [m.name for m in meals]
            
            # Extract potential meal name and find fuzzy matches
            potential_meal_name = self._extract_meal_name_from_request(message.content)
            fuzzy_matches = self._fuzzy_match_meal_name(potential_meal_name, meal_names)
            
            if not fuzzy_matches:
                return AIResponse(
                    conversational_response=f"I couldn't find any meals similar to '{potential_meal_name}'. Available meals are: {', '.join(meal_names)}",
                    actions=[],
                    model_used="fallback"
                )
            
            # Use the best fuzzy match if confidence is good
            best_match, confidence = fuzzy_matches[0]
            
            if confidence < 0.7:  # Low confidence, ask for clarification
                top_matches = [match[0] for match in fuzzy_matches[:3]]
                return AIResponse(
                    conversational_response=f"I'm not sure which meal you meant by '{potential_meal_name}'. Did you mean one of these: {', '.join(top_matches)}?",
                    actions=[],
                    model_used="fallback"
                )
            
            # High confidence, proceed with scheduling
            meal_name = best_match
            
            # Simple date extraction (same as before)
            target_date = date.today()
            content_lower = message.content.lower()
            
            if "tomorrow" in content_lower:
                target_date = date.today() + timedelta(days=1)
            elif "today" in content_lower:
                target_date = date.today()
            else:
                # Handle weekday names
                weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                for i, day_name in enumerate(weekdays):
                    if day_name in content_lower:
                        days_ahead = (i - date.today().weekday()) % 7
                        if days_ahead == 0:
                            days_ahead = 7
                        target_date = date.today() + timedelta(days=days_ahead)
                        break
            
            # Schedule the meal (no occasion specified - will use meal's default)
            result = await self._execute_schedule_action({
                "meal_name": meal_name,
                "date": target_date.isoformat()
                # No occasion specified - will use meal's default
            })
            
            if result["success"]:
                confidence_msg = f" (I matched '{potential_meal_name}' to '{meal_name}')" if confidence < 1.0 else ""
                
                # Build response with natural date and conditional occasion mention
                if result.get("occasion_specified"):
                    response = f"✅ I've scheduled {meal_name} for {result['meal_type']} {result['natural_date']}!{confidence_msg}"
                else:
                    response = f"✅ I've scheduled {meal_name} for {result['natural_date']}!{confidence_msg}"
                action = AIAction(
                    type=ActionType.SCHEDULE_MEAL,
                    parameters=result
                )
                return AIResponse(
                    conversational_response=response,
                    actions=[action],
                    model_used="fallback"
                )
            else:
                return AIResponse(
                    conversational_response=f"❌ Sorry, I couldn't schedule that meal: {result['error']}",
                    actions=[],
                    model_used="fallback"
                )
        
        except Exception as e:
            return AIResponse(
                conversational_response=f"❌ An error occurred while processing your request: {str(e)}",
                actions=[],
                model_used="fallback"
            )


# Test function for fuzzy matching
async def test_fuzzy_matching():
    """Test the fuzzy matching capabilities"""
    agent = ScheduleAgent(fuzzy_threshold=0.6)
    
    # Simulate some saved meals
    print("🧪 Testing Fuzzy Matching Capabilities")
    print("=" * 50)
    
    # Test various typo scenarios
    test_cases = [
        "Schedule chiken parmesan for Tuesday",  # Missing 'c'
        "Add psta to Wednesday",                   # Missing 'a' 
        "Schedule Chicken Parmasan for Thursday",  # Typo in 'parmesan'
        "Put turkey bowel on Friday",             # Wrong word 'bowel' vs 'bowl'
        "Schedule CHICKEN PARMESAN for Monday",   # Case variation
        "Add chicken parm for Saturday",          # Shortened name
        "Schedule completely wrong name for Sunday"  # No match
    ]
    
    for test_msg in test_cases:
        print(f"\n🔍 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")
        if result.actions:
            print(f"   Scheduled: {result.actions[0].parameters.get('meal_name', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(test_fuzzy_matching())