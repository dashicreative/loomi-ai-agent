"""
Test the complete conversation flow including previous recipe retrieval.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add agent to path
sys.path.insert(0, str(Path(__file__).parent))

from hybrid_recipe_agent import hybrid_agent, HybridAgentDeps


async def test_full_conversation():
    """Test complete conversation flow with query history."""
    
    print("🧪 TESTING FULL CONVERSATION FLOW")
    print("=" * 50)
    
    # Create persistent session
    deps = HybridAgentDeps(
        serpapi_key=os.getenv("SERPAPI_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
        google_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_cx=os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    )
    
    # Test 1: Normal recipe search
    print("\n1️⃣ FIRST SEARCH: Testing normal recipe query")
    print("-" * 40)
    
    result1 = await hybrid_agent.run(
        "Find me 3 chocolate cake recipes",
        deps=deps
    )
    
    agent_response1 = result1.data if hasattr(result1, 'data') else str(result1)
    print(f"✅ First search result: {str(agent_response1)[:100]}...")
    print(f"📊 Session state: {len(deps.query_history)} searches, {len(deps.recipe_memory)} recipes")
    
    # Test 2: Previous recipe retrieval  
    print("\n2️⃣ RETRIEVE PREVIOUS: Testing query history retrieval")
    print("-" * 40)
    
    result2 = await hybrid_agent.run(
        "Can you show me the recipes from my last search?",
        deps=deps
    )
    
    agent_response2 = result2.data if hasattr(result2, 'data') else str(result2)
    print(f"✅ Retrieval result: {str(agent_response2)[:100]}...")
    print(f"📊 Session state: {len(deps.query_history)} searches, {len(deps.recipe_memory)} recipes")
    
    # Test 3: Non-recipe query (scope validation)
    print("\n3️⃣ SCOPE VALIDATION: Testing non-recipe query")
    print("-" * 40)
    
    result3 = await hybrid_agent.run(
        "Help me plan a vacation to Japan",
        deps=deps
    )
    
    agent_response3 = result3.data if hasattr(result3, 'data') else str(result3)
    print(f"✅ Scope validation result: {str(agent_response3)}")
    
    # Test 4: New recipe search (should create new query ID)
    print("\n4️⃣ NEW SEARCH: Testing additional search in same session")
    print("-" * 40)
    
    result4 = await hybrid_agent.run(
        "Find me 2 gluten-free desserts",
        deps=deps
    )
    
    agent_response4 = result4.data if hasattr(result4, 'data') else str(result4)
    print(f"✅ New search result: {str(agent_response4)[:100]}...")
    print(f"📊 Final session state: {len(deps.query_history)} searches, {len(deps.recipe_memory)} recipes")
    
    # Show complete session history
    print("\n📚 COMPLETE SESSION HISTORY:")
    print("-" * 40)
    for i, query_record in enumerate(deps.query_history, 1):
        print(f"   {i}. {query_record['query_id']}: '{query_record['original_query']}' → {query_record['recipe_count']} recipes")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(test_full_conversation())