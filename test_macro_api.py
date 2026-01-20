#!/usr/bin/env python3
"""
Test script for the macro calculation API endpoint
"""

import asyncio
import json
import sys
from pathlib import Path

# Add macro agent to path
sys.path.append(str(Path(__file__).parent / "Ingredient_Macro_agent"))

from macro_agent import calculate_recipe_macros_optimized

async def test_macro_calculation():
    """Test the macro calculation directly (simulates what the API does)"""

    print("\n🧪 Testing Macro Calculation API Logic")
    print("="*60)

    # Sample ingredients (cookie recipe)
    ingredients = [
        {
            "name": "salted butter, softened",
            "quantity": "1",
            "unit": "cup"
        },
        {
            "name": "packed dark brown sugar",
            "quantity": "2",
            "unit": "cup"
        },
        {
            "name": "vanilla extract",
            "quantity": "2",
            "unit": "tsp"
        },
        {
            "name": "eggs",
            "quantity": "2",
            "unit": "count"
        },
        {
            "name": "all-purpose flour",
            "quantity": "1.75",
            "unit": "cup"
        },
        {
            "name": "salt",
            "quantity": "1",
            "unit": "tsp"
        },
        {
            "name": "baking soda",
            "quantity": "0.5",
            "unit": "tsp"
        },
        {
            "name": "old-fashioned oats",
            "quantity": "3",
            "unit": "cup"
        }
    ]

    print("\n📋 Input Ingredients:")
    for i, ing in enumerate(ingredients, 1):
        print(f"  {i}. {ing['quantity']} {ing['unit']} - {ing['name']}")

    print("\n🔄 Processing...")

    try:
        # Call the macro agent (same as API does)
        result_string, ingredient_results = await calculate_recipe_macros_optimized(ingredients)

        # Parse result string (same as API does)
        import re
        numbers = re.findall(r'(\d+);', result_string)

        if len(numbers) < 4:
            print(f"❌ Invalid result format: expected 4 numbers, got {len(numbers)}")
            return

        calories = int(numbers[0])
        protein = int(numbers[1])
        fat = int(numbers[2])
        carbs = int(numbers[3])

        # Extract per-ingredient sources
        ingredient_sources = [result['source'] for result in ingredient_results]

        print("\n✅ API Response (JSON):")
        print("-"*60)

        response = {
            "success": True,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
            "ingredient_sources": ingredient_sources,
            "elapsed_seconds": 2.5  # Would be actual time in API
        }

        print(json.dumps(response, indent=2))

        print("\n📊 Data Source Breakdown:")
        print("-"*60)
        for i, ing in enumerate(ingredients):
            source = ingredient_sources[i]
            print(f"  {i+1}. {ing['name'][:40]:40} → {source}")

        print("\n🎯 Summary:")
        print(f"  • Total Calories: {calories}")
        print(f"  • Total Protein: {protein}g")
        print(f"  • Total Fat: {fat}g")
        print(f"  • Total Carbs: {carbs}g")

        # Count sources
        from collections import Counter
        source_counts = Counter(ingredient_sources)
        print(f"\n  Source Distribution:")
        for source, count in source_counts.items():
            pct = (count / len(ingredient_sources)) * 100
            print(f"    - {source}: {count}/{len(ingredient_sources)} ({pct:.0f}%)")

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_macro_calculation())
    print("\n" + "="*60)
    print("✅ Test Complete!\n")
