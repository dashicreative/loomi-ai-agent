"""
CLI Interface for Testing Pydantic AI Recipe Agent
Interactive testing of the new Pydantic AI framework agent with session memory.
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

from pydantic_recipe_agent import find_recipes_with_pydantic_ai, RecipeAgentDeps


def print_agent_result(result, execution_time: float):
    """Print Pydantic AI agent results in detail."""
    print("\n" + "="*100)
    print("🤖 PYDANTIC AI AGENT EXECUTION RESULT")
    print("="*100)
    
    # Handle different result structures
    if hasattr(result, 'data'):
        data = result.data
        recipes = data if isinstance(data, list) else getattr(data, 'recipes', [])
        agent_summary = f"Found {len(recipes)} recipes using Pydantic AI"
        total_found = len(recipes)
        performance = getattr(data, 'performance', None)
    else:
        recipes = getattr(result, 'recipes', [])
        agent_summary = getattr(result, 'agent_summary', f"Found {len(recipes)} recipes using Pydantic AI")
        total_found = getattr(result, 'total_found', len(recipes))
        performance = getattr(result, 'performance', None)
    
    print(f"📊 {agent_summary}")
    print(f"🍽️ Recipes found: {total_found}")
    print(f"⏱️ Total execution time: {execution_time:.1f} seconds")
    
    # Performance scoring display
    if performance:
        perf = performance.get("overall_score", {})
        print(f"🏆 Performance: Speed {perf.get('speed', 0)}% | Quality {perf.get('quality', 0)}% | Accuracy {perf.get('accuracy', 0)}% | Grade: {perf.get('grade', 'N/A')}")
        
        # Session insights
        session_insights = performance.get("session_insights", {})
        if session_insights.get("searches_completed", 0) > 1:
            avg = session_insights.get("session_averages", {})
            print(f"📈 Session avg: Speed {avg.get('speed', 0)}% | Quality {avg.get('quality', 0)}% | Accuracy {avg.get('accuracy', 0)}%")
    
    if not recipes:
        print("⚠️ No recipes found")
        return
    
    # Show each recipe in detail  
    for i, recipe in enumerate(recipes, 1):
        print(f"\n{'='*50} RECIPE {i} {'='*50}")
        
        # Basic info
        print(f"📌 Title: {recipe.get('title', 'No title')}")
        print(f"🔗 URL: {recipe.get('source_url', 'No URL')}")
        print(f"📸 Image: {recipe.get('image_url', 'No image')}")
        print(f"⏰ Cook Time: {recipe.get('cook_time', 'Not specified')}")
        print(f"🍽️ Servings: {recipe.get('servings', 'Not specified')}")
        
        # Session context indicators
        if recipe.get('_from_session_bank'):
            print(f"🔄 From Session Bank (original query: '{recipe.get('_original_query', 'Unknown')}')")
            print(f"📊 Relevance Score: {recipe.get('_session_relevance_score', 0):.2f}")
        
        # Ingredients (show first 8)
        ingredients = recipe.get('ingredients', [])
        print(f"\n📝 INGREDIENTS ({len(ingredients)} total):")
        if ingredients:
            for j, ingredient in enumerate(ingredients[:8], 1):
                print(f"  {j:2d}. {ingredient}")
            if len(ingredients) > 8:
                print(f"  ... and {len(ingredients) - 8} more ingredients")
        else:
            print("  ❌ No ingredients found")
        
        # Instructions (show first 5)
        instructions = recipe.get('instructions', [])
        print(f"\n👨‍🍳 INSTRUCTIONS ({len(instructions)} steps):")
        if instructions:
            for j, instruction in enumerate(instructions[:5], 1):
                print(f"  {j:2d}. {instruction}")
            if len(instructions) > 5:
                print(f"  ... and {len(instructions) - 5} more steps")
        else:
            print("  ❌ No instructions found")
        
        # Nutrition (first 4)
        nutrition = recipe.get('nutrition', [])
        print(f"\n🥗 NUTRITION:")
        if nutrition:
            for nutrient in nutrition[:4]:
                print(f"  • {nutrient}")
        else:
            print("  ❌ No nutrition data")
    
    print("\n" + "="*100)


async def interactive_cli():
    """Interactive CLI for testing the Pydantic AI agent."""
    print("\n" + "="*80)
    print("🤖 PYDANTIC AI RECIPE DISCOVERY AGENT - CLI TESTER")
    print("="*80)
    print("🔧 Uses Pydantic AI framework with Three Pillar Intelligence")
    print("💾 Features session memory - recipes are remembered across searches!")
    print("💡 Try queries like: 'chocolate cake', 'vegan pasta recipes', 'quick dinner'")
    print("🔄 Try multiple searches to see session memory in action")
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
    
    # Create persistent dependencies for session memory
    deps = RecipeAgentDeps(
        serpapi_key=serpapi_key,
        openai_key=openai_key,
        google_key=google_key,
        google_cx=google_cx
    )
    
    print(f"🧠 Session memory initialized - recipes will be remembered!")
    
    while True:
        try:
            # Get user input
            user_input = input("\n🍽️ What recipes would you like me to find? > ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print(f"\n📊 Session Summary:")
                print(f"   Total queries: {len(deps.session_queries)}")
                print(f"   Recipes in memory bank: {len(deps.session_recipe_bank)}")
                print(f"   URLs shown: {len(deps.session_shown_urls)}")
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
            
            print(f"🎯 Looking for {target_count} recipes...")
            print(f"🧠 Session context: {len(deps.session_recipe_bank)} recipes in memory bank")
            
            # Execute Pydantic AI agent workflow
            start_time = time.time()
            
            # Use the persistent deps to maintain session state
            from pydantic_recipe_agent import recipe_agent
            result = await recipe_agent.run(
                f"Find {target_count} high-quality recipes for: {user_input}",
                deps=deps
            )
            
            execution_time = time.time() - start_time
            
            # Handle result properly (Pydantic AI returns different structure)
            result_data = result.data if hasattr(result, 'data') else result
            
            # Create a compatible result structure for display
            display_result = type('Result', (), {
                'total_found': len(result_data.get('recipes', [])) if isinstance(result_data, dict) else len(getattr(result_data, 'recipes', [])),
                'agent_summary': getattr(result_data, 'agent_summary', f"Pydantic AI search completed"),
                'recipes': result_data.get('recipes', []) if isinstance(result_data, dict) else getattr(result_data, 'recipes', []),
                'performance': result_data.get('performance') if isinstance(result_data, dict) else getattr(result_data, 'performance', None)
            })()
            
            print_agent_result(display_result, execution_time)
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user - goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def single_query_test(query: str, count: int = 4):
    """Test Pydantic AI agent with a single query (for script usage)."""
    print(f"🧪 Testing Pydantic AI agent with query: '{query}' (target: {count} recipes)")
    
    start_time = time.time()
    result = await find_recipes_with_pydantic_ai(query, count)
    execution_time = time.time() - start_time
    
    print_agent_result(result, execution_time)
    
    return result


async def session_memory_demo():
    """Demonstrate session memory capabilities."""
    print("\n🧪 PYDANTIC AI AGENT - SESSION MEMORY DEMO")
    print("="*60)
    
    # Create persistent dependencies
    deps = RecipeAgentDeps(
        serpapi_key=os.getenv("SERPAPI_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
        google_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_cx=os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    )
    
    from pydantic_recipe_agent import recipe_agent
    
    # First search
    print("\n1️⃣ First search: 'chocolate cake'")
    result1 = await recipe_agent.run(
        "Find 2 high-quality recipes for: chocolate cake",
        deps=deps
    )
    print(f"   Found {result1.data.total_found} recipes")
    print(f"   Session bank now has: {len(deps.session_recipe_bank)} recipes")
    
    # Second search (should leverage session memory)
    print("\n2️⃣ Second search: 'quick dessert'")
    result2 = await recipe_agent.run(
        "Find 3 high-quality recipes for: quick dessert",
        deps=deps
    )
    print(f"   Found {result2.data.total_found} recipes")
    print(f"   Session bank now has: {len(deps.session_recipe_bank)} recipes")
    
    # Check for session memory usage
    session_recipes = [r for r in result2.data.recipes if r.get('_from_session_bank')]
    if session_recipes:
        print(f"   🎉 SUCCESS: {len(session_recipes)} recipes came from session memory!")
        for recipe in session_recipes:
            print(f"      - {recipe.get('title', 'Unknown')} (from '{recipe.get('_original_query', 'Unknown')}')")
    else:
        print("   ℹ️ No recipes reused from session memory (may be expected depending on relevance)")
    
    print(f"\n📊 Final session state:")
    print(f"   Queries processed: {len(deps.session_queries)}")
    print(f"   Recipes in memory: {len(deps.session_recipe_bank)}")
    print(f"   URLs tracked: {len(deps.session_shown_urls)}")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check if running with arguments for single test
    if len(sys.argv) > 1:
        if sys.argv[1] == "demo":
            # Run session memory demo
            asyncio.run(session_memory_demo())
        else:
            # Single query test
            query = " ".join(sys.argv[1:])
            asyncio.run(single_query_test(query))
    else:
        # Run interactive CLI
        asyncio.run(interactive_cli())