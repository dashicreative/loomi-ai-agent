# Scheduling Agent Requirements Document

## Agent Overview

The Scheduling Agent is a conversational AI sub-agent within the meal planning application that handles all meal scheduling operations. It maintains conversational context, builds "schedule profiles" from partial user input, and makes intelligent decisions based on user data when information is incomplete.

## Core Purpose & Scope

**Primary Function**: Handle all meal scheduling requests through natural conversation
**Scope**: Meal scheduling operations only - recipe discovery and other functions are handled by separate agents
**Interaction Style**: Extremely conversational, friendly, and helpful with intelligent follow-up questions

## Core Functionality Requirements

### 1. Schedule Profile Building
The agent must construct a complete "schedule profile" for each request containing:

**Required Components**:
- **What meal**: Specific meal name from user's saved meals
- **When to schedule**: Date and/or time specification

**Optional Components**:
- **Meal occasion**: breakfast, lunch, dinner, snack (defaults to dinner if not specified)
- **Number of batches**: How many servings/portions (defaults to 1)
- **Frequency**: Single occurrence vs recurring patterns

### 2. Intelligent Information Gathering
When users provide incomplete information, the agent must:

1. **Ask clarifying questions** to obtain missing required components
2. **Limit follow-up attempts** to maximum 2 clarification requests
3. **Use user data** to make intelligent suggestions when information is missing
4. **Fall back to reasonable defaults** when user data is insufficient

### 3. User Data Analysis for Smart Suggestions
The agent should analyze user's historical data to inform decisions:

**Meal Selection Logic**:
- Most frequently scheduled meals
- Recently added but unscheduled meals  
- Meals scheduled on similar days of the week
- Seasonal or time-based patterns

**Timing Logic**:
- User's typical scheduling patterns (which days they usually schedule meals)
- Most common meal occasions for specific meal types
- Avoided days or times based on past deletions/rescheduling

**Suggestion Constraints**:
- Maximum 7 meal suggestions at once
- Typical response: 3 meal suggestions
- Never return complete saved meals list (overwhelming)

### 4. Conversation Management

**Context Window**: 
- Begins with user's initial request
- Maintains context through clarification questions and responses
- Ends after successful action completion or user confirmation of "no further help needed"
- Auto-expires after 10 minutes of inactivity

**Conversation Flow**:
1. Parse initial request for schedule profile components
2. Ask clarifying questions for missing required information (max 2 attempts)
3. Use user data or defaults to fill gaps
4. Confirm action before execution
5. Execute scheduling action
6. Ask if user needs additional help
7. End conversation or continue based on response

## Required Capabilities

