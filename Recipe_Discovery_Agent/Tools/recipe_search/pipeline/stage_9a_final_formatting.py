"""
Stage 9: Final Formatting
Handles final formatting of recipes for iOS app consumption.

This module formats parsed recipes into the final structure required by the iOS app.
"""

from typing import Dict, List
import re
import asyncio
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list


def clean_nutrition_for_final_formatting(unified_nutrition: List[str]) -> Dict[str, float]:
    """
    Enhanced nutrition cleaning that handles messy data and returns clean numeric values.
    DUPLICATED from stage_6_requirements_verification.py because this parser actually works.
    
    Args:
        unified_nutrition: Raw nutrition strings from recipe parsing
        
    Returns:
        Dict with clean numeric values: {"protein": 30.0, "calories": 402.0, "carbs": 50.0, "fat": 13.0}
    """
    nutrition_clean = {}
    
    if not unified_nutrition:
        return nutrition_clean
    
    # Step 1: Combine and preprocess all nutrition text
    full_text = " ".join(unified_nutrition).lower()
    
    # Step 2: Split mashed-together strings using common delimiters
    # Handle cases like "Calories300Protein25gFat10g" or "calories: 300 protein: 25g fat: 10g"
    delimited_text = re.sub(r'([a-z])(\d)', r'\1 \2', full_text)  # Add space before numbers
    delimited_text = re.sub(r'(\d)([a-z])', r'\1 \2', delimited_text)  # Add space after numbers
    delimited_text = re.sub(r'(calories|protein|carbs|carbohydrates|fat)', r' \1', delimited_text)
    
    # Step 3: Remove interfering text
    clean_text = delimited_text.replace('per serving', '').replace('per portion', '')
    clean_text = clean_text.replace('amount per serving', '').replace('nutrition facts', '')
    
    # Step 4: Enhanced patterns with validation - FIXED ORDER
    nutrition_patterns = {
        "calories": [
            r'(\d{2,4})\s*calories\b',              # "334 calories" - PRIORITIZE NUMBER FIRST
            r'(\d{2,4})\s*kcal\b',                  # "334 kcal"  
            r'calories[:\s]*(\d{2,4})\b',           # "Calories: 334" - SECONDARY
            r'energy[:\s]*(\d{2,4})\b',             # "Energy: 334"
        ],
        "protein": [
            r'(\d+(?:\.\d+)?)\s*g\s*protein\b',         # "19g protein" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*grams?\s*protein\b',    # "19 grams protein"  
            r'protein[:\s]*(\d+(?:\.\d+)?)\s*g?\b',     # "Protein: 19g" - SECONDARY
        ],
        "carbs": [
            r'(\d+(?:\.\d+)?)\s*g\s*carbohydrates?\b',      # "26g carbohydrates" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*g\s*carbs\b',              # "26g carbs"
            r'carbohydrates?[:\s]*(\d+(?:\.\d+)?)\s*g?\b',  # "Carbohydrates: 26g" - SECONDARY
            r'carbs[:\s]*(\d+(?:\.\d+)?)\s*g?\b',
            r'total\s+carbohydrates?[:\s]*(\d+(?:\.\d+)?)\b',
        ],
        "fat": [
            r'(\d+(?:\.\d+)?)\s*g\s*fat\b',                 # "17g fat" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*g\s*total\s*fat\b',         # "17g total fat"
            r'(?:total\s+)?fat[:\s]*(\d+(?:\.\d+)?)\s*g?\b', # "Fat: 17g" - SECONDARY
        ]
    }
    
    # Step 5: Extract and validate values
    for nutrient, patterns in nutrition_patterns.items():
        found_value = None
        for pattern in patterns:
            match = re.search(pattern, clean_text)
            if match and found_value is None:  # Take first valid match
                try:
                    value = float(match.group(1))
                    
                    # Validation: reject obviously wrong values
                    if nutrient == "calories" and (value < 10 or value > 5000):
                        continue  # Skip invalid calorie values
                    elif nutrient in ["protein", "carbs", "fat"] and (value < 0 or value > 200):
                        continue  # Skip invalid macro values
                    
                    found_value = value
                    break
                except ValueError:
                    continue
        
        if found_value is not None:
            nutrition_clean[nutrient] = found_value
    
    return nutrition_clean


