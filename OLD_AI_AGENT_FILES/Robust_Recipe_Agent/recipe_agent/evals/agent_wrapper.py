"""
Agent Wrapper for Pydantic AI Evaluation

Adapts the Recipe Discovery Agent to work with Pydantic AI evaluation framework
by providing the correct interface and handling session management.
"""

import sys
from pathlib import Path
import os
from dotenv import load_dotenv

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from Discovery_Agent import recipe_discovery_agent
from recipe_agent.Dependencies import RecipeDeps, SessionContext

# Load environment variables
load_dotenv()


def agent_for_evaluation(user_input: str):
    """
    Wrapper function for evaluation - matches Pydantic Evals interface.
    
    Creates fresh session and dependencies for each test case to ensure
    isolated, reproducible evaluation results.
    
    Args:
        user_input: User query string to test
        
    Returns:
        Dict with agent response and tool outputs for evaluator analysis
    """
    
    # Create fresh session for each test (isolation)
    session = SessionContext()
    
    # Create dependencies with API keys
    deps = RecipeDeps(
        serpapi_key=os.getenv("SERPAPI_KEY"),
        firecrawl_key=os.getenv("FIRECRAWL_API_KEY"), 
        openai_key=os.getenv("OPENAI_API_KEY"),
        google_search_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
        session=session
    )
    
    # Run agent with test input (synchronous)
    result = recipe_discovery_agent.run_sync(user_input, deps=deps)
    
    # Return in format expected by evaluators
    return {
        'data': str(result),  # Agent's conversational response
        'all_messages': result.all_messages(),  # Complete message history including tool outputs
        'session_id': session.session_id,
        'metadata': {
            'test_input': user_input,
            'session_context': {
                'saved_meals_count': len(session.saved_meals),
                'shown_urls_count': len(session.shown_recipe_urls)
            }
        }
    }


def agent_for_evaluation_sync(user_input: str):
    """
    Synchronous wrapper - just calls the main function since it's already sync.
    """
    return agent_for_evaluation(user_input)


if __name__ == "__main__":
    # Quick test of wrapper functionality
    print("Testing agent wrapper...")
    
    test_result = agent_for_evaluation_sync("chicken recipes")
    print(f"Response: {test_result.get('data', 'No response')}")
    print(f"Messages count: {len(test_result.get('all_messages', []))}")
    print("Wrapper working correctly!")