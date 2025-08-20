"""
Ingredient parsing utility for structured data extraction.

Parses ingredient strings like "2 cups flour" into structured format:
{
    "quantity": "2",
    "unit": "cups", 
    "ingredient": "flour",
    "original": "2 cups flour"
}

For iOS app integration requiring separate quantity, unit, and ingredient fields.
"""

import re
from typing import Dict, Optional, Tuple


# Common measurement units (order matters - longer units first to avoid partial matches)
UNITS = [
    # Volume
    'tablespoons', 'tablespoon', 'tbsps', 'tbsp', 'tbs',
    'teaspoons', 'teaspoon', 'tsps', 'tsp',
    'cups', 'cup', 'c',
    'fluid ounces', 'fluid ounce', 'fl ozs', 'fl oz',
    'ounces', 'ounce', 'ozs', 'oz',
    'pints', 'pint', 'pts', 'pt',
    'quarts', 'quart', 'qts', 'qt',
    'gallons', 'gallon', 'gals', 'gal',
    'liters', 'liter', 'litres', 'litre', 'l',
    'milliliters', 'milliliter', 'millilitres', 'millilitre', 'mls', 'ml',
    
    # Weight
    'pounds', 'pound', 'lbs', 'lb',
    'grams', 'gram', 'gs', 'g',
    'kilograms', 'kilogram', 'kgs', 'kg',
    
    # Size descriptors
    'large', 'medium', 'small', 'extra large', 'extra small',
    'jumbo', 'mini', 'baby',
    
    # Container/package units
    'cans', 'can', 'jars', 'jar', 'bottles', 'bottle',
    'packages', 'package', 'pkgs', 'pkg',
    'boxes', 'box', 'containers', 'container',
    
    # Piece units
    'pieces', 'piece', 'slices', 'slice', 'strips', 'strip',
    'cloves', 'clove', 'bulbs', 'bulb', 'heads', 'head',
    'stalks', 'stalk', 'sprigs', 'sprig', 'bunches', 'bunch',
    
    # Generic
    'whole', 'halves', 'half', 'quarters', 'quarter'
]

# Create regex pattern for units (case insensitive)
UNITS_PATTERN = '|'.join([re.escape(unit) for unit in UNITS])

def parse_ingredient(ingredient_str: str) -> Dict[str, Optional[str]]:
    """
    Parse ingredient string into structured components.
    
    Args:
        ingredient_str: Raw ingredient string like "2 cups all-purpose flour"
    
    Returns:
        Dict with quantity, unit, ingredient, and original fields
    """
    if not ingredient_str or not ingredient_str.strip():
        return {
            "quantity": None,
            "unit": None,
            "ingredient": "",
            "original": ingredient_str
        }
    
    original = ingredient_str.strip()
    text = original.lower()
    
    # Pattern to match: [quantity] [unit] [ingredient]
    # Quantity can be: 1, 1.5, 1/2, 1 1/2, 2-3, etc.
    quantity_pattern = r'^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)'
    
    # Try to match quantity at the start
    quantity_match = re.match(quantity_pattern, text)
    
    if not quantity_match:
        # No quantity found - might be "salt to taste" or similar
        return {
            "quantity": None,
            "unit": None,
            "ingredient": original,
            "original": original
        }
    
    quantity = quantity_match.group(1).strip()
    remaining_text = text[quantity_match.end():].strip()
    
    # Try to match unit after quantity
    unit_pattern = f'^({UNITS_PATTERN})\\b'
    unit_match = re.match(unit_pattern, remaining_text, re.IGNORECASE)
    
    if unit_match:
        unit = unit_match.group(1).strip()
        ingredient = remaining_text[unit_match.end():].strip()
        
        # Clean up ingredient (remove leading commas, etc.)
        ingredient = re.sub(r'^[,\s]+', '', ingredient)
        
        # Preserve original capitalization for ingredient
        # Find the ingredient part in the original string
        orig_ingredient_start = len(quantity) + len(unit) + 2  # +2 for spaces
        orig_ingredient = original[orig_ingredient_start:].strip()
        orig_ingredient = re.sub(r'^[,\s]+', '', orig_ingredient)
        
    else:
        # No unit found, everything after quantity is ingredient
        unit = None
        ingredient = remaining_text
        
        # Preserve original capitalization
        orig_ingredient_start = len(quantity) + 1  # +1 for space
        orig_ingredient = original[orig_ingredient_start:].strip()
    
    return {
        "quantity": quantity,
        "unit": unit,
        "ingredient": orig_ingredient if unit else orig_ingredient,
        "original": original
    }


def parse_ingredients_list(ingredients: list) -> list:
    """
    Parse a list of ingredient strings into structured format.
    
    Args:
        ingredients: List of raw ingredient strings
        
    Returns:
        List of structured ingredient dictionaries
    """
    return [parse_ingredient(ing) for ing in ingredients if ing and ing.strip()]

