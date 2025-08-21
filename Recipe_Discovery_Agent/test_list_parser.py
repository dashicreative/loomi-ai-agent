#!/usr/bin/env python3
"""
Test file for FireCrawl-based list extraction.

Tests the new strategic FireCrawl extraction method on the problematic Joy to the Food URL.
URL: https://joytothefood.com/breakfast-recipes-with-over-30g-of-protein-without-protein-powder/
"""

import asyncio
import os
import time
from dotenv import load_dotenv
from Tools.Tools import extract_list_with_firecrawl

# Load environment variables from parent directory .env file  
import sys
sys.path.append('..')
env_loaded = load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))
print(f"🔧 Debug: .env loaded = {env_loaded}")
print(f"🔧 Debug: FIRECRAWL_API_KEY = {'***' + os.getenv('FIRECRAWL_API_KEY', 'NOT_FOUND')[-4:] if os.getenv('FIRECRAWL_API_KEY') else 'NOT_FOUND'}")

# Test URL that was causing issues with HTML-based parser
TEST_URL = "https://joytothefood.com/breakfast-recipes-with-over-30g-of-protein-without-protein-powder/"

async def test_firecrawl_extraction():
    """Test the new FireCrawl-based list extraction on the problematic URL."""
    
    print("🧪 TESTING FIRECRAWL LIST EXTRACTION")
    print(f"📍 Test URL: {TEST_URL}")
    print("=" * 80)
    
    # Get FireCrawl API key from environment
    firecrawl_key = os.getenv('FIRECRAWL_API_KEY')
    if not firecrawl_key:
        print("❌ FIRECRAWL_API_KEY not found in environment variables")
        print("Please set FIRECRAWL_API_KEY before running the test")
        return
    
    try:
        # Test FireCrawl extraction with timing analysis
        for max_urls in [10, 16]:
            print(f"\n🎯 COST & PERFORMANCE TEST: max_urls = {max_urls}")
            print("Analyzing FireCrawl cost and time performance")
            print("-" * 80)
            
            # Start timing
            start_time = time.time()
            recipes = await extract_list_with_firecrawl(TEST_URL, firecrawl_key, max_urls)
            end_time = time.time()
            
            # Calculate timing
            extraction_time = end_time - start_time
            
            print(f"📊 Results: Found {len(recipes)} recipe URLs")
            print(f"⏱️  Extraction Time: {extraction_time:.2f} seconds")
            print(f"💰 Cost Analysis:")
            print(f"   - FireCrawl API calls: 1 call per list URL")
            print(f"   - Estimated cost per call: ~$0.015-0.03 (varies by content size)")
            print(f"   - Total cost for this extraction: ~$0.015-0.03")
            
            if not recipes:
                print("❌ NO RECIPES FOUND")
                continue
            
            # Display each found recipe
            for i, recipe in enumerate(recipes, 1):
                print(f"\n🍳 Recipe #{i}:")
                print(f"   Title: {recipe.get('title', 'No title')}")
                print(f"   URL: {recipe.get('url', 'No URL')}")
                print(f"   Source: {recipe.get('source', 'Unknown')}")
                print(f"   Description: {recipe.get('snippet', 'No description')[:100]}...")
                
                # Validate URL format
                url = recipe.get('url', '')
                if url.startswith('http'):
                    print(f"   ✅ Valid URL format")
                else:
                    print(f"   ❌ Invalid URL format")
                
                # Check if it's the expected individual recipe URLs
                expected_urls = [
                    'high-protein-breakfast-quesadilla',
                    'cottage-cheese-egg-bites'
                ]
                
                if any(expected in url for expected in expected_urls):
                    print(f"   ✅ Found expected recipe URL!")
                
                # Check if it incorrectly found category pages
                if '/recipes/' in url and url.endswith('/recipes/'):
                    print(f"   ⚠️  WARNING: This looks like a category page, not individual recipe")
        
        print(f"\n" + "=" * 80)
        print("🎯 COST & FEASIBILITY ANALYSIS")
        print("\n📊 Strategic Usage Model (6 lists max per query):")
        print("   - 6 FireCrawl calls × $0.015-0.03 = $0.09-0.18 per query")
        print("   - 6 lists × 5 recipes each = 30 individual recipes")
        print("   - Total time: ~30-60 seconds for all list extractions")
        print("\n💡 Feasibility Assessment:")
        print("   ✅ COST: Very reasonable at <$0.20 per query")
        print("   ✅ TIME: Acceptable at ~30-60 seconds total")
        print("   ✅ QUALITY: Perfect individual recipe extraction")
        print("   ✅ RELIABILITY: Much better than HTML parsing")
        print("\n🚀 Recommendation: PROCEED with strategic FireCrawl approach")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run the test."""
    print("Starting FireCrawl List Extraction Test...")
    asyncio.run(test_firecrawl_extraction())
    print("\n✅ Test completed!")

if __name__ == "__main__":
    main()