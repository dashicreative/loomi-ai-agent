from pydantic_ai import RunContext
from typing import Dict, Optional
import httpx
import os
from dataclasses import dataclass


@dataclass
class RecipeDeps:
    api_key: str


#Spponacular Recipe API request tool foro new recipes
async def search_recipes(ctx: RunContext[RecipeDeps], query: str, number: int = 3, include_nutrition: bool = False) -> Dict:
    """
    Search for recipes using the Spoonacular API.
    Returns recipe data including title, image, prep time, and optional nutrition info.
    """
    async with httpx.AsyncClient() as client:
        # Step 1: Quick search with minimal data
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {
            "apiKey": ctx.deps.api_key,
            "query": query,
            "number": number,
            "addRecipeInformation": False,  # Don't fetch extra info initially
            "addRecipeNutrition": False,
            "fillIngredients": False
        }
        
        response = await client.get(url, params=params)
        response.raise_for_status()
        search_data = response.json()
        
        results = search_data.get("results", [])
        
        # Step 2: Fetch details only for the recipes we'll actually display (top 3)
        detailed_recipes = []
        for recipe in results[:3]:  # Only fetch details for top 3
            recipe_id = recipe.get("id")
            
            # Get full details for this specific recipe
            detail_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
            detail_params = {
                "apiKey": ctx.deps.api_key,
                "includeNutrition": include_nutrition
            }
            
            detail_response = await client.get(detail_url, params=detail_params)
            detail_response.raise_for_status()
            detail_data = detail_response.json()
            
            # Extract only what we need
            detailed_recipes.append({
                "id": detail_data.get("id"),
                "title": detail_data.get("title"),
                "image": detail_data.get("image"),
                "sourceUrl": detail_data.get("sourceUrl"),
                "servings": detail_data.get("servings"),
                "readyInMinutes": detail_data.get("readyInMinutes"),
                "ingredients": [ing.get("name") for ing in detail_data.get("extendedIngredients", [])][:5]  # Just top 5 ingredients
            })
        
        # Return simplified results
        simplified_results = {
            "results": detailed_recipes,
            "totalResults": search_data.get("totalResults", 0)
        }
        
        return simplified_results