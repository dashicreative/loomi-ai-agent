"""
Comprehensive Schedule Agent - Combines Multi-Task + All Enhanced Features

This agent includes:
- Multi-task consecutive processing
- Advanced fuzzy matching
- Natural date formatting
- Smart occasion handling
- Conflict detection and resolution
- Clarification handling
- User preferences integration
- All prompt template enhancements
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


# Enhanced Pydantic models with all features
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


class ClearScheduleParameters(BaseModel):
    date_range: str = Field(..., description="Date range to clear: 'all', 'week', 'month', or 'custom'")
    start_date: Optional[str] = Field(default=None, description="Start date for custom range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="End date for custom range (YYYY-MM-DD)")


class ScheduleAction(BaseModel):
    type: str
    parameters: Dict[str, Any]


class TaskAction(BaseModel):
    task_number: int
    meal_name: str
    date: str
    occasion: Optional[str] = None
    servings: Optional[int] = Field(default=4)
    notes: Optional[str] = None
    original_text: str


class AgentResponse(BaseModel):
    status: str = Field(..., description="success, needs_clarification, partial_success, or error")
    conversational_response: str
    actions: Optional[List[ScheduleAction]] = Field(default_factory=list)
    
    # Multi-task fields
    total_tasks: Optional[int] = None
    completed_tasks: Optional[int] = None
    failed_tasks: Optional[int] = None
    
    # Clarification fields
    clarification_type: Optional[str] = None
    pending_actions: Optional[List[ScheduleAction]] = None
    clarification_options: Optional[List[ClarificationOption]] = None
    conflicts: Optional[List[Conflict]] = None
    validation_errors: Optional[List[str]] = None


class ComprehensiveScheduleAgent:
    """
    Comprehensive Schedule Agent with ALL enhanced features + multi-task support
    """
    
    def __init__(self, fuzzy_threshold: float = 0.6):
        self.storage = LocalStorage()
        self.fuzzy_threshold = fuzzy_threshold
        
        # Comprehensive prompt template combining all features
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """# Comprehensive Meal Scheduling Agent - Multi-Task + Advanced Features

## System Role
You are an advanced meal scheduling agent that can handle both single and multiple scheduling requests with sophisticated clarification, conflict resolution, and fuzzy matching capabilities.

## Multi-Task Processing
When users request multiple tasks:
1. Parse ALL individual tasks from the request
2. Process them consecutively (one-by-one, not parallel)
3. Handle each task with full advanced capabilities
4. Provide comprehensive summary of all results

## Your Advanced Capabilities
- Schedule single or multiple meals to specific dates and meal occasions
- Reschedule existing meals to new dates/occasions
- **Clear scheduled meals for specified date ranges (all, week, month, or custom dates)**
- Handle relative dates (today, tomorrow, Monday, next week, etc.)
- Process batch scheduling requests consecutively
- Validate scheduling conflicts and constraints
- Generate precise action parameters for the execution engine
- **Handle meal name variations, typos, and fuzzy matches**
- **Provide clarifications when needed**
- **Detect and resolve scheduling conflicts**
- **Support user preferences and serving sizes**

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

