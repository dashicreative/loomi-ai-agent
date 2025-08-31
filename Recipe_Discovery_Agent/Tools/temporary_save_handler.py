"""
TEMPORARY: Chat-based meal saving for testing
DELETE THIS FILE WHEN UI IS CONNECTED

This allows testing meal saving via chat commands like "save meal #3"
"""

import re
from typing import Optional, Dict
from .session_tools import save_meal_to_session


async def handle_temporary_save_command(message: str, session_id: Optional[str] = None) -> Optional[Dict]:
    """
    TEMPORARY FUNCTION - DELETE WHEN UI IS CONNECTED
    
    Handles chat commands like "save meal #3" or "save recipe #2"
    This simulates the UI save button for testing purposes.
    
    Args:
        message: User message to check for save commands
        session_id: Current session ID
        
    Returns:
        Dict with save result if command matched, None otherwise
    """
    
    # Check for save patterns
    patterns = [
        r'save\s+meal\s+#?(\d+)',
        r'save\s+recipe\s+#?(\d+)',
        r'save\s+#?(\d+)',
        r'save\s+the\s+(\w+)\s+one',  # "save the third one"
    ]
    
    message_lower = message.lower()
    
    # Try numeric patterns
    for pattern in patterns[:3]:
        match = re.search(pattern, message_lower)
        if match:
            meal_number = int(match.group(1))
            result = await save_meal_to_session(session_id, meal_number)
            
            # Add temporary flag to indicate this was from chat
            result['_temporary_chat_save'] = True
            result['_delete_when_ui_connected'] = True
            
            return result
    
    # Handle word numbers
    word_to_num = {
        'first': 1, 'second': 2, 'third': 3,
        'fourth': 4, 'fifth': 5
    }
    
    match = re.search(patterns[3], message_lower)
    if match:
        word = match.group(1)
        if word in word_to_num:
            meal_number = word_to_num[word]
            result = await save_meal_to_session(session_id, meal_number)
            
            # Add temporary flag
            result['_temporary_chat_save'] = True
            result['_delete_when_ui_connected'] = True
            
            return result
    
    return None


# TEMPORARY: Export for agent to use
# DELETE THIS EXPORT WHEN UI IS CONNECTED
async def temporary_save_meal_tool(user_message: str, session_id: Optional[str] = None) -> Dict:
    """
    TEMPORARY TOOL - DELETE WHEN UI IS CONNECTED
    
    Tool wrapper for the agent to call when user says "save meal #X"
    
    Args:
        user_message: The user's message containing save command
        session_id: Session ID (optional, will use most recent if not provided)
        
    Returns:
        Dict with save result
    """
    # If no session_id provided, try to get the most recent session
    if not session_id:
        from .session_context import ACTIVE_SESSIONS
        if ACTIVE_SESSIONS:
            # Get the most recently created/used session
            session_id = list(ACTIVE_SESSIONS.keys())[-1]
            print(f"   📝 Using session: {session_id}")
    
    result = await handle_temporary_save_command(user_message, session_id)
    
    if result:
        return result
    else:
        return {
            "success": False,
            "message": "No save command found. Try 'save meal #3' or 'save recipe #2'",
            "_temporary_tool": True,
            "_delete_when_ui_connected": True
        }