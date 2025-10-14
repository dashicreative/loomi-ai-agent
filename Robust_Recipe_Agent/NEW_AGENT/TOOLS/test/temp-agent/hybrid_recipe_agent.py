"""
Hybrid Recipe Discovery Agent - Best of Both Worlds
Combines simple agent speed with Pydantic AI intelligence using 2 composite tools.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import json

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Pydantic AI imports
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from web_search_tool import WebSearchTool
from url_classification_tool import URLClassificationTool  
from recipe_parsing_tool import RecipeParsingTool
from list_parsing_tool import ListParsingTool
from performance_scorer import AgentPerformanceScorer, SessionPerformanceTracker


@dataclass
class UserIntent:
    """User's recipe discovery intent - stored in session memory."""
    subject: Optional[str] = None           # "cheesecake", "pasta"
    dish_type: Optional[str] = None         # "breakfast", "dinner"
    ingredient_constraints: Optional[List[str]] = None
    allergy_constraints: Optional[List[str]] = None    # CRITICAL
    time_constraints: Optional[str] = None
    nutritional_constraints: Optional[List[str]] = None
    execution_constraints: Optional[List[str]] = None
    enhanced_query: Optional[str] = None    # Query with "recipe" added if needed


@dataclass
class HybridAgentDeps:
    """Dependencies for the Hybrid Recipe Discovery Agent."""
    # API keys
    serpapi_key: str
    openai_key: str
    google_key: Optional[str] = None
    google_cx: Optional[str] = None
    
    # Tool instances (initialized in post_init)
    search_tool: WebSearchTool = field(init=False)
    classification_tool: URLClassificationTool = field(init=False)
    recipe_parsing_tool: RecipeParsingTool = field(init=False)
    list_parsing_tool: ListParsingTool = field(init=False)
    
    # Performance tracking
    scorer: AgentPerformanceScorer = field(init=False)
    session_tracker: SessionPerformanceTracker = field(init=False)
    
    # Session state
    session_shown_urls: Set[str] = field(default_factory=set)
    session_recipe_bank: List[Dict] = field(default_factory=list)
    query_start_time: Optional[float] = None
    user_intent: Optional[UserIntent] = None    # Store intent across conversation
    
    def __post_init__(self):
        """Initialize tool instances after dataclass creation."""
        self.search_tool = WebSearchTool(self.serpapi_key, self.google_key, self.google_cx)
        self.classification_tool = URLClassificationTool(self.openai_key)
        self.recipe_parsing_tool = RecipeParsingTool(self.openai_key)
        self.list_parsing_tool = ListParsingTool(self.openai_key)
        self.scorer = AgentPerformanceScorer()
        self.session_tracker = SessionPerformanceTracker()


# Load system prompt
def load_hybrid_system_prompt() -> str:
    """Load the hybrid system prompt from file."""
    prompt_path = Path(__file__).parent / "hybrid_system_prompt.txt"
    try:
        return prompt_path.read_text()
    except FileNotFoundError:
        return """You are Loomi, an expert recipe discovery agent with 2 smart tools.
        Use search_and_parse_recipes for initial results, then parse_backlog_recipes if needed."""


# Create the Hybrid Pydantic AI agent
hybrid_agent = Agent(
    'openai:gpt-4o',
    deps_type=HybridAgentDeps,
    system_prompt=load_hybrid_system_prompt()
)


