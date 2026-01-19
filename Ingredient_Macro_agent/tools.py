"""
Tools for Macro Calculation Agent
Provides USDA lookup, unit conversion, and macro calculation functionality.
"""

import re
import json
import httpx
from typing import Dict, Optional, List, Any
from pydantic_ai import RunContext
from dependencies import MacroDeps


# Unicode fraction map for conversion
UNICODE_FRACTIONS = {
    '¼': 0.25, '½': 0.5, '¾': 0.75,
    '⅐': 0.142857, '⅑': 0.111111, '⅒': 0.1,
    '⅓': 0.333333, '⅔': 0.666667,
    '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8,
    '⅙': 0.166667, '⅚': 0.833333,
    '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875
}


def detect_preparation_state(ingredient_name: str) -> str:
    """
    Detect if ingredient is raw, cooked, or has other preparation state that affects nutrition.

    Args:
        ingredient_name: Full ingredient name with description

    Returns:
        Preparation keyword to include in USDA search, or empty string
    """
    name_lower = ingredient_name.lower()

    # Cooking state keywords that significantly affect nutrition
    if any(keyword in name_lower for keyword in ['cooked', 'boiled', 'steamed', 'baked', 'roasted', 'grilled', 'fried', 'sauteed', 'sautéed']):
        # Find which cooking method
        for method in ['cooked', 'boiled', 'steamed', 'baked', 'roasted', 'grilled', 'fried', 'sauteed', 'sautéed']:
            if method in name_lower:
                return method

    if 'raw' in name_lower:
        return 'raw'

    # Default: assume raw for vegetables/proteins, no modifier for others
    return ''


def parse_quantity(quantity_str: str) -> float:
    """
    Parse quantity string into float, handling mixed fractions, unicode fractions, and ranges.

    Examples:
        "2" → 2.0
        "1/2" → 0.5
        "1 1/2" → 1.5
        "½" → 0.5
        "1-2" → 1.5 (average of range)
        "~2" → 2.0

    Args:
        quantity_str: Quantity as string

    Returns:
        Parsed quantity as float
    """
    try:
        # Clean up whitespace
        quantity_str = quantity_str.strip()

        # Handle approximate symbols
        quantity_str = quantity_str.replace('~', '').replace('≈', '').replace('about', '').strip()

        # Handle unicode fractions
        for unicode_char, decimal_value in UNICODE_FRACTIONS.items():
            if unicode_char in quantity_str:
                # Check if there's a whole number before the fraction
                parts = quantity_str.split(unicode_char)
                if parts[0].strip():
                    whole = float(parts[0].strip())
                    return whole + decimal_value
                else:
                    return decimal_value

        # Handle ranges (e.g., "1-2 cups") - use midpoint
        if '-' in quantity_str and quantity_str.count('-') == 1:
            range_parts = quantity_str.split('-')
            if len(range_parts) == 2:
                try:
                    low = float(range_parts[0].strip())
                    high = float(range_parts[1].strip())
                    return (low + high) / 2.0
                except ValueError:
                    pass  # Fall through to other parsing

        # Handle mixed fractions (e.g., "1 1/2")
        if ' ' in quantity_str and '/' in quantity_str:
            parts = quantity_str.split()
            if len(parts) == 2:
                whole_part = float(parts[0])
                fraction_part = parts[1]

                if '/' in fraction_part:
                    frac_parts = fraction_part.split('/')
                    if len(frac_parts) == 2:
                        numerator = float(frac_parts[0])
                        denominator = float(frac_parts[1])
                        return whole_part + (numerator / denominator)

        # Handle simple fractions (e.g., "1/2")
        if '/' in quantity_str:
            frac_parts = quantity_str.split('/')
            if len(frac_parts) == 2:
                numerator = float(frac_parts[0].strip())
                denominator = float(frac_parts[1].strip())
                return numerator / denominator

        # Handle simple numbers
        return float(quantity_str)

    except (ValueError, ZeroDivisionError):
        # Fallback for unparseable quantities
        return 1.0


