# Session Features Testing Guide

## How to Test the New Features

### 1. **Basic Recipe Search (with Session Tracking)**
```python
# The search now automatically tracks shown URLs
result = await search_and_process_recipes_tool(
    ctx, 
    query="chicken recipes",
    session_id="user-session-123"  # Optional, auto-generated if not provided
)
```

### 2. **"Find More" Feature (Excludes Previous Results)**
```python
# Subsequent searches automatically exclude previously shown URLs
result = await search_and_process_recipes_tool(
    ctx,
    query="chicken recipes",  # Same query
    session_id="user-session-123"  # Same session
)
# This will return DIFFERENT recipes, not duplicates
```

### 3. **Save a Meal (User Clicks Save)**
```python
# When user saves recipe #3 from current batch
from Tools.session_tools import save_meal_to_session

result = await save_meal_to_session(
    session_id="user-session-123",
    meal_number=3  # Recipe position 1-5
)
```

### 4. **Analyze Saved Meals**
```python
from Tools.session_tools import analyze_saved_meals

# Total calories
result = await analyze_saved_meals(
    session_id="user-session-123",
    query="total calories?"
)

# Protein goal calculation
result = await analyze_saved_meals(
    session_id="user-session-123",
    query="I have a 100g protein goal, how much more do I need?"
)

# All nutrition totals
result = await analyze_saved_meals(
    session_id="user-session-123",
    query="show all nutrition totals"
)

# Average per meal
result = await analyze_saved_meals(
    session_id="user-session-123",
    query="average calories per meal"
)
```

### 5. **Get Session Status**
```python
from Tools.session_tools import get_session_status

status = await get_session_status("user-session-123")
# Returns saved meals, shown URLs count, search history
```

## Query Examples for Testing

### Basic Queries:
- "Find chicken recipes with 30g protein"
- "Find more" (excludes previous results)
- "Find more but vegetarian" (excludes previous + adds requirement)

### After Saving Meals:
- "How many calories in my saved meals?"
- "Total protein?"
- "I need 100g protein today, how much more?"
- "Which saved meal has the most calories?"
- "Average nutrition per meal?"

### Recipe References:
- "Can you tell me more about recipe #3?"
- "Is recipe #2 gluten-free?"
- "Which one has more protein, #1 or #4?"

## Testing Flow

1. **Run the test script:**
```bash
python test_session_features.py
```

2. **Test in actual agent conversation:**
   - Start with a recipe search
   - Simulate saving meals (recipes 1, 3, 4)
   - Ask about nutrition totals
   - Ask about protein goals
   - Try "find more" to get new recipes

3. **Check session persistence:**
   - URLs are tracked to prevent duplicates
   - Saved meals persist throughout session
   - Nutrition calculations work correctly

## Key Features Working:

✅ **Session Context Tracking** - Maintains state across searches
✅ **URL Exclusion** - "Find more" never shows duplicates  
✅ **Saved Meals** - Track what user saves
✅ **Nutrition Analysis** - Total/average calculations
✅ **Goal Calculations** - "Need 15g more protein"
✅ **Recipe References** - "Recipe #3" understood
✅ **Session Info** - Track all activity

## Debug Output:

When running searches, you'll see:
- `🔄 Generated mock session ID: mock-session-xxxxx`
- `🚫 Excluding X previously shown URLs from search`
- `📝 Created new session: session-id`

## Next Steps:

Phase 1 ✅ Complete - Conversation Intelligence implemented

Ready for:
- Phase 2: Error Recovery & Edge Cases
- Phase 3: Search Quality Improvements  
- Phase 4: Result Presentation Polish