@hybrid_agent.tool
async def search_and_parse_recipes(
    ctx: RunContext[HybridAgentDeps],
    query: str,
    url_count: int = 25,
    search_strategy: str = "priority_only"
) -> Dict:
    """
    COMPOSITE TOOL: Complete search-to-recipes pipeline in one fast operation.
    
    Combines: Search → Classify → Parse individual recipes
    Returns: Parsed recipes + backlog list URLs for potential expansion
    
    This maintains the 6-second speed of the simple agent while giving
    the LLM strategic control over search parameters.
    """
    tool_start = time.time()
    print(f"🔍 [TOOL] Starting search_and_parse_recipes: {url_count} URLs, {search_strategy} strategy")
    
    if not ctx.deps.query_start_time:
        ctx.deps.query_start_time = time.time()
    
    try:
        # STEP 1: Search for URLs (existing WebSearchTool code)
        search_result = await ctx.deps.search_tool.search(
            query=query,
            result_count=url_count,
            search_strategy=search_strategy,
            exclude_urls=ctx.deps.session_shown_urls
        )
        
        if not search_result["urls"]:
            return {
                "parsed_recipes": [],
                "backlog_list_urls": [],
                "timing_info": {"error": "No URLs found"},
                "quality_assessment": "poor"
            }
        
        print(f"   Found {len(search_result['urls'])} URLs")
        
        # STEP 2: Classify URLs (existing URLClassificationTool code)
        classification_result = await ctx.deps.classification_tool.classify_urls(search_result["urls"])
        classified_urls = classification_result["classified_urls"]
        
        # Separate recipe URLs and list URLs
        recipe_urls = [url for url in classified_urls if url.get("type") == "recipe"]
        list_urls = [url for url in classified_urls if url.get("type") == "list"]
        
        print(f"   Classified: {len(recipe_urls)} recipe pages, {len(list_urls)} list pages")
        
        # STEP 3: Parse individual recipe URLs (existing RecipeParsingTool code)
        parsed_recipes = []
        if recipe_urls:
            recipe_parse_result = await ctx.deps.recipe_parsing_tool.parse_recipes(
                urls=recipe_urls,
                parsing_depth="standard",
                timeout_seconds=15  # Aggressive timeout for speed
            )
            parsed_recipes = recipe_parse_result["parsed_recipes"]
            print(f"   Parsed {len(parsed_recipes)} recipes successfully")
        
        # Calculate timing and quality
        elapsed = time.time() - ctx.deps.query_start_time
        quality_assessment = "excellent" if len(parsed_recipes) >= 3 else "good" if len(parsed_recipes) >= 1 else "poor"
        
        # Update session state with found URLs
        for recipe in parsed_recipes:
            if recipe.get("source_url"):
                ctx.deps.session_shown_urls.add(recipe["source_url"])
        
        result = {
            "parsed_recipes": parsed_recipes,
            "backlog_list_urls": list_urls,  # For potential Tool 2 usage
            "timing_info": {
                "elapsed_seconds": round(elapsed, 1),
                "recipes_per_second": round(len(parsed_recipes) / elapsed, 2) if elapsed > 0 else 0,
                "search_efficiency": f"{len(parsed_recipes)}/{url_count} URLs → recipes"
            },
            "quality_assessment": quality_assessment,
            "source_distribution": search_result.get("source_distribution", {}),
            "constraint_analysis": _analyze_constraint_satisfaction(parsed_recipes, query)
        }
        
        tool_elapsed = time.time() - tool_start
        print(f"✅ [TOOL] search_and_parse_recipes completed in {elapsed:.1f}s: {len(parsed_recipes)} recipes, {len(list_urls)} backlog URLs")
        print(f"⏱️ [TOOL] Total tool execution time: {tool_elapsed:.2f}s")
        return result
        
    except Exception as e:
        tool_elapsed = time.time() - tool_start
        print(f"❌ [TOOL] Error in search_and_parse_recipes after {tool_elapsed:.2f}s: {e}")
        return {
            "parsed_recipes": [],
            "backlog_list_urls": [],
            "timing_info": {"error": str(e)},
            "quality_assessment": "poor"
        }


