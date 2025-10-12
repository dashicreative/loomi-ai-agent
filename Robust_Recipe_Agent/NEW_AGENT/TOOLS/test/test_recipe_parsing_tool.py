"""
RecipeParsingTool Unit Tests
Tests individual recipe URL parsing with various scenarios.
"""

import asyncio
import os
import sys
from pathlib import Path
import json
from datetime import datetime

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from recipe_parsing_tool import RecipeParsingTool


def print_result(title: str, result):
    """Pretty print parsing results."""
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)
    print(json.dumps(result, indent=2, default=str))
    print("="*80 + "\n")


async def test_recipe_parsing_tool():
    """Test RecipeParsingTool with various recipe URL types."""
    
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("Recipe extraction may fail without API key...")
        return
    
    tool = RecipeParsingTool(openai_key=openai_key)
    
    print("\n" + "🍳 TESTING RECIPE PARSING TOOL " + "🍳")
    print("="*80)
    
    # Test 1: Single Recipe URL  
    print("\n📝 Test 1: Single Recipe Parsing")
    
    single_recipe = [
        {
            "url": "https://www.allrecipes.com/recipe/213742/cheesy-chicken-broccoli-casserole/",
            "title": "Cheesy Chicken Broccoli Casserole Recipe",
            "snippet": "This easy casserole combines chicken, broccoli, and cheese...",
            "source": "serpapi",
            "type": "recipe",
            "confidence": 0.9
        }
    ]
    
    try:
        result1 = await tool.parse_recipes(single_recipe, parsing_depth="standard")
        print_result("Test 1: Single Recipe Parse", {
            "total_attempted": result1["processing_stats"]["total_attempted"],
            "successful_parses": result1["processing_stats"]["successful_parses"],
            "parse_quality": result1["parse_quality"],
            "timing": result1["_timing"],
            "recipe_preview": {
                "title": result1["parsed_recipes"][0].get("title", "Not found") if result1["parsed_recipes"] else "No recipes",
                "ingredients_count": len(result1["parsed_recipes"][0].get("ingredients", [])) if result1["parsed_recipes"] else 0,
                "has_instructions": bool(result1["parsed_recipes"][0].get("instructions")) if result1["parsed_recipes"] else False
            }
        })
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
    
    # Test 2: Multiple Recipe URLs (Parallel Processing)
    print("\n📝 Test 2: Multiple Recipe Parsing (Parallel)")
    
    multiple_recipes = [
        {
            "url": "https://www.simplyrecipes.com/recipes/classic_chocolate_chip_cookies/",
            "title": "Classic Chocolate Chip Cookies",
            "snippet": "The best chocolate chip cookie recipe...",
            "source": "serpapi",
            "type": "recipe",
            "confidence": 0.9
        },
        {
            "url": "https://www.allrecipes.com/recipe/10909/annas-chocolate-chip-cookies/",
            "title": "Anna's Chocolate Chip Cookies Recipe", 
            "snippet": "These cookies are crispy on the outside...",
            "source": "serpapi",
            "type": "recipe",
            "confidence": 0.9
        },
        {
            "url": "https://food52.com/recipes/25945-classic-snickerdoodles",
            "title": "Classic Snickerdoodles Recipe",
            "snippet": "Soft and chewy cinnamon sugar cookies...",
            "source": "serpapi", 
            "type": "recipe",
            "confidence": 0.85
        }
    ]
    
    try:
        result2 = await tool.parse_recipes(multiple_recipes, parsing_depth="standard")
        print_result("Test 2: Multiple Recipe Parse", {
            "total_attempted": result2["processing_stats"]["total_attempted"],
            "successful_parses": result2["processing_stats"]["successful_parses"],
            "failed_parses": result2["processing_stats"]["failed_parses"],
            "success_rate": result2["processing_stats"]["success_rate"],
            "parse_quality": result2["parse_quality"],
            "timing": result2["_timing"],
            "recipes_overview": [
                {
                    "title": recipe.get("title", "Unknown")[:40],
                    "source_url": recipe.get("source_url", "")[:50],
                    "ingredients": len(recipe.get("ingredients", [])),
                    "has_image": bool(recipe.get("image_url"))
                }
                for recipe in result2["parsed_recipes"]
            ]
        })
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
    
    # Test 3: Mixed URL Types (should filter automatically) 
    print("\n📝 Test 3: Mixed URL Types (Auto-Filtering)")
    
    mixed_urls = [
        {
            "url": "https://www.allrecipes.com/recipe/16354/easy-meatloaf/",
            "title": "Easy Meatloaf Recipe",
            "type": "recipe",
            "confidence": 0.9
        },
        {
            "url": "https://www.allrecipes.com/recipes/meat-and-poultry/",
            "title": "Best Meat and Poultry Recipes",
            "type": "list",  # Should be skipped by RecipeParsingTool
            "confidence": 0.8
        },
        {
            "url": "https://www.bonappetit.com/recipe/classic-beef-stew",
            "title": "Classic Beef Stew",
            "type": "recipe", 
            "confidence": 0.85
        }
    ]
    
    try:
        result3 = await tool.parse_recipes(mixed_urls, parsing_depth="quick", timeout_seconds=10)
        print_result("Test 3: Mixed URLs (Auto-Filter)", {
            "total_attempted": result3["processing_stats"]["total_attempted"],
            "successful_parses": result3["processing_stats"]["successful_parses"],
            "skipped_count": len(result3.get("skipped_urls", [])),
            "timing": result3["_timing"],
            "filtering_worked": "Should only parse URLs with type='recipe'"
        })
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
    
    # Test 4: Error Handling (Bad URLs)
    print("\n📝 Test 4: Error Handling & Timeouts")
    
    error_test_urls = [
        {
            "url": "https://httpstat.us/403",  # Will return 403 Forbidden
            "title": "Test 403 Error",
            "type": "recipe",
            "confidence": 0.9
        },
        {
            "url": "https://httpstat.us/500",  # Will return 500 error
            "title": "Test 500 Error", 
            "type": "recipe",
            "confidence": 0.9
        },
        {
            "url": "https://www.allrecipes.com/recipe/231559/simple-macaroni-and-cheese/",
            "title": "Simple Macaroni and Cheese",  # Should work
            "type": "recipe",
            "confidence": 0.9
        }
    ]
    
    try:
        result4 = await tool.parse_recipes(error_test_urls, timeout_seconds=5)  # Short timeout
        print_result("Test 4: Error Handling", {
            "total_attempted": result4["processing_stats"]["total_attempted"],
            "successful_parses": result4["processing_stats"]["successful_parses"],
            "failed_parses": result4["processing_stats"]["failed_parses"],
            "timeouts": result4["processing_stats"]["timeouts"],
            "timing": result4["_timing"],
            "error_examples": [
                {
                    "url": fail["url_object"]["url"][:40] + "...",
                    "error": fail["error"][:60] + "...",
                    "failure_point": fail["failure_point"]
                }
                for fail in result4["failed_urls"][:2]  # First 2 errors
            ]
        })
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")


async def main():
    """Main test runner for RecipeParsingTool."""
    print("\n" + "="*80)
    print("🚀 RECIPE PARSING TOOL - UNIT TESTS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check configuration
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    if not has_openai:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("Recipe parsing tests will likely fail...")
    else:
        print("✅ Using OpenAI for recipe extraction")
    
    # Run tests
    await test_recipe_parsing_tool()
    
    print("\n✅ RecipeParsingTool tests completed!")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    asyncio.run(main())