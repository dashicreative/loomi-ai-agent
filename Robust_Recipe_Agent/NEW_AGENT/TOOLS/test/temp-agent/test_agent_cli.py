"""
CLI Interface for Testing Simplified Recipe Agent
Interactive testing of 4-tool agent workflow.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict

# Add simple_agent to path
sys.path.insert(0, str(Path(__file__).parent))

from simple_agent import SimpleRecipeAgent


def print_agent_result(result: Dict):
    """Print agent results in detail for debugging."""
    print("\n" + "="*100)
    print("🤖 AGENT EXECUTION RESULT")
    print("="*100)
    
    if result.get("error"):
        print(f"❌ Error: {result['error']}")
        return
    
    recipes = result.get("recipes", [])
    summary = result.get("agent_summary", "")
    
    print(f"📊 {summary}")
    print(f"🍽️ Recipes found: {len(recipes)}")
    
    # Performance scoring display
    if result.get("performance"):
        perf = result["performance"]["overall_score"]
        print(f"🏆 Performance: Speed {perf['speed']}% | Quality {perf['quality']}% | Accuracy {perf['accuracy']}% | Grade: {perf['grade']}")
        
        # Session insights
        session_insights = result["performance"].get("session_insights", {})
        if session_insights.get("searches_completed", 0) > 1:
            avg = session_insights.get("session_averages", {})
            print(f"📈 Session avg: Speed {avg.get('speed', 0)}% | Quality {avg.get('quality', 0)}% | Accuracy {avg.get('accuracy', 0)}%")
    
    if not recipes:
        print("⚠️ No recipes found")
        return
    
    # Show each recipe in detail (what the agent sees)
    for i, recipe in enumerate(recipes, 1):
        print(f"\n{'='*50} RECIPE {i} {'='*50}")
        
        # Basic info
        print(f"📌 Title: {recipe.get('title', 'No title')}")
        print(f"🔗 URL: {recipe.get('source_url', 'No URL')}")
        print(f"📸 Image: {recipe.get('image_url', 'No image')}")
        print(f"⏰ Cook Time: {recipe.get('cook_time', 'Not specified')}")
        print(f"🍽️ Servings: {recipe.get('servings', 'Not specified')}")
        
        # Ingredients (full list - what agent sees)
        ingredients = recipe.get('ingredients', [])
        print(f"\n📝 INGREDIENTS ({len(ingredients)} total):")
        if ingredients:
            for j, ingredient in enumerate(ingredients, 1):
                print(f"  {j:2d}. {ingredient}")
        else:
            print("  ❌ No ingredients found")
        
        # Instructions (full list - what agent sees) 
        instructions = recipe.get('instructions', [])
        print(f"\n👨‍🍳 INSTRUCTIONS ({len(instructions)} steps):")
        if instructions:
            for j, instruction in enumerate(instructions, 1):
                print(f"  {j:2d}. {instruction}")
        else:
            print("  ❌ No instructions found")
        
        # Nutrition (what agent sees)
        nutrition = recipe.get('nutrition', [])
        print(f"\n🥗 NUTRITION:")
        if nutrition:
            for nutrient in nutrition:
                print(f"  • {nutrient}")
        else:
            print("  ❌ No nutrition data")
        
        # Metadata (what agent has for decisions)
        print(f"\n🔍 METADATA:")
        search_title = recipe.get('search_title', 'N/A')
        search_snippet = recipe.get('search_snippet', 'N/A')
        print(f"  Search Title: {search_title}")
        print(f"  Search Snippet: {search_snippet[:100]}{'...' if len(search_snippet) > 100 else ''}")
    
    print("\n" + "="*100)


async def interactive_cli():
    """Interactive CLI for testing the simplified agent."""
    print("\n" + "="*80)
    print("🤖 SIMPLIFIED RECIPE DISCOVERY AGENT - CLI TESTER")
    print("="*80)
    print("🔧 Tests 4 tools: WebSearch → Classification → Parsing → Present")
    print("📝 Shows full recipe data (what the agent sees for decisions)")
    print("💡 Try queries like: 'chocolate cake', 'vegan pasta recipes', 'quick dinner'")
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
        print("\n⚠️ Please set required environment variables in .env file")
        print("Cannot continue without API keys.")
        return
    
    print("✅ API keys configured")
    
    # Create agent
    agent = SimpleRecipeAgent(serpapi_key, openai_key, google_key, google_cx)
    
    while True:
        try:
            # Get user input
            user_input = input("\n🍽️ What recipes would you like me to find? > ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
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
            elif any(num in user_input for num in ["10 ", "ten "]):
                target_count = 10
            
            print(f"🎯 Looking for {target_count} recipes...")
            
            # Execute agent workflow
            start_time = time.time()
            result = await agent.find_recipes(user_input, target_count)
            execution_time = time.time() - start_time
            
            print(f"\n⏱️ Total execution time: {execution_time:.1f} seconds")
            
            # Print detailed results (what agent sees)
            print_agent_result(result)
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user - goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def single_query_test(query: str, count: int = 4):
    """Test agent with a single query (for script usage)."""
    print(f"🧪 Testing agent with query: '{query}' (target: {count} recipes)")
    
    result = await test_agent_interaction(query, count)
    print_agent_result(result)
    
    return result


async def test_agent_interaction(query: str, target_recipes: int = 4) -> Dict:
    """Test wrapper function."""
    serpapi_key = os.getenv("SERPAPI_KEY") 
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_SEARCH_KEY")
    google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    if not serpapi_key or not openai_key:
        return {"error": "Missing API keys"}
    
    agent = SimpleRecipeAgent(serpapi_key, openai_key, google_key, google_cx)
    return await agent.find_recipes(query, target_recipes)


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check if running with arguments for single test
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        asyncio.run(single_query_test(query))
    else:
        # Run interactive CLI
        asyncio.run(interactive_cli())