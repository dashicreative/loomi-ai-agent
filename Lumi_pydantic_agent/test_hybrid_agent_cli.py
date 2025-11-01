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

from agents.hybrid_recipe_agent import find_recipes_with_hybrid_agent, HybridAgentDeps


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


def print_app_ready_results(app_response: dict, execution_time: float):
    """Print the complete app-ready response structure."""
    print("\n" + "="*100)
    print("🎨 COMPLETE APP-READY RESPONSE")
    print("="*100)
    print(f"⏱️ Total execution time: {execution_time:.1f} seconds")
    print(f"⏱️ Formatting time: {app_response.get('processing_time', 0):.1f} seconds")
    
    # Agent's conversational response
    print("\n💬 AGENT RESPONSE:")
    print("-" * 50)
    print(app_response.get('agent_response', ''))
    print("-" * 50)
    
    # Recipe summary
    recipes = app_response.get('recipes', [])
    print(f"\n📋 FORMATTED RECIPES ({len(recipes)} found):")
    print("-" * 50)
    
    if recipes:
        for i, recipe in enumerate(recipes, 1):
            print(f"\n🍽️ Recipe {i}: {recipe.get('title', 'Unknown')}")
            
            # Show source URL (actual field from recipe)
            source_url = recipe.get('source_url', 'Unknown')
            if source_url != 'Unknown':
                print(f"   📍 Source: {source_url}")
            else:
                print(f"   📍 Source: {recipe.get('metadata', {}).get('source_domain', 'Unknown')}")
            
            # Show timing info
            ready_time = recipe.get('readyInMinutes', recipe.get('totalTime', 'Unknown'))
            cook_time = recipe.get('cookTime', 'Unknown')
            prep_time = recipe.get('prepTime', 'Unknown')
            
            print(f"   ⏰ Ready in: {ready_time} minutes")
            if cook_time != 'Unknown':
                print(f"   🔥 Cook time: {cook_time}")
            if prep_time != 'Unknown':
                print(f"   ⏱️ Prep time: {prep_time}")
            
            print(f"   👥 Servings: {recipe.get('servings', 'Unknown')}")
            
            # Show ingredient count and first few ingredients
            ingredients = recipe.get('ingredients', [])
            print(f"   🧄 Ingredients: {len(ingredients)} total")
            if ingredients:
                for j, ing in enumerate(ingredients[:3]):  # Show first 3
                    quantity = ing.get('quantity', '')
                    unit = ing.get('unit', '')
                    name = ing.get('ingredient', '')
                    print(f"      {j+1}. {quantity} {unit} {name}".strip())
                if len(ingredients) > 3:
                    print(f"      ... and {len(ingredients) - 3} more")
            
            # Always show nutrition section (even if empty)
            nutrition = recipe.get('nutrition')
            def safe_float(value, default=0):
                try:
                    return float(value) if value else default
                except (ValueError, TypeError):
                    return default
            
            if nutrition and isinstance(nutrition, dict):
                calories = safe_float(nutrition.get('calories', 0))
                protein = safe_float(nutrition.get('protein', 0))
                fat = safe_float(nutrition.get('fat', 0))
                carbs = safe_float(nutrition.get('carbs', 0))
                print(f"   📊 Nutrition: {calories:.0f} cal, {protein:.0f}g protein, {fat:.0f}g fat, {carbs:.0f}g carbs")
            else:
                print(f"   📊 Nutrition: Not available")
    else:
        print("   No recipes found")
    
    print("\n" + "="*100)
    print(f"🏆 SUCCESS: Agent conversation + {len(recipes)} structured recipes ready for app")
    print("="*100)


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
    
    # Check search provider status
    has_google = bool(google_key and google_cx)
    has_serpapi = bool(serpapi_key)
    
    if has_google:
        print("✅ Google Custom Search API configured (primary)")
    elif has_serpapi:
        print("✅ SerpAPI configured (fallback)")
        if not google_key:
            print("❌ Missing GOOGLE_SEARCH_KEY")
        if not google_cx:
            print("❌ Missing GOOGLE_SEARCH_ENGINE_ID")
    else:
        print("❌ No search provider configured")
        if not google_key:
            print("❌ Missing GOOGLE_SEARCH_KEY")
        if not google_cx:
            print("❌ Missing GOOGLE_SEARCH_ENGINE_ID")
        if not serpapi_key:
            print("❌ Missing SERPAPI_KEY")
    
    if not openai_key:
        print("❌ Missing OPENAI_API_KEY - classification and parsing will fail")
    
    if not (has_google or has_serpapi) or not openai_key:
        print("\n⚠️ Please set required environment variables")
        print("Cannot continue without API keys.")
        return
    
    print("✅ All required API keys configured")
    
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
            
            # Target count for display purposes only (agent will determine actual search strategy)
            display_target = 4  # Default display hint
            if "1 recipe" in user_input.lower() or "a recipe" in user_input.lower():
                display_target = 1  # Hint for display, but discovery mode will still find 15+
            elif any(num in user_input for num in ["2 ", "two "]):
                display_target = 2  
            elif any(num in user_input for num in ["3 ", "three "]):
                display_target = 3
            elif any(num in user_input for num in ["5 ", "five "]):
                display_target = 5
            
            print(f"🎯 Looking for recipes with hybrid architecture...")
            
            # Execute Hybrid AI agent workflow
            start_time = time.time()
            print(f"⏱️ [CLI] Starting hybrid agent workflow at {time.time():.2f}")
            
            # Use the persistent deps to maintain session state
            from agents.hybrid_recipe_agent import hybrid_agent
            
            # Track recipe memory before agent call to identify new recipes
            recipe_ids_before = set(deps.recipe_memory.keys())
            
            agent_call_start = time.time()
            # Let agent determine search strategy based on constraints, not CLI parsing
            result = await hybrid_agent.run(
                user_input,  # Send clean query without CLI target count interference
                deps=deps
            )
            agent_call_elapsed = time.time() - agent_call_start
            
            print(f"⏱️ [CLI] Agent call took: {agent_call_elapsed:.2f}s")
            
            # Extract agent response and mode information
            agent_response = result.data if hasattr(result, 'data') else str(result)
            
            # Get recipe IDs based on agent mode and response
            recipe_ids_to_return = _extract_recipe_ids_from_agent_result(
                result, deps, recipe_ids_before
            )
            
            print(f"📊 [CLI] Found {len(recipe_ids_to_return)} recipes to return")
            
            # Check if formatting is already integrated by looking at recipe memory
            formatting_integrated = False
            if recipe_ids_to_return:
                # Check if first recipe has integrated formatting
                first_recipe_id = recipe_ids_to_return[0]
                if first_recipe_id in deps.recipe_memory:
                    recipe_data = deps.recipe_memory[first_recipe_id]
                    formatting_integrated = recipe_data.get('is_formatted', False)
            
            # Handle production API response assembly
            if recipe_ids_to_return:
                print(f"🎨 [CLI] Assembling production API response...")
                formatting_start = time.time()
                
                # Get clean app-ready recipes from session memory
                recipes_data = []
                for recipe_id in recipe_ids_to_return:
                    if recipe_id in deps.recipe_memory:
                        recipe_data = deps.recipe_memory[recipe_id]
                        recipes_data.append(recipe_data)
                
                # Create production API response
                app_response = {
                    "agent_response": agent_response,
                    "recipes": recipes_data,  # Clean app-ready format with _metadata
                    "total_results": len(recipes_data),
                    "processing_time": 0.0,  # Processing already done in pipeline
                    "timestamp": time.time()
                }
                
                formatting_elapsed = time.time() - formatting_start
                print(f"🎨 [CLI] API response assembly took: {formatting_elapsed:.2f}s")
                
                execution_time = time.time() - start_time
                print(f"⏱️ [CLI] Total CLI execution: {execution_time:.2f}s")
                print_app_ready_results(app_response, execution_time)
            else:
                execution_time = time.time() - start_time
                print(f"⏱️ [CLI] Total CLI execution: {execution_time:.2f}s")
                
                # No recipes found - just show agent response
                print_raw_results(agent_response, execution_time)
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted by user - goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


