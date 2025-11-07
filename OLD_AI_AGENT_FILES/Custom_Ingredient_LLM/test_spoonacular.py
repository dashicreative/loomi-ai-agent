#!/usr/bin/env python3

import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")

async def test_spoonacular_api():
    """Direct test of Spoonacular API"""
    
    ingredients = ["tomato", "chicken", "apple"]
    
    for ingredient in ingredients:
        print(f"\n🔍 Testing: {ingredient}")
        print("-" * 40)
        
        base_url = "https://api.spoonacular.com/food/ingredients/search"
        params = {
            "apiKey": SPOONACULAR_API_KEY,
            "query": ingredient,
            "number": 3
        }
        
        print(f"API Key: {SPOONACULAR_API_KEY[:10]}...")  # Debug: show first 10 chars
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params) as response:
                    print(f"Status: {response.status}")
                    data = await response.json()
                    print(f"Response: {data}")
                    
                    if data.get("results"):
                        for i, result in enumerate(data["results"], 1):
                            image_name = result.get("image", "")
                            print(f"\nResult {i}:")
                            print(f"  Name: {result.get('name')}")
                            print(f"  Image: {image_name}")
                            if image_name:
                                full_url = f"https://img.spoonacular.com/ingredients_250x250/{image_name}"
                                print(f"  Full URL: {full_url}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_spoonacular_api())