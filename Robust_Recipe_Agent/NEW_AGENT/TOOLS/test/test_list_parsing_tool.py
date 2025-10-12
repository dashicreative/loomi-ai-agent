"""
ListParsingTool Unit Tests  
Tests list page processing and recipe extraction.
"""

import asyncio
import os
import sys
from pathlib import Path
import json
from datetime import datetime

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from list_parsing_tool import ListParsingTool


def print_result(title: str, result):
    """Pretty print parsing results."""
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)
    print(json.dumps(result, indent=2, default=str))
    print("="*80 + "\n")


async def test_list_parsing_tool():
    """Test ListParsingTool with various list page types."""
    
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("List parsing tests will likely fail...")
        return
    
    tool = ListParsingTool(openai_key=openai_key)
    
    print("\n" + "📋 TESTING LIST PARSING TOOL " + "📋")
    print("="*80)
    
    # Test 1: Single List URL
    print("\n📝 Test 1: Single List Page Processing")
    
    single_list = [
        {
            "url": "https://www.allrecipes.com/gallery/best-chocolate-desserts/",
            "title": "25 Best Chocolate Dessert Recipes",
            "snippet": "From brownies to cakes, these are our top chocolate desserts...",
            "source": "serpapi",
            "type": "list",
            "confidence": 0.85
        }
    ]
    
    try:
        result1 = await tool.extract_recipe_urls_from_lists(single_list, max_recipes_per_list=5)
        print_result("Test 1: Single List URL Extraction", {
            "lists_attempted": result1["processing_stats"]["lists_attempted"],
            "lists_successful": result1["processing_stats"]["lists_successful"],
            "recipe_urls_extracted": result1["processing_stats"]["recipe_urls_extracted"],
            "avg_per_list": result1["processing_stats"]["avg_urls_per_list"],
            "timing": result1["_timing"],
            "extracted_urls_preview": [
                {
                    "title": url_obj.get("title", "Unknown")[:40],
                    "url": url_obj.get("url", "")[:50] + "...",
                    "type": url_obj.get("type", "unknown"),
                    "extracted_from": url_obj.get("extracted_from_list", "")[:30] + "..."
                }
                for url_obj in result1["extracted_recipe_urls"][:3]  # First 3 URLs
            ]
        })
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
    
    # Test 2: Multiple List URLs
    print("\n📝 Test 2: Multiple List Pages")
    
    multiple_lists = [
        {
            "url": "https://food52.com/recipes/collection/thanksgiving-sides",
            "title": "Top 20 Thanksgiving Side Dish Ideas",
            "snippet": "The best Thanksgiving sides to complete your feast...",
            "source": "serpapi",
            "type": "list",
            "confidence": 0.85
        },
        {
            "url": "https://www.eatingwell.com/gallery/healthy-breakfast-recipes/",
            "title": "30 Healthy Breakfast Recipe Ideas",
            "snippet": "Start your day right with these nutritious breakfast recipes...",
            "source": "serpapi",
            "type": "list", 
            "confidence": 0.8
        }
    ]
    
    try:
        result2 = await tool.extract_recipe_urls_from_lists(multiple_lists, max_recipes_per_list=3)
        print_result("Test 2: Multiple List Processing", {
            "lists_attempted": result2["processing_stats"]["lists_attempted"],
            "lists_successful": result2["processing_stats"]["lists_successful"], 
            "total_urls": result2["processing_stats"]["recipe_urls_extracted"],
            "avg_per_list": result2["processing_stats"]["avg_urls_per_list"],
            "timing": result2["_timing"],
            "breakdown_by_list": [
                f"List {i+1}: {url['title'][:30]}... → extracted URLs"
                for i, url in enumerate(multiple_lists)
            ] if result2["extracted_recipe_urls"] else ["No URLs extracted"]
        })
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
    
    # Test 3: Mixed URL Types (Should Filter Automatically)
    print("\n📝 Test 3: Mixed URLs (Auto-Filtering)")
    
    mixed_urls = [
        {
            "url": "https://www.allrecipes.com/gallery/easy-dinner-ideas/",
            "title": "50 Easy Dinner Ideas", 
            "type": "list",  # Should be processed
            "confidence": 0.9
        },
        {
            "url": "https://www.bonappetit.com/recipe/classic-beef-stew",
            "title": "Classic Beef Stew",
            "type": "recipe",  # Should be skipped by ListParsingTool
            "confidence": 0.9
        },
        {
            "url": "https://food52.com/blog/cooking-tips",
            "title": "Best Cooking Tips",
            "type": "other",  # Should be skipped
            "confidence": 0.6
        }
    ]
    
    try:
        result3 = await tool.extract_recipe_urls_from_lists(mixed_urls, max_recipes_per_list=3)
        print_result("Test 3: Mixed URLs (Should Filter)", {
            "lists_attempted": result3["processing_stats"]["lists_attempted"],
            "skipped_count": len(result3.get("skipped_urls", [])),
            "recipe_urls_extracted": result3["processing_stats"]["recipe_urls_extracted"],
            "timing": result3["_timing"],
            "filtering_note": "Should only process URLs with type='list'"
        })
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
    
    # Test 4: Error Handling (Failed List URLs)
    print("\n📝 Test 4: List Processing Error Handling")
    
    error_test_lists = [
        {
            "url": "https://httpstat.us/404",  # Will return 404
            "title": "Non-existent List Page",
            "type": "list",
            "confidence": 0.8
        },
        {
            "url": "https://www.allrecipes.com/gallery/easy-appetizers/",
            "title": "Easy Appetizer Ideas",  # Should work
            "type": "list", 
            "confidence": 0.85
        }
    ]
    
    try:
        result4 = await tool.extract_recipe_urls_from_lists(error_test_lists, max_recipes_per_list=2)
        print_result("Test 4: Error Handling", {
            "lists_attempted": result4["processing_stats"]["lists_attempted"],
            "lists_successful": result4["processing_stats"]["lists_successful"],
            "failed_lists": len(result4["failed_lists"]),
            "recipe_urls_extracted": result4["processing_stats"]["recipe_urls_extracted"],
            "timing": result4["_timing"],
            "error_examples": [
                {
                    "url": fail["url_object"]["url"][:40] + "...",
                    "error": fail["error"][:50] + "...",
                    "failure_point": fail["failure_point"]
                }
                for fail in result4["failed_lists"][:2]
            ] if result4["failed_lists"] else ["No errors"]
        })
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
    
    # Test 5: Performance with Timeout Control
    print("\n📝 Test 5: Timeout & Performance Testing")
    
    timeout_test_lists = [
        {
            "url": "https://www.eatingwell.com/recipes/collections/",
            "title": "Recipe Collections", 
            "type": "list",
            "confidence": 0.8
        }
    ]
    
    try:
        # Test with short timeout
        result5 = await tool.extract_recipe_urls_from_lists(
            timeout_test_lists, 
            max_recipes_per_list=2,
            list_fetch_timeout=10
        )
        print_result("Test 5: Performance & Timeouts", {
            "processing_stats": result5["processing_stats"],
            "timing": result5["_timing"],
            "timeout_settings": {
                "list_fetch_timeout": 10
            }
        })
    except Exception as e:
        print(f"❌ Test 5 failed: {e}")


async def main():
    """Main test runner for ListParsingTool."""
    print("\n" + "="*80)
    print("🚀 LIST PARSING TOOL - UNIT TESTS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check configuration
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    if not has_openai:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("List parsing tests will fail without API key...")
    else:
        print("✅ Using OpenAI for list extraction")
    
    # Run tests
    await test_list_parsing_tool()
    
    print("\n✅ ListParsingTool tests completed!")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    asyncio.run(main())