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
    original_query: Optional[str] = None    # Raw user input - prevent hallucination
    enhanced_query: Optional[str] = None    # Query with "recipe" added if needed
    subject: Optional[str] = None           # "cheesecake", "pasta"
    dish_type: Optional[str] = None         # "breakfast", "dinner"
    ingredient_constraints: Optional[List[str]] = None
    allergy_constraints: Optional[List[str]] = None    # CRITICAL
    time_constraints: Optional[str] = None
    nutritional_constraints: Optional[List[str]] = None
    execution_constraints: Optional[List[str]] = None


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
    
    # Recipe memory RAG system
    recipe_memory: Dict[str, Dict] = field(default_factory=dict)  # recipe_id -> full_recipe_object
    recipe_counter: int = field(default=0)  # For generating unique IDs
    
    # Session query tracking (Phase 1: in-session only)
    session_queries: List[Dict] = field(default_factory=list)  # Query history for session
    query_counter: int = field(default=0)  # For generating query IDs
    current_query_id: Optional[str] = None  # Current search context
    
    # Intent-based attempt tracking
    intent_history: List[Dict] = field(default_factory=list)  # Intent-based search tracking
    intent_counter: int = field(default=0)  # For generating intent IDs
    current_intent_id: Optional[str] = None  # Links related searches
    current_attempt: int = field(default=0)  # Attempt number for current intent
    
    # User interaction tracking (Phase 1: in-session only)  
    user_interactions: Dict[str, List[str]] = field(default_factory=dict)  # recipe_id -> [actions]
    
    
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
    subject: str = None,
    dietary_constraints: List[str] = [],
    query_allergies: List[str] = [],
    user_profile_allergies: List[str] = [],
    ignore_profile_allergies: bool = False,
    nutrition_requirements: List[str] = [],
    time_constraints: str = None,
    is_continuation: bool = False,
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
    # Combine allergy constraints for comprehensive safety
    combined_allergies = []
    if not ignore_profile_allergies:
        combined_allergies.extend(user_profile_allergies)
    combined_allergies.extend(query_allergies)
    # Remove duplicates while preserving order
    combined_allergies = list(dict.fromkeys(combined_allergies))
    
    print(f"🎯 [CONSTRAINTS] Agent passed: subject='{subject}', dietary={dietary_constraints}, allergies={combined_allergies}, nutrition={nutrition_requirements}, time={time_constraints}")
    if user_profile_allergies and ignore_profile_allergies:
        print(f"⚠️ [SAFETY] Profile allergies ignored for this search: {user_profile_allergies}")
    
    if not ctx.deps.query_start_time:
        ctx.deps.query_start_time = time.time()
    
    # Handle intent tracking (new vs continuation)
    if is_continuation and ctx.deps.current_intent_id:
        # Continuing existing intent
        ctx.deps.current_attempt += 1
        print(f"🔄 [INTENT] Continuing intent {ctx.deps.current_intent_id}, attempt {ctx.deps.current_attempt}")
        
        # Escalate search strategy based on attempt number
        if ctx.deps.current_attempt == 2:
            search_strategy = "mixed" if search_strategy == "priority_only" else search_strategy
        elif ctx.deps.current_attempt >= 3:
            search_strategy = "broad"
        print(f"📈 [ESCALATION] Attempt {ctx.deps.current_attempt} using {search_strategy} strategy")
    else:
        # New intent
        ctx.deps.intent_counter += 1
        ctx.deps.current_intent_id = f"intent_{ctx.deps.intent_counter:03d}"
        ctx.deps.current_attempt = 1
        print(f"🆕 [INTENT] Started new intent {ctx.deps.current_intent_id}, attempt 1")
    
    # Create query ID for this specific search
    ctx.deps.query_counter += 1
    ctx.deps.current_query_id = f"search_{ctx.deps.query_counter:03d}"
    print(f"🔍 [QUERY] Started search {ctx.deps.current_query_id}")
    
    # Create constraint object from agent parameters
    agent_constraints = {
        "subject": subject,
        "dietary_constraints": dietary_constraints,
        "allergy_constraints": combined_allergies,  # Use combined list
        "nutrition_requirements": nutrition_requirements,
        "time_constraints": time_constraints
    }
    
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
        
        # PARALLEL LLM CONSTRAINT VERIFICATION
        constraint_results = []
        if ctx.deps.user_intent and parsed_recipes:
            constraint_results = await _verify_constraints_with_parallel_llm(
                parsed_recipes, 
                ctx.deps.user_intent, 
                ctx.deps.openai_key
            )
        
        # RECIPE MEMORY RAG SYSTEM - Store full recipes, return summaries
        recipe_summaries = []
        for i, recipe in enumerate(parsed_recipes):
            # Generate unique recipe ID
            ctx.deps.recipe_counter += 1
            recipe_id = f"session_recipe_{ctx.deps.recipe_counter:03d}"
            
            # Store full recipe in memory
            ctx.deps.recipe_memory[recipe_id] = recipe.copy()
            
            # Get constraint results for this recipe
            constraint_details = {}
            simple_scores = {"accuracy": 100.0, "quality": 100.0, "speed": 100.0}
            
            if i < len(constraint_results) and not isinstance(constraint_results[i], Exception):
                constraint_data = constraint_results[i]
                if constraint_data.get("llm_verified"):
                    constraint_details = constraint_data.get("constraint_results", {})
                    
                    # Calculate accuracy score
                    total_constraints = len(constraint_details)
                    satisfied_constraints = sum(1 for satisfied in constraint_details.values() if satisfied)
                    accuracy_score = round((satisfied_constraints / total_constraints * 100), 1) if total_constraints > 0 else 100.0
                    simple_scores["accuracy"] = accuracy_score
            
            # Calculate quality score
            domain = _extract_domain_from_url(recipe.get('source_url', ''))
            has_image = bool(recipe.get('image_url'))
            is_priority_site = any(priority in domain for priority in ['allrecipes.com', 'simplyrecipes.com', 'seriouseats.com', 'food52.com', 'budgetbytes.com'])
            quality_score = 100.0 if is_priority_site and has_image else 80.0 if is_priority_site else 60.0 if has_image else 40.0
            simple_scores["quality"] = quality_score
            
            # Add query context and position to stored recipe
            recipe_with_context = recipe.copy()
            recipe_with_context.update({
                "recipe_id": recipe_id,
                "query_id": ctx.deps.current_query_id,
                "user_position": i + 1,  # Position in search results (1, 2, 3, etc.)
                "shown_to_user": True,   # Recipes from search tool are shown
                "timestamp": time.time()
            })
            
            # Store full recipe in memory with context
            ctx.deps.recipe_memory[recipe_id] = recipe_with_context
            
            # Create recipe summary for agent
            recipe_summary = {
                "recipe_id": recipe_id,
                "query_id": ctx.deps.current_query_id,
                "user_position": i + 1,
                "title": recipe.get('title', ''),
                "url": recipe.get('source_url', ''),
                "simple_scores": simple_scores,
                "constraint_details": constraint_details,
                "source_domain": domain,
                "has_image": has_image,
                "cook_time_minutes": _extract_cook_time_minutes(recipe.get('cook_time', '')),
                
                # Minimal reference data (only for cross-referencing if needed)
                "ingredients_summary": f"{len(recipe.get('ingredients', []))} ingredients",
                "instructions_summary": f"{len(recipe.get('instructions', []))} steps"
            }
            
            recipe_summaries.append(recipe_summary)
        
        print(f"💾 [MEMORY] Stored {len(recipe_summaries)} recipes in session memory (IDs: {ctx.deps.recipe_counter-len(recipe_summaries)+1:03d}-{ctx.deps.recipe_counter:03d})")
        
        # Calculate accuracy for intent tracking
        total_constraints = len([c for c in agent_constraints.values() if c])
        accuracy_sum = sum(constraint.get('simple_scores', {}).get('accuracy', 0) for constraint in _check_recipes_against_constraints(parsed_recipes, agent_constraints))
        average_accuracy = accuracy_sum / len(parsed_recipes) if parsed_recipes else 0
        
        # Save attempt to intent tracking
        attempt_record = {
            "attempt_number": ctx.deps.current_attempt,
            "query_id": ctx.deps.current_query_id,
            "search_strategy": search_strategy,
            "recipes_found": len(parsed_recipes),
            "average_accuracy": round(average_accuracy, 1),
            "timestamp": time.time()
        }
        
        # Update or create intent history
        if ctx.deps.current_intent_id:
            # Find existing intent or create new
            intent_record = None
            for intent in ctx.deps.intent_history:
                if intent["intent_id"] == ctx.deps.current_intent_id:
                    intent_record = intent
                    break
            
            if not intent_record:
                # New intent record
                intent_record = {
                    "intent_id": ctx.deps.current_intent_id,
                    "original_query": query,
                    "subject": subject,
                    "constraints": agent_constraints,
                    "attempts": [],
                    "best_accuracy": 0,
                    "total_recipes_found": 0
                }
                ctx.deps.intent_history.append(intent_record)
            
            # Add this attempt
            intent_record["attempts"].append(attempt_record)
            intent_record["best_accuracy"] = max(intent_record["best_accuracy"], average_accuracy)
            intent_record["total_recipes_found"] += len(parsed_recipes)
            
            print(f"📊 [INTENT] Intent {ctx.deps.current_intent_id}: attempt {ctx.deps.current_attempt}, accuracy {average_accuracy:.1f}%")
        
        # Save query to session history for reference resolution
        if recipe_summaries:
            query_record = {
                "query_id": ctx.deps.current_query_id,
                "intent_id": ctx.deps.current_intent_id,
                "attempt_number": ctx.deps.current_attempt,
                "user_query": query,
                "recipe_ids": [summary["recipe_id"] for summary in recipe_summaries],
                "recipe_count": len(recipe_summaries),
                "constraints_used": agent_constraints,
                "timestamp": time.time(),
                "search_strategy": search_strategy
            }
            ctx.deps.session_queries.append(query_record)
            print(f"📚 [HISTORY] Saved query {ctx.deps.current_query_id}: '{query}' → {len(recipe_summaries)} recipes")
        
        result = {
            "recipe_summaries": recipe_summaries,  # Return summaries, not full recipes
            "backlog_list_urls": list_urls,
            "timing_info": {
                "elapsed_seconds": round(elapsed, 1),
                "recipes_per_second": round(len(parsed_recipes) / elapsed, 2) if elapsed > 0 else 0,
                "search_efficiency": f"{len(parsed_recipes)}/{url_count} URLs → recipes"
            },
            "quality_assessment": quality_assessment,
            "source_distribution": search_result.get("source_distribution", {}),
            "recipes_with_constraints": _check_recipes_against_constraints(parsed_recipes, agent_constraints),
            "intent_context": {
                "intent_id": ctx.deps.current_intent_id,
                "attempt_number": ctx.deps.current_attempt,
                "average_accuracy": round(average_accuracy, 1),
                "search_strategy_used": search_strategy,
                "is_continuation": is_continuation
            }
        }
        
        tool_elapsed = time.time() - tool_start
        print(f"✅ [TOOL] search_and_parse_recipes completed in {elapsed:.1f}s: {len(parsed_recipes)} recipes, {len(list_urls)} backlog URLs")
        print(f"⏱️ [TOOL] Total tool execution time: {tool_elapsed:.2f}s")
        
        # DEBUG: Show complete search tool output that agent receives
        print(f"\n🔍 [DEBUG] COMPLETE SEARCH TOOL OUTPUT TO AGENT:")
        print("=" * 80)
        
        # Print high-level data
        print(f"📊 Quality Assessment: {result['quality_assessment']}")
        print(f"📊 Source Distribution: {result['source_distribution']}")
        print(f"📊 Timing Info: {result['timing_info']}")
        print(f"📊 Intent Context: {result['intent_context']}")
        print(f"📋 Recipe Summaries: {len(result['recipe_summaries'])} items")
        print(f"📋 Constraint Analysis: {len(result['recipes_with_constraints'])} items")
        print(f"📋 Backlog URLs: {len(result['backlog_list_urls'])} items")
        
        # Print ALL recipe summaries (what agent uses for decisions)
        print(f"\n📝 ALL RECIPE SUMMARIES (Agent Decision Data):")
        for i, summary in enumerate(result['recipe_summaries'], 1):
            print(f"\\n   Recipe {i}:")
            print(f"      ID: {summary.get('recipe_id', 'Unknown')}")
            print(f"      Title: {summary.get('title', 'Unknown')}")
            print(f"      URL: {summary.get('url', 'Unknown')}")
            print(f"      Simple Scores: {summary.get('simple_scores', {})}")
            print(f"      Constraint Details: {summary.get('constraint_details', {})}")
            print(f"      Domain: {summary.get('source_domain', 'Unknown')}")
            print(f"      Has Image: {summary.get('has_image', False)}")
            print(f"      Cook Time: {summary.get('cook_time_minutes', 'Unknown')} minutes")
            print(f"      Ingredients: {summary.get('ingredients_summary', 'Unknown')}")
            print(f"      Instructions: {summary.get('instructions_summary', 'Unknown')}")
        
        # Print constraint verification details
        print(f"\\n📊 CONSTRAINT VERIFICATION DETAILS:")
        for i, constraint in enumerate(result['recipes_with_constraints'], 1):
            print(f"\\n   Recipe {i} Constraints:")
            print(f"      Title: {constraint.get('recipe_title', 'Unknown')}")
            print(f"      Simple Scores: {constraint.get('simple_scores', {})}")
            print(f"      Constraint Details: {constraint.get('constraint_details', {})}")
        
        print("=" * 80)
        
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
        
        # PARALLEL LLM CONSTRAINT VERIFICATION (same as main tool)
        constraint_results = []
        if ctx.deps.user_intent and parsed_recipes:
            constraint_results = await _verify_constraints_with_parallel_llm(
                parsed_recipes, 
                ctx.deps.user_intent, 
                ctx.deps.openai_key
            )
        
        # RECIPE MEMORY RAG SYSTEM - Store backlog recipes too
        recipe_summaries = []
        for i, recipe in enumerate(parsed_recipes):
            # Generate unique recipe ID
            ctx.deps.recipe_counter += 1
            recipe_id = f"session_recipe_{ctx.deps.recipe_counter:03d}"
            
            # Store full recipe in memory
            ctx.deps.recipe_memory[recipe_id] = recipe.copy()
            
            # Get constraint results for this recipe
            constraint_details = {}
            simple_scores = {"accuracy": 100.0, "quality": 100.0, "speed": 100.0}
            
            if i < len(constraint_results) and not isinstance(constraint_results[i], Exception):
                constraint_data = constraint_results[i]
                if constraint_data.get("llm_verified"):
                    constraint_details = constraint_data.get("constraint_results", {})
                    
                    # Calculate accuracy score
                    total_constraints = len(constraint_details)
                    satisfied_constraints = sum(1 for satisfied in constraint_details.values() if satisfied)
                    accuracy_score = round((satisfied_constraints / total_constraints * 100), 1) if total_constraints > 0 else 100.0
                    simple_scores["accuracy"] = accuracy_score
            
            # Calculate quality score
            domain = _extract_domain_from_url(recipe.get('source_url', ''))
            has_image = bool(recipe.get('image_url'))
            is_priority_site = any(priority in domain for priority in ['allrecipes.com', 'simplyrecipes.com', 'seriouseats.com', 'food52.com', 'budgetbytes.com'])
            quality_score = 100.0 if is_priority_site and has_image else 80.0 if is_priority_site else 60.0 if has_image else 40.0
            simple_scores["quality"] = quality_score
            
            # Create recipe summary for agent
            recipe_summary = {
                "recipe_id": recipe_id,
                "title": recipe.get('title', ''),
                "url": recipe.get('source_url', ''),
                "simple_scores": simple_scores,
                "constraint_details": constraint_details,
                "source_domain": domain,
                "has_image": has_image,
                "cook_time_minutes": _extract_cook_time_minutes(recipe.get('cook_time', '')),
                "ingredients_summary": f"{len(recipe.get('ingredients', []))} ingredients",
                "instructions_summary": f"{len(recipe.get('instructions', []))} steps"
            }
            
            recipe_summaries.append(recipe_summary)
        
        elapsed = time.time() - start_time
        
        result = {
            "recipe_summaries": recipe_summaries,  # ← Return summaries, not full recipes
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


    # Agent handles intent internally - no tool needed!
    intent_elapsed = time.time() - intent_start
    print(f"⏱️ [INTENT] Intent analysis completed in {intent_elapsed:.2f}s")
    
    return f"Agent should extract constraints internally and pass to search tool"


@hybrid_agent.tool
def get_full_recipe_details(ctx: RunContext[HybridAgentDeps], recipe_id: str) -> Dict:
    """
    Retrieve full recipe details from memory by recipe ID.
    Use this only when you need complete ingredient/instruction details for decision-making.
    """
    if recipe_id not in ctx.deps.recipe_memory:
        return {"error": f"Recipe ID {recipe_id} not found in memory"}
    
    full_recipe = ctx.deps.recipe_memory[recipe_id]
    
    print(f"📖 [MEMORY] Retrieved full details for recipe {recipe_id}: {full_recipe.get('title', 'Unknown')}")
    
    return {
        "recipe_id": recipe_id,
        "full_recipe": full_recipe,
        "ingredients": full_recipe.get('ingredients', []),
        "instructions": full_recipe.get('instructions', []),
        "nutrition": full_recipe.get('nutrition', []),
        "cook_time": full_recipe.get('cook_time', ''),
        "servings": full_recipe.get('servings', '')
    }


@hybrid_agent.tool
def find_recipe_by_reference(
    ctx: RunContext[HybridAgentDeps], 
    user_description: str,
    search_reference: str = "last"
) -> Dict:
    """
    Find a specific recipe from session memory based on user description.
    Use when user references specific recipes: "the scottish one", "recipe #3", "the quick one"
    """
    print(f"🔍 [REFERENCE] Resolving user reference: '{user_description}' from {search_reference} search")
    
    if not ctx.deps.session_queries:
        return {
            "error": "No previous searches in session",
            "message": "No previous searches to reference. Would you like me to find some recipes?"
        }
    
    # Determine which search to look in
    if search_reference == "last":
        target_query = ctx.deps.session_queries[-1]
    else:
        # Could add logic for "second to last", etc.
        target_query = ctx.deps.session_queries[-1]
    
    # Find matching recipe based on description
    matching_recipes = []
    for recipe_id in target_query["recipe_ids"]:
        if recipe_id in ctx.deps.recipe_memory:
            recipe = ctx.deps.recipe_memory[recipe_id]
            match_score = _calculate_reference_match(recipe, user_description)
            if match_score > 0:
                matching_recipes.append((recipe_id, recipe, match_score))
    
    if not matching_recipes:
        return {
            "error": "No matching recipe found",
            "message": f"Couldn't find a recipe matching '{user_description}' from your {search_reference} search"
        }
    
    # Sort by match score and return best match
    matching_recipes.sort(key=lambda x: x[2], reverse=True)
    best_match_id, best_match_recipe, score = matching_recipes[0]
    
    result = {
        "recipe_id": best_match_id,
        "recipe_title": best_match_recipe.get('title', ''),
        "user_position": best_match_recipe.get('user_position', 'Unknown'),
        "match_confidence": score,
        "query_context": {
            "query_id": target_query["query_id"],
            "original_query": target_query["user_query"]
        },
        "message": f"Found recipe: {best_match_recipe.get('title', 'Unknown')}"
    }
    
    print(f"✅ [REFERENCE] Resolved '{user_description}' → {best_match_id} (confidence: {score:.2f})")
    return result


def _calculate_reference_match(recipe: Dict, user_description: str) -> float:
    """Calculate how well a recipe matches a user's description."""
    description_lower = user_description.lower()
    title_lower = recipe.get('title', '').lower()
    
    match_score = 0.0
    
    # Direct title matching
    if any(word in title_lower for word in description_lower.split() if len(word) > 3):
        match_score += 0.5
    
    # Position references  
    if 'first' in description_lower or '#1' in description_lower:
        match_score += 1.0 if recipe.get('user_position') == 1 else 0.0
    elif 'second' in description_lower or '#2' in description_lower:
        match_score += 1.0 if recipe.get('user_position') == 2 else 0.0
    elif 'third' in description_lower or '#3' in description_lower:
        match_score += 1.0 if recipe.get('user_position') == 3 else 0.0
    elif 'last' in description_lower:
        # Would need to know total count, but approximate
        match_score += 0.8 if recipe.get('user_position', 0) >= 3 else 0.0
    
    # Characteristic matching
    if 'quick' in description_lower:
        cook_time = recipe.get('cook_time_minutes')
        match_score += 0.7 if cook_time and cook_time <= 30 else 0.0
    
    # Cuisine/style matching
    cuisine_terms = ['scottish', 'italian', 'mexican', 'asian', 'french', 'american']
    for term in cuisine_terms:
        if term in description_lower and term in title_lower:
            match_score += 0.8
    
    return min(1.0, match_score)


@hybrid_agent.tool  
def track_user_interaction(
    ctx: RunContext[HybridAgentDeps],
    recipe_id: str,
    interaction_type: str
) -> str:
    """
    Track user interactions with recipes for session context.
    Use when you know user performed specific actions.
    """
    if recipe_id not in ctx.deps.recipe_memory:
        return f"Recipe {recipe_id} not found in session memory"
    
    # Initialize interaction list if not exists
    if recipe_id not in ctx.deps.user_interactions:
        ctx.deps.user_interactions[recipe_id] = []
    
    # Add interaction if not already tracked
    if interaction_type not in ctx.deps.user_interactions[recipe_id]:
        ctx.deps.user_interactions[recipe_id].append(interaction_type)
        print(f"👆 [INTERACTION] User {interaction_type} recipe {recipe_id}")
    
    return f"Tracked user interaction: {interaction_type} for {recipe_id}"


@hybrid_agent.tool
def initialize_search(ctx: RunContext[HybridAgentDeps], user_query: str) -> str:
    """Initialize a new search session with timing."""
    ctx.deps.query_start_time = time.time()
    return f"Search initialized for: '{user_query}'"




async def _verify_constraints_with_parallel_llm(
    recipes: List[Dict], 
    user_intent: Optional[UserIntent],
    openai_key: str
) -> List[Dict]:
    """Verify recipe constraints using parallel LLM calls for accuracy."""
    import asyncio
    from openai import AsyncOpenAI
    
    if not recipes or not user_intent:
        return []
    
    print(f"🧠 [CONSTRAINT] Starting {len(recipes)} parallel LLM constraint checks...")
    
    # Create async OpenAI client
    client = AsyncOpenAI(api_key=openai_key)
    
    # Create parallel tasks for each recipe
    tasks = []
    for recipe in recipes:
        task = _check_single_recipe_with_llm(client, recipe, user_intent)
        tasks.append(task)
    
    # Execute all constraint checks in parallel
    constraint_start = time.time()
    constraint_results = await asyncio.gather(*tasks, return_exceptions=True)
    constraint_elapsed = time.time() - constraint_start
    
    print(f"🧠 [CONSTRAINT] Parallel LLM checks completed in {constraint_elapsed:.2f}s")
    
    return constraint_results


async def _check_single_recipe_with_llm(
    client, 
    recipe: Dict, 
    user_intent: UserIntent
) -> Dict:
    """Single LLM call to verify all constraints for one recipe."""
    try:
        # Build constraint list including subject matching
        constraints_to_check = []
        
        # Subject match constraint (critical!)
        if user_intent.subject:
            constraints_to_check.append(f"subject_match_{user_intent.subject}")
        
        # Add other constraints
        if user_intent.ingredient_constraints:
            constraints_to_check.extend(user_intent.ingredient_constraints)
        if user_intent.allergy_constraints:
            constraints_to_check.extend([f"{allergy}_excluded" for allergy in user_intent.allergy_constraints])
        if user_intent.nutritional_constraints:
            constraints_to_check.extend(user_intent.nutritional_constraints)
        if user_intent.time_constraints:
            constraints_to_check.append(user_intent.time_constraints)
        
        # Create focused prompt with few-shot examples
        prompt = f"""Verify if this recipe satisfies these constraints. Return exact JSON format only.

FEW-SHOT EXAMPLES:

Example 1:
Recipe: "Chocolate Chip Cookies" with oat flour, dairy-free chocolate chips, 15g protein
Constraints: ["subject_match_cookies", "gluten_free", "dairy_free", "min_protein_20g"]
Output: {{"subject_match": true, "gluten_free": true, "dairy_free": true, "min_protein_20g": false}}

Example 2: 
Recipe: "Strawberry Cake" with regular flour, strawberries, 300 calories
Constraints: ["subject_match_cheesecake", "gluten_free", "max_calories_250"]  
Output: {{"subject_match": false, "gluten_free": false, "max_calories_250": false}}

Example 3:
Recipe: "Vegan Strawberry Cheesecake" with cashews, strawberries, almond flour, 25g protein
Constraints: ["subject_match_cheesecake", "vegan", "gluten_free", "min_protein_20g"]
Output: {{"subject_match": true, "vegan": true, "gluten_free": true, "min_protein_20g": true}}

NOW CHECK THIS RECIPE:

Recipe Title: "{recipe.get('title', '')}"
Ingredients: {recipe.get('ingredients', [])}
Nutrition: {recipe.get('nutrition', [])}
Cook Time: {recipe.get('cook_time', '')}

Constraints to verify: {constraints_to_check}

Return only the JSON with true/false for each constraint:"""

        # Make LLM call
        response = await client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cheap for constraint checking
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=200    # Short response expected
        )
        
        # Parse JSON response
        import json
        constraint_results = json.loads(response.choices[0].message.content.strip())
        
        return {
            "recipe_title": recipe.get('title', ''),
            "constraint_results": constraint_results,
            "llm_verified": True
        }
        
    except Exception as e:
        print(f"❌ [CONSTRAINT] LLM verification failed for {recipe.get('title', 'Unknown')}: {e}")
        # Fallback to keyword matching
        return {
            "recipe_title": recipe.get('title', ''),
            "constraint_results": {},
            "llm_verified": False
        }


