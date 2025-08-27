#!/usr/bin/env python3
"""Test script to debug search_and_process_recipes_tool"""

import asyncio
import os
from dotenv import load_dotenv
from Dependencies import RecipeDeps
from pydantic_ai import RunContext
from Tools import search_and_process_recipes_tool

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
    
    print("Testing search_and_process_recipes_tool...")
    try:
        result = await search_and_process_recipes_tool(
            ctx,
            query="steak recipe",
            needed_count=5
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())