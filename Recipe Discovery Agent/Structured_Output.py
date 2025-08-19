from typing import TypedDict, List, Optional, Dict

#Strcuture of Nutrtional info
class NutritionInfo(TypedDict):
    calories: float
    protein: float
    carbs: float
    fat: float


#Strcuture of Recipe info
class RecipeInfo(TypedDict):
    id: int
    title: str
    image: str
    sourceUrl: Optional[str]
    servings: int
    readyInMinutes: int
    nutrition: Optional[NutritionInfo]


#The Final strcutured output for the agent
class AgentOutput(TypedDict):
    response: str  # Natural language response to user
    recipes: List[RecipeInfo]  # Recipes found from API
    totalResults: int  # Total recipes found in search
    searchQuery: str  # What was searched for