### Successful Scheduling (Single or Multiple Tasks)
```json
{{
  "status": "success",
  "conversational_response": "I've scheduled [meal details] for you! (I matched '[user_input]' to '[actual_meal_name]')",
  "total_tasks": number,
  "completed_tasks": number,
  "failed_tasks": 0,
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

### Successful Clear Schedule
```json
{{
  "status": "success",
  "conversational_response": "I've cleared [X] meals from your [time period] schedule!",
  "total_tasks": 1,
  "completed_tasks": 1,
  "failed_tasks": 0,
  "actions": [
    {{
      "type": "clear_schedule",
      "parameters": {{
        "date_range": "all|week|month|custom",
        "start_date": "YYYY-MM-DD (for custom range only)",
        "end_date": "YYYY-MM-DD (for custom range only)"
      }}
    }}
  ]
}}
```

### Partial Success (Some Tasks Failed)
```json
{{
  "status": "partial_success",
  "conversational_response": "I scheduled [X] meals successfully, but had issues with [Y] tasks...",
  "total_tasks": number,
  "completed_tasks": number,
  "failed_tasks": number,
  "actions": [...successful actions...],
  "validation_errors": ["errors for failed tasks"]
}}
```

### Needs Clarification
```json
{{
  "status": "needs_clarification",
  "conversational_response": "I need clarification for some of your requests...",
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
Check if date + occasion already has a scheduled meal. If so, note in conflicts array and ask for resolution.

## Multi-Task Examples
- Single: "Schedule chicken for Tuesday" → 1 task
- Multiple: "Schedule chicken for Tuesday and pasta for Wednesday" → 2 tasks
- Complex: "Add chicken for breakfast today, pasta for lunch tomorrow, and salmon for Friday" → 3 tasks
- Clear: "Clear the schedule for this week" → 1 clear task
- Clear All: "Clear entire meal schedule" or "clear all scheduled meals" → 1 clear all task

## Clear Schedule Examples
- "Clear schedule for this week" → date_range: "week"
- "Clear all scheduled meals" / "clear entire schedule" → date_range: "all" 
- "Clear schedule for this month" → date_range: "month"
- "Clear schedule from Monday to Friday" → date_range: "custom", start_date/end_date

## Critical Rules
1. Always respond with valid JSON in the specified format
2. Use exact meal names from available_meals list (after fuzzy matching)
3. Convert all dates to YYYY-MM-DD format
4. Be conversational but concise - use natural date words (today, tomorrow, Monday) instead of exact dates
5. Handle ambiguity by requesting clarification
6. **When using fuzzy matches, acknowledge the match in your response**
7. **Prefer exact matches over fuzzy matches when available**
8. **If no occasion specified, set occasion to null - the system will use meal's default**
9. **Use natural date language in responses: today, tomorrow, Monday, etc.**
10. **For multiple tasks, process each one thoroughly with full capabilities**
11. **Detect conflicts across all tasks and handle appropriately**"""),
            ("human", "{user_request}")
        ])
        
        self.output_parser = JsonOutputParser()
    
    def _fuzzy_match_meal_name(self, user_input: str, available_meals: List[str]) -> List[Tuple[str, float]]:
        """Find fuzzy matches for meal names using multiple strategies"""
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
    
    def _format_fuzzy_matches(self, fuzzy_matches: List[Tuple[str, float]]) -> str:
        """Format fuzzy matches for the prompt"""
        if not fuzzy_matches:
            return "No fuzzy matches found"
        
        formatted = []
        for meal_name, confidence in fuzzy_matches:
            confidence_pct = int(confidence * 100)
            formatted.append(f"- {meal_name} ({confidence_pct}% match)")
        
        return "\n".join(formatted)
    
    def _extract_potential_meal_names(self, text: str) -> List[str]:
        """Extract potential meal names from the entire request for fuzzy matching"""
        scheduling_words = {
            'schedule', 'add', 'put', 'plan', 'book', 'set', 'for', 'on', 'at', 'and',
            'today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 
            'saturday', 'sunday', 'next', 'this', 'breakfast', 'lunch', 'dinner', 'snack'
        }
        
        words = text.lower().split()
        potential_names = []
        current_phrase = []
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalnum())
            if clean_word and clean_word not in scheduling_words:
                current_phrase.append(clean_word)
            else:
                if current_phrase:
                    potential_names.append(' '.join(current_phrase))
                    current_phrase = []
        
        if current_phrase:
            potential_names.append(' '.join(current_phrase))
        
        return potential_names
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process message with comprehensive capabilities and multi-task support
        """
        try:
            # Load current data
            meals = self.storage.load_meals()
            available_meals = [meal.name for meal in meals]
            scheduled_meals = self.storage.load_scheduled_meals()
            
            # Get fuzzy matches for potential meal names in the request
            potential_meal_names = self._extract_potential_meal_names(message.content)
            all_fuzzy_matches = []
            for potential_name in potential_meal_names:
                matches = self._fuzzy_match_meal_name(potential_name, available_meals)
                all_fuzzy_matches.extend(matches)
            
            # Remove duplicates and sort
            unique_matches = list(set(all_fuzzy_matches))
            unique_matches.sort(key=lambda x: x[1], reverse=True)
            
            # Format context
            user_preferences = message.user_context.get("preferences", {"default_servings": 4})
            
            # Build the prompt with comprehensive context
            chain = self.prompt | llm_service.claude | self.output_parser
            
            # Execute the chain with full context
            response_dict = await chain.ainvoke({
                "user_request": message.content,
                "current_date": date.today().isoformat(),
                "available_meals": ", ".join(available_meals),
                "fuzzy_matches": self._format_fuzzy_matches(unique_matches[:10]),
                "scheduled_meals": self._format_scheduled_meals(scheduled_meals),
                "user_preferences": str(user_preferences)
            })
            
            # Convert dict to AgentResponse object
            agent_response = AgentResponse(**response_dict)
            
            # Process based on status
            if agent_response.status in ["success", "partial_success"]:
                # Execute the actions consecutively
                executed_actions = []
                for action in agent_response.actions:
                    if action.type == "schedule_meal":
                        result = await self._execute_schedule_action(action.parameters)
                        if result["success"]:
                            executed_actions.append(AIAction(
                                type=ActionType.SCHEDULE_MEAL,
                                parameters=result
                            ))
                    elif action.type == "clear_schedule":
                        result = await self._execute_clear_action(action.parameters)
                        if result["success"]:
                            executed_actions.append(AIAction(
                                type=ActionType.CLEAR_SCHEDULE,
                                parameters=result
                            ))
                
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=executed_actions,
                    model_used="comprehensive_agent"
                )
            
            elif agent_response.status == "needs_clarification":
                # Return clarification request
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="comprehensive_agent"
                )
            
            else:  # error
                return AIResponse(
                    conversational_response=agent_response.conversational_response,
                    actions=[],
                    model_used="comprehensive_agent"
                )
                
        except Exception as e:
            print(f"Comprehensive agent processing error: {e}")
            # Fallback to enhanced single-task processing
            return await self._fallback_process_with_fuzzy(message)
    
    async def _execute_schedule_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the meal scheduling action with comprehensive handling"""
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
                "occasion_specified": bool(parameters.get("occasion")),
                "servings": parameters.get("servings", 4),
                "notes": parameters.get("notes")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_clear_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the clear schedule action"""
        try:
            date_range = parameters.get("date_range", "all")
            start_date = None
            end_date = None
            
            # Parse custom date range if provided
            if date_range == "custom":
                if parameters.get("start_date"):
                    start_date = date.fromisoformat(parameters["start_date"])
                if parameters.get("end_date"):
                    end_date = date.fromisoformat(parameters["end_date"])
            
            # Execute the clear operation
            cleared_count = self.storage.clear_schedule(
                date_range=date_range,
                start_date=start_date,
                end_date=end_date
            )
            
            return {
                "success": True,
                "cleared_count": cleared_count,
                "date_range": date_range,
                "range_description": self._get_range_description(date_range, start_date, end_date)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_range_description(self, date_range: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> str:
        """Get a human-readable description of the date range"""
        if date_range == "all":
            return "entire schedule"
        elif date_range == "week":
            return "this week's schedule"
        elif date_range == "month":
            return "this month's schedule"
        elif date_range == "custom" and start_date and end_date:
            start_natural = self._format_date_naturally(start_date)
            end_natural = self._format_date_naturally(end_date)
            return f"schedule from {start_natural} to {end_natural}"
        else:
            return "schedule"
    
    async def _fallback_process_with_fuzzy(self, message: ChatMessage) -> AIResponse:
        """Enhanced fallback processing with fuzzy matching and natural dates"""
        try:
            meals = self.storage.load_meals()
            meal_names = [m.name for m in meals]
            
            # Extract potential meal name and find fuzzy matches
            potential_meal_name = self._extract_potential_meal_names(message.content)[0] if self._extract_potential_meal_names(message.content) else message.content
            fuzzy_matches = self._fuzzy_match_meal_name(potential_meal_name, meal_names)
            
            if not fuzzy_matches:
                return AIResponse(
                    conversational_response=f"I couldn't find any meals similar to '{potential_meal_name}'. Available meals are: {', '.join(meal_names)}",
                    actions=[],
                    model_used="comprehensive_fallback"
                )
            
            # Use the best fuzzy match if confidence is good
            best_match, confidence = fuzzy_matches[0]
            
            if confidence < 0.7:  # Low confidence, ask for clarification
                top_matches = [match[0] for match in fuzzy_matches[:3]]
                return AIResponse(
                    conversational_response=f"I'm not sure which meal you meant by '{potential_meal_name}'. Did you mean one of these: {', '.join(top_matches)}?",
                    actions=[],
                    model_used="comprehensive_fallback"
                )
            
            # High confidence, proceed with scheduling
            meal_name = best_match
            
            # Simple date extraction
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
                    model_used="comprehensive_fallback"
                )
            else:
                return AIResponse(
                    conversational_response=f"❌ Sorry, I couldn't schedule that meal: {result['error']}",
                    actions=[],
                    model_used="comprehensive_fallback"
                )
        
        except Exception as e:
            return AIResponse(
                conversational_response=f"❌ An error occurred while processing your request: {str(e)}",
                actions=[],
                model_used="comprehensive_fallback"
            )


# Test function for comprehensive capabilities
async def test_comprehensive_agent():
    """Test the comprehensive agent with all capabilities"""
    agent = ComprehensiveScheduleAgent(fuzzy_threshold=0.6)
    
    test_cases = [
        "Schedule storage test meal for today",  # Single task
        "Schedule storage test meal today and api test meal tomorrow",  # Multi-task
        "Add storge test meal for breakfast today and psta for lunch tomorrow",  # Multi-task with typos and occasions
        "Schedule nonexistent meal for today",  # Error handling
        "Schedule chicken parmesan today and pasta tomorrow",  # Fuzzy matching across multiple tasks
        "Clear the schedule for this week",  # Clear week
        "Clear all scheduled meals",  # Clear all
        "Clear schedule for this month",  # Clear month
    ]
    
    print("🧪 Testing Comprehensive Schedule Agent - All Features")
    print("=" * 60)
    
    for test_msg in test_cases:
        print(f"\n🔍 Test: '{test_msg}'")
        message = ChatMessage(content=test_msg, user_context={"preferences": {"default_servings": 4}})
        
        result = await agent.process(message)
        print(f"📝 Response: {result.conversational_response}")
        print(f"⚡ Actions: {len(result.actions)}")
        if result.actions:
            for i, action in enumerate(result.actions):
                params = action.parameters
                print(f"   {i+1}. {params.get('meal_name', 'N/A')} on {params.get('natural_date', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(test_comprehensive_agent())