#!/usr/bin/env python3
"""
Test CLI for Macro Calculation Agent
Allows testing ingredient arrays and viewing macro calculation output.
"""

import json
import time
from macro_agent import calculate_recipe_macros_sync

def test_sample_ingredients():
    """Test with the sample ingredients provided by user"""
    
    print("🥘 MACRO CALCULATION AGENT - TEST CLI")
    print("=" * 60)
    
    # Sample ingredient array (Loaded Greek Chicken Salad Bowl)
    sample_ingredients = [
        {"name": "pita", "quantity": "1", "unit": "count"},
        {"name": "uncooked potato", "quantity": "400", "unit": "gram"},
        {"name": "aromat seasoning", "quantity": "2", "unit": "teaspoon"},
        {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        {"name": "uncooked chicken breast, diced", "quantity": "200", "unit": "gram"},
        {"name": "of garlic, minced", "quantity": "2", "unit": "clove"},
        {"name": "paprika", "quantity": "1", "unit": "teaspoon"},
        {"name": "cumin", "quantity": "1", "unit": "teaspoon"},
        {"name": "chilli powder", "quantity": "0.5", "unit": "teaspoon"},
        {"name": "Squeeze of lemon juice", "quantity": "1", "unit": "count"},
        {"name": "natural Greek style yoghurt", "quantity": "15", "unit": "gram"},
        {"name": "Salt", "quantity": "1", "unit": "count"},
        {"name": "pepper", "quantity": "1", "unit": "count"},
        {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        {"name": "natural Greek yoghurt", "quantity": "2", "unit": "tablespoon"},
        {"name": "baby cucumber", "quantity": "1", "unit": "count"},
        {"name": "mint leaves", "quantity": "2", "unit": "count"},
        {"name": "of garlic, minced", "quantity": "1", "unit": "clove"},
        {"name": "Squeeze of lemon", "quantity": "1", "unit": "count"},
        {"name": "olive oil", "quantity": "1", "unit": "teaspoon"},
        {"name": "Salt", "quantity": "1", "unit": "count"},
        {"name": "pepper", "quantity": "1", "unit": "count"},
        {"name": "cherry tomatoes", "quantity": "5", "unit": "count"},
        {"name": "baby cucumbers", "quantity": "2", "unit": "count"},
        {"name": "red onion", "quantity": "0.5", "unit": "count"},
        {"name": "olives", "quantity": "6", "unit": "count"},
        {"name": "dried dill", "quantity": "0.5", "unit": "teaspoon"},
        {"name": "feta cheese, crumbled", "quantity": "50", "unit": "gram"},
        {"name": "olive oil", "quantity": "1", "unit": "teaspoon"}
    ]
    
    print("📋 Input Ingredients:")
    print("-" * 40)
    for i, ingredient in enumerate(sample_ingredients, 1):
        name = ingredient['name'][:50] + "..." if len(ingredient['name']) > 50 else ingredient['name']
        print(f"{i:2}. {ingredient['quantity']} {ingredient['unit']} - {name}")
    
    print("\n🔄 Processing with Macro Agent (Parallel Mode)...")
    print("-" * 40)

    try:
        # Calculate macros using the agent with timing
        start_time = time.time()
        result_string, ingredient_results = calculate_recipe_macros_sync(sample_ingredients)
        elapsed_time = time.time() - start_time

        print(f"⏱️  Processing Time: {elapsed_time:.2f}s")

        print("\n✅ CALCULATED MACROS:")
        print("-" * 40)

        # Parse result with metadata
        if isinstance(result_string, str) and ';' in result_string:
            # New format: calories;metadata,protein;metadata,fat;metadata,carbs;metadata
            # Extract numbers using regex (since metadata contains commas)
            import re
            numbers = re.findall(r'(\d+);', result_string)

            if len(numbers) >= 4:
                print(f"🔥 Calories: {numbers[0]}")
                print(f"💪 Protein:  {numbers[1]}g")
                print(f"🥑 Fat:      {numbers[2]}g")
                print(f"🌾 Carbs:    {numbers[3]}g")

                # Extract metadata (appears after first semicolon, before the next number)
                metadata_start = result_string.find(';') + 1
                # Find the next number; pattern (finds ,69; after the metadata)
                next_num_match = re.search(r',\d+;', result_string[metadata_start:])
                if next_num_match:
                    metadata_end = metadata_start + next_num_match.start()
                    metadata = result_string[metadata_start:metadata_end]
                    print(f"\n📈 Data Quality: {metadata}")
            else:
                print("📊 Raw Result:")
                print(result_string)
        else:
            print("📊 Raw Result:")
            print(result_string)

        print(f"\n🎯 Output Format: calories;metadata,protein;metadata,fat;metadata,carbs;metadata")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("\nℹ️  This is expected for initial testing - the agent needs full tool implementation.")
        
    print("\n" + "=" * 60)


def test_custom_ingredients():
    """Allow user to input custom ingredients"""
    
    print("\n🔧 CUSTOM INGREDIENT TEST")
    print("=" * 40)
    print("Enter ingredients one by one. Type 'done' when finished.")
    
    ingredients = []
    
    while True:
        print(f"\nIngredient #{len(ingredients) + 1}:")
        name = input("  Name (with description): ").strip()
        
        if name.lower() == 'done':
            break
            
        if not name:
            continue
            
        quantity = input("  Quantity: ").strip()
        unit = input("  Unit: ").strip()
        
        ingredients.append({
            "name": name,
            "quantity": quantity,
            "unit": unit
        })
        
        print(f"  ✅ Added: {quantity} {unit} - {name}")
    
    if ingredients:
        print(f"\n📋 Processing {len(ingredients)} custom ingredients...")
        
        try:
            result = calculate_recipe_macros_sync(ingredients)
            print("\n✅ Results:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
    else:
        print("\nNo ingredients entered.")


def main():
    """Main test function"""
    
    print("\n🧪 AGENT INFRASTRUCTURE TEST")
    print("=" * 60)
    
    # Test 1: Sample ingredients
    test_sample_ingredients()
    
    # Ask if user wants to test custom ingredients
    try:
        test_custom = input("\nTest with custom ingredients? (y/n): ").strip().lower()
        if test_custom in ['y', 'yes']:
            test_custom_ingredients()
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Test ended.")
    
    print("\n🎉 Test CLI complete!")


if __name__ == "__main__":
    main()