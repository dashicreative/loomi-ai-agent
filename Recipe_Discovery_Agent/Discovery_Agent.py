from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pathlib import Path
from Structured_Output import AgentOutput
from Tools import (
    search_and_process_recipes_tool,
    save_meal_to_session,
    analyze_saved_meals,
    temporary_save_meal_tool  # TEMPORARY: DELETE WHEN UI CONNECTED
)
from Dependencies import RecipeDeps
import os
import time
from dotenv import load_dotenv
import logfire


#Setting up logfire for tracing
logfire.configure(scrubbing=False)  # Disable scrubbing to allow system prompt
logfire.instrument_pydantic_ai()

# Load environment variables
load_dotenv()

# Load system prompt from file
def load_system_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent / filename
    with open(prompt_path, 'r') as f:
        return f.read()


def build_context_aware_prompt(session) -> str:
    """
    Build system prompt with current session context.
    
    Args:
        session: Current SessionContext with saved meals and current recipes
        
    Returns:
        Context-aware system prompt
    """
    base_prompt = load_system_prompt("System_Prompt.txt")
    
    # Add current session context
    context_addition = "\n\n## CURRENT SESSION CONTEXT\n"
    
    # Current recipes (numbered 1-5)
    if session.current_batch_recipes:
        context_addition += f"\n**Currently Shown Recipes (1-{len(session.current_batch_recipes)}):**\n"
        for i, recipe in enumerate(session.current_batch_recipes, 1):
            title = recipe.get('title', 'Unknown')
            calories = "Unknown"
            protein = "Unknown"
            
            # Extract nutrition from iOS format
            nutrition = recipe.get('nutrition', [])
            for nutrient in nutrition:
                if isinstance(nutrient, dict):
                    name = nutrient.get('name', '').lower()
                    amount = nutrient.get('amount', '0')
                    unit = nutrient.get('unit', '')
                    
                    if 'calorie' in name:
                        calories = f"{amount}{unit}"
                    elif 'protein' in name:
                        protein = f"{amount}{unit}"
            
            context_addition += f"{i}. {title} ({calories}, {protein} protein)\n"
    
    # Saved meals summary
    if session.saved_meals:
        totals = session.get_saved_nutrition_totals()
        context_addition += f"\n**Saved Meals ({len(session.saved_meals)} total):**\n"
        for meal in session.saved_meals:
            title = meal.get('title', 'Unknown')
            orig_num = meal.get('original_number', '?')
            context_addition += f"- {title} (originally #{orig_num})\n"
        
        context_addition += f"\n**Saved Meals Nutrition Totals:**\n"
        context_addition += f"- Calories: {totals['calories']:.0f} kcal\n"
        context_addition += f"- Protein: {totals['protein']:.1f}g\n"
        context_addition += f"- Fat: {totals['fat']:.1f}g\n"
        context_addition += f"- Carbs: {totals['carbs']:.1f}g\n"
        
        # Show nutrition gaps if any
        if session.current_nutrition_gaps:
            context_addition += f"\n**Current Nutrition Gaps:**\n"
            for nutrient, gap in session.current_nutrition_gaps.items():
                context_addition += f"- Need {gap:.1f}g more {nutrient}\n"
    
    # Session stats
    context_addition += f"\n**Session Stats:**\n"
    context_addition += f"- Total searches: {len(session.search_history)}\n"
    context_addition += f"- URLs shown: {len(session.shown_recipe_urls)}\n"
    context_addition += f"- Meals saved: {len(session.saved_meals)}\n"
    
    return base_prompt + context_addition

model: KnownModelName = 'openai:gpt-4o'  # Using type-safe model name

# Set up dependencies
deps = RecipeDeps(
    serpapi_key=os.getenv("SERPAPI_KEY"),
    firecrawl_key=os.getenv("FIRECRAWL_API_KEY"),
    openai_key=os.getenv("OPENAI_API_KEY"),
    google_search_key=os.getenv("GOOGLE_SEARCH_KEY"),
    google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID")
)



