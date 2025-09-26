from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName
from pathlib import Path
from typing import Optional, Dict
from .Structured_Output import AgentOutput
from .Tools import search_and_process_recipes_tool
from .Dependencies import RecipeDeps, SessionContext
import os
import time
from dotenv import load_dotenv
import logfire


# Setting up logfire for tracing (skip if no credentials for Railway compatibility)
try:
    logfire.configure(scrubbing=False)  # Disable scrubbing to allow system prompt
    logfire.instrument_pydantic_ai()
    print("✅ Logfire configured successfully")
except Exception as e:
    print(f"⚠️  Logfire setup skipped: {e}")
    # Continue without logfire for Railway deployment

# Load environment variables
load_dotenv()

# Load system prompt from file
def load_system_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent / filename
    with open(prompt_path, 'r') as f:
        return f.read()


def build_context_aware_prompt(session: SessionContext) -> str:
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



# Recipe discovery agent with dynamic system prompt - Proper Pydantic AI Pattern
recipe_discovery_agent = Agent(
    model,
    deps_type=RecipeDeps
)

# Dynamic system prompt that includes session context
@recipe_discovery_agent.system_prompt
def dynamic_system_prompt(ctx: RunContext[RecipeDeps]) -> str:
    """Dynamic system prompt with current session context."""
    return build_context_aware_prompt(ctx.deps.session)

# Tools using proper dependency injection
@recipe_discovery_agent.tool
async def save_meal(ctx: RunContext[RecipeDeps], meal_number: int) -> Dict:
    """Save a meal from current batch to saved meals."""
    from .Tools.session_tools_refactored import save_meal_tool
    return await save_meal_tool(ctx, meal_number)

@recipe_discovery_agent.tool  
async def analyze_saved_meals(ctx: RunContext[RecipeDeps], query: str, daily_goals: Optional[Dict] = None) -> Dict:
    """Analyze saved meals based on user query."""
    from .Tools.session_tools_refactored import analyze_saved_meals_tool
    return await analyze_saved_meals_tool(ctx, query, daily_goals)

@recipe_discovery_agent.tool
async def temporary_save_meal(ctx: RunContext[RecipeDeps], user_message: str) -> Dict:
    """TEMPORARY: Handle chat save commands with intelligent recipe name matching. DELETE WHEN UI CONNECTED."""
    import re
    from difflib import SequenceMatcher
    
    session = ctx.deps.session
    message_lower = user_message.lower()
    
    # Early validation
    if not session.current_batch_recipes:
        return {
            "success": False,
            "message": "No recipes currently displayed. Please search for recipes first.",
            "_temporary_tool": True
        }
    
    # Pattern 1: Direct numeric patterns (fastest)
    numeric_patterns = [
        r'save\s+meal\s+#?(\d+)',
        r'save\s+recipe\s+#?(\d+)', 
        r'save\s+#?(\d+)'
    ]
    
    for pattern in numeric_patterns:
        match = re.search(pattern, message_lower)
        if match:
            meal_number = int(match.group(1))
            return await save_meal(ctx, meal_number)
    
    # Pattern 2: Word numbers (second fastest)
    word_to_num = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}
    word_match = re.search(r'save\s+the\s+(\w+)\s+one', message_lower)
    if word_match:
        word = word_match.group(1)
        if word in word_to_num:
            meal_number = word_to_num[word]
            return await save_meal(ctx, meal_number)
    
    # Pattern 3: Intelligent recipe name matching (for natural language)
    # Extract potential recipe name from user message
    save_patterns = [
        r'save\s+(?:the\s+)?(.+?)(?:\s+recipe|\s+one|$)',
        r'save\s+(?:recipe\s+)?(.+?)(?:\s+for\s+me|$)',
        r'(?:can\s+you\s+)?save\s+(.+?)(?:\s+please|$)'
    ]
    
    for save_pattern in save_patterns:
        match = re.search(save_pattern, message_lower)
        if match:
            potential_name = match.group(1).strip()
            
            # Skip if it's just a number or common words
            if potential_name.isdigit() or potential_name in ['that', 'this', 'it', 'one']:
                continue
            
            # Find best matching recipe by title similarity
            best_match = None
            best_score = 0.0
            best_index = -1
            
            for i, recipe in enumerate(session.current_batch_recipes):
                recipe_title = recipe.get('title', '').lower()
                
                # Calculate similarity score
                similarity = SequenceMatcher(None, potential_name, recipe_title).ratio()
                
                # Also check if any key words from potential_name appear in title
                potential_words = set(potential_name.split())
                title_words = set(recipe_title.split())
                word_overlap = len(potential_words & title_words) / len(potential_words) if potential_words else 0
                
                # Combined score (70% similarity, 30% word overlap)
                combined_score = (similarity * 0.7) + (word_overlap * 0.3)
                
                if combined_score > best_score and combined_score > 0.3:  # Minimum threshold
                    best_match = recipe
                    best_score = combined_score
                    best_index = i + 1
            
            if best_match:
                logfire.debug("recipe_name_match", 
                              user_input=potential_name, 
                              matched_title=best_match.get('title'),
                              score=best_score,
                              session_id=ctx.deps.session.session_id)
                return await save_meal(ctx, best_index)
    
    # Pattern 4: Context-based matching (last resort - provide helpful context)
    current_titles = [f"{i+1}. {recipe.get('title', 'Unknown')}" for i, recipe in enumerate(session.current_batch_recipes)]
    
    return {
        "success": False,
        "message": f"I couldn't identify which recipe to save from '{user_message}'. Current recipes:\n" + "\n".join(current_titles) + "\n\nTry: 'save meal #3' or 'save recipe #2'",
        "_temporary_tool": True,
        "_available_recipes": current_titles
    }

