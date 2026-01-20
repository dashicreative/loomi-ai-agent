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
    # Map common ingredient names to better USDA search terms
    ingredient_search_map = {
        "eggs": "egg whole raw",
        "egg": "egg whole raw",
        "salt": "salt table",
        "butter": "butter salted",
        "salted butter": "butter salted",
        "unsalted butter": "butter without salt",
        "brown sugar": "sugars brown",
        "white sugar": "sugars granulated",
        "sugar": "sugars granulated",
        "all-purpose flour": "wheat flour white all-purpose",
        "flour": "wheat flour white all-purpose",
        "oats": "oats whole grain rolled",
        "old-fashioned oats": "oats whole grain rolled old fashioned",
    }

    # Clean ingredient name for lookup
    name_clean = ingredient_name.lower().strip()

    # Check if we have a better search term
    search_query = ingredient_search_map.get(name_clean, ingredient_name)

    # Detect preparation state (raw, cooked, etc.)
    prep_state = detect_preparation_state(ingredient_name)
    if prep_state and prep_state not in search_query.lower():
        search_query = f"{search_query} {prep_state}"

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
            # Don't specify dataType - let USDA return all types for best matches
        }
        
        # API key is required as query parameter (not header)
        if ctx.deps.usda_api_key:
            params["api_key"] = ctx.deps.usda_api_key
        
        response = await ctx.deps.http_client.get(search_url, params=params)
        response.raise_for_status()

        data = response.json()
        foods = data.get("foods", [])

        if not foods:
            print(f"⚠️  USDA: No results for '{search_query}'")
            return {"error": "No USDA data found", "source": "USDA_API"}
            
        # Take first result (most relevant match)
        food = foods[0]
        food_description = food.get("description", "Unknown")
        nutrients = food.get("foodNutrients", [])
        portions = food.get("foodPortions", [])  # Extract portion/measure data

        # Debug: Show what USDA matched
        print(f"  📍 USDA matched '{ingredient_name}' → '{food_description}'")
        
        # Initialize macro data structure
        macro_data = {
            "calories": 0,
            "protein": 0,
            "fat": 0,
            "carbs": 0,
            "source": "USDA",
            "description": food.get("description", ingredient_name),
            "fdcId": food.get("fdcId", ""),
            "portions": portions  # Include USDA portion data for density lookup
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
            nutrient_name = nutrient.get("nutrientName", "Unknown")
            if nutrient_id in nutrient_map:
                value = nutrient.get("value", 0)
                macro_name = nutrient_map[nutrient_id]
                macro_data[macro_name] = round(float(value), 1)
                print(f"      {macro_name}: {value} (ID {nutrient_id}: {nutrient_name})")

        # If calories are missing, calculate from macros (fat*9 + protein*4 + carbs*4)
        if macro_data["calories"] == 0 and (macro_data["protein"] > 0 or macro_data["fat"] > 0 or macro_data["carbs"] > 0):
            calculated_calories = (macro_data["fat"] * 9) + (macro_data["protein"] * 4) + (macro_data["carbs"] * 4)
            macro_data["calories"] = round(calculated_calories, 1)
            print(f"      ⚙️  Calculated missing calories: {calculated_calories:.1f} kcal")

        # Validate data - reject obviously wrong values
        # Carbs should never exceed ~100g per 100g for most foods
        if macro_data["carbs"] > 105:
            print(f"      ⚠️  REJECTED: Carbs {macro_data['carbs']}g too high (likely bad data)")
            return {"error": f"Invalid carbs data: {macro_data['carbs']}g", "source": "USDA_API"}

        # Fat should never exceed 100g per 100g
        if macro_data["fat"] > 105:
            print(f"      ⚠️  REJECTED: Fat {macro_data['fat']}g too high (likely bad data)")
            return {"error": f"Invalid fat data: {macro_data['fat']}g", "source": "USDA_API"}

        # Protein should never exceed 100g per 100g (except pure protein powder)
        if macro_data["protein"] > 105:
            print(f"      ⚠️  REJECTED: Protein {macro_data['protein']}g too high (likely bad data)")
            return {"error": f"Invalid protein data: {macro_data['protein']}g", "source": "USDA_API"}

        # Cache successful result
        ctx.deps.ingredient_cache[cache_key] = macro_data
        return macro_data
        
    except httpx.HTTPStatusError as e:
        error_msg = f"USDA API HTTP {e.response.status_code}: {e.response.text[:100]}"
        print(f"⚠️  USDA HTTP Error for '{ingredient_name}': {e.response.status_code}")
        print(f"    Response: {e.response.text[:200]}")
        return {"error": error_msg, "source": "USDA_API", "status_code": e.response.status_code}
    except Exception as e:
        error_msg = f"USDA lookup failed: {type(e).__name__}: {str(e)}"
        print(f"⚠️  USDA Exception for '{ingredient_name}': {type(e).__name__}: {str(e)}")
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
            print(f"⚠️  WEB: No search results for '{ingredient_name}'")
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
        
    except httpx.HTTPStatusError as e:
        print(f"⚠️  WEB HTTP Error for '{ingredient_name}': {e.response.status_code}")
        print(f"    Response: {e.response.text[:200]}")
        error_msg = f"Web search HTTP {e.response.status_code}"
        return {"error": error_msg, "source": "WEB_SEARCH"}
    except Exception as e:
        error_msg = f"Web nutrition search failed: {type(e).__name__}: {str(e)}"
        print(f"⚠️  WEB Exception for '{ingredient_name}': {type(e).__name__}: {str(e)}")
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


def convert_to_grams(ctx: RunContext[MacroDeps], quantity: str, unit: str, ingredient_name: str, usda_portions=None) -> tuple[float, str]:
    """
    Convert ingredient quantity to grams using 4-tier fallback system.

    Tier 1: USDA portion data (most accurate)
    Tier 2: Hardcoded density table (fast & reliable)
    Tier 3: LLM estimation (handled separately in batch)
    Tier 4: Water density default (last resort)

    Args:
        quantity: Amount as string (e.g., "1", "1.5", "1/2", "1 1/2", "½")
        unit: Unit type (cups, oz, tbsp, etc.)
        ingredient_name: Ingredient name for density lookup
        usda_portions: Optional USDA foodPortions data from nutrition lookup

    Returns:
        Tuple of (weight in grams, source indicator)
        Source: "USDA_PORTION", "TABLE", "WATER", or "LLM"
    """
    # Use comprehensive parsing helper
    gram_amount = parse_quantity(quantity)

    unit_lower = unit.lower().strip()

    # Direct weight units (already in grams/oz/lb)
    if unit_lower in ctx.deps.weight_conversions:
        return (gram_amount * ctx.deps.weight_conversions[unit_lower], "DIRECT")

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
        return (gram_amount * tiny_units[unit_lower], "TABLE")

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

        # TIER 1: Check USDA portion data (most accurate)
        if usda_portions:
            for portion in usda_portions:
                portion_unit = portion.get("measureUnit", {}).get("name", "").lower()
                # Match unit (cup, tbsp, tsp, etc.)
                if unit_lower.rstrip('s') in portion_unit or portion_unit in unit_lower:
                    grams_per_unit = portion.get("gramWeight", 0)
                    if grams_per_unit > 0:
                        print(f"  ✅ Tier 1 (USDA Portion): 1 {unit_lower} = {grams_per_unit}g")
                        return (gram_amount * grams_per_unit, "USDA_PORTION")

        # TIER 2: Check hardcoded density table
        ingredient_lower = ingredient_name.lower()
        for key, density in ctx.deps.volume_to_grams.items():
            if key in ingredient_lower:
                grams_result = (volume_ml / 240) * density  # Convert to cup equivalent, then to grams
                print(f"  ✅ Tier 2 (Density Table): 1 cup ≈ {density}g")
                return (grams_result, "TABLE")

        # TIER 4: Water default (Tier 3 LLM will be handled in batch later)
        print(f"  ⚠️  Tier 4 (Water Default): '{ingredient_name}' density unknown")
        print(f"     Using water density (240g/cup) - may need LLM estimation")
        return (volume_ml, "WATER")  # 1ml = 1g for water-like density
    
    # Count/piece units - estimate based on ingredient type
    if unit_lower in ["count", "piece", "pieces", "clove", "cloves"]:
        # Comprehensive piece weights for common ingredients (in grams)
        # Based on USDA data, research, and verified sources
        piece_weights = {
            # Eggs & Dairy
            "egg": 50, "eggs": 50,

            # Vegetables
            "garlic": 3, "clove": 3, "garlic clove": 3,
            "onion": 150, "yellow onion": 150, "white onion": 150, "red onion": 150,
            "shallot": 25,
            "potato": 150, "russet potato": 200, "sweet potato": 130, "red potato": 140, "yukon gold": 150,
            # Tomatoes - specific varieties BEFORE generic to ensure correct substring matching
            "cherry tomato": 17, "cherry tomatoes": 17,
            "grape tomato": 10, "grape tomatoes": 10,
            "roma tomato": 100, "roma tomatoes": 100,
            "plum tomato": 100, "plum tomatoes": 100,
            "beefsteak tomato": 200, "beefsteak tomatoes": 200,
            "tomato": 150, "tomatoes": 150,
            # Carrots - specific types before generic
            "baby carrot": 10, "baby carrots": 10,
            "medium carrot": 60,
            "carrot": 60, "carrots": 60,
            "celery": 40, "celery stalk": 40, "celery rib": 40,
            # Cucumbers - specific types before generic
            "english cucumber": 400, "persian cucumber": 150, "baby cucumber": 150,
            "cucumber": 300,
            "bell pepper": 150, "bell peppers": 150,
            "red bell pepper": 150, "red bell peppers": 150,
            "green bell pepper": 150, "green bell peppers": 150,
            "yellow bell pepper": 150, "yellow bell peppers": 150,
            "orange bell pepper": 150, "orange bell peppers": 150,
            "jalapeño": 15, "jalapeños": 15,
            "habanero": 10, "habaneros": 10,
            "serrano": 12, "serranos": 12,
            "poblano": 80, "poblanos": 80,
            "cayenne": 8,
            "zucchini": 200, "yellow squash": 200,
            "eggplant": 450, "japanese eggplant": 200,
            "avocado": 150,
            "lemon": 50, "lemons": 50, "lime": 45, "limes": 45, "orange": 130, "oranges": 130, "grapefruit": 250, "tangerine": 90, "tangerines": 90,
            "ginger": 15, "ginger knob": 30,
            "mushroom": 15, "mushrooms": 15,
            "portobello": 80, "portobello mushroom": 80,
            "shiitake": 10, "shiitake mushroom": 10,
            "cremini": 15, "cremini mushroom": 15,
            "button mushroom": 15, "button mushrooms": 15,
            "brussels sprout": 10, "brussels sprouts": 10,
            "asparagus": 15, "asparagus spear": 15,
            "broccoli floret": 20, "cauliflower floret": 15,
            "radish": 10, "turnip": 150, "beet": 80, "rutabaga": 400,
            "corn": 150, "ear of corn": 150,
            "artichoke": 150,
            "leek": 100,

            # Leafy Greens & Herbs (per leaf or small bunch)
            "basil leaf": 0.5, "basil": 0.5,
            "mint leaf": 0.5, "mint": 0.5, "mint leaves": 0.5,
            "parsley": 0.5, "parsley leaf": 0.5, "parsley sprig": 2,
            "cilantro": 0.5, "cilantro leaf": 0.5, "coriander leaf": 0.5,
            "sage leaf": 0.3, "thyme sprig": 1, "rosemary sprig": 2,
            "dill sprig": 1, "dill": 1,
            "bay leaf": 0.3,
            "lettuce leaf": 15, "romaine leaf": 20, "iceberg leaf": 15,
            "spinach leaf": 5, "spinach": 5,
            "kale leaf": 8, "kale": 8,
            "arugula": 2, "watercress": 2,

            # Fruits
            "apple": 180, "banana": 120, "pear": 170, "peach": 150, "plum": 65, "nectarine": 140,
            "strawberry": 15, "strawberries": 15,
            "blueberry": 1, "blueberries": 1,
            "raspberry": 1, "raspberries": 1,
            "blackberry": 2, "blackberries": 2,
            "cranberry": 1, "cranberries": 1,
            "grape": 3, "grapes": 3,
            "cherry": 8, "cherries": 8,
            "mango": 200, "papaya": 450, "pineapple": 900,
            "kiwi": 70, "fig": 50, "date": 7,
            "apricot": 35, "cantaloupe": 600, "honeydew": 900, "watermelon": 4500,
            "coconut": 400, "pomegranate": 250,

            # Dried Fruits
            "raisin": 0.5, "raisins": 0.5,
            "dried cranberry": 0.5, "dried cranberries": 0.5,
            "dried blueberry": 0.5, "dried blueberries": 0.5,
            "prune": 10, "prunes": 10,
            "dried apricot": 8, "dried apricots": 8,
            "dried fig": 15, "dried figs": 15,
            "dried date": 7, "dried dates": 7,
            "dried cherry": 1, "dried cherries": 1,

            # Proteins - Poultry
            "chicken breast": 200, "chicken thigh": 150, "chicken wing": 50, "chicken drumstick": 100, "chicken tender": 40,

            # Proteins - Meat
            "pork chop": 180, "pork tenderloin": 450, "pork rib": 70,
            "steak": 250, "beef patty": 115, "ground beef patty": 115,
            "lamb chop": 150, "lamb shank": 250,
            "sausage": 50, "hot dog": 45, "bratwurst": 85,
            "bacon strip": 15, "bacon slice": 15, "bacon rasher": 15,
            "meatball": 25,

            # Proteins - Seafood
            "salmon fillet": 180, "tuna steak": 150, "cod fillet": 170, "tilapia fillet": 150,
            "shrimp": 15, "prawns": 20, "prawn": 20, "jumbo shrimp": 25,
            "scallop": 30, "scallops": 30, "sea scallop": 40, "sea scallops": 40, "bay scallop": 8, "bay scallops": 8,
            "oyster": 20, "oysters": 20, "clam": 15, "clams": 15, "mussel": 10, "mussels": 10,
            "crab leg": 50, "crab legs": 50, "lobster tail": 200, "lobster tails": 200,

            # Breads & Grains
            "slice bread": 30, "bread slice": 30, "toast": 30, "bread roll": 50,
            "bagel": 85, "english muffin": 60, "pita": 60, "tortilla": 50, "naan": 90, "flatbread": 60,
            "croissant": 50, "donut": 60, "doughnut": 60, "muffin": 60, "biscuit": 60, "scone": 70,
            "pancake": 40, "waffle": 75, "crumpet": 60,

            # Nuts & Seeds (per piece)
            "walnut": 5, "walnuts": 5,
            "almond": 1.2, "almonds": 1.2,
            "pecan": 5, "pecans": 5,
            "cashew": 2, "cashews": 2,
            "peanut": 1, "peanuts": 1,
            "macadamia": 2, "macadamias": 2,
            "pistachio": 1, "pistachios": 1,
            "hazelnut": 1.5, "hazelnuts": 1.5,
            "brazil nut": 5, "brazil nuts": 5,
            "pine nut": 0.1, "pine nuts": 0.1,
            "sunflower seed": 0.05, "sunflower seeds": 0.05,

            # Olives
            "olive": 4, "olives": 4, "kalamata olive": 6, "green olive": 4, "black olive": 4,

            # Other
            "chocolate chip": 0.3, "chocolate square": 5,
        }

        ingredient_lower = ingredient_name.lower()
        for key, weight in piece_weights.items():
            if key in ingredient_lower:
                return (gram_amount * weight, "TABLE")

        print(f"  ⚠️  Unknown piece weight for '{ingredient_name}', using 50g default")
        return (gram_amount * 50, "ESTIMATE")  # Generic piece weight

    # Fallback: assume 100g per unit
    print(f"  ⚠️  Unknown unit '{unit}', treating as 100g per unit")
    return (gram_amount * 100, "ESTIMATE")


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