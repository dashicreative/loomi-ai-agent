"""
Tools for Macro Calculation Agent
Provides USDA lookup, unit conversion, and macro calculation functionality.
"""

import re
import json
from typing import Dict, Optional, List, Any
from pydantic_ai import RunContext
from dependencies import MacroDeps


async def usda_lookup(ctx: RunContext[MacroDeps], ingredient_name: str) -> Dict:
    """
    Look up nutrition data from USDA FoodData Central API.
    
    Args:
        ingredient_name: Clean ingredient name to search for
        
    Returns:
        Dictionary with nutrition data per 100g or error info
    """
    # Check cache first (avoid duplicate API calls)
    cache_key = ingredient_name.lower().strip()
    if cache_key in ctx.deps.ingredient_cache:
        return ctx.deps.ingredient_cache[cache_key]
    
    try:
        # Use correct USDA FDC API endpoint for search
        search_url = f"{ctx.deps.usda_base_url}/foods/search"
        
        # Proper query parameters based on official API docs
        params = {
            "query": ingredient_name,
            "pageSize": 5,  # Limit results for speed
            "dataType": ["Foundation", "Survey (FNDDS)", "Branded"],  # Include quality data types
        }
        
        # API key is required as query parameter (not header)
        if ctx.deps.usda_api_key:
            params["api_key"] = ctx.deps.usda_api_key
        
        response = await ctx.deps.http_client.get(search_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        foods = data.get("foods", [])
        
        if not foods:
            return {"error": "No USDA data found", "source": "USDA_API"}
            
        # Take first result (most relevant match)
        food = foods[0]
        nutrients = food.get("foodNutrients", [])
        
        # Initialize macro data structure
        macro_data = {
            "calories": 0,
            "protein": 0,
            "fat": 0,
            "carbs": 0,
            "source": "USDA",
            "description": food.get("description", ingredient_name),
            "fdcId": food.get("fdcId", "")
        }
        
        # Correct USDA nutrient IDs from official documentation
        nutrient_map = {
            1008: "calories",    # Energy (kcal)
            1003: "protein",     # Protein (g)
            1004: "fat",         # Total lipid (fat) (g) 
            1005: "carbs",       # Carbohydrate, by difference (g)
        }
        
        # Extract nutrition values from USDA response
        for nutrient in nutrients:
            nutrient_id = nutrient.get("nutrientId")
            if nutrient_id in nutrient_map:
                value = nutrient.get("value", 0)
                macro_name = nutrient_map[nutrient_id]
                macro_data[macro_name] = round(float(value), 1)
                
        # Cache successful result
        ctx.deps.ingredient_cache[cache_key] = macro_data
        return macro_data
        
    except httpx.HTTPStatusError as e:
        error_msg = f"USDA API HTTP {e.response.status_code}: {e.response.text[:100]}"
        return {"error": error_msg, "source": "USDA_API", "status_code": e.response.status_code}
    except Exception as e:
        error_msg = f"USDA lookup failed: {type(e).__name__}: {str(e)}"
        return {"error": error_msg, "source": "USDA_API"}


async def web_nutrition_search(ctx: RunContext[MacroDeps], ingredient_name: str) -> Dict:
    """
    Search the web for nutrition information when USDA fails.
    Uses Google Custom Search to find nutrition data from multiple sources.
    
    Args:
        ingredient_name: Ingredient to search nutrition info for
        
    Returns:
        Dictionary with estimated nutrition data or error
    """
    cache_key = f"web_{ingredient_name.lower().strip()}"
    if cache_key in ctx.deps.ingredient_cache:
        return ctx.deps.ingredient_cache[cache_key]
    
    try:
        # Build nutrition-specific search query
        query = f"{ingredient_name} nutrition facts calories protein fat carbs per 100g"
        
        params = {
            "key": ctx.deps.google_api_key,
            "cx": ctx.deps.google_search_engine_id,
            "q": query,
            "num": 5,  # Limit results for speed
            "gl": "us",
            "hl": "en"
        }
        
        response = await ctx.deps.http_client.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params
        )
        response.raise_for_status()
        
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            return {"error": "No web nutrition data found", "source": "WEB_SEARCH"}
        
        # Extract nutrition hints from search snippets
        # This is a simple heuristic-based approach
        nutrition_text = ""
        for item in items[:3]:  # Use top 3 results
            snippet = item.get("snippet", "")
            title = item.get("title", "")
            nutrition_text += f"{title} {snippet} "
        
        # Estimate nutrition values from search text using basic patterns
        estimated_macros = {
            "calories": _extract_calories(nutrition_text),
            "protein": _extract_protein(nutrition_text),
            "fat": _extract_fat(nutrition_text),
            "carbs": _extract_carbs(nutrition_text),
            "source": "WEB_SEARCH",
            "description": ingredient_name,
            "search_query": query
        }
        
        # Cache the web result
        ctx.deps.ingredient_cache[cache_key] = estimated_macros
        return estimated_macros
        
    except Exception as e:
        error_msg = f"Web nutrition search failed: {type(e).__name__}: {str(e)}"
        return {"error": error_msg, "source": "WEB_SEARCH"}


