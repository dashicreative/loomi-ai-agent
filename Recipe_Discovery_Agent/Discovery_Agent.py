from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pathlib import Path
from Structured_Output import AgentOutput
from Tools.Tools import search_and_extract_recipes
from Dependencies import RecipeDeps
import os
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
serpapi_key = os.getenv("SERPAPI_KEY")
firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

print(f"DEBUG - SERPAPI_KEY loaded: {serpapi_key[:10]}..." if serpapi_key else "DEBUG - SERPAPI_KEY is None")
print(f"DEBUG - FIRECRAWL_KEY loaded: {firecrawl_key[:10]}..." if firecrawl_key else "DEBUG - FIRECRAWL_KEY is None")

deps = RecipeDeps(
    serpapi_key=serpapi_key,
    firecrawl_key=firecrawl_key,
    openai_key=openai_key
)



#Recipe discovery agent instantiation
recipe_discovery_agent = Agent(
    model,
    system_prompt=load_system_prompt("System_Prompt.txt"),
    output_type=AgentOutput,
    tools=[search_and_extract_recipes],
    deps_type=RecipeDeps
)
























# Interactive loop
def main():
    print("🍳 Recipe Discovery Agent")
    print("Type 'quit' to exit\n")
    
    while True:
        user_input = input("\nWhat recipes would you like to find? > ")
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        try:
            result = recipe_discovery_agent.run_sync(
                user_input,
                deps=deps
            )
            
            # Display the response
            print(f"\n{result.output['response']}")
            print(f"\nFound {result.output['totalResults']} recipes for: {result.output['searchQuery']}")
            
            # Display first few recipes if any
            if result.output['recipes']:
                print("\nTop recipes:")
                for i, recipe in enumerate(result.output['recipes'][:3], 1):
                    print(f"{i}. {recipe['title']} - Ready in {recipe['readyInMinutes']}")
                    
        except Exception as e:
            import traceback
            print(f"Error: {e}")
            print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
