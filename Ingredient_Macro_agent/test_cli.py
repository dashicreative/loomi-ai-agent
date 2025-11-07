#!/usr/bin/env python3
"""
Test CLI for Macro Calculation Agent
Allows testing ingredient arrays and viewing macro calculation output.
"""

import json
from macro_agent import calculate_recipe_macros_sync

def test_sample_ingredients():
    """Test with the sample ingredients provided by user"""
    
    print("🥘 MACRO CALCULATION AGENT - TEST CLI")
    print("=" * 60)
    
    # Sample ingredient array (from user's example)
    sample_ingredients = [
        {
            "name": "1 inch knob of peeled fresh ginger (finely diced)",
            "quantity": "1",
            "unit": "count"
        },
        {
            "name": "3 garlic cloves (finely diced)",
            "quantity": "3",
            "unit": "count"
        },
        {
            "name": "1 small jalapeño pepper (seeded, and finely diced)",
            "quantity": "1",
            "unit": "count"
        },
        {
            "name": "½ large yellow onion (julienned)",
            "quantity": "0.5",
            "unit": "count"
        },
        {
            "name": "1 large red bell pepper (stemmed, seeded, and cut into ¼-inch thick strips)",
            "quantity": "1",
            "unit": "count"
        },
        {
            "name": "juice ½ lime (plus wedges for serving)",
            "quantity": "0.5",
            "unit": "count"
        },
        {
            "name": "handful cilantro leaves (roughly chopped, plus more for garnish)",
            "quantity": "1",
            "unit": "count"
        }
    ]
    
    print("📋 Input Ingredients:")
    print("-" * 40)
    for i, ingredient in enumerate(sample_ingredients, 1):
        name = ingredient['name'][:50] + "..." if len(ingredient['name']) > 50 else ingredient['name']
        print(f"{i:2}. {ingredient['quantity']} {ingredient['unit']} - {name}")
    
    print("\n🔄 Processing with Macro Agent...")
    print("-" * 40)
    
    try:
        # Calculate macros using the agent
        result = calculate_recipe_macros_sync(sample_ingredients)
        
        print("\n✅ CALCULATED MACROS:")
        print("-" * 40)
        
        if isinstance(result, list) and len(result) == 4:
            print(f"🔥 {result[0]}")
            print(f"💪 {result[1]}")  
            print(f"🥑 {result[2]}")
            print(f"🌾 {result[3]}")
        else:
            print("📊 Raw Result:")
            print(json.dumps(result, indent=2))
        
        print(f"\n🎯 Expected Output Format:")
        print('["X calories", "X g protein", "X g fat", "X g carbs"]')
        
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