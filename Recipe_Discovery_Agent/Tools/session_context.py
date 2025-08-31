"""
Session Context Management for Recipe Discovery Agent

Handles conversation state, saved meals tracking, and session-level memory.
"""

from typing import Dict, List, Set, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json

# TODO: DELETE WHEN UI INTEGRATION - Mock session storage until frontend passes real session IDs
ACTIVE_SESSIONS: Dict[str, 'SessionContext'] = {}


@dataclass
class SessionContext:
    """
    Maintains state for a user's recipe discovery session.
    
    Attributes:
        session_id: Unique identifier for this session
        shown_recipe_urls: All URLs shown to prevent duplicates
        saved_meals: Full recipe data for meals user has saved
        current_batch_recipes: Current 5 recipes being shown (numbered 1-5)
        created_at: Session start time
        last_activity: Last interaction time
        search_history: List of all search queries in this session
    """
    session_id: str
    shown_recipe_urls: Set[str] = field(default_factory=set)
    saved_meals: List[Dict] = field(default_factory=list)
    current_batch_recipes: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    search_history: List[str] = field(default_factory=list)
    current_nutrition_gaps: Dict[str, float] = field(default_factory=dict)  # Track gaps like {"protein": 15.0}
    
    def save_meal(self, meal_number: int) -> bool:
        """
        Save a meal from the current batch to saved meals.
        
        Args:
            meal_number: Recipe number (1-5) from current batch
            
        Returns:
            True if saved successfully, False if meal number invalid
        """
        if 1 <= meal_number <= len(self.current_batch_recipes):
            meal = self.current_batch_recipes[meal_number - 1].copy()
            meal['saved_at'] = datetime.now().isoformat()
            meal['original_number'] = meal_number
            
            # Avoid duplicate saves
            if not any(m.get('sourceUrl') == meal.get('sourceUrl') for m in self.saved_meals):
                self.saved_meals.append(meal)
                self.last_activity = datetime.now()
                return True
        return False
    
    def add_shown_urls(self, urls: List[str]):
        """Add URLs to the shown set to prevent duplicates."""
        self.shown_recipe_urls.update(urls)
        self.last_activity = datetime.now()
    
    def update_current_batch(self, recipes: List[Dict]):
        """Update the current batch of 5 recipes being shown."""
        self.current_batch_recipes = recipes[:5]
        # Add their URLs to shown set
        urls = [r.get('sourceUrl', '') for r in recipes if r.get('sourceUrl')]
        self.add_shown_urls(urls)
        self.last_activity = datetime.now()
    
    def get_saved_nutrition_totals(self) -> Dict[str, float]:
        """
        Calculate total nutrition across all saved meals.
        
        Returns:
            Dictionary with total calories, protein, fat, carbs
        """
        totals = {
            'calories': 0.0,
            'protein': 0.0,
            'fat': 0.0,
            'carbs': 0.0
        }
        
        for meal in self.saved_meals:
            nutrition = meal.get('nutrition', [])
            for nutrient_info in nutrition:
                if isinstance(nutrient_info, dict):
                    name = nutrient_info.get('name', '').lower()
                    value_str = str(nutrient_info.get('value', '0'))
                    # Extract numeric value
                    try:
                        value = float(''.join(c for c in value_str if c.isdigit() or c == '.'))
                    except:
                        value = 0.0
                    
                    if 'calorie' in name:
                        totals['calories'] += value
                    elif 'protein' in name:
                        totals['protein'] += value
                    elif 'fat' in name:
                        totals['fat'] += value
                    elif 'carb' in name:
                        totals['carbs'] += value
        
        return totals
    
    def to_dict(self) -> Dict:
        """Convert session context to dictionary for serialization."""
        return {
            'session_id': self.session_id,
            'shown_recipe_urls': list(self.shown_recipe_urls),
            'saved_meals': self.saved_meals,
            'current_batch_recipes': self.current_batch_recipes,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'search_history': self.search_history,
            'saved_meals_count': len(self.saved_meals),
            'total_shown_urls': len(self.shown_recipe_urls)
        }


def get_or_create_session(session_id: Optional[str] = None) -> SessionContext:
    """
    Get existing session or create new one.
    
    Args:
        session_id: Optional session ID. If None, creates new session.
        
    Returns:
        SessionContext instance
    """
    if session_id is None:
        # TODO: DELETE WHEN UI INTEGRATION - Auto-generate mock session ID
        import uuid
        session_id = f"mock-session-{uuid.uuid4().hex[:8]}"
        print(f"🔄 Generated mock session ID: {session_id}")
    
    if session_id not in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS[session_id] = SessionContext(session_id=session_id)
        print(f"📝 Created new session: {session_id}")
    
    return ACTIVE_SESSIONS[session_id]


def cleanup_old_sessions(hours: int = 24):
    """
    Remove sessions older than specified hours.
    
    Args:
        hours: Number of hours before considering session stale
    """
    from datetime import timedelta
    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    
    to_remove = []
    for sid, context in ACTIVE_SESSIONS.items():
        if context.last_activity < cutoff:
            to_remove.append(sid)
    
    for sid in to_remove:
        del ACTIVE_SESSIONS[sid]
        print(f"🗑️ Cleaned up old session: {sid}")