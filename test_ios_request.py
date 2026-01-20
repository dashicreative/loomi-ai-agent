#!/usr/bin/env python3
"""
Test the exact payload that iOS is sending to debug the issue
"""

import asyncio
import json
import sys
from pathlib import Path

# Add macro agent to path
sys.path.append(str(Path(__file__).parent / "Ingredient_Macro_agent"))

from macro_agent import calculate_recipe_macros_optimized

async def test_ios_payload():
    """Test with the exact payload from iOS"""

    print("\n🧪 Testing iOS Payload")
    print("="*60)

    # Exact payload from iOS logs
    ingredients = [
        {"name": "pita", "quantity": "1", "unit": "count"},
        {"name": "uncooked potato", "quantity": "400", "unit": "gram"},
        {"quantity": "2", "unit": "teaspoon", "name": "aromat seasoning"},
        {"quantity": "1", "unit": "teaspoon", "name": "olive oil"},
        {"quantity": "200", "unit": "gram", "name": "uncooked chicken breast"},
        {"quantity": "2", "unit": "clove", "name": "garlic"},
        {"quantity": "1", "unit": "teaspoon", "name": "paprika"},
        {"quantity": "1", "unit": "teaspoon", "name": "cumin"},
        {"name": "chilli powder", "quantity": "1/2", "unit": "teaspoon"},
        {"name": "lemon juice", "quantity": "1", "unit": "count"},
        {"name": "natural Greek yogurt", "quantity": "15", "unit": "gram"},
        {"name": "Salt", "quantity": "1", "unit": "count"},
        {"name": "pepper", "quantity": "1", "unit": "count"},
        {"name": "baby cucumber", "quantity": "1", "unit": "count"},
        {"name": "mint leaves", "quantity": "2", "unit": "count"},
        {"name": "cherry tomatoes", "quantity": "5", "unit": "count"},
        {"name": "red onion", "quantity": "1/2", "unit": "count"},
        {"name": "olives", "quantity": "5-6", "unit": "count"},
        {"name": "dried dill", "quantity": "1/2", "unit": "teaspoon"},
        {"name": "feta cheese", "quantity": "50", "unit": "gram"}
    ]

    print(f"\n📋 Testing {len(ingredients)} ingredients:")
    for i, ing in enumerate(ingredients[:3], 1):
        print(f"  {i}. {ing['quantity']} {ing['unit']} - {ing['name']}")
    print(f"  ... and {len(ingredients) - 3} more")

    try:
        print("\n🔄 Processing with macro agent...")
        result_string, ingredient_results = await calculate_recipe_macros_optimized(ingredients)

        # Parse result
        import re
        numbers = re.findall(r'(\d+);', result_string)

        if len(numbers) >= 4:
            calories = int(numbers[0])
            protein = int(numbers[1])
            fat = int(numbers[2])
            carbs = int(numbers[3])

            ingredient_sources = [result['source'] for result in ingredient_results]

            print(f"\n✅ Success!")
            print(f"  Calories: {calories}")
            print(f"  Protein: {protein}g")
            print(f"  Fat: {fat}g")
            print(f"  Carbs: {carbs}g")
            print(f"  Sources: {len(ingredient_sources)} tracked")

            # Show source breakdown
            from collections import Counter
            source_counts = Counter(ingredient_sources)
            print(f"\n  Source Distribution:")
            for source, count in source_counts.items():
                pct = (count / len(ingredient_sources)) * 100
                print(f"    {source}: {count}/{len(ingredient_sources)} ({pct:.0f}%)")

        else:
            print(f"\n❌ Unexpected result format: {result_string[:100]}")

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ios_payload())
    print("\n" + "="*60 + "\n")
