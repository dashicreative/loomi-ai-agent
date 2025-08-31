from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set
from datetime import datetime
from pydantic import BaseModel, Field, computed_field
import uuid


class SessionContext(BaseModel):
    """
    Session context for recipe discovery conversation.
    Enhanced with Pydantic BaseModel for validation and computed properties.
    """
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique session identifier")
    shown_recipe_urls: Set[str] = Field(default_factory=set, description="URLs shown to prevent duplicates")
    saved_meals: List[Dict] = Field(default_factory=list, max_items=100, description="User's saved meals")
    current_batch_recipes: List[Dict] = Field(default_factory=list, max_items=5, description="Current displayed recipes")
    search_history: List[str] = Field(default_factory=list, max_items=50, description="Search query history")
    current_nutrition_gaps: Dict[str, float] = Field(default_factory=dict, description="Tracked nutrition gaps for goals")
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    last_activity: datetime = Field(default_factory=datetime.now, description="Last user interaction")
    
    class Config:
        # Allow mutation for state updates
        allow_mutation = True
        # Enable JSON serialization
        json_encoders = {
            set: list,
            datetime: lambda v: v.isoformat()
        }
    
    @computed_field
    @property
    def saved_meals_count(self) -> int:
        """Auto-computed count of saved meals"""
        return len(self.saved_meals)
    
    @computed_field
    @property  
    def nutrition_totals(self) -> Dict[str, float]:
        """Auto-computed nutrition totals from saved meals"""
        totals = {'calories': 0.0, 'protein': 0.0, 'fat': 0.0, 'carbs': 0.0}
        
        for meal in self.saved_meals:
            nutrition = meal.get('nutrition', [])
            for nutrient in nutrition:
                if isinstance(nutrient, dict):
                    name = nutrient.get('name', '').lower()
                    amount_str = nutrient.get('amount', nutrient.get('value', '0'))
                    try:
                        value = float(''.join(c for c in str(amount_str) if c.isdigit() or c == '.'))
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
    
    @computed_field
    @property
    def total_shown_urls(self) -> int:
        """Auto-computed count of shown URLs"""
        return len(self.shown_recipe_urls)
    
    def save_meal(self, meal_number: int) -> bool:
        """Save a meal from current batch to saved meals."""
        if 1 <= meal_number <= len(self.current_batch_recipes):
            meal = self.current_batch_recipes[meal_number - 1].copy()
            meal['saved_at'] = datetime.now().isoformat()
            meal['original_number'] = meal_number
            
            # Avoid duplicates
            if not any(m.get('sourceUrl') == meal.get('sourceUrl') for m in self.saved_meals):
                self.saved_meals.append(meal)
                self.last_activity = datetime.now()
                return True
        return False
    
    def update_current_batch(self, recipes: list):
        """Update current batch and track shown URLs."""
        self.current_batch_recipes = recipes[:5]
        urls = [r.get('sourceUrl', '') for r in recipes if r.get('sourceUrl')]
        self.shown_recipe_urls.update(urls)
        self.last_activity = datetime.now()
    
    def get_nutrition_totals(self) -> Dict[str, float]:
        """Legacy method - use nutrition_totals property instead"""
        return self.nutrition_totals
    
    def to_json_for_frontend(self) -> Dict:
        """Export session data for frontend consumption with automatic serialization"""
        return {
            "session_id": self.session_id,
            "saved_meals_count": self.saved_meals_count,
            "total_shown_urls": self.total_shown_urls,
            "nutrition_totals": self.nutrition_totals,
            "current_nutrition_gaps": self.current_nutrition_gaps,
            "search_history": self.search_history[-10:],  # Last 10 searches
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "saved_meals": self.saved_meals,
            "current_batch": self.current_batch_recipes
        }


@dataclass
class RecipeDeps:
    """Dependencies for the Recipe Discovery Agent"""
    serpapi_key: str  # SerpAPI key for web search
    firecrawl_key: str  # FireCrawl API key for fallback scraping
    openai_key: str  # OpenAI API key for LLM reranking
    google_search_key: str  # Google Custom Search API key for fallback search
    google_search_engine_id: str  # Google Custom Search Engine ID
    
    # Session context - proper Pydantic AI pattern
    session: SessionContext = field(default_factory=SessionContext)