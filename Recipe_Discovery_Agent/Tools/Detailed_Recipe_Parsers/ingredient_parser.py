"""
Ingredient validation and enhancement utility.

Validates structured ingredient data from LLM and adds cart_friendly field.
No longer parses strings - expects structured data from universal_recipe_parser.

Enhanced structure includes shopping-aware fields:
{
    "quantity": "1",           # Shopping quantity (rounded up for whole items)
    "unit": "count",          # Shopping unit
    "ingredient": "lime",      # Clean ingredient name
    "amount": "0.5",          # Recipe amount if different
    "cart_friendly": true,     # Computed field for cart eligibility
    ...
}
"""

from typing import Dict, List, Optional


def validate_ingredient(ingredient: Dict) -> Dict:
    """
    Validate and enhance a structured ingredient from LLM.
    
    Args:
        ingredient: Structured ingredient dictionary from LLM
        
    Returns:
        Enhanced ingredient dictionary with cart_friendly field
    """
    # Ensure all fields exist with defaults
    ingredient.setdefault('quantity', None)
    ingredient.setdefault('unit', None)
    ingredient.setdefault('ingredient', '')
    ingredient.setdefault('store_quantity', None)
    ingredient.setdefault('store_unit', None)
    ingredient.setdefault('amount', None)
    ingredient.setdefault('size', None)
    ingredient.setdefault('additional_context', None)
    ingredient.setdefault('alternatives', [])
    ingredient.setdefault('pantry_staple', False)
    ingredient.setdefault('optional', False)
    ingredient.setdefault('disqualified', False)
    ingredient.setdefault('original', '')
    
    # Add cart_friendly logic - use store fields for cart eligibility
    ingredient['cart_friendly'] = bool(
        ingredient.get('store_quantity') and 
        ingredient.get('store_unit') and 
        ingredient.get('ingredient') and
        not ingredient.get('disqualified', False) and
        not ingredient.get('optional', False)
    )
    
    return ingredient


def parse_ingredients_list(ingredients: List) -> List[Dict]:
    """
    Validate a list of structured ingredients from LLM.
    
    Args:
        ingredients: List of structured ingredient dictionaries from LLM
        
    Returns:
        List of validated ingredient dictionaries with cart_friendly field
    """
    if not ingredients:
        return []
    
    validated = []
    for ing in ingredients:
        if isinstance(ing, dict):
            validated.append(validate_ingredient(ing))
        # No string handling - LLM should output structured data
    
    return validated