async def usda_lookup(ctx: RunContext[MacroDeps], ingredient_name: str) -> Dict:
    """
    Look up nutrition data from USDA FoodData Central API.

    Args:
        ingredient_name: Clean ingredient name to search for

    Returns:
        Dictionary with nutrition data per 100g or error info
    """
    # Detect preparation state (raw, cooked, etc.)
    prep_state = detect_preparation_state(ingredient_name)

    # Build search query with preparation state if detected
    search_query = ingredient_name
    if prep_state:
        # Ensure preparation state is in the search
        if prep_state not in ingredient_name.lower():
            search_query = f"{ingredient_name} {prep_state}"

    # Check cache first (avoid duplicate API calls)
    cache_key = search_query.lower().strip()
    if cache_key in ctx.deps.ingredient_cache:
        return ctx.deps.ingredient_cache[cache_key]

    try:
        # Use correct USDA FDC API endpoint for search
        search_url = f"{ctx.deps.usda_base_url}/foods/search"

        # Proper query parameters based on official API docs
        params = {
            "query": search_query,  # Use enhanced query with prep state
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
        quantity: Amount as string (e.g., "1", "1.5", "1/2", "1 1/2", "½")
        unit: Unit type (cups, oz, tbsp, etc.)
        ingredient_name: Ingredient name for density lookup

    Returns:
        Weight in grams
    """
    # Use comprehensive parsing helper
    gram_amount = parse_quantity(quantity)
    
    unit_lower = unit.lower().strip()

    # Direct weight units
    if unit_lower in ctx.deps.weight_conversions:
        return gram_amount * ctx.deps.weight_conversions[unit_lower]

    # Tiny units (pinch, dash, etc.) - very small amounts
    tiny_units = {
        "pinch": 0.35,      # ~0.35g per pinch
        "dash": 0.5,        # ~0.5g per dash
        "smidgen": 0.18,    # ~0.18g per smidgen
        "hint": 0.25,       # ~0.25g per hint
        "drop": 0.05,       # ~0.05g per drop
        "splash": 2.0,      # ~2g per splash
        "drizzle": 5.0,     # ~5g per drizzle
        "squeeze": 10.0,    # ~10g per squeeze (e.g., lemon)
    }

    if unit_lower in tiny_units:
        return gram_amount * tiny_units[unit_lower]

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
        # Comprehensive piece weights for common ingredients (in grams)
        piece_weights = {
            # Eggs & Dairy
            "egg": 50, "eggs": 50,

            # Vegetables
            "garlic": 3, "clove": 3,
            "onion": 150, "yellow onion": 150, "white onion": 150, "red onion": 150,
            "shallot": 25,
            "potato": 150, "russet potato": 200, "sweet potato": 130,
            "tomato": 150, "cherry tomato": 15, "grape tomato": 10, "roma tomato": 100,
            "carrot": 60, "baby carrot": 10,
            "celery": 40, "celery stalk": 40,
            "cucumber": 300, "baby cucumber": 120, "english cucumber": 400,
            "bell pepper": 150, "red bell pepper": 150, "green bell pepper": 150, "jalapeño": 15, "habanero": 10,
            "zucchini": 200, "yellow squash": 200,
            "eggplant": 450, "japanese eggplant": 200,
            "avocado": 150,
            "lemon": 50, "lime": 45, "orange": 130,
            "ginger": 15, "ginger knob": 30,
            "mushroom": 15, "portobello": 80, "shiitake": 10,

            # Fruits
            "apple": 180, "banana": 120, "pear": 170, "peach": 150, "plum": 65,
            "strawberry": 15, "blueberry": 1, "raspberry": 1, "blackberry": 2,
            "grape": 3, "cherry": 8,
            "mango": 200, "papaya": 450, "pineapple": 900,
            "kiwi": 70, "fig": 50, "date": 7,

            # Proteins
            "chicken breast": 200, "chicken thigh": 150, "chicken wing": 50,
            "pork chop": 180, "pork tenderloin": 450,
            "steak": 250, "beef patty": 115,
            "salmon fillet": 180, "tuna steak": 150, "shrimp": 15, "prawn": 20,
            "sausage": 50, "hot dog": 45, "bacon strip": 15, "bacon slice": 15,

            # Breads & Grains
            "slice bread": 30, "bread slice": 30, "toast": 30,
            "bagel": 85, "english muffin": 60, "pita": 60, "tortilla": 50, "naan": 90,
            "croissant": 50, "donut": 60, "muffin": 60,

            # Other
            "walnut": 5, "almond": 1, "pecan": 5, "cashew": 2,
            "chocolate chip": 0.3,
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