# Helper functions  
def _check_recipes_against_constraints(recipes: List[Dict], agent_constraints: Dict) -> List[Dict]:
    """Check each recipe against agent-provided constraints and return detailed constraint satisfaction."""
    if not recipes:
        return []
    
    # Extract constraint parameters from agent
    subject = agent_constraints.get("subject")
    dietary_constraints = agent_constraints.get("dietary_constraints", [])
    allergy_constraints = agent_constraints.get("allergy_constraints", [])
    nutrition_requirements = agent_constraints.get("nutrition_requirements", [])
    time_constraints = agent_constraints.get("time_constraints")
    
    # Check if agent provided any constraints (including subject)
    has_constraints = any([subject, dietary_constraints, allergy_constraints, nutrition_requirements, time_constraints])
    
    if not has_constraints:
        # No constraints - return recipes with basic scoring
        return [{"recipe_title": r.get("title"), "recipe_url": r.get("source_url"), "constraint_details": {"no_constraints": True}} for r in recipes]
    
    results = []
    
    for recipe in recipes:
        title = recipe.get('title', '')
        ingredients_text = ' '.join(recipe.get('ingredients', [])).lower()
        nutrition = recipe.get('nutrition', [])
        cook_time = recipe.get('cook_time', '')
        
        # Detailed constraint checking per recipe
        constraint_details = {}
        
        # Check subject match (critical for relevance)
        if subject:
            title_lower = title.lower()
            ingredients_lower = ingredients_text
            
            # Basic subject matching - is this actually the requested dish?
            if subject == 'cheesecake':
                constraint_details['subject_match'] = 'cheesecake' in title_lower
            elif subject == 'chocolate cake' or subject == 'cake':
                constraint_details['subject_match'] = any(term in title_lower for term in ['cake', 'chocolate'])
            elif subject == 'chicken':
                constraint_details['subject_match'] = 'chicken' in title_lower or 'chicken' in ingredients_lower
            elif subject == 'pizza':
                constraint_details['subject_match'] = 'pizza' in title_lower
            elif subject == 'pasta':
                constraint_details['subject_match'] = 'pasta' in title_lower or 'pasta' in ingredients_lower
            else:
                # Generic match for other subjects
                constraint_details['subject_match'] = subject.lower() in title_lower or subject.lower() in ingredients_lower
        
        # Check dietary constraints from agent
        if dietary_constraints:
            for constraint in dietary_constraints:
                if constraint == 'gluten-free':
                    constraint_details['gluten_free'] = not any(gluten_term in ingredients_text for gluten_term in ['flour', 'wheat', 'bread', 'pasta'])
                elif constraint == 'vegan':
                    constraint_details['vegan'] = not any(non_vegan in ingredients_text for non_vegan in ['chicken', 'beef', 'pork', 'fish', 'egg', 'milk', 'cheese', 'butter'])
                elif constraint == 'dairy-free':
                    constraint_details['dairy_free'] = not any(dairy in ingredients_text for dairy in ['milk', 'cheese', 'butter', 'cream', 'yogurt'])
                elif constraint == 'keto':
                    constraint_details['keto'] = not any(high_carb in ingredients_text for high_carb in ['flour', 'sugar', 'bread', 'pasta', 'rice'])
        
        # Check allergy constraints from agent (CRITICAL)
        if allergy_constraints:
            for allergy in allergy_constraints:
                if allergy == 'nuts':
                    constraint_details['nuts_excluded'] = not any(nut in ingredients_text for nut in ['nut', 'almond', 'walnut', 'pecan', 'cashew', 'peanut'])
                elif allergy == 'shellfish':
                    constraint_details['shellfish_excluded'] = not any(shellfish in ingredients_text for shellfish in ['shrimp', 'crab', 'lobster', 'shellfish'])
                elif allergy == 'eggs':
                    constraint_details['eggs_excluded'] = 'egg' not in ingredients_text
        
        # Check nutritional requirements from agent
        if nutrition_requirements:
            for requirement in nutrition_requirements:
                if 'protein' in requirement:
                    # Extract amount (e.g., "min_protein_20g" or "20g protein")
                    import re
                    match = re.search(r'(\d+)', requirement)
                    if match:
                        target_protein = int(match.group(1))
                        recipe_protein = _extract_protein_from_nutrition(nutrition)
                        constraint_details[f'min_{target_protein}g_protein'] = recipe_protein >= target_protein if recipe_protein is not None else False
                elif 'calorie' in requirement:
                    # Extract amount (e.g., "max_calories_300")
                    import re
                    match = re.search(r'(\d+)', requirement)
                    if match:
                        target_calories = int(match.group(1))
                        recipe_calories = _extract_calories_from_nutrition(nutrition)
                        constraint_details[f'max_{target_calories}_calories'] = recipe_calories <= target_calories if recipe_calories is not None else False
        
        # Check time constraints from agent
        if time_constraints:
            if time_constraints == 'quick' or time_constraints == 'fast':
                cook_minutes = _extract_cook_time_minutes(cook_time)
                constraint_details['quick'] = cook_minutes <= 30 if cook_minutes is not None else False
            elif 'minutes' in time_constraints:
                # Extract time limit (e.g., "under_30_minutes" or "30 minutes")
                import re
                match = re.search(r'(\d+)', time_constraints)
                if match:
                    target_minutes = int(match.group(1))
                    cook_minutes = _extract_cook_time_minutes(cook_time)
                    constraint_details[f'under_{target_minutes}_minutes'] = cook_minutes <= target_minutes if cook_minutes is not None else False
        
        # Calculate simple scores
        total_constraints = len(constraint_details)
        satisfied_constraints = sum(1 for satisfied in constraint_details.values() if satisfied)
        accuracy_score = round((satisfied_constraints / total_constraints * 100), 1) if total_constraints > 0 else 100.0
        
        # Quality score (priority site + image)
        source_url = recipe.get('source_url', '')
        domain = _extract_domain_from_url(source_url)
        has_image = bool(recipe.get('image_url'))
        is_priority_site = any(priority in domain for priority in ['allrecipes.com', 'simplyrecipes.com', 'seriouseats.com', 'food52.com'])
        quality_score = 100.0 if is_priority_site and has_image else 80.0 if is_priority_site else 60.0 if has_image else 40.0
        
        results.append({
            "recipe_title": title,
            "recipe_url": source_url,
            "simple_scores": {
                "accuracy": accuracy_score,
                "quality": quality_score,
                "speed": 100.0  # Speed is consistent across recipes in same search
            },
            "constraint_details": constraint_details
        })
    
    return results


