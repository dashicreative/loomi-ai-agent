#!/usr/bin/env python3
"""
Test script for quantity normalization in json_recipe_model.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from json_recipe_model import normalize_quantity, normalize_ingredient_units

def test_quantity_normalization():
    """Test various quantity formats"""

    print("\n🧪 Quantity Normalization Test")
    print("="*60)

    # Test cases: (input, expected_output, description)
    test_cases = [
        # Ranges - take max
        ("5-6", "6", "Range (5-6) → max"),
        ("2-3", "3", "Range (2-3) → max"),
        ("1-2", "2", "Range (1-2) → max"),

        # Fractions
        ("1/2", "0.5", "Simple fraction"),
        ("1/4", "0.25", "Quarter fraction"),
        ("3/4", "0.75", "Three quarters"),
        ("2/3", "0.6666666666666666", "Two thirds"),

        # Mixed numbers
        ("1 1/2", "1.5", "Mixed number (1 1/2)"),
        ("2 1/4", "2.25", "Mixed number (2 1/4)"),

        # Clean numbers (should pass through)
        ("5", "5", "Whole number"),
        ("2.5", "2.5", "Decimal number"),
        ("100", "100", "Large number"),

        # Edge cases
        ("", "", "Empty string"),
        ("  3  ", "3", "Whitespace trimmed"),
    ]

    print("\n📋 Test Cases:")
    print("-"*60)

    passed = 0
    failed = 0

    for input_val, expected, description in test_cases:
        result = normalize_quantity(input_val)
        status = "✅" if result == expected else "❌"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} {description:30} | '{input_val}' → '{result}' (expected: '{expected}')")

    print("\n📊 Summary:")
    print("-"*60)
    print(f"✅ Passed: {passed}/{len(test_cases)}")
    print(f"❌ Failed: {failed}/{len(test_cases)}")

def test_ingredient_normalization():
    """Test full ingredient normalization including quantities"""

    print("\n\n🧪 Full Ingredient Normalization Test")
    print("="*60)

    test_ingredients = [
        {"name": "olives", "quantity": "5-6", "unit": "count"},
        {"name": "flour", "quantity": "1/2", "unit": "c"},
        {"name": "butter", "quantity": "1 1/2", "unit": "tbsp"},
        {"name": "cherry tomatoes", "quantity": "2-3", "unit": "count"},
        {"name": "sugar", "quantity": "2", "unit": "cups"},
    ]

    print("\n📋 Input Ingredients:")
    print("-"*60)
    for i, ing in enumerate(test_ingredients, 1):
        print(f"{i:2}. {ing['quantity']:8} {ing['unit']:10} → {ing['name']}")

    # Normalize
    normalized = normalize_ingredient_units(test_ingredients)

    print("\n✅ Normalized Ingredients:")
    print("-"*60)
    for i, ing in enumerate(normalized, 1):
        orig = test_ingredients[i-1]
        qty_change = "✓" if orig['quantity'] != ing['quantity'] else "→"
        unit_change = "✓" if orig['unit'] != ing['unit'] else "→"
        print(f"{i:2}. {ing['quantity']:8} {qty_change} {ing['unit']:10} {unit_change} {ing['name']}")

    print("\n📊 Normalization Summary:")
    print("-"*60)

    qty_changes = 0
    unit_changes = 0

    for i, ing in enumerate(normalized):
        orig = test_ingredients[i]
        if orig['quantity'] != ing['quantity']:
            print(f"  • Quantity: '{orig['quantity']}' → '{ing['quantity']}' ({orig['name']})")
            qty_changes += 1
        if orig['unit'] != ing['unit']:
            print(f"  • Unit: '{orig['unit']}' → '{ing['unit']}' ({orig['name']})")
            unit_changes += 1

    print(f"\n✅ {qty_changes} quantities normalized")
    print(f"✅ {unit_changes} units normalized")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_quantity_normalization()
    test_ingredient_normalization()
