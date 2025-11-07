"""
Pydantic AI Recipe Discovery Agent
Uses Pydantic AI framework with Three Pillar Intelligence and session memory.
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
class RecipeAgentDeps:
    """Dependencies for the Recipe Discovery Agent."""
    # API keys
    serpapi_key: str
    openai_key: str
    google_key: Optional[str] = None
    google_cx: Optional[str] = None
    
    # Tool instances
    search_tool: WebSearchTool = field(init=False)
    classification_tool: URLClassificationTool = field(init=False)
    recipe_parsing_tool: RecipeParsingTool = field(init=False)
    list_parsing_tool: ListParsingTool = field(init=False)
    
    # Performance intelligence
    scorer: AgentPerformanceScorer = field(init=False)
    session_tracker: SessionPerformanceTracker = field(init=False)
    
    # Session state (maintained across conversation)
    session_shown_urls: Set[str] = field(default_factory=set)
    session_recipe_bank: List[Dict] = field(default_factory=list)
    session_queries: List[str] = field(default_factory=list)
    
    # Current search state (reset per search)
    query_start_time: Optional[float] = None
    current_recipes: List[Dict] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize tool instances after dataclass creation."""
        self.search_tool = WebSearchTool(self.serpapi_key, self.google_key, self.google_cx)
        self.classification_tool = URLClassificationTool(self.openai_key)
        self.recipe_parsing_tool = RecipeParsingTool(self.openai_key)
        self.list_parsing_tool = ListParsingTool(self.openai_key)
        self.scorer = AgentPerformanceScorer()
        self.session_tracker = SessionPerformanceTracker()


class RecipeSearchResult(BaseModel):
    """Structured output for recipe search results."""
    recipes: List[Dict]
    total_found: int
    search_time: str
    agent_summary: str
    performance: Optional[Dict] = None


# Load system prompt
def load_system_prompt() -> str:
    """Load the system prompt from file."""
    prompt_path = Path(__file__).parent / "simplified_system_prompt.txt"
    try:
        return prompt_path.read_text()
    except FileNotFoundError:
        return """You are Loomi, an expert culinary AI assistant specializing in intelligent recipe discovery.
        Use your tools to find high-quality recipes that match user requirements with Speed > Quality > Accuracy priority."""


# Create the Pydantic AI agent (now with environment variables loaded)
recipe_agent = Agent(
    'openai:gpt-4o',
    deps_type=RecipeAgentDeps,
    system_prompt=load_system_prompt()
)


@recipe_agent.tool
async def search_for_recipe_urls(
    ctx: RunContext[RecipeAgentDeps], 
    query: str, 
    result_count: int = 25,
    search_strategy: str = "priority_only"
) -> Dict:
    """
    Search for recipe URLs using flexible strategies.
    Always start with priority_only strategy unless explicitly overridden.
    """
    return await ctx.deps.search_tool.search(
        query=query,
        result_count=result_count,
        search_strategy=search_strategy,
        exclude_urls=ctx.deps.session_shown_urls
    )


@recipe_agent.tool  
async def classify_recipe_urls(ctx: RunContext[RecipeAgentDeps], urls: List[Dict]) -> Dict:
    """
    Classify URLs as individual recipe pages or list/collection pages.
    Enriches URLs with type metadata for intelligent processing.
    """
    return await ctx.deps.classification_tool.classify_urls(urls)


@recipe_agent.tool
async def parse_individual_recipes(
    ctx: RunContext[RecipeAgentDeps], 
    urls: List[Dict], 
    parsing_depth: str = "standard",
    timeout_seconds: int = 15
) -> Dict:
    """
    Parse individual recipe pages to extract complete recipe data.
    Use aggressive timeouts for speed optimization.
    """
    # Filter to only recipe-type URLs
    recipe_urls = [url for url in urls if url.get("type") == "recipe"]
    
    if not recipe_urls:
        return {"parsed_recipes": [], "failed_urls": [], "parse_quality": "none"}
    
    return await ctx.deps.recipe_parsing_tool.parse_recipes(
        urls=recipe_urls,
        parsing_depth=parsing_depth,
        timeout_seconds=timeout_seconds
    )


@recipe_agent.tool
async def extract_recipes_from_lists(
    ctx: RunContext[RecipeAgentDeps],
    urls: List[Dict],
    max_recipes_per_list: int = 5
) -> Dict:
    """
    Extract individual recipe URLs from list/collection pages.
    Then parse the extracted recipes for complete data.
    """
    # Filter to only list-type URLs
    list_urls = [url for url in urls if url.get("type") == "list"]
    
    if not list_urls:
        return {"extracted_recipe_urls": [], "failed_lists": []}
    
    return await ctx.deps.list_parsing_tool.extract_recipe_urls_from_lists(
        urls=list_urls,
        max_recipes_per_list=max_recipes_per_list
    )