def _extract_protein_from_nutrition(nutrition: List[str]) -> Optional[int]:
    """Extract protein grams from nutrition list."""
    import re
    for nutrient in nutrition:
        if 'protein' in nutrient.lower():
            match = re.search(r'(\d+)', nutrient)
            if match:
                return int(match.group(1))
    return None


def _extract_calories_from_nutrition(nutrition: List[str]) -> Optional[int]:
    """Extract calories from nutrition list."""
    import re
    for nutrient in nutrition:
        if 'calorie' in nutrient.lower() or 'kcal' in nutrient.lower():
            match = re.search(r'(\d+)', nutrient)
            if match:
                return int(match.group(1))
    return None


def _extract_cook_time_minutes(cook_time: str) -> Optional[int]:
    """Extract cook time in minutes from cook_time string."""
    import re
    if not cook_time:
        return None
    
    # Handle PT format (PT35M = 35 minutes)
    if cook_time.startswith('PT') and cook_time.endswith('M'):
        match = re.search(r'PT(\d+)M', cook_time)
        if match:
            return int(match.group(1))
    
    # Handle other formats
    match = re.search(r'(\d+)', cook_time)
    if match:
        return int(match.group(1))
    
    return None


def _extract_domain_from_url(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url.lower())
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return "unknown"


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