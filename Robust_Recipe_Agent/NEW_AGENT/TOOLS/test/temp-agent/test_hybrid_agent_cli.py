"""
CLI Interface for Testing Hybrid Recipe Agent
Tests the best-of-both-worlds approach with 2 composite tools.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict

# Add agent to path
sys.path.insert(0, str(Path(__file__).parent))

from hybrid_recipe_agent import find_recipes_with_hybrid_agent, HybridAgentDeps


def print_raw_results(agent_response: str, execution_time: float):
    """Print the raw agent response to see exactly what data it received."""
    print("\n" + "="*100)
    print("🤖 HYBRID AGENT RAW RESPONSE")
    print("="*100)
    print(f"⏱️ Total execution time: {execution_time:.1f} seconds")
    print("\n📋 RAW AGENT OUTPUT:")
    print("-" * 50)
    print(agent_response)
    print("-" * 50)
    print("\n" + "="*100)


async def interactive_cli():
    """Interactive CLI for testing the Hybrid AI agent."""
    print("\n" + "="*80)
    print("🤖 HYBRID RECIPE AGENT - CLI TESTER")
    print("="*80)
    print("🚀 Best of both worlds: Simple agent speed + Pydantic AI intelligence")
    print("🛠️ Uses 2 composite tools for strategic flexibility")
    print("📊 Shows RAW tool results so you can see agent decision data")
    print("💡 Try queries like: 'chocolate cake', 'quick dinner', 'gluten-free vegan dessert'")
    print("Type 'quit' to exit\n")
    
    # Check API keys
    serpapi_key = os.getenv("SERPAPI_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_SEARCH_KEY")
    google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    if not serpapi_key:
        print("❌ Missing SERPAPI_KEY - search will fail")
    if not openai_key:
        print("❌ Missing OPENAI_API_KEY - classification and parsing will fail")
    
    if not (serpapi_key and openai_key):
        print("\n⚠️ Please set required environment variables")
        print("Cannot continue without API keys.")
        return
    
    print("✅ API keys configured")
    
    # Create persistent dependencies for session state
    deps = HybridAgentDeps(
        serpapi_key=serpapi_key,
        openai_key=openai_key,
        google_key=google_key,
        google_cx=google_cx
    )
    
    print(f"🧠 Hybrid agent ready with session memory!")
    
    while True:
        try:
            # Get user input
            user_input = input("\n🍽️ What recipes would you like me to find? > ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print(f"\n📊 Session Summary:")
                print(f"   URLs tracked: {len(deps.session_shown_urls)}")
                print(f"   Recipe bank: {len(deps.session_recipe_bank)}")
                print("👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Parse target count from query if specified
            target_count = 4  # Default
            if "1 recipe" in user_input.lower() or "a recipe" in user_input.lower():
                target_count = 1
            elif any(num in user_input for num in ["2 ", "two "]):
                target_count = 2  
            elif any(num in user_input for num in ["3 ", "three "]):
                target_count = 3
            elif any(num in user_input for num in ["5 ", "five "]):
                target_count = 5
            
            print(f"🎯 Looking for {target_count} recipes with hybrid architecture...")
            
            # Execute Hybrid AI agent workflow
            start_time = time.time()
            print(f"⏱️ [CLI] Starting hybrid agent workflow at {time.time():.2f}")
            
            # Use the persistent deps to maintain session state
            from hybrid_recipe_agent import hybrid_agent
            
            agent_call_start = time.time()
            result = await hybrid_agent.run(
                f"Find {target_count} high-quality recipes for: {user_input}",
                deps=deps
            )
            agent_call_elapsed = time.time() - agent_call_start
            
            execution_time = time.time() - start_time
            
            print(f"⏱️ [CLI] Agent call took: {agent_call_elapsed:.2f}s")
            print(f"⏱️ [CLI] Total CLI execution: {execution_time:.2f}s")
            
            # Handle result properly (Pydantic AI returns different structure)
            result_data = result.data if hasattr(result, 'data') else str(result)
            
            # Print the raw agent response
            print_raw_results(result_data, execution_time)
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user - goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def single_query_test(query: str, count: int = 4):
    """Test Hybrid AI agent with a single query (for script usage)."""
    print(f"🧪 Testing Hybrid AI agent with query: '{query}' (target: {count} recipes)")
    
    start_time = time.time()
    result = await find_recipes_with_hybrid_agent(query, count)
    execution_time = time.time() - start_time
    
    print_raw_results(result, execution_time)
    
    return result


async def speed_comparison_demo():
    """Demonstrate speed comparison between approaches."""
    print("\n🏁 HYBRID AGENT - SPEED COMPARISON DEMO")
    print("="*60)
    
    queries = [
        "chocolate cake",
        "quick chicken dinner", 
        "gluten-free vegan dessert"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Testing: '{query}'")
        print("-" * 40)
        
        start_time = time.time()
        result = await find_recipes_with_hybrid_agent(query, 3)
        execution_time = time.time() - start_time
        
        print(f"⏱️ Execution time: {execution_time:.1f} seconds")
        print(f"📊 Result preview: {result[:200]}...")
        
        if i < len(queries):
            print("\nWaiting 2 seconds before next test...")
            await asyncio.sleep(2)
    
    print(f"\n🏆 Speed comparison complete!")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check if running with arguments for single test
    if len(sys.argv) > 1:
        if sys.argv[1] == "demo":
            # Run speed comparison demo
            asyncio.run(speed_comparison_demo())
        else:
            # Single query test
            query = " ".join(sys.argv[1:])
            asyncio.run(single_query_test(query))
    else:
        # Run interactive CLI
        asyncio.run(interactive_cli())