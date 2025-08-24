#!/usr/bin/env python3
"""Test script to debug process_recipe_batch_tool"""

import asyncio
import os
from dotenv import load_dotenv
from Dependencies import RecipeDeps
from pydantic_ai import RunContext
from Tools import process_recipe_batch_tool

# Load environment variables
load_dotenv()

async def test():
    # Set up dependencies
    deps = RecipeDeps(
        serpapi_key=os.getenv("SERPAPI_KEY"),
        firecrawl_key=os.getenv("FIRECRAWL_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Create a mock context
    class MockContext:
        def __init__(self):
            self.deps = deps
    
    ctx = MockContext()
    
    # Test URLs
    test_urls = [
        {"url": "https://www.allrecipes.com/recipe/steak", "title": "Test Steak Recipe"}
    ]
    
    print("Testing process_recipe_batch_tool...")
    try:
        result = await process_recipe_batch_tool(
            ctx,
            urls=test_urls,
            user_query="steak recipe",
            needed_count=5
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())