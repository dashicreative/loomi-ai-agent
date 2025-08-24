from pydantic_ai import RunContext
from typing import Dict, List, Optional
import httpx
import asyncio
import os
import random
import re
import sys
from pathlib import Path
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from Dependencies import RecipeDeps
# Import the parser and ingredient parsing
from .Detailed_Recipe_Parsers.Parsers import parse_recipe
from .Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list
from .Detailed_Recipe_Parsers.list_parser import ListParser
from .Detailed_Recipe_Parsers.url_classifier import classify_urls_batch
from bs4 import BeautifulSoup

"""Complete Data Flow:

  User Query
      ↓
  search_and_extract_recipes()  ← **MAIN AGENT TOOL** (Only tool the agent can call)
      ↓
  1. search_recipes_serpapi()     ← Supplemental: Get 30 URLs from web
      ↓
  2. expand_urls_with_lists()     ← Supplemental: Smart URL expansion (lists → individual recipes)
      ↓
  3. rerank_results_with_llm()    ← Supplemental: LLM picks best 10 URLs from expanded pool
      ↓
  4. parse_recipe() (parallel)    ← Supplemental: Extract recipe data from top 5
      ↓
  5. Format for agent             ← Supplemental: Structure data for user display
      ↓
  Agent Response

**AGENT TOOLS vs SUPPLEMENTAL FUNCTIONS:**
- AGENT TOOL: search_and_extract_recipes() - Only function the agent can invoke
- SUPPLEMENTAL: All other functions are internal helpers, not exposed to agent
"""


# Priority recipe sites for search
PRIORITY_SITES = [
    "allrecipes.com",
    "simplyrecipes.com", 
    "eatingwell.com",
    "foodnetwork.com",
    "delish.com",
    "seriouseats.com",
    "foodandwine.com",
    "thepioneerwoman.com",
    "food.com",
    "epicurious.com",
    "bbcgoodfood.com"  # Added at bottom - good site but lower priority
]

# Sites to completely block from processing
BLOCKED_SITES = [
    "reddit.com",
    "youtube.com",
    "instagram.com", 
    "pinterest.com",
    "facebook.com",
    "tiktok.com",
    "twitter.com"
]




# Initialize the advanced list parser (will be updated with OpenAI key during runtime)
list_parser = None

async def extract_recipe_urls_from_list(url: str, content: str, max_urls: int = 5) -> List[Dict]:
    """
    UPGRADED: Extract individual recipe URLs using advanced multi-tiered list parser.
    
    Uses ListParser class with:
    - Tier 1: JSON-LD structured data parsing
    - Tier 2: Recipe card structure analysis  
    - Tier 3: Enhanced link analysis with confidence scoring
    
    Args:
        url: The list page URL
        content: HTML content of the list page
        max_urls: Maximum URLs to extract (default 5)
        
    Returns:
        List of recipe URL dictionaries with metadata
    """
    return await list_parser.extract_recipe_urls(url, content, max_urls)


