"""
WebSearchTool Unit Tests
Tests the WebSearchTool with various configurations and scenarios.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, Any
import json
from datetime import datetime

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from web_search_tool import WebSearchTool


def print_result(title: str, result: Any):
    """Pretty print tool results."""
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)
    
    if isinstance(result, dict):
        # Pretty print JSON
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result)
    print("="*80 + "\n")


async def test_web_search_tool():
    """Test the WebSearchTool with various configurations."""
    
    # Load API keys from environment
    serpapi_key = os.getenv("SERPAPI_KEY")
    google_key = os.getenv("GOOGLE_SEARCH_KEY")
    google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    # Initialize tool
    tool = WebSearchTool(
        serpapi_key=serpapi_key,
        google_key=google_key,
        google_cx=google_cx
    )
    
    print("\n" + "🔍 TESTING WEB SEARCH TOOL " + "🔍")
    print("="*80)
    
    # Test 1: Basic search with priority strategy
    print("\n📝 Test 1: Basic Priority Search")
    print("Query: 'chocolate chip cookies'")
    print("Strategy: 'priority_only'")
    print("Count: 10")
    
    try:
        result1 = await tool.search(
            query="chocolate chip cookies",
            result_count=10,
            search_strategy="priority_only"
        )
        print_result("Test 1: Priority Search Results", {
            "total_found": result1["total_found"],
            "distribution": result1["source_distribution"],
            "timing": result1["_timing"],
            "first_3_results": result1["urls"][:3] if result1["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
    
    # Test 2: Mixed strategy with more results
    print("\n📝 Test 2: Mixed Strategy Search")
    print("Query: 'vegan pasta'")
    print("Strategy: 'mixed'")
    print("Count: 20")
    
    try:
        result2 = await tool.search(
            query="vegan pasta",
            result_count=20,
            search_strategy="mixed"
        )
        print_result("Test 2: Mixed Search Results", {
            "total_found": result2["total_found"],
            "distribution": result2["source_distribution"],
            "query_used": result2["query_used"],
            "timing": result2["_timing"],
            "first_3_results": result2["urls"][:3] if result2["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
    
    # Test 3: Broad search with exclusions
    print("\n📝 Test 3: Broad Search with Exclusions")
    print("Query: 'cheesecake'")
    print("Strategy: 'broad'")
    print("Excluding: previous URLs")
    
    # Simulate some URLs to exclude (from previous searches)
    exclude_urls = {
        "https://www.allrecipes.com/recipe/8350/chantal-s-new-york-cheesecake/",
        "https://www.simplyrecipes.com/recipes/perfect_cheesecake/"
    }
    
    try:
        result3 = await tool.search(
            query="cheesecake",
            result_count=15,
            search_strategy="broad",
            exclude_urls=exclude_urls,
            additional_blocked_sites={"tasty.co"}  # Block tasty.co additionally
        )
        print_result("Test 3: Broad Search with Exclusions", {
            "total_found": result3["total_found"],
            "distribution": result3["source_distribution"],
            "excluded_count": len(exclude_urls),
            "timing": result3["_timing"],
            "first_3_results": result3["urls"][:3] if result3["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
    
    # Test 4: Time-restricted search
    print("\n📝 Test 4: Recent Recipes Only")
    print("Query: 'thanksgiving turkey'")
    print("Time range: 'w' (past week)")
    
    try:
        result4 = await tool.search(
            query="thanksgiving turkey",
            result_count=10,
            search_strategy="mixed",
            time_range="w"  # Past week only
        )
        print_result("Test 4: Time-Restricted Search", {
            "total_found": result4["total_found"],
            "query_used": result4["query_used"],
            "timing": result4["_timing"],
            "first_3_results": result4["urls"][:3] if result4["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
    
    # Test 5: Regional search
    print("\n📝 Test 5: Regional British Search")
    print("Query: 'fish and chips'")
    print("Region: 'uk'")
    
    try:
        result5 = await tool.search(
            query="fish and chips",
            result_count=10,
            search_strategy="mixed",
            region="uk",
            language="en"
        )
        print_result("Test 5: Regional Search", {
            "total_found": result5["total_found"],
            "distribution": result5["source_distribution"],
            "timing": result5["_timing"],
            "first_3_results": result5["urls"][:3] if result5["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 5 failed: {e}")
    
    # Test 6: Testing timing recommendations
    print("\n📝 Test 6: Simulating Long Search")
    print("Simulating 65 seconds elapsed...")
    
    # Manually set elapsed time to test timing logic
    tool.query_start_time = datetime.now().timestamp() - 65  # 65 seconds ago
    
    try:
        result6 = await tool.search(
            query="complex dietary restricted meal",
            result_count=5,
            search_strategy="mixed"
        )
        print_result("Test 6: Timing Recommendations", {
            "timing": result6["_timing"],
            "should_show": "time_status should be 'exceeded' and action 'ask_user'",
            "first_3_results": result6["urls"][:3] if result6["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 6 failed: {e}")

    # Test 7: Blocked Sites Verification
    print("\n📝 Test 7: Blocked Sites Verification")
    print("Query: 'chocolate cake recipe site:facebook.com OR site:youtube.com'")
    print("Should return 0 results due to blocking")
    
    try:
        result7 = await tool.search(
            query="chocolate cake recipe site:facebook.com OR site:youtube.com",
            result_count=10,
            search_strategy="broad"  # Use broad to test filtering
        )
        print_result("Test 7: Blocked Sites Test", {
            "total_found": result7["total_found"],
            "distribution": result7["source_distribution"],
            "timing": result7["_timing"],
            "message": "Should be 0 results - all blocked",
            "first_3_results": result7["urls"][:3] if result7["urls"] else []
        })
        
        # Verify no blocked domains leaked through
        for url_obj in result7["urls"]:
            url = url_obj.get("url", "").lower()
            if any(blocked in url for blocked in ['facebook', 'youtube', 'tiktok', 'pinterest']):
                print(f"🚨 CRITICAL: Blocked site leaked through: {url}")
    except Exception as e:
        print(f"❌ Test 7 failed: {e}")

    # Test 8: Edge case - no results
    print("\n📝 Test 8: No Results Edge Case")
    print("Query: 'qwertyuiop asdfghjkl'")
    
    try:
        result8 = await tool.search(
            query="qwertyuiop asdfghjkl",
            result_count=10,
            search_strategy="mixed"
        )
        print_result("Test 8: No Results", {
            "total_found": result8["total_found"],
            "distribution": result8["source_distribution"],
            "timing": result8["_timing"],
            "first_3_results": result8["urls"][:3] if result8["urls"] else []
        })
    except Exception as e:
        print(f"❌ Test 8 failed: {e}")


async def main():
    """Main test runner for WebSearchTool."""
    print("\n" + "="*80)
    print("🚀 WEB SEARCH TOOL - UNIT TESTS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check configuration
    has_serpapi = bool(os.getenv("SERPAPI_KEY"))
    has_google = bool(os.getenv("GOOGLE_SEARCH_KEY") and os.getenv("GOOGLE_SEARCH_ENGINE_ID"))
    
    if not (has_serpapi or has_google):
        print("⚠️ WARNING: No search provider configured!")
        print("Please set either:")
        print("  - SERPAPI_KEY")
        print("  - GOOGLE_SEARCH_KEY and GOOGLE_SEARCH_ENGINE_ID")
        print("\nSome tests may fail without API keys...")
    else:
        provider = "SerpAPI" if has_serpapi else "Google Custom Search"
        print(f"✅ Using {provider} for testing")
    
    # Run tests
    await test_web_search_tool()
    
    print("\n✅ WebSearchTool tests completed!")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    asyncio.run(main())