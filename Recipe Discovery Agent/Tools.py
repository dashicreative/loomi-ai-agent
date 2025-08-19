from pydantic_ai import RunContext
from typing import Dict, Optional
import httpx
import os
from dataclasses import dataclass


@dataclass
class RecipeDeps:
    api_key: str


#Spponacular Recipe API request tool foro new recipes
async def search_recipes(ctx: RunContext[RecipeDeps], query: str, number: int = 5, include_nutrition: bool = False) -> Dict:
    """
    Search for recipes using the Spoonacular API.
    Returns recipe data including title, image, prep time, and optional nutrition info.
    """
    async with httpx.AsyncClient() as client:
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {
            "apiKey": ctx.deps.api_key,
            "query": query,
            "number": number,
            "addRecipeInformation": True,
            "addRecipeNutrition": include_nutrition
        }
        
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()