@recipe_agent.tool
def analyze_user_intent(ctx: RunContext[RecipeAgentDeps], user_query: str, target_count: int = 4) -> Dict:
    """
    Analyze user query to determine Three Pillar dial positions.
    Uses natural language understanding to set Speed/Quality/Accuracy priorities.
    """
    query_lower = user_query.lower()
    
    # Speed indicators
    speed_terms = ['quick', 'fast', 'easy', 'simple', 'tonight', 'right now', 'need something', 'urgent']
    speed_priority = any(term in query_lower for term in speed_terms) or target_count == 1
    
    # Quality indicators  
    quality_terms = ['beautiful', 'impressive', 'restaurant-quality', 'special', 'birthday', 'celebration', 'guests', 'amazing', 'perfect']
    quality_emphasis = any(term in query_lower for term in quality_terms)
    
    # Accuracy/constraint indicators
    accuracy_terms = ['gluten-free', 'vegan', 'dairy-free', 'protein', 'calories', 'keto', 'diabetic', 'no nuts', 'allergy']
    constraint_count = sum(1 for term in accuracy_terms if term in query_lower)
    high_accuracy_need = constraint_count >= 2
    
    # Session learning adaptation
    session_insights = ctx.deps.session_tracker.get_session_insights()
    avg_speed = session_insights.get("session_averages", {}).get("speed", 85)
    
    # Set dials based on user intent (ALWAYS start with priority_only)
    if speed_priority:
        speed_approach = "conservative"
        url_count = 12 if target_count <= 2 else 18
        search_strategy = "priority_only"
    elif high_accuracy_need:
        speed_approach = "standard" 
        url_count = min(target_count * 6, 35)
        search_strategy = "priority_only"
    elif quality_emphasis:
        speed_approach = "standard"
        url_count = min(target_count * 5, 25)
        search_strategy = "priority_only"
    else:
        # Balanced approach - ALWAYS start with priority_only
        speed_approach = "standard"
        url_count = min(target_count * 5, 25)
        search_strategy = "priority_only"  # Fixed: Always start with priority sites
    
    return {
        "speed_approach": speed_approach,
        "quality_approach": "high" if quality_emphasis else "balanced",  
        "accuracy_approach": "strict" if high_accuracy_need else "flexible",
        "url_count": url_count,
        "search_strategy": search_strategy,
        "user_priorities": {
            "speed_priority": speed_priority,
            "quality_emphasis": quality_emphasis, 
            "accuracy_critical": high_accuracy_need
        }
    }


@recipe_agent.tool
def start_recipe_search(ctx: RunContext[RecipeAgentDeps], user_query: str) -> str:
    """
    Initialize a new recipe search session.
    Sets up timing and resets current search state.
    """
    ctx.deps.query_start_time = time.time()
    ctx.deps.current_recipes = []
    
    # Track query context
    if user_query not in ctx.deps.session_queries:
        ctx.deps.session_queries.append(user_query)
    
    return f"Started recipe search for: '{user_query}'"


@recipe_agent.tool
def save_recipes_to_session_bank(ctx: RunContext[RecipeAgentDeps], recipes: List[Dict], user_query: str) -> str:
    """
    Save good recipes to session bank for future searches within this session.
    Enables intelligent recipe reuse and context building.
    """
    saved_count = 0
    
    for recipe in recipes:
        if _recipe_meets_basic_quality(recipe):
            # Create recipe bank entry with context
            bank_entry = {
                "recipe": recipe.copy(),
                "original_query": user_query,
                "saved_timestamp": time.time(),
                "source_domain": _extract_domain(recipe.get('source_url', '')),
                "quality_indicators": {
                    "has_image": bool(recipe.get('image_url')),
                    "ingredient_count": len(recipe.get('ingredients', [])),
                    "instruction_count": len(recipe.get('instructions', [])),
                    "has_nutrition": bool(recipe.get('nutrition'))
                }
            }
            
            # Avoid duplicates
            if not any(existing['recipe'].get('source_url') == recipe.get('source_url') 
                      for existing in ctx.deps.session_recipe_bank):
                ctx.deps.session_recipe_bank.append(bank_entry)
                saved_count += 1
    
    return f"Saved {saved_count} quality recipes to session bank (total: {len(ctx.deps.session_recipe_bank)})"


@recipe_agent.tool
def retrieve_relevant_past_recipes(ctx: RunContext[RecipeAgentDeps], current_query: str, max_recipes: int = 3) -> List[Dict]:
    """
    Retrieve past recipes from session bank that might be relevant to current query.
    Enables smart recipe supplementation from session history.
    """
    if not ctx.deps.session_recipe_bank:
        return []
    
    relevant_recipes = []
    current_words = set(current_query.lower().split())
    
    for bank_entry in ctx.deps.session_recipe_bank:
        recipe = bank_entry["recipe"]
        original_query = bank_entry["original_query"]
        
        # Calculate relevance score
        relevance_score = _calculate_recipe_relevance(recipe, original_query, current_query, current_words)
        
        if relevance_score > 0.3:  # Threshold for relevance
            recipe_with_score = recipe.copy()
            recipe_with_score["_session_relevance_score"] = relevance_score
            recipe_with_score["_from_session_bank"] = True
            recipe_with_score["_original_query"] = original_query
            relevant_recipes.append((recipe_with_score, relevance_score))
    
    # Sort by relevance and return top matches
    relevant_recipes.sort(key=lambda x: x[1], reverse=True)
    return [recipe for recipe, score in relevant_recipes[:max_recipes]]