def _extract_calories(text: str) -> float:
    """Extract calorie estimate from search text using regex patterns."""
    patterns = [
        r'(\d+)\s*calories?',
        r'(\d+)\s*kcal',
        r'calories?[\s:]*(\d+)',
        r'energy[\s:]*(\d+)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    
    # Default estimate for common ingredients if no pattern found
    return 50.0  # Conservative estimate


def _extract_protein(text: str) -> float:
    """Extract protein estimate from search text."""
    patterns = [
        r'(\d+(?:\.\d+)?)\s*g?\s*protein',
        r'protein[\s:]*(\d+(?:\.\d+)?)\s*g?',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    
    return 3.0  # Conservative protein estimate


def _extract_fat(text: str) -> float:
    """Extract fat estimate from search text."""
    patterns = [
        r'(\d+(?:\.\d+)?)\s*g?\s*fat',
        r'fat[\s:]*(\d+(?:\.\d+)?)\s*g?',
        r'(\d+(?:\.\d+)?)\s*g?\s*lipid',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    
    return 1.0  # Conservative fat estimate


def _extract_carbs(text: str) -> float:
    """Extract carbohydrate estimate from search text."""
    patterns = [
        r'(\d+(?:\.\d+)?)\s*g?\s*carbs?',
        r'(\d+(?:\.\d+)?)\s*g?\s*carbohydrates?',
        r'carbs?[\s:]*(\d+(?:\.\d+)?)\s*g?',
        r'carbohydrates?[\s:]*(\d+(?:\.\d+)?)\s*g?',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    
    return 10.0  # Conservative carb estimate


def convert_to_grams(ctx: RunContext[MacroDeps], quantity: str, unit: str, ingredient_name: str) -> float:
    """
    Convert ingredient quantity to grams for macro calculations.
    
    Args:
        quantity: Amount as string (e.g., "1", "1.5", "1/2")
        unit: Unit type (cups, oz, tbsp, etc.)
        ingredient_name: Ingredient name for density lookup
        
    Returns:
        Weight in grams
    """
    try:
        # Parse quantity (handle fractions)
        if "/" in quantity:
            parts = quantity.split("/")
            if len(parts) == 2:
                gram_amount = float(parts[0]) / float(parts[1])
            else:
                gram_amount = float(quantity)
        else:
            gram_amount = float(quantity)
            
    except ValueError:
        return 100.0  # Default fallback
    
    unit_lower = unit.lower().strip()
    
    # Direct weight units
    if unit_lower in ctx.deps.weight_conversions:
        return gram_amount * ctx.deps.weight_conversions[unit_lower]
    
    # Volume units (need ingredient density)
    volume_units = {
        "cup": 240, "cups": 240,
        "tbsp": 15, "tablespoon": 15, "tablespoons": 15,
        "tsp": 5, "teaspoon": 5, "teaspoons": 5,
        "ml": 1, "milliliter": 1, "milliliters": 1,
        "l": 1000, "liter": 1000, "liters": 1000
    }
    
    if unit_lower in volume_units:
        volume_ml = gram_amount * volume_units[unit_lower]
        
        # Try to find ingredient density
        ingredient_lower = ingredient_name.lower()
        for key, density in ctx.deps.volume_to_grams.items():
            if key in ingredient_lower:
                return (volume_ml / 240) * density  # Convert to cup equivalent, then to grams
                
        # Default density (water equivalent)
        return volume_ml  # 1ml = 1g for water-like density
    
    # Count/piece units - estimate based on ingredient type
    if unit_lower in ["count", "piece", "pieces", "clove", "cloves"]:
        # Rough estimates for common items
        piece_weights = {
            "egg": 50, "garlic": 3, "onion": 150, "apple": 180,
            "banana": 120, "carrot": 60, "potato": 150
        }
        
        ingredient_lower = ingredient_name.lower()
        for key, weight in piece_weights.items():
            if key in ingredient_lower:
                return gram_amount * weight
                
        return gram_amount * 50  # Generic piece weight
        
    # Fallback: assume 100g per unit
    return gram_amount * 100


def calculate_macros_for_ingredient(ctx: RunContext[MacroDeps], ingredient: Dict) -> Dict:
    """
    Calculate macros for a single ingredient based on its quantity.
    
    Args:
        ingredient: Dict with name, quantity, unit
        
    Returns:
        Dict with calculated macros in grams/calories
    """
    name = ingredient.get("name", "")
    quantity = ingredient.get("quantity", "1")
    unit = ingredient.get("unit", "count")
    
    # Clean ingredient name for lookup (remove preparation details)
    clean_name = re.sub(r'\([^)]*\)', '', name).strip()  # Remove parentheses
    clean_name = clean_name.split(',')[0].strip()  # Take first part before comma
    
    # Get gram weight for this ingredient
    weight_grams = convert_to_grams(ctx, quantity, unit, clean_name)
    
    # Default macro values (will try USDA lookup in actual implementation)
    macros = {
        "calories": 0,
        "protein": 0,
        "fat": 0, 
        "carbs": 0,
        "ingredient": name,
        "weight_grams": weight_grams
    }
    
    return macros


def sum_all_macros(macro_list: List[Dict]) -> Dict:
    """
    Sum macros from all ingredients to get recipe totals.
    
    Args:
        macro_list: List of ingredient macro dictionaries
        
    Returns:
        Dict with total macros
    """
    totals = {
        "total_calories": 0,
        "total_protein": 0,
        "total_fat": 0,
        "total_carbs": 0
    }
    
    for ingredient_macros in macro_list:
        totals["total_calories"] += ingredient_macros.get("calories", 0)
        totals["total_protein"] += ingredient_macros.get("protein", 0)
        totals["total_fat"] += ingredient_macros.get("fat", 0)
        totals["total_carbs"] += ingredient_macros.get("carbs", 0)
        
    # Round to whole numbers
    for key in totals:
        totals[key] = round(totals[key])
        
    return totals