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
    
    while True:
        user_input = input("\nWhat recipes would you like to find? > ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        try:
            print(f"\n⏱️  AGENT PROCESSING STARTED...")
            agent_start = time.time()
            
            result = recipe_discovery_agent.run_sync(
                user_input,
                deps=deps
            )
            
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