def _extract_recipe_ids_from_agent_result(result, deps, recipe_ids_before):
    """
    Extract recipe IDs to return based on agent mode and response.
    Production-ready: handles both discovery and selective modes.
    """
    try:
        # Try to get mode information from agent result
        tool_result = None
        
        # Check if result has tool usage data (from Pydantic AI)
        if hasattr(result, 'all_messages'):
            # Find the tool call result
            for message in result.all_messages():
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'content') and isinstance(item.content, dict):
                            tool_result = item.content
                            break
        
        # If we found structured tool result
        if tool_result and isinstance(tool_result, dict):
            mode = tool_result.get('mode', 'discovery')
            action = tool_result.get('action', 'return_all_discovered')
            recipe_ids = tool_result.get('recipe_ids', [])
            
            if mode == 'discovery' or action == 'return_all_discovered':
                # Discovery mode: return all newly discovered recipes
                recipe_ids_after = set(deps.recipe_memory.keys())
                return list(recipe_ids_after - recipe_ids_before)
            elif mode == 'selective' and recipe_ids:
                # Selective mode: return only agent-selected recipes
                return recipe_ids
            else:
                # Fallback to discovery behavior
                recipe_ids_after = set(deps.recipe_memory.keys())
                return list(recipe_ids_after - recipe_ids_before)
        else:
            # Legacy fallback: return all new recipes
            recipe_ids_after = set(deps.recipe_memory.keys())
            return list(recipe_ids_after - recipe_ids_before)
            
    except Exception as e:
        print(f"   ⚠️ Mode extraction failed: {e}")
        # Safe fallback: return all new recipes
        recipe_ids_after = set(deps.recipe_memory.keys())
        return list(recipe_ids_after - recipe_ids_before)


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
    # Load environment variables from parent directory
    from dotenv import load_dotenv
    
    # Try loading from parent directory first, then current directory
    env_paths = [
        "/Users/agustin/Desktop/loomi_ai_agent/.env",
        ".env"
    ]
    
    for env_path in env_paths:
        if load_dotenv(env_path):
            print(f"📁 Loaded environment from: {env_path}")
            break
    else:
        load_dotenv()  # Default fallback
    
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