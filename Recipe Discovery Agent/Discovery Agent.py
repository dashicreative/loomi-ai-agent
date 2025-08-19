from pydantic_ai import Agent, RunContext, SystemPrompt
from pathlib import Path
from Structured_Output import AgentOutput


# Load system prompt from file
def load_system_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent / "prompts" / filename
    with open(prompt_path, 'r') as f:
        return f.read()



#Recipe discovery agent instantiation

recipe_discovery_agent = Agent(
    SystemPrompt(load_system_prompt("System_Prompt.txt")),
    output_type=AgentOutput
)
