"""
Stage 9: Final Formatting
Handles final formatting of recipes for iOS app consumption.

This module formats parsed recipes into the final structure required by the iOS app.
"""

from typing import Dict, List
from ..Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list


def format_recipes_for_ios(recipes: List[Dict], max_recipes: int = 5) -> List[Dict]:
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
        
        formatted_recipes.append({
            "id": len(formatted_recipes) + 1,
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,
            "nutrition": structured_nutrition,
            "_instructions_for_analysis": recipe.get("instructions", [])
        })
    
    return formatted_recipes


def create_minimal_recipes_for_agent(formatted_recipes: List[Dict]) -> List[Dict]:
    """
    Create minimal context for agent to reduce response time.
    
    Args:
        formatted_recipes: List of formatted recipe dictionaries
        
    Returns:
        List of minimal recipe data for agent context
    """
    minimal_recipes = []
    
    for recipe in formatted_recipes:
        minimal_recipes.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "servings": recipe["servings"],
            "readyInMinutes": recipe["readyInMinutes"],
            "ingredients": [ing["ingredient"] for ing in recipe["ingredients"][:8]],
            "nutrition": recipe.get("nutrition", [])
        })
    
    return minimal_recipes


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