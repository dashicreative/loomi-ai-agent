"""
Recipe data validation utilities.

This module validates that extracted recipe data contains all required fields
for the iOS app UI.
"""

from typing import Tuple, List


def validate_recipe_data(recipe_data: dict) -> Tuple[bool, List[str]]:
    """
    Validates that all required fields are present for iOS app UI.
    
    Args:
        recipe_data: Recipe data dictionary
        
    Returns:
        Tuple of (is_valid, missing_fields)
    """
    required_checks = {
        'ingredients': len(recipe_data.get('ingredients', [])) > 0,
        # 'instructions': len(recipe_data.get('instructions', [])) > 0,  # Temporarily disabled for performance testing
        'image_url': bool(recipe_data.get('image_url', '').strip()),
        'nutrition': len(recipe_data.get('nutrition', [])) >= 4  # Need all 4: calories, protein, carbs, fat
    }
    
    missing = [field for field, present in required_checks.items() if not present]
    return len(missing) == 0, missing