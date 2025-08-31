"""
Stage 5: Nutrition Normalization
Normalizes nutrition data from different sources into a consistent format.

This module handles all nutrition data processing and parsing operations.
"""

import re
from typing import Dict, Optional, List


# ONLY the 4 required nutrition fields for iOS app
REQUIRED_NUTRITION = ["calories", "protein", "fat", "carbs"]

# Common nutrition terms and their variations - ONLY the 4 required values
NUTRITION_TERMS = {
    "calories": ["calories", "kcal", "cal", "energy"],
    "protein": ["protein", "proteins"],
    "fat": ["fat", "fats", "total fat"],
    "carbs": ["carbs", "carbohydrates", "carbohydrate", "total carbohydrates"]
}

# Common units for nutrition
NUTRITION_UNITS = ["g", "mg", "kcal", "cal", "grams", "milligrams"]


def normalize_nutrition_data(recipe):
    """
    Convert all nutrition formats to simple string array for consistency.
    This ensures all recipes have nutrition data in the same format regardless of parsing source.
    """
    unified = []
    
    # Priority 1: From structured format (JSON-LD parsed)
    if recipe.get('structured_nutrition'):
        for item in recipe['structured_nutrition']:
            if isinstance(item, dict) and item.get('amount') and item.get('name'):
                amount = str(item['amount']).strip()
                unit = str(item.get('unit', '')).strip()
                name = str(item['name']).strip().lower()
                
                # Normalize common nutrition names
                if name in ['protein', 'fat', 'carbs', 'carbohydrates']:
                    unified.append(f"{amount}{unit} {name}")
                elif name in ['calories', 'kcal']:
                    unified.append(f"{amount} calories")
                elif name == 'sodium':
                    unified.append(f"{amount}{unit} sodium")
                elif name == 'fiber':
                    unified.append(f"{amount}{unit} fiber")
    
    # Priority 2: From raw format (HTML parsed)
    elif recipe.get('nutrition') and isinstance(recipe['nutrition'], list):
        for item in recipe['nutrition']:
            if isinstance(item, str) and item.strip():
                # Clean up the string format
                cleaned = item.strip()
                # Normalize "kcal" to "calories"
                cleaned = cleaned.replace('kcal calories', 'calories').replace('kcal', 'calories')
                unified.append(cleaned)
    
    # Store the unified format
    recipe['unified_nutrition'] = unified
    return recipe


def parse_nutrition_string(nutrition_str: str) -> Dict[str, Optional[str]]:
    """
    Parse nutrition string into structured components.
    
    Args:
        nutrition_str: Raw nutrition string like "30g protein" or "250 calories"
    
    Returns:
        Dict with name, amount, unit, and original fields
    """
    if not nutrition_str or not nutrition_str.strip():
        return {
            "name": "",
            "amount": None,
            "unit": None,
            "original": nutrition_str
        }
    
    original = nutrition_str.strip().lower()
    
    # Pattern to match: [amount][unit] [nutrition_name] OR [nutrition_name] [amount][unit]
    # Examples: "30g protein", "protein 30g", "250 calories", "calories: 250"
    
    # Try pattern: amount + unit + nutrition_name (e.g., "30g protein")
    pattern1 = r'(\d+(?:\.\d+)?)\s*([a-z]+)?\s+(.+)'
    match1 = re.match(pattern1, original)
    
    if match1:
        amount = match1.group(1)
        unit = match1.group(2) or ""
        nutrition_text = match1.group(3).strip()
        
        # Find nutrition name
        nutrition_name = find_nutrition_name(nutrition_text)
        if nutrition_name:
            return {
                "name": nutrition_name,
                "amount": amount,
                "unit": unit,
                "original": nutrition_str.strip()
            }
    
    # Try pattern: nutrition_name + amount + unit (e.g., "protein 30g", "calories: 250")
    pattern2 = r'([a-z\s:]+?)\s*[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)'
    match2 = re.match(pattern2, original)
    
    if match2:
        nutrition_text = match2.group(1).strip().rstrip(':')
        amount = match2.group(2)
        unit = match2.group(3) or ""
        
        # Find nutrition name
        nutrition_name = find_nutrition_name(nutrition_text)
        if nutrition_name:
            return {
                "name": nutrition_name,
                "amount": amount,
                "unit": unit,
                "original": nutrition_str.strip()
            }
    
    # If no patterns match, return empty structure
    return {
        "name": "",
        "amount": None,
        "unit": None,
        "original": nutrition_str.strip()
    }


def find_nutrition_name(text: str) -> Optional[str]:
    """
    Find the standardized nutrition name from text.
    
    Args:
        text: Text that might contain nutrition terms
        
    Returns:
        Standardized nutrition name or None
    """
    text_lower = text.lower().strip()
    
    for standard_name, variations in NUTRITION_TERMS.items():
        for variation in variations:
            if variation in text_lower:
                return standard_name
    
    return None


def parse_nutrition_list(nutrition_data: List[str]) -> List[Dict]:
    """
    Parse a list of nutrition strings into structured format.
    
    Args:
        nutrition_data: List of raw nutrition strings
        
    Returns:
        List of structured nutrition dictionaries
    """
    return [parse_nutrition_string(nutrition) for nutrition in nutrition_data if nutrition and nutrition.strip()]


def extract_required_nutrition(nutrition_list: List[Dict]) -> Dict[str, Dict]:
    """
    Extract only the required nutrition fields for iOS app.
    
    Args:
        nutrition_list: List of parsed nutrition dictionaries
        
    Returns:
        Dict with required nutrition fields only
    """
    required_data = {}
    
    for nutrition in nutrition_list:
        name = nutrition.get("name", "")
        if name in REQUIRED_NUTRITION:
            required_data[name] = nutrition
    
    return required_data