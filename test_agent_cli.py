"""
Local CLI Test for Recipe Discovery Agent

This allows you to interact with the agent directly in terminal mode,
just like the original Discovery_Agent.py main() function.

Usage: python test_agent_cli.py
"""

import os
import time
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from Recipe_Discovery_Agent.Discovery_Agent import create_recipe_discovery_agent
from Recipe_Discovery_Agent.Dependencies import RecipeDeps, SessionContext
from dotenv import load_dotenv
import logfire

# Load environment variables
load_dotenv()

def main():
    print("🧪 Recipe Discovery Agent - LOCAL CLI TEST MODE")
    print("🔧 This is for testing/debugging - same agent as Railway API")
    print("Type 'quit' to exit\n")
    
    # Validate required environment variables
    required_vars = {
        'OPENAI_API_KEY': os.getenv("OPENAI_API_KEY"),
        'SERPAPI_KEY': os.getenv("SERPAPI_KEY"), 
        'FIRECRAWL_API_KEY': os.getenv("FIRECRAWL_API_KEY")
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file:")
        for var in missing_vars:
            print(f"  - {var}=your_key_here")
        return
    
    print("✅ All required environment variables found")
    
    # Create session
    session = SessionContext()
    print(f"📝 Session ID: {session.session_id}")
    print("💡 You can test queries like: 'Find me 5 cheesecake recipes'\n")
    
    # Create dependencies
    deps_with_session = RecipeDeps(
        serpapi_key=required_vars['SERPAPI_KEY'],
        firecrawl_key=required_vars['FIRECRAWL_API_KEY'],
        openai_key=required_vars['OPENAI_API_KEY'],
        google_search_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
        session=session
    )
    
    # Create agent
    try:
        agent = create_recipe_discovery_agent()
        print("✅ Recipe Discovery Agent initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return
    
    # Track message history for conversation continuity
    message_history = []
    
    while True:
        user_input = input("\nWhat recipes would you like to find? > ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        try:
            agent_start = time.time()
            
            print(f"\n🔄 Processing: '{user_input}'")
            print("⏳ This may take 30-60 seconds for recipe search and parsing...")
            
            # Run agent with search query
            result = agent.run_sync(
                user_input,
                deps=deps_with_session,
                message_history=message_history
            )
            
            # Update message history
            message_history.extend(result.all_messages())
            
            agent_time = time.time() - agent_start
            
            # Show agent response
            agent_response = result.data if hasattr(result, 'data') else str(result)
            print(f"\n🤖 Agent Response: {agent_response}")
            
            # Extract and display recipe data (same logic as FastAPI)
            all_recipes = []
            total_results = 0
            
            print(f"\n🔍 Analyzing tool outputs from {len(result.all_messages())} messages...")
            
            for i, message in enumerate(result.all_messages()):
                print(f"📨 Message {i}: {type(message).__name__}")
                
                # Check for tool results in message content
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for j, item in enumerate(message.content):
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'full_recipes' in output:
                                batch_recipes = output.get('full_recipes', [])
                                print(f"  🍽️ Found {len(batch_recipes)} recipes in tool output")
                                all_recipes.extend(batch_recipes)
                                
                                # Show recipe titles
                                for recipe in batch_recipes:
                                    title = recipe.get('title', 'No title')
                                    print(f"    - {title}")
            
            # Show summary
            print(f"\n📊 RESULTS SUMMARY:")
            print(f"   ⏱️ Processing time: {agent_time:.1f}s")
            print(f"   🍽️ Total recipes found: {len(all_recipes)}")
            print(f"   📝 Current session has: {len(session.current_batch_recipes)} recipes")
            print(f"   💾 Saved meals: {len(session.saved_meals)}")
            
            if all_recipes:
                print(f"\n🍽️ RECIPE DETAILS:")
                for i, recipe in enumerate(all_recipes, 1):
                    title = recipe.get('title', 'Unknown')
                    ingredients_count = len(recipe.get('ingredients', []))
                    url = recipe.get('sourceUrl', 'No URL')
                    print(f"   {i}. {title}")
                    print(f"      - {ingredients_count} ingredients")
                    print(f"      - {url}")
            else:
                print("⚠️ No recipes extracted from tool outputs")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()