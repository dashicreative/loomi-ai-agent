"""
Refactored Session Tools - Proper Pydantic AI Patterns

Clean tools that use RunContext dependency injection instead of global state.
"""

from typing import Dict, Optional
from pydantic_ai import RunContext
from Dependencies import RecipeDeps


async def save_meal_tool(ctx: RunContext[RecipeDeps], meal_number: int) -> Dict:
    """
    Save a meal from current batch to saved meals.
    Proper Pydantic AI tool using dependency injection.
    
    # TODO: UI INTEGRATION POINT
    # Frontend calls this when user clicks "Save" on recipe card
    
    Args:
        meal_number: Recipe number (1-5) from current batch
        
    Returns:
        Dict with save status
    """
    session = ctx.deps.session
    
    if not session.current_batch_recipes:
        return {
            "success": False,
            "message": "No recipes currently displayed. Please search for recipes first."
        }
    
    if meal_number < 1 or meal_number > len(session.current_batch_recipes):
        return {
            "success": False,
            "message": f"Invalid meal number {meal_number}. Please choose 1-{len(session.current_batch_recipes)}."
        }
    
    success = session.save_meal(meal_number)
    
    if success:
        meal = session.current_batch_recipes[meal_number - 1]
        return {
            "success": True,
            "message": f"Saved '{meal.get('title', 'Recipe')}' to your meal collection.",
            "saved_meal": {
                "title": meal.get('title'),
                "number": meal_number,
                "total_saved": len(session.saved_meals)
            }
        }
    else:
        return {
            "success": False,
            "message": "This recipe has already been saved."
        }


async def analyze_saved_meals_tool(ctx: RunContext[RecipeDeps], query: str, daily_goals: Optional[Dict] = None) -> Dict:
    """
    Analyze saved meals based on user query.
    Proper Pydantic AI tool using dependency injection.
    
    Args:
        query: Analysis query (e.g., "total calories", "protein for 100g goal")
        daily_goals: Optional daily nutrition goals
        
    Returns:
        Dict with analysis results
    """
    session = ctx.deps.session
    
    if not session.saved_meals:
        return {
            "status": "no_saved_meals",
            "message": "You haven't saved any meals yet in this session.",
            "analysis": None
        }
    
    # Get nutrition totals using proper method
    totals = session.get_nutrition_totals()
    query_lower = query.lower()
    
    # Goal-based queries (check FIRST)
    if any(word in query_lower for word in ['need', 'left', 'remain', 'goal', 'target', 'more']):
        import re
        goal_match = re.search(r'(\d+)\s*g', query_lower)
        
        if 'protein' in query_lower and goal_match:
            goal = float(goal_match.group(1))
            remaining = max(0, goal - totals['protein'])
            percentage = (totals['protein'] / goal * 100) if goal > 0 else 0
            
            # Store gap in session for future "meet my goal" queries
            if remaining > 0:
                session.current_nutrition_gaps['protein'] = remaining
            
            return {
                "status": "success",
                "analysis_type": "protein_goal",
                "goal": goal,
                "current": totals['protein'],
                "remaining": remaining,
                "percentage": percentage,
                "message": f"You've consumed {totals['protein']:.1f}g of your {goal:.0f}g protein goal ({percentage:.0f}% complete). You need {remaining:.1f}g more protein.",
                "meal_count": len(session.saved_meals)
            }
    
    # Total queries
    if any(word in query_lower for word in ['total', 'sum', 'all', 'how much', 'how many']):
        if 'calorie' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_calories", 
                "value": totals['calories'],
                "message": f"Your {len(session.saved_meals)} saved meals contain {totals['calories']:.0f} total calories.",
                "meal_count": len(session.saved_meals)
            }
        elif 'protein' in query_lower:
            return {
                "status": "success",
                "analysis_type": "total_protein",
                "value": totals['protein'],
                "message": f"Your {len(session.saved_meals)} saved meals contain {totals['protein']:.1f}g total protein.",
                "meal_count": len(session.saved_meals)
            }
    
    # Average queries
    if 'average' in query_lower or 'avg' in query_lower:
        meal_count = len(session.saved_meals) if session.saved_meals else 1
        averages = {k: v / meal_count for k, v in totals.items()}
        
        return {
            "status": "success",
            "analysis_type": "averages",
            "values": averages,
            "message": f"Average nutrition per meal ({len(session.saved_meals)} meals saved):",
            "breakdown": {
                "calories": f"{averages['calories']:.0f} kcal",
                "protein": f"{averages['protein']:.1f}g",
                "fat": f"{averages['fat']:.1f}g", 
                "carbs": f"{averages['carbs']:.1f}g"
            }
        }
    
    # Default: Return summary
    return {
        "status": "success",
        "analysis_type": "summary",
        "message": f"You have {len(session.saved_meals)} saved meals.",
        "totals": totals,
        "meal_count": len(session.saved_meals)
    }


async def temporary_save_meal_tool(ctx: RunContext[RecipeDeps], user_message: str) -> Dict:
    """
    TEMPORARY: Handle chat-based save commands like "save meal #3"
    DELETE THIS TOOL WHEN UI IS CONNECTED
    
    Args:
        user_message: User's message containing save command
        
    Returns:
        Dict with save result
    """
    import re
    
    patterns = [
        r'save\s+meal\s+#?(\d+)',
        r'save\s+recipe\s+#?(\d+)', 
        r'save\s+#?(\d+)',
        r'save\s+the\s+(\w+)\s+one'
    ]
    
    message_lower = user_message.lower()
    
    # Try numeric patterns
    for pattern in patterns[:3]:
        match = re.search(pattern, message_lower)
        if match:
            meal_number = int(match.group(1))
            return await save_meal_tool(ctx, meal_number)
    
    # Handle word numbers
    word_to_num = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}
    match = re.search(patterns[3], message_lower)
    if match:
        word = match.group(1)
        if word in word_to_num:
            meal_number = word_to_num[word]
            return await save_meal_tool(ctx, meal_number)
    
    return {
        "success": False,
        "message": "No save command found. Try 'save meal #3' or 'save recipe #2'",
        "_temporary_tool": True
    }