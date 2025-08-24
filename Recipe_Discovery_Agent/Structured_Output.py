from typing_extensions import TypedDict
from typing import List, Optional, Dict


#Structure of Nutritional info
class NutritionInfo(TypedDict):
    calories: float
    protein: float
    carbs: float
    fat: float


#Structure of parsed ingredient info
class IngredientInfo(TypedDict):
    quantity: Optional[str]  # Shopping quantity (rounded up for whole items like limes)
    unit: Optional[str]      # Shopping unit (count for whole items, lb, cup, etc.)
    ingredient: str          # Clean ingredient name without prep instructions
    amount: Optional[str]    # Recipe amount if different from shopping (e.g., "0.5" for half lime, "4 cloves")
    size: Optional[str]      # Size descriptor (large, small, medium)
    additional_context: Optional[str]  # Prep state (melted, minced, softened, store-bought)
    alternatives: List[str]  # List of alternative ingredients (e.g., ["almond milk", "oat milk"])
    pantry_staple: bool      # True for salt, pepper, oil, basic spices
    optional: bool           # True for garnish, "to taste" items
    disqualified: bool       # True for cross-references, homemade items that can't be bought
    original: str            # Original ingredient string for reference


#Structure of Recipe info
class RecipeInfo(TypedDict):
    id: int
    title: str
    image: str
    sourceUrl: Optional[str]
    servings: str
    readyInMinutes: str
    ingredients: List[IngredientInfo]  # Now structured ingredients
    nutrition: Optional[NutritionInfo]


#The Final strcutured output for the agent
class AgentOutput(TypedDict):
    response: str  # Natural language response to user
    recipes: List[RecipeInfo]  # Recipes found from API
    totalResults: int  # Total recipes found in search
    searchQuery: str  # What was searched for