@hybrid_agent.tool
async def parse_backlog_recipes(
    ctx: RunContext[HybridAgentDeps],
    backlog_list_urls: List[Dict],
    max_recipes_needed: int = 3
) -> Dict:
    """
    COMPOSITE TOOL: Extract and parse additional recipes from backlog list URLs.
    
    Combines: List extraction → Recipe parsing
    Used when initial search didn't find enough recipes.
    
    This skips the search step and processes the deferred list URLs.
    """
    print(f"🔄 Executing parse_backlog_recipes: {len(backlog_list_urls)} list URLs, need {max_recipes_needed} recipes")
    
    if not backlog_list_urls:
        return {
            "parsed_recipes": [],
            "timing_info": {"message": "No backlog URLs to process"}
        }
    
    start_time = time.time()
    
    try:
        # STEP 1: Extract recipe URLs from list pages (existing ListParsingTool code)
        list_extract_result = await ctx.deps.list_parsing_tool.extract_recipe_urls_from_lists(
            urls=backlog_list_urls,
            max_recipes_per_list=max(max_recipes_needed // len(backlog_list_urls), 2)
        )
        
        extracted_recipe_urls = list_extract_result["extracted_recipe_urls"]
        print(f"   Extracted {len(extracted_recipe_urls)} recipe URLs from lists")
        
        if not extracted_recipe_urls:
            return {
                "parsed_recipes": [],
                "timing_info": {"message": "No recipe URLs extracted from lists"}
            }
        
        # STEP 2: Parse extracted recipe URLs (existing RecipeParsingTool code)
        recipe_parse_result = await ctx.deps.recipe_parsing_tool.parse_recipes(
            urls=extracted_recipe_urls,
            parsing_depth="quick",  # Faster parsing for backlog
            timeout_seconds=10
        )
        
        parsed_recipes = recipe_parse_result["parsed_recipes"]
        print(f"   Parsed {len(parsed_recipes)} additional recipes from backlog")
        
        # Update session state
        for recipe in parsed_recipes:
            if recipe.get("source_url"):
                ctx.deps.session_shown_urls.add(recipe["source_url"])
        
        elapsed = time.time() - start_time
        
        result = {
            "parsed_recipes": parsed_recipes,
            "timing_info": {
                "elapsed_seconds": round(elapsed, 1),
                "extraction_efficiency": f"{len(extracted_recipe_urls)} URLs from {len(backlog_list_urls)} lists",
                "parsing_efficiency": f"{len(parsed_recipes)} recipes from {len(extracted_recipe_urls)} URLs"
            }
        }
        
        print(f"✅ parse_backlog_recipes completed in {elapsed:.1f}s: {len(parsed_recipes)} additional recipes")
        return result
        
    except Exception as e:
        print(f"❌ Error in parse_backlog_recipes: {e}")
        return {
            "parsed_recipes": [],
            "timing_info": {"error": str(e)}
        }


@hybrid_agent.tool
def analyze_user_intent(ctx: RunContext[HybridAgentDeps], user_query: str) -> str:
    """Analyze user query to extract intent and enhance query if needed."""
    print(f"🧠 [INTENT] Analyzing user intent for: '{user_query}'")
    
    # Simple intent analysis (can be enhanced later)
    query_lower = user_query.lower()
    
    # Extract subject (main dish/food item)
    food_terms = [
        'cake', 'cheesecake', 'bread', 'pizza', 'pasta', 'soup', 'salad',
        'chicken', 'beef', 'fish', 'dessert', 'cookies', 'pie', 'muffins',
        'steak', 'curry', 'tacos', 'burgers', 'sandwich', 'smoothie'
    ]
    
    subject = None
    for term in food_terms:
        if term in query_lower:
            subject = term
            break
    
    # Extract constraints (simplified for now)
    ingredient_constraints = []
    allergy_constraints = []
    
    if 'gluten-free' in query_lower:
        ingredient_constraints.append('gluten-free')
    if 'vegan' in query_lower:
        ingredient_constraints.append('vegan')
    if 'dairy-free' in query_lower:
        ingredient_constraints.append('dairy-free')
    if 'nut-free' in query_lower or 'no nuts' in query_lower:
        allergy_constraints.append('nuts')
    
    # Extract time constraints
    time_constraints = None
    if 'quick' in query_lower or 'fast' in query_lower:
        time_constraints = 'quick'
    elif 'under 30 minutes' in query_lower or '30 minutes' in query_lower:
        time_constraints = 'under 30 minutes'
    
    # Enhance query with "recipe" if needed
    enhanced_query = user_query
    recipe_terms = ['recipe', 'recipes', 'how to make', 'cooking', 'baking']
    has_recipe_term = any(term in query_lower for term in recipe_terms)
    
    if subject and not has_recipe_term:
        enhanced_query = f"{user_query} recipe"
        print(f"🧠 [INTENT] Enhanced query: '{enhanced_query}'")
    
    # Store intent in session memory
    ctx.deps.user_intent = UserIntent(
        subject=subject,
        ingredient_constraints=ingredient_constraints if ingredient_constraints else None,
        allergy_constraints=allergy_constraints if allergy_constraints else None,
        time_constraints=time_constraints,
        enhanced_query=enhanced_query
    )
    
    return f"Intent analyzed: subject='{subject}', enhanced_query='{enhanced_query}'"


@hybrid_agent.tool
def initialize_search(ctx: RunContext[HybridAgentDeps], user_query: str) -> str:
    """Initialize a new search session with timing."""
    ctx.deps.query_start_time = time.time()
    return f"Search initialized for: '{user_query}'"


# Helper functions
def _analyze_constraint_satisfaction(recipes: List[Dict], query: str) -> Dict:
    """Analyze how well recipes satisfy user constraints."""
    query_lower = query.lower()
    constraints = []
    
    # Simple constraint detection
    if 'gluten-free' in query_lower:
        constraints.append('gluten-free')
    if 'vegan' in query_lower:
        constraints.append('vegan')
    if 'quick' in query_lower or 'fast' in query_lower:
        constraints.append('quick')
    
    # Analyze recipe satisfaction (simplified)
    satisfied_count = 0
    for recipe in recipes:
        title = recipe.get('title', '').lower()
        ingredients = ' '.join(recipe.get('ingredients', [])).lower()
        recipe_text = f"{title} {ingredients}"
        
        recipe_satisfies = True
        for constraint in constraints:
            if constraint == 'gluten-free' and 'flour' in recipe_text:
                recipe_satisfies = False
            elif constraint == 'vegan' and any(non_vegan in recipe_text for non_vegan in ['chicken', 'beef', 'milk', 'egg']):
                recipe_satisfies = False
            elif constraint == 'quick' and recipe.get('cook_time', '').replace('PT', '').replace('M', '').isdigit():
                cook_minutes = int(recipe.get('cook_time', 'PT999M').replace('PT', '').replace('M', ''))
                if cook_minutes > 30:
                    recipe_satisfies = False
        
        if recipe_satisfies:
            satisfied_count += 1
    
    return {
        "constraints_identified": constraints,
        "total_recipes": len(recipes),
        "satisfied_count": satisfied_count,
        "satisfaction_rate": round(satisfied_count / len(recipes) * 100, 1) if recipes else 0
    }


# Main interface function for testing
async def find_recipes_with_hybrid_agent(
    user_query: str, 
    target_count: int = 4,
    serpapi_key: str = None,
    openai_key: str = None,
    google_key: str = None,
    google_cx: str = None
) -> str:
    """
    Main interface for finding recipes using Hybrid AI agent.
    Returns raw results for debugging with detailed timing.
    """
    overall_start = time.time()
    
    # Create dependencies
    print(f"⏱️ [DEBUG] Creating dependencies...")
    deps_start = time.time()
    deps = HybridAgentDeps(
        serpapi_key=serpapi_key or os.getenv("SERPAPI_KEY"),
        openai_key=openai_key or os.getenv("OPENAI_API_KEY"),
        google_key=google_key or os.getenv("GOOGLE_SEARCH_KEY"),
        google_cx=google_cx or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    )
    deps_elapsed = time.time() - deps_start
    print(f"⏱️ [DEBUG] Dependencies created in {deps_elapsed:.2f}s")
    
    # Use Hybrid AI agent to orchestrate the search
    print(f"⏱️ [DEBUG] Starting Pydantic AI agent.run()...")
    agent_start = time.time()
    
    result = await hybrid_agent.run(
        f"Find {target_count} high-quality recipes for: {user_query}",
        deps=deps
    )
    
    agent_elapsed = time.time() - agent_start
    overall_elapsed = time.time() - overall_start
    
    print(f"⏱️ [DEBUG] Pydantic AI agent.run() completed in {agent_elapsed:.2f}s")
    print(f"⏱️ [DEBUG] Total function time: {overall_elapsed:.2f}s")
    print(f"⏱️ [DEBUG] BREAKDOWN:")
    print(f"⏱️ [DEBUG]   - Dependencies: {deps_elapsed:.2f}s")
    print(f"⏱️ [DEBUG]   - Agent orchestration: {agent_elapsed:.2f}s") 
    print(f"⏱️ [DEBUG]   - Overhead: {(overall_elapsed - deps_elapsed - agent_elapsed):.2f}s")
    
    if hasattr(deps, 'query_start_time') and deps.query_start_time:
        tool_elapsed = time.time() - deps.query_start_time
        agent_reasoning_time = agent_elapsed - tool_elapsed
        print(f"⏱️ [DEBUG] DETAILED BREAKDOWN:")
        print(f"⏱️ [DEBUG]   - Tool execution: {tool_elapsed:.2f}s")
        print(f"⏱️ [DEBUG]   - Agent reasoning/formatting: {agent_reasoning_time:.2f}s")
    
    # Return the agent's response (should include raw tool data)
    return result.data if hasattr(result, 'data') else str(result)


if __name__ == "__main__":
    print("🤖 Hybrid Recipe Agent - Best of Both Worlds")
    print("Use test_hybrid_agent_cli.py for interactive testing")
    print("Or import this module to use the agent programmatically")