"""
Test file for HTML Cache Manager
Tests batch fetching, caching, and domain-specific rate limiting
"""
import asyncio
from Tools.html_cache_manager import HTMLCacheManager
import time

async def test_html_cache():
    """Test HTML cache manager functionality"""
    
    print("🧪 Testing HTML Cache Manager\n")
    
    # Initialize cache manager
    cache = HTMLCacheManager()
    
    # Test URLs from different domains
    test_urls = [
        "https://www.allrecipes.com/recipe/23600/worlds-best-lasagna/",
        "https://www.foodnetwork.com/recipes/bobby-flay/perfectly-grilled-steak-recipe-1973350",
        "https://www.simplyrecipes.com/recipes/homemade_pizza/",
        "https://www.allrecipes.com/recipe/244195/maple-salmon/",
        "https://www.foodnetwork.com/recipes/alton-brown/baked-macaroni-and-cheese-recipe-1939524",
        "https://www.eatingwell.com/recipe/251927/spaghetti-squash-lasagna-with-broccolini/",
        "https://joytothefood.com/breakfast-recipes-with-over-30g-of-protein-without-protein-powder/",
        "https://www.delish.com/cooking/recipe-ideas/a25237036/baked-salmon-recipe/"
    ]
    
    print(f"📝 Testing with {len(test_urls)} URLs from multiple domains\n")
    
    # Test 1: Initial batch fetch
    print("Test 1: Batch fetching URLs...")
    start_time = time.time()
    
    results = await cache.batch_fetch(test_urls)
    
    fetch_time = time.time() - start_time
    print(f"✅ Fetched {len(results)} URLs in {fetch_time:.2f} seconds")
    
    # Check results
    successful = sum(1 for html in results.values() if html is not None)
    failed = sum(1 for html in results.values() if html is None)
    
    print(f"   - Successful: {successful}")
    print(f"   - Failed: {failed}")
    
    # Test 2: Cache hit performance
    print("\nTest 2: Testing cache hits...")
    start_time = time.time()
    
    # Fetch same URLs again - should be from cache
    results2 = await cache.batch_fetch(test_urls)
    
    cache_time = time.time() - start_time
    print(f"✅ Cache retrieval took {cache_time:.2f} seconds")
    
    # Verify cache is working
    if cache_time < fetch_time / 10:  # Cache should be at least 10x faster
        print("   - Cache is working efficiently!")
    else:
        print("   - Warning: Cache may not be working as expected")
    
    # Test 3: Mixed cache hits and new URLs
    print("\nTest 3: Testing mixed cache hits and new fetches...")
    mixed_urls = test_urls[:3] + [
        "https://www.food.com/recipe/easy-meatloaf-5566",
        "https://www.seriouseats.com/recipes/2011/12/serious-eats-halal-cart-style-chicken-and-rice-white-sauce-recipe.html"
    ]
    
    start_time = time.time()
    results3 = await cache.batch_fetch(mixed_urls)
    mixed_time = time.time() - start_time
    
    print(f"✅ Mixed fetch took {mixed_time:.2f} seconds")
    
    # Test 4: Get statistics
    print("\nTest 4: Cache statistics...")
    stats = cache.get_stats()
    print(f"📊 Cache Statistics:")
    print(f"   - Total attempted: {stats['total_attempted']}")
    print(f"   - Successful: {stats['successful']}")
    print(f"   - Failed: {stats['failed']}")
    print(f"   - Cache hits: {stats['cache_hits']}")
    
    if stats['total_attempted'] > 0:
        success_rate = (stats['successful'] / stats['total_attempted']) * 100
        print(f"   - Success rate: {success_rate:.1f}%")
    
    # Test 5: Individual cache operations
    print("\nTest 5: Testing individual cache operations...")
    
    # Test has_html
    test_url = test_urls[0]
    if cache.has_html(test_url):
        print(f"✅ has_html() works - URL is cached")
    
    # Test get_html
    html = cache.get_html(test_url)
    if html and len(html) > 0:
        print(f"✅ get_html() works - Retrieved {len(html)} characters")
    
    # Test clear_cache
    cache.clear_cache()
    if not cache.has_html(test_url):
        print(f"✅ clear_cache() works - Cache is empty")
    
    print("\n✨ All tests completed!")
    
    return results

async def test_domain_rate_limiting():
    """Test that domain-specific rate limiting is working"""
    
    print("\n🧪 Testing Domain Rate Limiting\n")
    
    cache = HTMLCacheManager()
    
    # Multiple URLs from same domain to test rate limiting
    same_domain_urls = [
        f"https://www.allrecipes.com/recipe/{i}/" 
        for i in range(23600, 23610)  # 10 URLs from same domain
    ]
    
    print(f"📝 Testing rate limiting with {len(same_domain_urls)} URLs from allrecipes.com")
    print("   (Should respect 3 concurrent requests limit)")
    
    start_time = time.time()
    results = await cache.batch_fetch(same_domain_urls)
    fetch_time = time.time() - start_time
    
    print(f"✅ Completed in {fetch_time:.2f} seconds")
    print(f"   - This timing reflects rate-limited concurrent fetching")
    
    successful = sum(1 for html in results.values() if html is not None)
    print(f"   - Successfully fetched: {successful}/{len(same_domain_urls)}")

if __name__ == "__main__":
    # Run tests
    print("=" * 50)
    print("HTML CACHE MANAGER TEST SUITE")
    print("=" * 50)
    
    # Test basic functionality
    asyncio.run(test_html_cache())
    
    # Test rate limiting
    asyncio.run(test_domain_rate_limiting())
    
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)