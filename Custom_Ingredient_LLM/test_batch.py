#!/usr/bin/env python3

import asyncio
import json
import time
from Custom_Ingredient_LLM_Batch import process_ingredients_with_fallback

async def test_batch_processing():
    """Test batch processing with various scenarios"""
    
    # Test 1: Small batch (less than 5)
    print("\n" + "="*60)
    print("Test 1: Small batch (3 ingredients)")
    print("="*60)
    
    ingredients_small = ["chicken breast", "olive oil", "tomato"]
    start = time.time()
    result = await process_ingredients_with_fallback(ingredients_small)
    elapsed = time.time() - start
    
    print(f"⏱️  Time taken: {elapsed:.2f} seconds")
    print(f"📊 Total: {result['total_count']}, Success: {result['successful_count']}, Failed: {result['failed_count']}")
    for r in result['results']:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['ingredient_name']}")
    
    # Test 2: Exact batch size (5)
    print("\n" + "="*60)
    print("Test 2: Exact batch size (5 ingredients)")
    print("="*60)
    
    ingredients_exact = ["salmon", "quinoa", "avocado", "lemon", "garlic"]
    start = time.time()
    result = await process_ingredients_with_fallback(ingredients_exact)
    elapsed = time.time() - start
    
    print(f"⏱️  Time taken: {elapsed:.2f} seconds")
    print(f"📊 Total: {result['total_count']}, Success: {result['successful_count']}, Failed: {result['failed_count']}")
    for r in result['results']:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['ingredient_name']}")
    
    # Test 3: Multiple batches (8 ingredients = 5 + 3)
    print("\n" + "="*60)
    print("Test 3: Multiple batches (8 ingredients)")
    print("="*60)
    
    ingredients_multi = [
        "beef", "potato", "carrot", "onion", "celery",  # First batch of 5
        "thyme", "rosemary", "butter"  # Second batch of 3
    ]
    start = time.time()
    result = await process_ingredients_with_fallback(ingredients_multi)
    elapsed = time.time() - start
    
    print(f"⏱️  Time taken: {elapsed:.2f} seconds")
    print(f"📊 Total: {result['total_count']}, Success: {result['successful_count']}, Failed: {result['failed_count']}")
    for r in result['results']:
        status = "✅" if r['success'] else "❌"
        calories = r.get('nutrition', {}).get('calories', 'N/A') if r['success'] else 'N/A'
        print(f"{status} {r['ingredient_name']}: {calories} cal")
    
    # Test 4: Mixed valid and invalid items
    print("\n" + "="*60)
    print("Test 4: Mixed valid and invalid items")
    print("="*60)
    
    ingredients_mixed = ["apple", "broom", "cheese", "plastic", "rice"]
    start = time.time()
    result = await process_ingredients_with_fallback(ingredients_mixed)
    elapsed = time.time() - start
    
    print(f"⏱️  Time taken: {elapsed:.2f} seconds")
    print(f"📊 Total: {result['total_count']}, Success: {result['successful_count']}, Failed: {result['failed_count']}")
    for r in result['results']:
        status = "✅" if r['success'] else "❌"
        message = r.get('message', '') if not r['success'] else f"Category: {r.get('category', 'N/A')}"
        print(f"{status} {r['ingredient_name']}: {message}")
    
    # Test 5: Duplicates (should be deduplicated)
    print("\n" + "="*60)
    print("Test 5: Duplicates handling")
    print("="*60)
    
    ingredients_dupes = ["tomato", "TOMATO", "Tomato", "basil", "basil"]
    result = await process_ingredients_with_fallback(ingredients_dupes)
    
    print(f"Input: {ingredients_dupes}")
    print(f"📊 Unique results: {result['total_count']}")
    for r in result['results']:
        print(f"  - {r['ingredient_name']}")

async def test_api_endpoint():
    """Test the actual API endpoint"""
    
    print("\n" + "="*60)
    print("Test API Endpoint")
    print("="*60)
    
    import aiohttp
    
    url = "http://localhost:8001/process-ingredients-batch"
    
    test_data = {
        "ingredient_names": ["chicken", "rice", "broccoli", "soy sauce", "ginger", "garlic", "sesame oil"]
    }
    
    print(f"Testing with {len(test_data['ingredient_names'])} ingredients...")
    print(f"Ingredients: {', '.join(test_data['ingredient_names'])}")
    
    try:
        async with aiohttp.ClientSession() as session:
            start = time.time()
            async with session.post(url, json=test_data) as response:
                elapsed = time.time() - start
                
                if response.status == 200:
                    data = await response.json()
                    print(f"\n✅ Success! Time taken: {elapsed:.2f} seconds")
                    print(f"📊 Total: {data['total_count']}, Success: {data['successful_count']}, Failed: {data['failed_count']}")
                    
                    print("\nResults summary:")
                    for r in data['results']:
                        if r['success']:
                            print(f"  ✅ {r['ingredient_name']}: {r['category']} ({r['nutrition']['calories']} cal/100{r['nutrition']['per_100']})")
                        else:
                            print(f"  ❌ {r['ingredient_name']}: {r.get('message', 'Failed')}")
                else:
                    print(f"❌ Error {response.status}: {await response.text()}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("Make sure the API server is running on port 8001")

if __name__ == "__main__":
    print("🧪 Batch Processing Test Suite")
    
    # Run unit tests
    asyncio.run(test_batch_processing())
    
    # Optionally test API endpoint
    print("\n" + "="*60)
    response = input("\nTest API endpoint? (y/n): ")
    if response.lower() == 'y':
        asyncio.run(test_api_endpoint())