# Main search tool
recipe_discovery_agent.tool(search_and_process_recipes_tool)
























# Interactive loop
def main():
    print("🍳 Recipe Discovery Agent - Refactored with Proper Pydantic AI Patterns")
    print("Type 'quit' to exit\n")
    
    # TODO: UI INTEGRATION - Frontend should provide existing session or create new one
    # TEMPORARY: Create session in deps for this conversation
    session = SessionContext()
    print(f"📝 Session ID: {session.session_id}")
    print("💡 Tip: Say 'save meal #3' to save recipes for testing\n")
    
    # Create deps with session - Proper Pydantic AI Pattern
    deps_with_session = RecipeDeps(
        serpapi_key=os.getenv("SERPAPI_KEY"),
        firecrawl_key=os.getenv("FIRECRAWL_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
        google_search_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
        session=session  # Session context in dependencies
    )
    
    # Track message history for conversation continuity
    message_history = []
    
    while True:
        user_input = input("\nWhat recipes would you like to find? > ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        try:
            agent_start = time.time()
            logfire.info("agent_request_started", 
                         user_input=user_input,
                         session_id=session.session_id)
            
            # Log session context for monitoring
            logfire.debug("agent_context", 
                          current_recipes=len(session.current_batch_recipes),
                          saved_meals=len(session.saved_meals),
                          session_id=session.session_id)
            
            # Pydantic AI automatically handles dynamic system prompt and context
            result = recipe_discovery_agent.run_sync(
                user_input,
                deps=deps_with_session,
                message_history=message_history
            )
            
            # Update message history for conversation continuity
            message_history.extend(result.all_messages())
            
            agent_time = time.time() - agent_start
            logfire.info("agent_response_completed",
                         response_time=agent_time,
                         session_id=session.session_id)
            
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
            
            # Log results summary
            if tool_data:
                logfire.info("results_displayed",
                             total_results=tool_data['totalResults'],
                             search_query=tool_data['searchQuery'],
                             session_id=session.session_id)
                    
        except Exception as e:
            logfire.error("agent_error", 
                          error=str(e),
                          user_input=user_input,
                          session_id=session.session_id)
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
