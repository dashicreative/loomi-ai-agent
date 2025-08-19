from pydantic_ai import RunContext
from typing import Dict, Optional
import httpx
import asyncio
import os
from dataclasses import dataclass


@dataclass
class RecipeDeps:
    api_key: str


#Spponacular Recipe API request tool foro new recipes
async def search_recipes(ctx: RunContext[RecipeDeps], query: str, number: int = 50, include_nutrition: bool = False, exclude_ingredients: str = "") -> Dict:
    """
    Search for recipes using the Spoonacular API.
    Returns recipe data including title, image, prep time, and optional nutrition info.
    
    Args:
        query: The search term for recipes
        number: Number of recipes to return (default 3)
        include_nutrition: Whether to include nutrition data
        exclude_ingredients: Comma-separated ingredients to exclude (e.g., "chocolate,oreo,nuts")
    """
    async with httpx.AsyncClient() as client:
        # Step 1: Back to complexSearch with minimal data
        url = "https://api.spoonacular.com/recipes/complexSearch"
        params = {
            "apiKey": ctx.deps.api_key,
            "query": query,
            "number": number,
            "addRecipeInformation": False,
            "addRecipeNutrition": False,
            "fillIngredients": False
        }
        
        # Add exclusions if provided
        if exclude_ingredients:
            params["excludeIngredients"] = exclude_ingredients
        
        response = await client.get(url, params=params)
        response.raise_for_status()
        search_data = response.json()
        
        results = search_data.get("results", [])
        
        # Step 2: Fetch details for top 3 recipes IN PARALLEL
        async def fetch_recipe_details(recipe_id: int) -> Dict:
            """Fetch details for a single recipe"""
            detail_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
            detail_params = {
                "apiKey": ctx.deps.api_key,
                "includeNutrition": include_nutrition
            }
            
            try:
                detail_response = await client.get(detail_url, params=detail_params)
                detail_response.raise_for_status()
                detail_data = detail_response.json()
                
                # Extract only what we need
                return {
                    "id": detail_data.get("id"),
                    "title": detail_data.get("title"),
                    "image": detail_data.get("image"),
                    "sourceUrl": detail_data.get("sourceUrl"),
                    "servings": detail_data.get("servings"),
                    "readyInMinutes": detail_data.get("readyInMinutes"),
                    "ingredients": [ing.get("name") for ing in detail_data.get("extendedIngredients", [])][:5]
                }
            except Exception as e:
                # Return basic info if detail fetch fails
                return {
                    "id": recipe_id,
                    "title": "Recipe details unavailable",
                    "error": str(e)
                }
        
        # Fetch all 3 recipe details simultaneously
        recipe_ids = [recipe.get("id") for recipe in results[:3]]
        detailed_recipes = await asyncio.gather(
            *[fetch_recipe_details(recipe_id) for recipe_id in recipe_ids]
        )
        
        # Return simplified results
        simplified_results = {
            "results": detailed_recipes,
            "totalResults": search_data.get("totalResults", 0)
        }
        
        return simplified_results