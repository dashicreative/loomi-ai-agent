#!/usr/bin/env python3
"""
Standard Recipe JSON Format

Defines the uniform JSON structure that all recipe parsers must output.
This ensures consistency across Instagram parser, recipe site parsers, and any future parsers.
"""

import json
from typing import Dict, List, Any


def create_standard_recipe_json(
    title: str,
    parser_method: str,
    ingredients: List[Dict[str, str]],
    directions: List[str],
    source_url: str,
    nutrition: Dict[str, str] = None,
    image: str = "",
    meal_occasion: str = "Other",
    total_time: str = ""
) -> Dict[str, Any]:
    """
    Create a standardized recipe dictionary structure.
    
    Args:
        title: Recipe title
        parser_method: Source parser identifier (e.g., "Instagram", "AllRecipes", etc.)
        ingredients: List of ingredient dicts with 'name', 'quantity', 'unit' keys
        directions: List of direction steps as strings
        source_url: Original recipe URL
        nutrition: Optional nutrition dict with 'calories', 'fat', 'carbs', 'protein' keys
        image: Optional image URL for the recipe (defaults to empty string)
        meal_occasion: Meal occasion category (Breakfast/Lunch/Dinner/Dessert/Snack/Other)
        total_time: Optional total cooking/prep time (e.g., "1 h 45 m", defaults to empty string)
        
    Returns:
        Standardized recipe dictionary
    """
    # Default empty nutrition if not provided
    if nutrition is None:
        nutrition = {
            "calories": "",
            "fat": "",
            "carbs": "",
            "protein": ""
        }
    
    return {
        "title": title,
        "parser_method": parser_method,
        "meal_occasion": meal_occasion,
        "total_time": total_time,
        "ingredients": ingredients,
        "directions": directions,
        "nutrition": nutrition,
        "image": image,
        "source_url": source_url
    }


def create_enhanced_recipe_json(
    title: str,
    parser_method: str,
    source_url: str,
    step_ingredient_result: Dict[str, Any],
    meta_step_result: List[Dict[str, Any]],
    meta_ingredients: List[Dict[str, Any]] = None,
    nutrition: Dict[str, str] = None,
    image: str = "",
    meal_occasion: str = "Other",
    servings: int = 0,
    total_time: str = ""
) -> Dict[str, Any]:
    """
    Create an enhanced recipe dictionary with step-ingredient matching, meta steps, and meta-ingredients.

    Args:
        title: Recipe title
        parser_method: Source parser identifier (e.g., "Instagram", "RecipeSite")
        source_url: Original recipe URL
        step_ingredient_result: Result from step_ingredient_matcher containing ingredients_with_ids and step_mappings
        meta_step_result: Result from meta_step_extractor containing structured steps
        meta_ingredients: Optional list of deduplicated meta-ingredients with linked_raw_ids (for shopping context)
        nutrition: Optional nutrition dict
        image: Optional image URL
        meal_occasion: Meal occasion category
        servings: Number of servings (0 if not found or invalid)
        total_time: Optional total cooking/prep time

    Returns:
        Enhanced recipe dictionary with ingredient IDs, meta-ingredients, and meta steps
    """
    # Default empty nutrition if not provided
    if nutrition is None:
        nutrition = {
            "calories": "",
            "fat": "",
            "carbs": "",
            "protein": ""
        }
    
    # Get ingredients with IDs from step_ingredient_result
    ingredients_with_ids = step_ingredient_result.get("ingredients_with_ids", {})
    step_mappings = step_ingredient_result.get("step_mappings", [])
    
    # Convert ingredients_with_ids to list format for JSON
    ingredients_list = []
    for ingredient_id, ingredient_data in ingredients_with_ids.items():
        ingredients_list.append({
            "id": ingredient_data["id"],
            "name": ingredient_data["name"],
            "quantity": ingredient_data["quantity"],
            "unit": ingredient_data["unit"]
        })
    
    # Create step mappings lookup for quick access
    step_ingredient_lookup = {mapping["step_number"]: mapping["ingredient_ids"] for mapping in step_mappings}
    
    # Build enhanced directions with ingredient IDs and meta step info
    enhanced_directions = []
    for step_info in meta_step_result:
        step_number = step_info["step_number"]
        
        enhanced_directions.append({
            "step_number": step_number,
            "text": step_info["text"],
            "type": step_info["type"],
            "meta_step_section": step_info["meta_step_section"],
            "ingredient_ids": step_ingredient_lookup.get(step_number, [])
        })
    
    # Build base recipe dictionary
    recipe_dict = {
        "title": title,
        "parser_method": parser_method,
        "meal_occasion": meal_occasion,
        "servings": servings,
        "total_time": total_time,
        "ingredients": ingredients_list,
        "directions": enhanced_directions,
        "nutrition": nutrition,
        "image": image,
        "source_url": source_url
    }

    # Add meta_ingredients if provided (deduplicated shopping-friendly list)
    if meta_ingredients:
        recipe_dict["meta_ingredients"] = meta_ingredients

    return recipe_dict


def format_standard_recipe_json(recipe_dict: Dict[str, Any]) -> str:
    """
    Convert standardized recipe dictionary to formatted JSON string.
    
    Args:
        recipe_dict: Recipe dictionary in standard format
        
    Returns:
        Formatted JSON string
    """
    return json.dumps(recipe_dict, indent=2, ensure_ascii=False)


# Template for easy reference by parsers
STANDARD_RECIPE_TEMPLATE = {
    "title": "",
    "parser_method": "",
    "meal_occasion": "Other",
    "total_time": "",
    "ingredients": [],
    "directions": [],
    "nutrition": {
        "calories": "",
        "fat": "",
        "carbs": "",
        "protein": ""
    },
    "image": "",
    "source_url": ""
}