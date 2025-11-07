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
    nutrition: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Create a standardized recipe dictionary structure.
    
    Args:
        title: Recipe title
        parser_method: Source parser identifier, identifying what type of link was parsed (e.g., "Instagram", "Recipe_Sites", etc.)
        ingredients: List of ingredient dicts with 'name', 'quantity', 'unit' keys
        directions: List of direction steps as strings
        source_url: Original recipe URL
        nutrition: Optional nutrition dict with 'calories', 'fat', 'carbs', 'protein' keys
        
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
        "ingredients": ingredients,
        "directions": directions,
        "nutrition": nutrition,
        "source_url": source_url
    }


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
    "ingredients": [],
    "directions": [],
    "nutrition": {
        "calories": "",
        "fat": "",
        "carbs": "",
        "protein": ""
    },
    "source_url": ""
}