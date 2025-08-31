"""
Session Management Tools for Recipe Discovery Agent

These tools allow the agent to save meals and analyze saved meals within a session.
"""

from typing import Dict, Optional
from .session_context import get_or_create_session


async def save_meal_to_session(session_id: Optional[str], meal_number: int) -> Dict:
    """
    Save a meal from the current batch to the session's saved meals.
    
    # TODO: UI INTEGRATION POINT
    # This is called when the user clicks "Save" on a recipe card in the UI.
    # Frontend should call this with: {session_id: "xxx", meal_number: 3}
    
    # TEMPORARY: Currently also called when user types "save meal #3" in chat
    # DELETE this chat-based saving when UI is connected
    
    Args:
        session_id: Session identifier (auto-generated if None)
        meal_number: Recipe number (1-5) from the current batch
        
    Returns:
        Dictionary with save status and message
    """
    session = get_or_create_session(session_id)
    
    if not session.current_batch_recipes:
        return {
            "success": False,
            "message": "No recipes currently displayed. Please search for recipes first."
        }
    
    if meal_number < 1 or meal_number > len(session.current_batch_recipes):
        return {
            "success": False,
            "message": f"Invalid meal number {meal_number}. Please choose a number between 1 and {len(session.current_batch_recipes)}."
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
            "message": f"This recipe has already been saved."
        }


async def analyze_saved_meals(session_id: Optional[str], query: str, daily_goals: Optional[Dict] = None) -> Dict:
    """
    Analyze saved meals based on user query.
    
    Args:
        session_id: Session identifier
        query: Analysis query (e.g., "total calories", "protein needed for 100g goal")
        daily_goals: Optional daily nutrition goals
        
    Returns:
        Dictionary with analysis results
    """
    from .saved_meals_analyzer import analyze_saved_meals_tool
    
    session = get_or_create_session(session_id)
    result = await analyze_saved_meals_tool(session, query, daily_goals)
    
    return result


async def get_session_status(session_id: Optional[str]) -> Dict:
    """
    Get current session status including saved meals and shown URLs.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Dictionary with session status information
    """
    session = get_or_create_session(session_id)
    
    return {
        "session_id": session.session_id,
        "saved_meals_count": len(session.saved_meals),
        "saved_meals": [
            {
                "title": meal.get('title', 'Unknown'),
                "saved_at": meal.get('saved_at'),
                "original_number": meal.get('original_number')
            }
            for meal in session.saved_meals
        ],
        "current_batch_count": len(session.current_batch_recipes),
        "total_shown_urls": len(session.shown_recipe_urls),
        "search_history": session.search_history,
        "nutrition_totals": session.get_saved_nutrition_totals() if session.saved_meals else None
    }


async def clear_session(session_id: Optional[str]) -> Dict:
    """
    Clear session data (for testing or when user starts over).
    
    Args:
        session_id: Session identifier
        
    Returns:
        Dictionary with clear status
    """
    from .session_context import ACTIVE_SESSIONS
    
    if session_id and session_id in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[session_id]
        return {
            "success": True,
            "message": f"Session {session_id} has been cleared."
        }
    else:
        return {
            "success": False,
            "message": "Session not found or already cleared."
        }