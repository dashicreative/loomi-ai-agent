#!/usr/bin/env python3
"""
Test script for unit normalization in json_recipe_model.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from json_recipe_model import normalize_ingredient_units

def test_unit_normalization():
    """Test various unit abbreviations and variations"""

    print("\n🧪 Unit Normalization Test")
    print("="*60)

    # Test ingredients with various unit formats
    test_ingredients = [
        {"name": "flour", "quantity": "2", "unit": "c"},              # c → cup
        {"name": "butter", "quantity": "1", "unit": "tbsp"},          # tbsp → tablespoon
        {"name": "salt", "quantity": "1", "unit": "tsp"},             # tsp → teaspoon
        {"name": "milk", "quantity": "1", "unit": "cups"},            # cups → cup
        {"name": "sugar", "quantity": "2", "unit": "C"},              # C → cup (case insensitive)
        {"name": "vanilla", "quantity": "1", "unit": "teaspoons"},    # teaspoons → teaspoon
        {"name": "chicken", "quantity": "1", "unit": "lb"},           # lb → pound
        {"name": "beef", "quantity": "2", "unit": "lbs"},             # lbs → pound
        {"name": "cheese", "quantity": "8", "unit": "oz"},            # oz → ounce
        {"name": "water", "quantity": "500", "unit": "ml"},           # ml → milliliter
        {"name": "oil", "quantity": "2", "unit": "tablespoons"},      # tablespoons → tablespoon
        {"name": "eggs", "quantity": "3", "unit": "count"},           # count → count (unchanged)
        {"name": "garlic", "quantity": "2", "unit": "cloves"},        # cloves → clove
        {"name": "pasta", "quantity": "1", "unit": "package"},        # package → package (unchanged)
    ]

    print("\n📋 Input Ingredients:")
    print("-"*60)
    for i, ing in enumerate(test_ingredients, 1):
        print(f"{i:2}. {ing['quantity']:5} {ing['unit']:15} → {ing['name']}")

    # Normalize the units
    normalized = normalize_ingredient_units(test_ingredients)

    print("\n✅ Normalized Ingredients:")
    print("-"*60)
    for i, ing in enumerate(normalized, 1):
        orig_unit = test_ingredients[i-1]['unit']
        new_unit = ing['unit']
        change_indicator = "✓" if orig_unit.lower() != new_unit else "→"
        print(f"{i:2}. {ing['quantity']:5} {new_unit:15} {change_indicator} {ing['name']}")

    print("\n📊 Normalization Summary:")
    print("-"*60)

    # Count changes
    changes = 0
    for i, ing in enumerate(normalized):
        if test_ingredients[i]['unit'].lower() != ing['unit']:
            orig = test_ingredients[i]['unit']
            new = ing['unit']
            print(f"  • '{orig}' → '{new}'")
            changes += 1

    print(f"\n✅ {changes}/{len(test_ingredients)} units normalized")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_unit_normalization()
