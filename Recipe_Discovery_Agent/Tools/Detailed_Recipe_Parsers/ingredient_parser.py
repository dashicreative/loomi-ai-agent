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
    
    # Convert Unicode fractions to regular fractions first
    text = original.replace('½', '1/2').replace('⅓', '1/3').replace('⅔', '2/3').replace('¼', '1/4').replace('¾', '3/4')
    text = text.replace('⅛', '1/8').replace('⅜', '3/8').replace('⅝', '5/8').replace('⅞', '7/8')
    text = text.replace('⅙', '1/6').replace('⅚', '5/6').replace('⅕', '1/5').replace('⅖', '2/5').replace('⅗', '3/5').replace('⅘', '4/5')
    text = text.lower()
    
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
        
        # Extract ingredient from original string by finding it after the unit
        # Search for the unit in the original string and take everything after it
        unit_search = re.search(rf'\b{re.escape(unit)}\b', original, re.IGNORECASE)
        if unit_search:
            orig_ingredient = original[unit_search.end():].strip()
            orig_ingredient = re.sub(r'^[,\s]+', '', orig_ingredient)
        else:
            orig_ingredient = ingredient
        
    else:
        # No unit found, everything after quantity is ingredient
        unit = None
        ingredient = remaining_text
        
        # Extract ingredient from original string by finding it after the quantity pattern
        # Find where the quantity ends in the original string
        orig_quantity_match = re.search(r'^(\d+\s+[\u00bc-\u00be\u2150-\u215e]|\d+[\u00bc-\u00be\u2150-\u215e]|[\u00bc-\u00be\u2150-\u215e]|\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)', original)
        if orig_quantity_match:
            orig_ingredient = original[orig_quantity_match.end():].strip()
        else:
            orig_ingredient = ingredient
    
    return {
        "quantity": quantity,
        "unit": unit,
        "ingredient": orig_ingredient,
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

