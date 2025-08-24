from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pathlib import Path
from Structured_Output import AgentOutput
from Tools import search_and_extract_recipes
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
    openai_key=os.getenv("OPENAI_API_KEY")
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
            print(f"\n⏱️  AGENT PROCESSING STARTED...")
            agent_start = time.time()
            
            result = recipe_discovery_agent.run_sync(
                user_input,
                deps=deps
            )
            
            agent_time = time.time() - agent_start
            print(f"\n⏱️  AGENT RESPONSE GENERATION: {agent_time:.2f}s")
            
            # Display the response
            print(f"\n{result.output['response']}")
            print(f"\nFound {result.output['totalResults']} recipes for: {result.output['searchQuery']}")
            
            # Display structured data for iOS app verification
            if result.output['recipes']:
                print("\n" + "="*80)
                print("📱 STRUCTURED DATA FOR iOS APP:")
                print("="*80)
                import json
                for i, recipe in enumerate(result.output['recipes'], 1):
                    print(f"\n🍳 Recipe {i}:")
                    print(json.dumps(recipe, indent=2))
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