async def extract_list_with_hybrid_approach(url: str, openai_key: str, max_urls: int = 10):
    """
    Hybrid approach: Fast HTML scraping + GPT-3.5 extraction.
    Mimics FireCrawl's structured extraction but much faster and cheaper.
    """
    if not openai_key:
        return []
    
    try:
        # Step 1: Fast HTML scraping
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        
        # Step 2: Clean and prepare content for LLM
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
            
        # Get text content with some structure preserved
        clean_content = soup.get_text(separator='\n', strip=True)
        
        # Limit content size to control costs
        max_chars = 15000  # ~3750 tokens
        if len(clean_content) > max_chars:
            clean_content = clean_content[:max_chars] + "...[content truncated]"
        
        # Step 3: LLM extraction with improved guidance
        prompt = f"""You are analyzing a recipe list page. Extract up to {max_urls} individual recipe links.

GUIDANCE:
- Only extract items that have actual clickable URLs in the content
- Do NOT extract text-only suggestions like "Five eggs" or "Greek yogurt" that have no links
- Use the EXACT URLs that appear in the content - do not modify or invent URLs
- Look for recipe links that lead to individual recipe pages
- Skip items that are just ingredient combinations without actual recipe links

Extract recipes in this JSON format:
{{
  "recipes": [
    {{
      "title": "recipe title from the content",
      "url": "exact URL found in the content", 
      "description": "description with nutrition info if available"
    }}
  ]
}}

Content to analyze:
{clean_content}"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a recipe extraction specialist. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
            )
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        llm_response = data['choices'][0]['message']['content'].strip()
        
        # Parse JSON response
        try:
            # Clean up response in case LLM added extra text
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            import json
            recipe_data = json.loads(llm_response)
            recipes = recipe_data.get('recipes', [])
            
            formatted_recipes = []
            for recipe in recipes[:max_urls]:
                if recipe.get('url') and recipe.get('title'):
                    recipe_url = recipe['url'].strip()
                    
                    # Basic URL cleanup
                    if not recipe_url.startswith('http'):
                        from urllib.parse import urljoin
                        recipe_url = urljoin(url, recipe_url)
                    
                    formatted_recipes.append({
                        'title': recipe['title'],
                        'url': recipe_url,
                        'snippet': recipe.get('description', 'Recipe from hybrid extraction'),
                        'source': 'hybrid_extraction',
                        'type': 'recipe'
                    })
            
            return formatted_recipes
                
        except json.JSONDecodeError:
            return []
        
    except Exception:
        return []


async def expand_urls_with_lists(initial_results: List[Dict], openai_key: str = None, max_total_urls: int = 60) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Smart URL expansion that processes list pages to extract individual recipes.
    
    Uses batch classification for efficient URL type detection, then expands list pages
    into individual recipe URLs while filtering out irrelevant content.
    
    Args:
        initial_results: List of search result dictionaries from SerpAPI
        openai_key: OpenAI API key for classification and extraction
        max_total_urls: Maximum total URLs to return (default 60)
        
    Returns:
        Expanded list of individual recipe URLs with safety metadata
    """
    if not initial_results or not openai_key:
        return [], []
    
    # Step 1: Batch classify all URLs at once (much faster than individual classification)
    print(f"🔍 Classifying {len(initial_results)} URLs in batch...")
    classifications = await classify_urls_batch(initial_results, openai_key)
    
    # Create a mapping of URL to classification for easy lookup
    classification_map = {c.url: c for c in classifications}
    
    expanded_urls = []
    fp1_failures = []  # Track failures
    list_urls_processed = 0  # Counter for strategic list processing
    
    # Step 2: Process URLs based on their classification
    for result in initial_results:
        # Stop if we've reached our URL limit
        if len(expanded_urls) >= max_total_urls:
            break
            
        url = result.get("url", "")
        title = result.get("title", "")
        
        if not url:
            continue
        
        # Get classification for this URL
        classification = classification_map.get(url)
        if not classification:
            # No classification available - skip
            fp1_failures.append({
                "url": url,
                "title": title,
                "error": "No classification available",
                "failure_point": "Classification_Failure_Point"
            })
            continue
        
        # Process based on classification type
        if classification.type == "recipe":
            # Individual recipe - add directly
            result_copy = result.copy()
            result_copy["type"] = "recipe"
            result_copy["classification_confidence"] = classification.confidence
            expanded_urls.append(result_copy)
            
        elif classification.type == "list":
            # List page - extract individual recipes
            list_urls_processed += 1
            
            # Cap list processing to avoid rate limits and control costs
            if list_urls_processed > 6:
                continue
            
            remaining_slots = max_total_urls - len(expanded_urls)
            max_extract = min(5, remaining_slots)  # Extract up to 5 or remaining slots
            
            if max_extract > 0:
                try:
                    # Fetch the list page content first
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()
                        html_content = response.text
                    
                    # Initialize ListParser with OpenAI key for intelligent filtering
                    intelligent_parser = ListParser(openai_key)
                    extracted_urls = await intelligent_parser.extract_recipe_urls(url, html_content, max_extract)
                    
                    # Add extracted URLs to our pool
                    for extracted_url in extracted_urls:
                        extracted_url["type"] = "recipe"  # Mark as recipe
                        extracted_url["google_position"] = result.get("google_position", 999)
                        extracted_url["from_list"] = url  # Track source list
                        expanded_urls.append(extracted_url)
                        
                        # Stop if we hit the limit while processing this list
                        if len(expanded_urls) >= max_total_urls:
                            break
                            
                except Exception as e:
                    fp1_failures.append({
                        "url": url,
                        "title": title,
                        "error": str(e),
                        "failure_point": "List_Extraction_Failure_Point"
                    })
            
        else:
            # Other types (blog, social, other) - filter out entirely
            # These don't move forward to the next stage
            pass
    
    # SAFETY CHECK: Ensure only recipe URLs are returned
    safe_urls = [url for url in expanded_urls if url.get("type") == "recipe"]
    
    return safe_urls[:max_total_urls], fp1_failures  # Return both expanded URLs and FP1 failures