async def format_recipes_for_ios_async(recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Async version of format_recipes_for_ios with parallel ingredient processing.
    """
    # Import stage_9b function dynamically to avoid circular imports
    from .stage_9b_ingredient_parsing import process_all_recipe_ingredients
    
    # STAGE 9B: Process ingredients in parallel before final formatting
    limited_recipes = recipes[:max_recipes]
    
    try:
        processed_recipes = await process_all_recipe_ingredients(limited_recipes)
    except Exception as e:
        print(f"⚠️  Stage 9b ingredient parsing failed: {e}")
        processed_recipes = limited_recipes  # Use original recipes as fallback
    
    return _format_recipes_sync(processed_recipes, max_recipes, fallback_used, exact_match_count)


def format_recipes_for_ios(recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Format recipes into iOS app structure.
    
    Args:
        recipes: List of parsed recipe dictionaries (may have pre-processed ingredients from Stage 9b)
        max_recipes: Maximum number of recipes to format
        
    Returns:
        List of formatted recipes ready for iOS consumption
    """
    limited_recipes = recipes[:max_recipes]
    return _format_recipes_sync(limited_recipes, max_recipes, fallback_used, exact_match_count)


def _format_recipes_sync(processed_recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Synchronous recipe formatting logic (shared by both async and sync versions).
    """
    formatted_recipes = []
    
    for recipe in processed_recipes:
        # Use processed ingredients from Stage 9b (already structured)
        processed_ingredients = recipe.get("ingredients", [])
        
        # If ingredients are already structured from Stage 9b, use them
        # Otherwise fall back to simple display format
        if processed_ingredients and len(processed_ingredients) > 0 and isinstance(processed_ingredients[0], dict) and "store_quantity" in processed_ingredients[0]:
            # Ingredients are already structured from Stage 9b
            structured_ingredients = processed_ingredients
        else:
            # Fallback: Convert to simple display format for iOS app
            structured_ingredients = [{"ingredient": ing if isinstance(ing, str) else ing.get("ingredient", "")} for ing in processed_ingredients] if processed_ingredients else []
        
        # Parse nutrition using the working parser from Stage 6 (applied to ALL final recipes)
        raw_nutrition = recipe.get("nutrition", [])
        parsed_nutrition = clean_nutrition_for_final_formatting(raw_nutrition)
        
        # Convert parsed nutrition to structured format for iOS
        structured_nutrition = []
        for nutrient, value in parsed_nutrition.items():
            structured_nutrition.append({
                "name": nutrient,
                "amount": str(value),
                "unit": "g" if nutrient in ["protein", "fat", "carbs"] else "kcal" if nutrient == "calories" else "",
                "original": f"{value}{('g' if nutrient in ['protein', 'fat', 'carbs'] else 'kcal' if nutrient == 'calories' else '')} {nutrient}"
            })
        
        # Determine if this is an exact match or closest match
        is_exact_match = (len(formatted_recipes) + 1) <= exact_match_count
        nutrition_percentage = recipe.get('nutrition_match_percentage')
        
        formatted_recipe = {
            "id": len(formatted_recipes) + 1,
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,
            "nutrition": structured_nutrition,
            "_instructions_for_analysis": recipe.get("instructions", [])
        }
        
        # Add metadata for agent context
        if fallback_used and not is_exact_match and nutrition_percentage is not None:
            formatted_recipe["_closest_match"] = True
            formatted_recipe["_nutrition_match_percentage"] = nutrition_percentage
        
        formatted_recipes.append(formatted_recipe)
    
    return formatted_recipes


def create_minimal_recipes_for_agent(formatted_recipes: List[Dict]) -> Dict:
    """
    Create minimal context for agent with fallback metadata.
    
    Args:
        formatted_recipes: List of formatted recipe dictionaries
        
    Returns:
        Dict with minimal recipe data and fallback metadata for agent context
    """
    minimal_recipes = []
    closest_match_count = 0
    exact_match_count = 0
    
    for recipe in formatted_recipes:
        is_closest_match = recipe.get("_closest_match", False)
        if is_closest_match:
            closest_match_count += 1
        else:
            exact_match_count += 1
            
        minimal_recipe = {
            "id": recipe["id"],
            "title": recipe["title"],
            "servings": recipe["servings"],
            "readyInMinutes": recipe["readyInMinutes"],
            "ingredients": [ing["ingredient"] for ing in recipe["ingredients"][:8]],
            "nutrition": recipe.get("nutrition", [])
        }
        
        # Include percentage for closest matches
        if is_closest_match:
            minimal_recipe["nutrition_match_percentage"] = recipe.get("_nutrition_match_percentage")
        
        minimal_recipes.append(minimal_recipe)
    
    return {
        "recipes": minimal_recipes,
        "exact_matches": exact_match_count,
        "closest_matches": closest_match_count,
        "fallback_used": closest_match_count > 0
    }


def create_failed_parse_report(fp1_failures: List[Dict], failed_parses: List[Dict]) -> Dict:
    """
    Create failure report for business analytics.
    
    Args:
        fp1_failures: List of content scraping failures
        failed_parses: List of recipe parsing failures
        
    Returns:
        Dictionary containing failure statistics and details
    """
    all_failures = fp1_failures + failed_parses
    
    return {
        "total_failed": len(all_failures),
        "content_scraping_failures": len(fp1_failures),
        "recipe_parsing_failures": len(failed_parses),
        "failed_urls": [
            {
                "url": fp.get("url") or fp.get("result", {}).get("url", ""),
                "failure_point": fp.get("failure_point", "Unknown"),
                "error": fp.get("error", "Unknown error")
            }
            for fp in all_failures
        ]
    }