#Recipe discovery agent instantiation
recipe_discovery_agent = Agent(
    model,
    system_prompt=load_system_prompt("System_Prompt.txt"),
    # Removed output_type=AgentOutput for performance - agent only returns response text
    tools=[
        search_and_process_recipes_tool,
        save_meal_to_session,
        analyze_saved_meals,
        temporary_save_meal_tool  # TEMPORARY: DELETE WHEN UI CONNECTED
    ],
    deps_type=RecipeDeps
)
























# Interactive loop
def main():
    print("🍳 Recipe Discovery Agent")
    print("Type 'quit' to exit\n")
    
    # TODO: UI INTEGRATION - Frontend should provide real session_id
    # TEMPORARY: Generate session ID for this conversation
    import uuid
    conversation_session_id = f"conversation-{uuid.uuid4().hex[:8]}"
    print(f"📝 Session ID: {conversation_session_id}")
    print("💡 Tip: Say 'save meal #3' to save recipes for testing\n")
    
    # Track message history for conversation context
    message_history = []
    
    while True:
        user_input = input("\nWhat recipes would you like to find? > ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        try:
            print(f"\n⏱️  AGENT PROCESSING STARTED...")
            agent_start = time.time()
            
            # Get current session context for agent awareness
            from Tools.session_context import get_or_create_session
            session = get_or_create_session(conversation_session_id)
            
            # Build context-aware system prompt
            context_prompt = build_context_aware_prompt(session)
            
            # Debug: Show context being provided to agent
            if session.current_batch_recipes or session.saved_meals:
                print(f"📋 Providing context: {len(session.current_batch_recipes)} current recipes, {len(session.saved_meals)} saved meals")
            
            # Update agent with current context
            recipe_discovery_agent.system_prompt = context_prompt
            
            result = recipe_discovery_agent.run_sync(
                user_input,
                deps=deps,
                message_history=message_history  # Maintain conversation context
            )
            
            # Update message history
            message_history.extend(result.all_messages())
            
            agent_time = time.time() - agent_start
            print(f"\n⏱️  AGENT RESPONSE GENERATION: {agent_time:.2f}s")
            
            # Agent now returns plain text response only (no expensive JSON generation)
            agent_response = result.data if hasattr(result, 'data') else str(result)
            
            # Get structured data from all process_recipe_batch_tool calls
            all_recipes = []
            search_query = user_input
            total_results = 0
            failed_reports = []
            
            for message in result.all_messages():
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            # Collect data from process_recipe_batch_tool calls
                            if 'full_recipes' in output:
                                batch_recipes = output.get('full_recipes', [])
                                all_recipes.extend(batch_recipes)
                                search_query = output.get('searchQuery', search_query)
                                if output.get('_failed_parse_report'):
                                    failed_reports.append(output['_failed_parse_report'])
            
            # Aggregate all batch results
            total_results = len(all_recipes)
            
            # Create aggregated tool data for display
            tool_data = None
            if all_recipes:
                # Combine failed reports from all batches
                combined_failed_report = {
                    "total_failed": sum(report.get("total_failed", 0) for report in failed_reports),
                    "content_scraping_failures": sum(report.get("content_scraping_failures", 0) for report in failed_reports),
                    "recipe_parsing_failures": sum(report.get("recipe_parsing_failures", 0) for report in failed_reports),
                    "failed_urls": []
                }
                for report in failed_reports:
                    combined_failed_report["failed_urls"].extend(report.get("failed_urls", []))
                
                tool_data = {
                    'full_recipes': all_recipes,
                    'totalResults': total_results,
                    'searchQuery': search_query,
                    '_failed_parse_report': combined_failed_report
                }
            
            # Display agent's conversational response
            print(f"\n{agent_response}")
            
            # Display structured data info
            if tool_data:
                print(f"\nFound {tool_data['totalResults']} recipes for: {tool_data['searchQuery']}")
                
                # Display structured data for iOS app verification
                if tool_data.get('full_recipes'):
                    print("\n" + "="*80)
                    print("📱 STRUCTURED DATA FOR iOS APP:")
                    print("="*80)
                    import json
                    for i, recipe in enumerate(tool_data['full_recipes'], 1):
                        print(f"\n🍳 Recipe {i}:")
                        print(json.dumps(recipe, indent=2))
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
