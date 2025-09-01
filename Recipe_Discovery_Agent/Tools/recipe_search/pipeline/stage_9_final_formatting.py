"""
Stage 9: Final Formatting
Handles final formatting of recipes for iOS app consumption.

This module formats parsed recipes into the final structure required by the iOS app.
"""

from typing import Dict, List
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list


def format_recipes_for_ios(recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Format recipes into iOS app structure.
    
    Args:
        recipes: List of parsed recipe dictionaries
        max_recipes: Maximum number of recipes to format
        
    Returns:
        List of formatted recipes ready for iOS consumption
    """
    formatted_recipes = []
    
    for recipe in recipes[:max_recipes]:
        # Keep ingredients as raw strings for instant display
        # Shopping conversion will happen in background after recipe save
        raw_ingredients = recipe.get("ingredients", [])
        # Convert to simple display format for iOS app
        structured_ingredients = [{"ingredient": ing} for ing in raw_ingredients] if raw_ingredients else []
        
        # Parse nutrition into structured format
        raw_nutrition = recipe.get("nutrition", [])
        structured_nutrition = parse_nutrition_list(raw_nutrition)
        
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