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
        number: Number of recipes to return (default 50)
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
            "addRecipeInformation": True,  # Include recipe details in initial search
            "addRecipeNutrition": include_nutrition,
            "fillIngredients": True  # Include ingredient information in initial search
        }
        
        # Add exclusions if provided
        if exclude_ingredients:
            params["excludeIngredients"] = exclude_ingredients
        
        response = await client.get(url, params=params)
        response.raise_for_status()
        search_data = response.json()
        
        results = search_data.get("results", [])
        
        # Step 2: Extract and format the data (ingredients already included!)
        formatted_recipes = []
        for recipe in results:
            # Extract ingredient names from extendedIngredients
            ingredients = []
            if "extendedIngredients" in recipe:
                ingredients = [ing.get("name", ing.get("original", "")) for ing in recipe.get("extendedIngredients", [])]
            
            formatted_recipes.append({
                "id": recipe.get("id"),
                "title": recipe.get("title"),
                "image": recipe.get("image"),
                "sourceUrl": recipe.get("sourceUrl"),
                "servings": recipe.get("servings"),
                "readyInMinutes": recipe.get("readyInMinutes"),
                "ingredients": ingredients  # Full ingredient list for agent analysis
            })
        
        # Return all results with ingredients for agent to analyze
        simplified_results = {
            "results": formatted_recipes,
            "totalResults": search_data.get("totalResults", 0)
        }
        
        return simplified_results