### Core Scheduling Operations
1. **Schedule specific meals on specific dates**
2. **Schedule meals for time periods** (week, multiple days)
3. **Reschedule existing meals** (move to different date/time)
4. **Clear scheduled meals** (specific days, date ranges, or meal occasions)
5. **Query current schedule** (what's scheduled, specific day queries)
6. **Batch scheduling** (multiple servings of same meal)
7. **Recurring meal scheduling** (weekly patterns, regular meals)

### Intelligence Features
1. **Partial input completion** using user data analysis
2. **Smart meal suggestions** based on scheduling history
3. **Conflict detection** (already scheduled meals on requested dates)
4. **Default meal occasion assignment** (dinner if not specified)
5. **Reasonable fallbacks** for new users or insufficient data

### Conversation Features
1. **Natural language understanding** for dates (today, tomorrow, Friday, next week)
2. **Context retention** within conversation window
3. **Clarification question generation**
4. **Confirmation requests** before executing actions
5. **Error handling** with helpful explanations
6. **Conversation continuation** management

## User Experience Guidelines

### Response Style
- **Friendly and conversational** tone
- **Clear and concise** explanations
- **Helpful suggestions** without overwhelming choices
- **Confirmation of actions** before execution
- **Graceful error handling** with alternatives

### Suggestion Limits
- **Maximum 7 suggestions** per response
- **Typical 3 suggestions** for meal recommendations
- **Prioritize by relevance** (frequency, recency, user patterns)
- **Include brief descriptions** when helpful

### Error Handling
- **Graceful degradation** when user data is insufficient
- **Clear explanations** when requests cannot be fulfilled
- **Alternative suggestions** when primary request fails
- **Helpful guidance** for correcting issues

## Technical Integration Requirements

### Data Access Needed
- **User's saved meals** (names, ingredients, meal occasions)
- **Current meal schedule** (dates, meals, occasions, servings)
- **Scheduling history** (frequency data, patterns, past deletions)
- **User preferences** (dietary restrictions, household size)

### Actions the Agent Can Execute
```python
# Schedule Operations
schedule_meal(meal_name, date, occasion, servings)
reschedule_meal(current_date, current_occasion, new_date, new_occasion)
clear_schedule(date_range, occasions)
query_schedule(date_range)

# Batch Operations  
schedule_multiple_meals(meal_list, date_range, distribution_pattern)
schedule_recurring_meal(meal_name, day_of_week, occasion, duration)
```

### Response Format
```python
{
    "conversational_response": "I'll schedule chicken parmesan for Tuesday dinner!",
    "actions": [
        {
            "type": "schedule_meal",
            "parameters": {
                "meal_name": "chicken parmesan",
                "date": "2025-01-15",
                "occasion": "dinner", 
                "servings": 1
            }
        }
    ],
    "needs_clarification": false,
    "clarification_question": null,
    "conversation_context": {...}
}
```

## Conversation Test Cases

### Test Category 1: Complete Information (Direct Scheduling)
1. **"Schedule chicken parmesan for Tuesday dinner"**
   - Expected: Direct scheduling, confirmation message
   
2. **"Add pasta to Monday lunch"**
   - Expected: Schedule pasta on next Monday for lunch
   
3. **"Put salmon on Friday for 4 servings"**
   - Expected: Schedule salmon for Friday dinner (default) with 4 servings
   
4. **"Schedule my egg tacos for breakfast on Friday"**
   - Expected: Schedule egg tacos for Friday breakfast

### Test Category 2: Missing Information - Meal Clarification
5. **"Schedule dinner for tomorrow"**
   - Expected: Ask which meal to schedule, provide 3 suggestions based on user data
   
6. **"Add something to Tuesday"**
   - Expected: Ask what meal and what meal occasion, suggest popular options
   
7. **"Schedule my usual breakfast for Friday"**
   - Expected: Identify most frequent breakfast item or ask for clarification

### Test Category 3: Missing Information - Date Clarification
8. **"Schedule chicken parmesan"**
   - Expected: Ask when to schedule it, suggest available dates
   
9. **"Add pasta to lunch"**
   - Expected: Ask which day, suggest upcoming days
   
10. **"Schedule my salmon for dinner"**
    - Expected: Ask what day, suggest based on user's typical patterns

### Test Category 4: Batch and Multi-Meal Scheduling
11. **"Schedule my meals for the week"**
    - Expected: Ask how many meals per day, which occasions, then suggest meal distribution
    
12. **"Plan 3 dinners this week"**
    - Expected: Suggest 3 meals for 3 different days, ask for confirmation
    
13. **"Schedule breakfast for every day next week"**
    - Expected: Ask which breakfast meal, then schedule for 7 days
    
14. **"Add 5 servings of chicken to Wednesday"**
    - Expected: Schedule chicken for Wednesday dinner with 5 servings

### Test Category 5: Rescheduling Operations
15. **"Move today's dinner to tomorrow"**
    - Expected: Identify today's dinner, move to tomorrow, confirm action
    
16. **"Reschedule Friday's lunch for Saturday"**
    - Expected: Move Friday lunch meal to Saturday lunch
    
17. **"Change Wednesday's breakfast to dinner"**
    - Expected: Move Wednesday breakfast meal to Wednesday dinner

### Test Category 6: Clearing and Querying
18. **"Clear my schedule for the week"**
    - Expected: Confirm deletion of all scheduled meals for current week
    
19. **"What's for dinner today?"**
    - Expected: Return today's scheduled dinner or indicate nothing scheduled
    
20. **"What's my meal schedule for this week?"**
    - Expected: List all scheduled meals organized by day and occasion
    
21. **"Remove Tuesday's lunch"**
    - Expected: Delete Tuesday lunch meal, confirm action

### Test Category 7: Complex and Edge Cases
22. **"Schedule pasta for Monday and chicken for Wednesday"**
    - Expected: Handle multiple scheduling requests in one message
    
23. **"Add my favorite meal for tomorrow"**
    - Expected: Identify most frequently scheduled meal or ask for clarification
    
24. **"Schedule something healthy for this week"**
    - Expected: Ask for more specific requirements, suggest healthy options from saved meals
    
25. **"Clear Friday and add something else"**
    - Expected: Clear Friday's meals, then ask what to add

### Test Category 8: Conversation Continuity
26. **Initial: "Schedule dinner for tomorrow"**
    **Follow-up: "Make it chicken parmesan"**
    - Expected: Remember context, schedule chicken parmesan for tomorrow dinner
    
27. **Initial: "What's for dinner this week?"**
    **Follow-up: "Change Wednesday to pasta"**
    - Expected: Understand context, change Wednesday dinner to pasta
    
28. **Initial: "Clear my schedule"**
    **Follow-up: "Actually just Monday"**
    - Expected: Clarify to only clear Monday's schedule

29. **Initial: "Schedule me dinner for tomorrow and breakfast for Tuesday"**
    **Follow-up: "Let's do steak"**
    - Expected: Remember multi-task context, schedule steak for tomorrow's dinner, then ask for Tuesday's breakfast selection
    - Tests: Multi-task context retention, sequential task processing, temporal context preservation

## Success Criteria

### Functional Requirements
- ✅ Handle all 29 test cases with appropriate responses
- ✅ Successfully build schedule profiles from partial information
- ✅ Make intelligent suggestions based on user data
- ✅ Maintain conversation context within conversation window
- ✅ Execute scheduling actions correctly in backend system

### Performance Requirements
- ✅ Average response time under 3 seconds
- ✅ 95% accuracy in intent recognition
- ✅ 90% user satisfaction with suggestions (when user data available)
- ✅ Graceful handling of edge cases and errors

### User Experience Requirements
- ✅ Natural conversational flow
- ✅ Maximum 2 clarification questions per request
- ✅ Clear confirmation of actions before execution
- ✅ Helpful error messages with alternatives
- ✅ Appropriate suggestion limits (3-7 options maximum)

## Developer Implementation Notes

### Key Decision Points
1. **User Data Insufficient**: How to gracefully fall back to defaults
2. **Conflicting Requests**: How to handle scheduling conflicts
3. **Ambiguous Dates**: How to interpret relative date references
4. **Meal Matching**: How to handle fuzzy matching of meal names
5. **Context Expiration**: How to handle conversation timeouts

### Integration Dependencies
- User meal database access
- Current schedule database access
- Scheduling history analytics
- User preference settings
- Date/time parsing utilities

This document provides complete requirements for implementing a robust, conversational scheduling agent that can handle the full spectrum of meal scheduling scenarios while maintaining excellent user experience through intelligent suggestions and natural conversation flow.