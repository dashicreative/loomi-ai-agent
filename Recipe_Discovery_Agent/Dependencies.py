from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime


@dataclass
class SessionContext:
    """
    Session context for recipe discovery conversation.
    Moved to Dependencies for proper Pydantic AI integration.
    """
    session_id: str = field(default_factory=lambda: f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shown_recipe_urls: set = field(default_factory=set)
    saved_meals: list = field(default_factory=list)
    current_batch_recipes: list = field(default_factory=list)
    search_history: list = field(default_factory=list)
    current_nutrition_gaps: Dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
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
        """Calculate total nutrition from saved meals."""
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