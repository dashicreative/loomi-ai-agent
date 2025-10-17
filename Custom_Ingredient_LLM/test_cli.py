#!/usr/bin/env python3

import asyncio
import json
import sys
from Custom_Ingredient_LLM import process_ingredient

async def test_ingredient(name: str):
    """Test the ingredient processing function"""
    
    print(f"\n🔍 Processing: {name}")
    print("-" * 60)
    
    try:
        result = await process_ingredient(name)
        
        if not result.get('success', False):
            print(f"❌ NOT A FOOD ITEM")
            print(f"📝 Message: {result.get('message', 'Unknown error')}")
            print(f"🚫 Input: '{result['ingredient_name']}'")
        else:
            print(f"✅ Ingredient: {result['ingredient_name']}")
            print(f"📊 Nutrition (per 100{result['nutrition']['per_100']}):")
            print(f"   • Calories: {result['nutrition']['calories']}")
            print(f"   • Carbs: {result['nutrition']['carbs_g']}g")
            print(f"   • Protein: {result['nutrition']['protein_g']}g")
            print(f"   • Fat: {result['nutrition']['fat_g']}g")
            print(f"🏷️  Category: {result['category']}")
            print(f"🖼️  Category Image: {result['category_image_url']}")
            print(f"📸 Ingredient Image: {'Found' if result['spoonacular_image_hit'] else 'Not found'}")
            if result.get('image_url'):
                print(f"   URL: {result['image_url']}")
        
        print("-" * 60)
        return result
    except Exception as e:
        print(f"❌ Error: {e}")
        print("-" * 60)
        return None

async def interactive_mode():
    """Interactive mode for testing ingredients"""
    
    print("\n🧪 Custom Ingredient LLM - Interactive Test Mode")
    print("=" * 60)
    print("Type 'exit' or 'quit' to stop")
    print("Press Ctrl+C to exit anytime\n")
    
    while True:
        try:
            ingredient = input("\n🥘 Enter ingredient name: ").strip()
            
            if ingredient.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
                
            if not ingredient:
                print("❗ Please enter an ingredient name")
                continue
                
            await test_ingredient(ingredient)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

async def main():
    if len(sys.argv) > 1:
        # Non-interactive mode: test with command line argument
        ingredient = " ".join(sys.argv[1:])
        await test_ingredient(ingredient)
    else:
        # Interactive mode
        await interactive_mode()

if __name__ == "__main__":
    asyncio.run(main())