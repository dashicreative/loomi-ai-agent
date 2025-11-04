"""
Simple Apify Actor Test - Single URL
Test API connection with one hardcoded URL to debug format issues.
"""

import asyncio
import httpx
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_single_url():
    """Test Apify actor with single hardcoded URL."""
    
    apify_token = os.getenv("APIFY_API_KEY")
    if not apify_token:
        print("❌ Missing APIFY_API_KEY in .env file")
        return
    
    test_url = "https://www.abeautifulplate.com/marcella-hazan-bolognese/"
    
    print("🧪 SIMPLE APIFY ACTOR TEST")
    print("=" * 50)
    print(f"🔗 Test URL: {test_url}")
    print(f"🔑 API Token: {apify_token[:20]}...")
    print()
    
    # Test different input formats and endpoints
    test_cases = [
        {
            "name": "Format 1: start_urls (underscore) with /runs endpoint", 
            "input": {"start_urls": [test_url]},
            "endpoint": "web.harvester~recipes-scraper",
            "api_path": "runs"
        },
        {
            "name": "Format 2: start_urls with run-sync-get-dataset-items",
            "input": {"start_urls": [test_url]},
            "endpoint": "web.harvester~recipes-scraper",
            "api_path": "run-sync-get-dataset-items"
        },
        {
            "name": "Format 3: start_urls with run-sync",
            "input": {"start_urls": [test_url]},
            "endpoint": "web.harvester~recipes-scraper", 
            "api_path": "run-sync"
        }
    ]
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, test_case in enumerate(test_cases, 1):
            print(f"🧪 TEST {i}: {test_case['name']}")
            print(f"   📋 Input: {json.dumps(test_case['input'], indent=2)}")
            
            endpoint_url = f"https://api.apify.com/v2/acts/{test_case['endpoint']}/{test_case['api_path']}?token={apify_token}"
            print(f"   🔗 Endpoint: {endpoint_url}")
            
            try:
                response = await client.post(
                    endpoint_url,
                    json=test_case['input'],
                    headers={"Content-Type": "application/json"}
                )
                
                print(f"   📊 Status: {response.status_code}")
                
                if response.status_code == 200:
                    results = response.json()
                    print(f"   ✅ SUCCESS! Got {len(results) if isinstance(results, list) else 'unknown'} results")
                    if isinstance(results, list) and len(results) > 0:
                        first_result = results[0]
                        print(f"   📋 Sample fields: {list(first_result.keys()) if isinstance(first_result, dict) else 'Not dict'}")
                    break  # Found working format!
                else:
                    print(f"   ❌ Failed: {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"   📝 Error: {error_data}")
                    except:
                        print(f"   📝 Raw response: {response.text[:200]}")
                
            except Exception as e:
                print(f"   ❌ Exception: {e}")
            
            print()
    
    print("🎯 Test complete!")


if __name__ == "__main__":
    asyncio.run(test_single_url())