@recipe_agent.tool
def calculate_performance_score(ctx: RunContext[RecipeAgentDeps], user_query: str, recipes: List[Dict], target_count: int = 4) -> Dict:
    """
    Calculate comprehensive performance scores for the search.
    Provides both tactical decision data and strategic learning insights.
    """
    if not ctx.deps.query_start_time:
        return {"error": "No search timing data available"}
    
    elapsed = time.time() - ctx.deps.query_start_time
    
    # Prepare result structure for scoring
    result = {
        "recipes": recipes,
        "total_found": len(recipes),
        "search_time": f"{elapsed:.1f} seconds"
    }
    
    # Performance scoring
    overall_score = ctx.deps.scorer.score_overall_search(user_query, result, elapsed, target_count)
    individual_scores = ctx.deps.scorer.score_individual_recipes(recipes, user_query)
    
    # Session learning
    ctx.deps.session_tracker.add_search_score(overall_score)
    
    return {
        "overall_score": {
            "speed": overall_score.speed,
            "quality": overall_score.quality,
            "accuracy": overall_score.accuracy,
            "overall": overall_score.overall,
            "grade": _get_grade(overall_score.overall)
        },
        "individual_scores": [
            {
                "domain": score.site_domain,
                "quality": score.quality_score,
                "accuracy": score.accuracy_score,
                "completeness": score.completeness_score
            }
            for score in individual_scores
        ],
        "session_insights": ctx.deps.session_tracker.get_session_insights(),
        "elapsed_time": elapsed
    }


@recipe_agent.tool
def update_session_state(ctx: RunContext[RecipeAgentDeps], recipes: List[Dict]) -> str:
    """
    Update session state with final recipes to avoid duplicates in future searches.
    """
    for recipe in recipes:
        url = recipe.get("source_url", "")
        if url:
            ctx.deps.session_shown_urls.add(url)
    
    return f"Updated session state with {len(recipes)} recipe URLs"


# Helper functions (not tools)
def _recipe_meets_basic_quality(recipe: Dict) -> bool:
    """Check if recipe meets basic quality standards for session storage."""
    return (
        bool(recipe.get('title')) and
        len(recipe.get('ingredients', [])) >= 3 and
        len(recipe.get('instructions', [])) >= 2 and
        bool(recipe.get('source_url'))
    )


def _extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url.lower())
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"


def _calculate_recipe_relevance(recipe: Dict, original_query: str, current_query: str, current_words: set) -> float:
    """Calculate how relevant a past recipe is to current query."""
    score = 0.0
    
    # Check title match
    title = recipe.get('title', '').lower()
    title_words = set(title.split())
    title_overlap = len(current_words.intersection(title_words))
    score += title_overlap * 0.3
    
    # Check ingredient match  
    ingredients_text = ' '.join(recipe.get('ingredients', [])).lower()
    ingredient_words = set(ingredients_text.split())
    ingredient_overlap = len(current_words.intersection(ingredient_words))
    score += ingredient_overlap * 0.2
    
    # Check original query similarity
    original_words = set(original_query.lower().split())
    query_overlap = len(current_words.intersection(original_words))
    score += query_overlap * 0.4
    
    # Boost for high-quality indicators
    if recipe.get('image_url'):
        score += 0.1
    if len(recipe.get('ingredients', [])) >= 5:
        score += 0.1
    
    return min(1.0, score)


def _get_grade(score: float) -> str:
    """Convert score to letter grade."""
    if score >= 90: return "A"
    elif score >= 80: return "B"
    elif score >= 70: return "C"
    elif score >= 60: return "D"
    else: return "F"


# Main interface function
async def find_recipes_with_pydantic_ai(
    user_query: str, 
    target_count: int = 4,
    serpapi_key: str = None,
    openai_key: str = None,
    google_key: str = None,
    google_cx: str = None
) -> Dict:
    """
    Main interface for finding recipes using Pydantic AI agent.
    Maintains session state across multiple calls within the same deps instance.
    """
    # Create or reuse dependencies
    deps = RecipeAgentDeps(
        serpapi_key=serpapi_key or os.getenv("SERPAPI_KEY"),
        openai_key=openai_key or os.getenv("OPENAI_API_KEY"),
        google_key=google_key or os.getenv("GOOGLE_SEARCH_KEY"),
        google_cx=google_cx or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    )
    
    # Use Pydantic AI agent to orchestrate the search
    result = await recipe_agent.run(
        f"Find {target_count} high-quality recipes for: {user_query}",
        deps=deps
    )
    
    # Return the result data directly (Pydantic AI handles the conversation)
    return result.data if hasattr(result, 'data') else result


if __name__ == "__main__":
    print("🤖 Pydantic AI Recipe Agent")
    print("Use test_pydantic_agent_cli.py for interactive testing")
    print("Or import this module to use the agent programmatically")