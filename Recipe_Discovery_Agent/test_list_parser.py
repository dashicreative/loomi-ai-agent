#!/usr/bin/env python3
"""
Test file for FireCrawl-based list extraction.

Tests the new strategic FireCrawl extraction method on the problematic Joy to the Food URL.
URL: https://joytothefood.com/breakfast-recipes-with-over-30g-of-protein-without-protein-powder/
"""

import asyncio
import os
from Tools.Tools import extract_list_with_firecrawl

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
        # Test FireCrawl extraction with different limits
        for max_urls in [3, 5, 8]:
            print(f"\n🎯 Testing FireCrawl extraction with max_urls = {max_urls}")
            print("-" * 60)
            
            recipes = await extract_list_with_firecrawl(TEST_URL, firecrawl_key, max_urls)
            
            print(f"📊 Results: Found {len(recipes)} recipe URLs")
            
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
        print("🎯 SPECIFIC TEST CASES")
        print("Expected to find:")
        print("  ✓ https://joytothefood.com/high-protein-breakfast-quesadilla/")
        print("  ✓ https://joytothefood.com/cottage-cheese-egg-bites/")
        print("Should NOT find:")
        print("  ✗ https://joytothefood.com/recipes/")
        
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