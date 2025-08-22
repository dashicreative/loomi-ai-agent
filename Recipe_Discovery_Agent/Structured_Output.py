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
    quantity: Optional[str]  # "2", "1/2", "2-3", None for "salt to taste"
    unit: Optional[str]      # "cups", "teaspoon", "large", None for no unit
    ingredient: str          # "all-purpose flour", "salt", "eggs"
    original: str           # Original string for fallback display


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