# =============================================================================
# SUPPLEMENTAL FUNCTIONS: Search and Ranking  
# These are NOT agent tools - they are internal helper functions
# =============================================================================

async def search_recipes_serpapi(ctx: RunContext[RecipeDeps], query: str, number: int = 40) -> Dict:
    """
    SUPPLEMENTAL FUNCTION: Search for recipes on the web using SerpAPI.
    Internal function for the search step.
    
    Args:
        query: The search query for recipes
        number: Number of results to return (default 40, filtered down)
    
    Returns:
        Dictionary containing search results with URLs and snippets
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Add "recipe" to query if not already present
        if "recipe" not in query.lower():
            query = f"{query} recipe"
        
        # Search broadly without site restrictions for quality results
        params = {
            "api_key": ctx.deps.serpapi_key,
            "engine": "google",
            "q": query,
            "num": number,
            "hl": "en",
            "gl": "us"
        }
        
        try:
            response = await client.get("https://serpapi.com/search", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.ReadTimeout:
            # RETRY LOGIC: SerpAPI can be slow, try once more with shorter timeout
            # This handles temporary network slowness without failing immediately
            try:
                async with httpx.AsyncClient(timeout=15.0) as retry_client:
                    response = await retry_client.get("https://serpapi.com/search", params=params)
                    response.raise_for_status()
                    data = response.json()
            except httpx.ReadTimeout:
                # GRACEFUL DEGRADATION: If both attempts timeout, return structured error
                # This prevents agent crash and allows user to retry or check connectivity
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "error": "SerpAPI requests timed out. Check network connectivity."
                }
        except Exception as e:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": f"Search failed: {str(e)}"
            }
        
        # Extract organic results
        organic_results = data.get("organic_results", [])
        
        # Format results for processing
        formatted_results = []
        for result in organic_results:
            url = result.get("link", "")
            
            # Skip blocked sites entirely
            is_blocked = any(blocked_site in url.lower() for blocked_site in BLOCKED_SITES)
            if is_blocked:
                continue
            
            formatted_results.append({
                "title": result.get("title", ""),
                "url": url,
                "snippet": result.get("snippet", ""),
                "source": result.get("source", ""),
                "google_position": result.get("position", 999)
            })
        
        return {
            "results": formatted_results[:30],  # Cap at 30 after filtering
            "total": len(formatted_results[:30]),
            "query": query
        }

async def rerank_results_with_llm(results: List[Dict], query: str, openai_key: str, top_k: int = 10) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Use GPT-3.5-turbo to rerank search results based on relevance to user query.
    Updated to handle larger URL pools (up to 60+ URLs from list expansion).
    
    Args:
        results: List of search results to rerank (can be 60+ URLs now)
        query: Original user query
        openai_key: OpenAI API key
        top_k: Number of top results to return after reranking
    
    Returns:
        Reranked list of results
    """
    if not results:
        return []
    
    # Handle larger result sets by processing in chunks
    max_to_rank = min(40, len(results))  # Increased from 20 to handle expanded URLs
    results_to_rank = results[:max_to_rank]
    
    # Prepare prompt for LLM
    recipe_list = "\n".join([
        f"{i+1}. {r['title']} - {r.get('snippet', '')[:100]}..."
        for i, r in enumerate(results_to_rank)
    ])
    
    prompt = f"""User is searching for: "{query}"

    Rank these recipes by relevance (best match first). Consider:   
    - Exact match to query terms
    - Dietary requirements mentioned (protein, calories, etc.)
    - Complexity/simplicity if mentioned
    - Cooking method if specified
    - Meal type (breakfast, lunch, dinner) if relevant

    Recipes:
    {recipe_list}

    Return ONLY a comma-separated list of numbers in order of relevance (e.g., "3,1,5,2,4...")
    Best match first. Include at least {min(top_k, len(results_to_rank))} rankings."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a recipe ranking assistant. Return only comma-separated numbers."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 150  # Increased for larger lists
            }
        )
        
        if response.status_code != 200:
            # If LLM fails, return original order
            return results[:top_k]
        
        data = response.json()
        ranking_text = data['choices'][0]['message']['content'].strip()
        
        # Parse the ranking
        try:
            rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
            reranked = []
            
            # Add recipes in the ranked order
            for idx in rankings:
                if 0 <= idx < len(results_to_rank) and results_to_rank[idx] not in reranked:
                    reranked.append(results_to_rank[idx])
            
            # Add any missing recipes from the ranked subset
            for result in results_to_rank:
                if result not in reranked and len(reranked) < top_k:
                    reranked.append(result)
            
            # Add remaining unranked URLs if we still need more
            remaining_results = results[max_to_rank:]
            for result in remaining_results:
                if len(reranked) >= top_k:
                    break
                reranked.append(result)
            
            return reranked[:top_k]
            
        except (ValueError, IndexError):
            # If parsing fails, return original order
            return results[:top_k]


async def rerank_with_full_recipe_data(scraped_recipes: List[Dict], query: str, openai_key: str) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Second-stage LLM ranking using full recipe data.
    
    Uses complete recipe information (ingredients, instructions, timing) for intelligent ranking.
    Much more accurate than title/snippet ranking for complex queries.
    
    Args:
        scraped_recipes: List of recipes with full parsed data
        query: Original user query
        openai_key: OpenAI API key
        
    Returns:
        Recipes reranked by deep content relevance
    """
    if not scraped_recipes:
        return []
    
    # Prepare detailed recipe data for LLM
    detailed_recipes = []
    for i, recipe in enumerate(scraped_recipes):
        # Build comprehensive recipe summary for LLM analysis
        ingredients_list = recipe.get("ingredients", [])[:10]  # First 10 ingredients
        # Extract ingredient names from structured format
        ingredients_text = ", ".join([ing.get("ingredient", "") for ing in ingredients_list if ing.get("ingredient")])
        instructions_preview = " ".join(recipe.get("instructions", [])[:2])[:200]  # First 2 steps, truncated
        
        recipe_summary = f"""{i+1}. {recipe.get('title', 'Untitled Recipe')}
Ingredients: {ingredients_text}
Cook Time: {recipe.get('cook_time', 'Not specified')}
Servings: {recipe.get('servings', 'Not specified')}
Instructions Preview: {instructions_preview}..."""
        
        detailed_recipes.append(recipe_summary)
    
    recipes_text = "\n\n".join(detailed_recipes)
    
    prompt = f"""User is searching for: "{query}"

    Rank these recipes by relevance using their FULL CONTENT (best match first).
    Analyze ingredients AND instructions for complete relevance matching.

    CRITICAL RANKING REQUIREMENTS:
    1. REQUIRED INCLUSIONS: If query mentions specific ingredients (e.g., "blueberry cheesecake"), those ingredients MUST appear in the recipe
    2. EXCLUSIONS: If query uses "without", "no", or "-" (e.g., "cheesecake without cane sugar"), ensure excluded items are NOT in ingredients
    3. EQUIPMENT REQUIREMENTS: Check instructions for equipment mentions (e.g., "no-bake", "slow cooker", "air fryer")
    4. COOKING METHOD: Match preparation methods from instructions (e.g., "grilled", "baked", "fried")
    5. SPECIFIC COOKING DIRECTIONS: Match any specific cooking techniques or directions the user requests that can be found in the recipe instructions
    6. RECIPE TYPE MATCHING - EXCLUSION RULE: 
       - If query asks for "[food] recipe" (e.g., "steak recipe"), EXCLUDE from consideration any recipes that are primarily marinades, sauces, or dressings
       - These recipes CANNOT appear in the final ranking unless user specifically asks for them (e.g., "steak marinade recipe")
       - Examples: "steak recipe" → EXCLUDE any steak marinades, "chicken recipe" → EXCLUDE chicken marinades/sauces
       - Only rank actual cooking recipes that prepare the main food item

    Additional factors:
    - Dietary requirements (high protein, low carb, etc.)
    - Time constraints (quick, under 30 minutes, etc.)
    - Meal type appropriateness

    Recipes with full details:
    {recipes_text}

    Return ONLY a comma-separated list of numbers in order of relevance (e.g., "3,1,5,2,4...")
    Best match first based on the COMPLETE recipe content."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are an expert recipe analyst. Rank recipes by deep content relevance to user queries. Return only comma-separated numbers."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }
        )
        
        if response.status_code != 200:
            # If LLM fails, return original order
            return scraped_recipes
        
        data = response.json()
        ranking_text = data['choices'][0]['message']['content'].strip()
        
        # Parse the ranking
        try:
            rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
            reranked = []
            
            # Add recipes in the ranked order
            for idx in rankings:
                if 0 <= idx < len(scraped_recipes) and scraped_recipes[idx] not in reranked:
                    reranked.append(scraped_recipes[idx])
            
            # Add any missing recipes
            for recipe in scraped_recipes:
                if recipe not in reranked:
                    reranked.append(recipe)
            
            return reranked
            
        except (ValueError, IndexError):
            # If parsing fails, return original order
            return scraped_recipes



# =============================================================================
# MAIN AGENT TOOL: This is the ONLY function the agent can invoke
# =============================================================================

async def search_and_extract_recipes(ctx: RunContext[RecipeDeps], query: str, max_recipes: int = 5) -> Dict:
    """
    **MAIN AGENT TOOL**: Complete recipe discovery flow with smart list processing.
    
    Enhanced flow: Search → URL Expansion → Rerank → Scrape → Extract
    - Detects and processes list pages (e.g. "25 Best Breakfast Recipes")
    - Extracts individual recipe URLs from lists
    - Handles both individual recipes and list-sourced recipes seamlessly
    
    This is the ONLY tool the agent can invoke - all other functions are internal helpers.
    
    Args:
        query: User's search query (supports criteria like "breakfast with 30g+ protein")
        max_recipes: Maximum number of recipes to return with full details (default 5)
    
    Returns:
        Dictionary with structured recipe data ready for agent processing
    """
    # Step 1: Search for recipes using SerpAPI (gets up to 30 URLs after blacklist filtering)
    search_results = await search_recipes_serpapi(ctx, query)
    
    # Clean stage summary with priority sites count
    results = search_results.get('results', [])
    priority_count = sum(1 for result in results if any(priority_site in result.get('url', '').lower() for priority_site in PRIORITY_SITES))
    print(f"\n📊 Stage 1: Web Search - Found {len(results)} URLs ({priority_count} from priority sites)")
    
    if not search_results.get("results"):
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No recipes found for your search"
        }
    
    # Step 2: Smart URL Expansion (process list pages → extract individual recipe URLs)
    # This is where the magic happens - converts list pages into individual recipe URLs
    expanded_results, fp1_failures = await expand_urls_with_lists(
        search_results["results"], 
        openai_key=ctx.deps.openai_key,
        max_total_urls=60
    )
    
    print(f"📊 Stage 2: URL Expansion - {len(search_results.get('results', []))} → {len(expanded_results)} URLs")
    
    if not expanded_results:
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No valid recipes found after processing search results"
        }
    
    # STAGE 1: Initial ranking by priority sites (quality over relevance)
    priority_urls = []
    non_priority_urls = []
    
    # Separate priority sites from non-priority sites and rank by PRIORITY_SITES order
    for result in expanded_results:
        url = result.get('url', '').lower()
        # Use more precise matching to avoid substring issues (e.g., bbcgoodfood.com containing food.com)
        if any(f"//{priority_site}" in url or f".{priority_site}" in url for priority_site in PRIORITY_SITES):
            # Find which priority site this URL belongs to and add its index for sorting
            for i, priority_site in enumerate(PRIORITY_SITES):
                if f"//{priority_site}" in url or f".{priority_site}" in url:
                    result['_priority_index'] = i
                    priority_urls.append(result)
                    break
        else:
            non_priority_urls.append(result)
    
    # Sort priority URLs by their order in PRIORITY_SITES list (lower index = higher priority)
    priority_urls.sort(key=lambda x: x.get('_priority_index', 999))
    
    # Combine: priority sites first (in PRIORITY_SITES order), then non-priority sites
    stage1_ranked_results = priority_urls + non_priority_urls
    
    print(f"📊 Stage 3: Initial Ranking - Selected top {min(15, len(stage1_ranked_results))} URLs for scraping")
    
    # Step 4: Parse ALL 30 URLs for Stage 2 ranking (LLM needs ingredient data)
    # Process all Stage 1 ranked results to give LLM full ingredient information
    candidates_to_parse = stage1_ranked_results[:15]  # Parse top 15 for Stage 2 ranking
    
    
    # Step 5: Parse all candidates
    extraction_tasks = []
    successful_parses = []
    failed_parses = []
    
    for result in candidates_to_parse:
        url = result.get("url")
        if url:
            task = parse_recipe(url, ctx.deps.openai_key)
            extraction_tasks.append(task)
    
    # Execute all extractions in parallel
    extracted_recipes = []
    if extraction_tasks:
        extracted_data = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        
        # Process extracted data - separate successful vs failed parses
        for i, data in enumerate(extracted_data):
            if isinstance(data, dict) and not data.get("error"):
                # Add search metadata to extracted recipe
                data["search_title"] = candidates_to_parse[i].get("title", "")
                data["search_snippet"] = candidates_to_parse[i].get("snippet", "")
                successful_parses.append(data)
            else:
                # Track failed parse for potential quality checking
                failed_parses.append({
                    "result": candidates_to_parse[i],
                    "error": str(data) if isinstance(data, Exception) else data.get("error", "Unknown error"),
                    "failure_point": "Recipe_Parsing_Failure_Point"
                })
        
        # No more quality checking - failed parses are simply tracked for reporting
        
        extracted_recipes = successful_parses
    
    print(f"📊 Stage 4: Recipe Scraping - Successfully parsed {len(extracted_recipes)} recipes")
    
    # Print failed URLs
    if failed_parses:
        failed_urls = [fp.get("result", {}).get("url", "") for fp in failed_parses]
        print(f"❌ Failed to parse: {', '.join(failed_urls)}")
    
    # STAGE 2: Deep content ranking using full recipe data
    if len(extracted_recipes) > 1:  # Only re-rank if we have multiple recipes
        final_ranked_recipes = await rerank_with_full_recipe_data(
            extracted_recipes,
            query,
            ctx.deps.openai_key
        )
    else:
        final_ranked_recipes = extracted_recipes
    
    print(f"📊 Stage 5: Final Ranking - Returning top {min(max_recipes, len(final_ranked_recipes))} recipes\n")
    
    # Step 6: Format final results for agent  
    formatted_recipes = []
    for recipe in final_ranked_recipes[:max_recipes]:  # Use final ranked results
        # Parse raw ingredient strings into structured format
        raw_ingredients = recipe.get("ingredients", [])
        structured_ingredients = parse_ingredients_list(raw_ingredients)
        
        formatted_recipes.append({
            "id": len(formatted_recipes) + 1,  # Simple ID generation
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,  # Now structured!
            # Instructions are available for agent analysis but won't be displayed
            "_instructions_for_analysis": recipe.get("instructions", [])
        })
    
    # Track all failure points for business reporting
    all_failures = fp1_failures + failed_parses  # Combine Content_Scraping and Recipe_Parsing failures
    failed_parse_report = {
        "total_failed": len(all_failures),
        "content_scraping_failures": len(fp1_failures),
        "recipe_parsing_failures": len(failed_parses),
        "failed_urls": [
            {
                "url": fp.get("url") or fp.get("result", {}).get("url", ""),
                "failure_point": fp.get("failure_point", "Unknown"),
                "error": fp.get("error", "Unknown error")
            }
            for fp in all_failures
        ]
    }
    
    return {
        "results": formatted_recipes,
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "_failed_parse_report": failed_parse_report  # For business analytics
    }
 



