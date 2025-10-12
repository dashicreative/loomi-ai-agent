"""
URLClassificationTool Unit Tests
Tests URL classification with deterministic and LLM approaches.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict
import json
from datetime import datetime

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from url_classification_tool import URLClassificationTool


def print_result(title: str, result: Dict):
    """Pretty print classification results."""
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)
    print(json.dumps(result, indent=2, default=str))
    print("="*80 + "\n")


async def test_url_classification_tool():
    """Test URLClassificationTool with various URL types."""
    
    # Load OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("Some tests may use fallback classification only...")
    
    # Initialize tool
    tool = URLClassificationTool(openai_key=openai_key)
    
    print("\n" + "🏷️ TESTING URL CLASSIFICATION TOOL " + "🏷️")
    print("="*80)
    
    # Test 1: Obvious Recipe URLs (should be deterministic)
    print("\n📝 Test 1: Clear Recipe URLs (Deterministic)")
    
    recipe_urls = [
        {
            "url": "https://www.allrecipes.com/recipe/213742/cheesy-chicken-broccoli-casserole/",
            "title": "Cheesy Chicken Broccoli Casserole Recipe",
            "snippet": "This easy casserole combines chicken, broccoli, and cheese...",
            "source": "serpapi"
        },
        {
            "url": "https://www.simplyrecipes.com/recipes/classic_chocolate_chip_cookies/",
            "title": "Classic Chocolate Chip Cookies Recipe",
            "snippet": "The best chocolate chip cookie recipe with crispy edges...",
            "source": "serpapi"
        }
    ]
    
    try:
        result1 = await tool.classify_urls(recipe_urls)
        print_result("Test 1: Recipe URL Classification", {
            "total_processed": result1["total_processed"],
            "distribution": result1["type_distribution"],
            "processing_stats": result1["processing_stats"],
            "timing": result1["_timing"],
            "classified_urls": [
                {
                    "url": url["url"],
                    "type": url["type"],
                    "confidence": url["confidence"],
                    "method": url["classification_method"],
                    "signals": url["classification_signals"]
                }
                for url in result1["classified_urls"]
            ]
        })
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
    
    # Test 2: Obvious List URLs (should be deterministic)
    print("\n📝 Test 2: Clear List URLs (Deterministic)")
    
    list_urls = [
        {
            "url": "https://www.allrecipes.com/gallery/best-chocolate-desserts/",
            "title": "25 Best Chocolate Dessert Recipes",
            "snippet": "From brownies to cakes, these are our top chocolate desserts...",
            "source": "serpapi"
        },
        {
            "url": "https://food52.com/recipes/collection/thanksgiving-sides",
            "title": "Top 20 Thanksgiving Side Dish Ideas",
            "snippet": "The best Thanksgiving sides to complete your feast...",
            "source": "serpapi"
        }
    ]
    
    try:
        result2 = await tool.classify_urls(list_urls)
        print_result("Test 2: List URL Classification", {
            "total_processed": result2["total_processed"],
            "distribution": result2["type_distribution"],
            "processing_stats": result2["processing_stats"],
            "timing": result2["_timing"],
            "classified_urls": [
                {
                    "url": url["url"], 
                    "type": url["type"],
                    "confidence": url["confidence"],
                    "method": url["classification_method"],
                    "signals": url["classification_signals"]
                }
                for url in result2["classified_urls"]
            ]
        })
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
    
    # Test 3: Mixed URLs (combination)
    print("\n📝 Test 3: Mixed URL Types")
    
    mixed_urls = [
        {
            "url": "https://www.bonappetit.com/recipe/classic-beef-stew",
            "title": "Classic Beef Stew",
            "snippet": "This hearty beef stew recipe...",
            "source": "serpapi"
        },
        {
            "url": "https://www.eatingwell.com/recipes/collections/healthy-dinner-ideas/",
            "title": "50 Healthy Dinner Ideas for Busy Weeknights",
            "snippet": "Quick and healthy dinner recipes for the family...",
            "source": "serpapi"
        },
        {
            "url": "https://www.foodandwine.com/lifestyle/kitchen/best-kitchen-tools",
            "title": "Best Kitchen Tools for Home Cooks",
            "snippet": "Essential kitchen equipment every cook needs...",
            "source": "serpapi"
        }
    ]
    
    try:
        result3 = await tool.classify_urls(mixed_urls)
        print_result("Test 3: Mixed URL Classification", {
            "total_processed": result3["total_processed"],
            "distribution": result3["type_distribution"],
            "processing_stats": result3["processing_stats"],
            "timing": result3["_timing"],
            "all_classifications": [
                {
                    "url": url["url"][:50] + "...",
                    "title": url["title"][:40] + "...",
                    "type": url["type"],
                    "confidence": url["confidence"],
                    "method": url["classification_method"]
                }
                for url in result3["classified_urls"]
            ]
        })
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
    
    # Test 4: Edge Cases and Error Handling
    print("\n📝 Test 4: Edge Cases & Error Handling")
    
    edge_case_urls = [
        {
            "url": "https://nonexistent-recipe-site-12345.com/recipe/fake",
            "title": "Fake Recipe That Won't Load",
            "snippet": "This URL should fail to fetch...",
            "source": "serpapi"
        },
        {
            "url": "https://www.allrecipes.com/",  # Homepage - ambiguous
            "title": "AllRecipes - Recipe Ideas & How-To Cooking Videos",
            "snippet": "Find and share everyday cooking inspiration...",
            "source": "serpapi"
        }
    ]
    
    try:
        result4 = await tool.classify_urls(edge_case_urls)
        print_result("Test 4: Edge Cases", {
            "total_processed": result4["total_processed"],
            "distribution": result4["type_distribution"],
            "processing_stats": result4["processing_stats"],
            "timing": result4["_timing"],
            "error_handling": [
                {
                    "url": url["url"][:50] + "...",
                    "type": url["type"],
                    "confidence": url["confidence"],
                    "method": url["classification_method"],
                    "signals": url["classification_signals"]
                }
                for url in result4["classified_urls"]
            ]
        })
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
    
    # Test 5: Performance with Larger Batch
    print("\n📝 Test 5: Performance Test (Larger Batch)")
    
    # Create mock batch of 15 URLs for performance testing
    performance_urls = []
    base_urls = [
        ("https://www.allrecipes.com/recipe/", "Recipe"),
        ("https://www.simplyrecipes.com/recipes/", "Simple Recipe"),
        ("https://food52.com/recipes/", "Food52 Recipe"),
        ("https://www.allrecipes.com/recipes/", "Recipe Collection"),
        ("https://www.bonappetit.com/gallery/", "Recipe Gallery")
    ]
    
    for i in range(15):
        base_url, base_title = base_urls[i % len(base_urls)]
        performance_urls.append({
            "url": f"{base_url}{i+1}/test-recipe-{i+1}",
            "title": f"{base_title} {i+1}",
            "snippet": f"Test recipe snippet {i+1}...",
            "source": "serpapi"
        })
    
    try:
        result5 = await tool.classify_urls(performance_urls)
        print_result("Test 5: Performance Test", {
            "total_processed": result5["total_processed"],
            "distribution": result5["type_distribution"],
            "processing_stats": result5["processing_stats"],
            "timing": result5["_timing"],
            "performance_metrics": {
                "urls_per_second": round(len(performance_urls) / result5["_timing"]["elapsed_since_query"], 1),
                "avg_confidence": round(
                    sum(url.get("confidence", 0) for url in result5["classified_urls"]) / len(result5["classified_urls"]), 2
                ) if result5["classified_urls"] else 0
            }
        })
    except Exception as e:
        print(f"❌ Test 5 failed: {e}")


async def main():
    """Main test runner for URLClassificationTool."""
    print("\n" + "="*80)
    print("🚀 URL CLASSIFICATION TOOL - UNIT TESTS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check configuration
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    if not has_openai:
        print("⚠️ WARNING: No OPENAI_API_KEY found")
        print("Tests will use deterministic fallback classification only...")
    else:
        print("✅ Using OpenAI for LLM classification")
    
    # Run tests
    await test_url_classification_tool()
    
    print("\n✅ URLClassificationTool tests completed!")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    asyncio.run(main())