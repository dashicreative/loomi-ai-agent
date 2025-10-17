import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Tuple
from openai import OpenAI
from dotenv import load_dotenv

# Import the single-ingredient processor functions
from .Custom_Ingredient_LLM import (
    validate_food_item,
    search_nutrition_data,
    get_spoonacular_image,
    CATEGORY_IMAGES,
    process_ingredient as process_single_ingredient
)

load_dotenv(override=True)

BATCH_SIZE = 5  # Process ingredients in batches of 5 to avoid rate limits

async def process_ingredient_batch(ingredient_names: List[str]) -> Dict:
    """
    Process multiple ingredients in parallel with batch size limits.
    
    Args:
        ingredient_names: List of ingredient names to process
        
    Returns:
        Dictionary with results list containing all processed ingredients
    """
    
    # Remove duplicates while preserving order
    unique_ingredients = []
    seen = set()
    for name in ingredient_names:
        name_lower = name.lower().strip()
        if name_lower not in seen:
            seen.add(name_lower)
            unique_ingredients.append(name.strip())
    
    results = []
    
    # Process in batches to avoid rate limits
    for i in range(0, len(unique_ingredients), BATCH_SIZE):
        batch = unique_ingredients[i:i + BATCH_SIZE]
        
        # Create tasks for parallel processing
        tasks = [process_single_ingredient(ingredient) for ingredient in batch]
        
        # Wait for all tasks in this batch to complete
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results and exceptions
        for ingredient, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                # Handle exceptions gracefully
                results.append({
                    "success": False,
                    "ingredient_name": ingredient,
                    "error": "PROCESSING_ERROR",
                    "message": str(result)
                })
            else:
                results.append(result)
        
        # Small delay between batches to respect rate limits
        if i + BATCH_SIZE < len(unique_ingredients):
            await asyncio.sleep(0.5)  # 500ms delay between batches
    
    return {
        "total_count": len(results),
        "successful_count": sum(1 for r in results if r.get("success", False)),
        "failed_count": sum(1 for r in results if not r.get("success", False)),
        "results": results
    }

async def process_ingredients_with_fallback(ingredient_names: List[str]) -> Dict:
    """
    Process ingredients with fallback for individual failures.
    
    This version ensures that if one ingredient fails, others still get processed.
    """
    
    if not ingredient_names:
        return {
            "total_count": 0,
            "successful_count": 0,
            "failed_count": 0,
            "results": []
        }
    
    # Validate input size
    if len(ingredient_names) > 50:  # Max 50 ingredients per request
        return {
            "error": "TOO_MANY_INGREDIENTS",
            "message": "Maximum 50 ingredients allowed per request",
            "max_allowed": 50,
            "received": len(ingredient_names)
        }
    
    return await process_ingredient_batch(ingredient_names)