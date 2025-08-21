from pydantic_ai import RunContext
from typing import Dict, List, Optional
import httpx
import asyncio
import os
import random
import re
from dataclasses import dataclass
from Dependencies import RecipeDeps
# Import the parser and ingredient parsing
from .Detailed_Recipe_Parsers.Parsers import parse_recipe
from .Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list
from .Detailed_Recipe_Parsers.list_parser import ListParser
from bs4 import BeautifulSoup
from .html_cache_manager import HTMLCacheManager
from .early_exit_manager import EarlyExitManager

# Initialize cache manager at module level (one per request)
_html_cache = None

def get_html_cache(firecrawl_key: Optional[str] = None) -> HTMLCacheManager:
    """Get or create HTML cache for current request"""
    global _html_cache
    if _html_cache is None:
        _html_cache = HTMLCacheManager(firecrawl_key=firecrawl_key)
    return _html_cache

def reset_html_cache():
    """Reset cache between requests"""
    global _html_cache
    _html_cache = None




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
    "epicurious.com"
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




# =============================================================================
# SUPPLEMENTAL FUNCTIONS: List vs Individual Recipe Detection
# These are NOT agent tools - they are internal helper functions
# =============================================================================

def detect_page_type(url: str, title: str, content: str = "") -> str:
    """
    SUPPLEMENTAL FUNCTION: Tiered detection system to identify list pages vs individual recipes.
    
    Uses 4-tier detection:
    1. Title + URL patterns (lightweight)
    2. Content keywords (medium)  
    3. HTML structure analysis (detailed)
    4. Content length heuristic (fallback)
    
    Args:
        url: The page URL
        title: Page title from search results
        content: Page content (optional, for deeper analysis)
        
    Returns:
        "list" or "recipe"
    """
    
    # TIER 1: Title and URL Pattern Analysis (Lightweight - handles most cases)
    list_title_patterns = [
        r'\b(\d+)\s+(best|top|easy|quick|healthy|delicious)\b',  # "25 Best", "10 Easy"
        r'\b(best|top|easy|quick)\s+(\d+)\b',  # "Best 15", "Top 10"
        r'\b(\d+)\s+(recipes?|breakfasts?|lunches?|dinners?|meals?|dishes?|ideas?|ways?)\b',  # "16 Breakfasts", "30 Recipes"
        r'\b(recipes?|ideas?|ways?|dishes?|meals?)\s*(for|to)\b',  # "Recipes for", "Ideas to"
        r'\b(collection|roundup|list)\b',  # "Recipe Collection", "Roundup"
        r'\bmultiple\b.*\b(recipes?|dishes?)\b'  # "Multiple recipes"
    ]
    
    recipe_title_patterns = [
        r'\b(recipe|how to make)\b',  # "Chocolate Cake Recipe", "How to make"
        r'\bcooking\s+\w+',  # "Cooking Chicken"
    ]
    
    # Check for list patterns in title
    title_lower = title.lower()
    for pattern in list_title_patterns:
        if re.search(pattern, title_lower):
            return "list"
    
    # Check for recipe patterns in title  
    for pattern in recipe_title_patterns:
        if re.search(pattern, title_lower) and not any(re.search(lp, title_lower) for lp in list_title_patterns):
            return "recipe"
    
    # Check URL patterns
    url_lower = url.lower()
    if any(pattern in url_lower for pattern in ['/best-', '/top-', '/roundup', '/collection', '/ideas', '/ways', '-recipes-with-', 'breakfast-recipes-with']):
        return "list"
    if any(pattern in url_lower for pattern in ['/recipe/', '-recipe.', 'recipe-']):
        return "recipe"
    
    # TIER 2: Content Keywords (if content provided and Tier 1 indeterminate)
    if content:
        content_lower = content.lower()
        
        # List content indicators
        list_content_patterns = [
            r'\bhere are\s+(\d+|\w+)\s+(recipes?|ideas?|ways?)\b',  # "Here are 10 recipes"
            r'\btry these\s+(\d+|\w+)\b',  # "Try these 5"
            r'\brecipe roundup\b',
            r'\bmultiple.*recipes?\b',
            r'\bcollection of.*recipes?\b'
        ]
        
        for pattern in list_content_patterns:
            if re.search(pattern, content_lower):
                return "list"
        
        # TIER 3: HTML Structure Analysis
        if '<' in content:  # Basic check that we have HTML
            try:
                soup = BeautifulSoup(content, 'html.parser')
                
                # Count recipe-like headings (h2, h3, h4 that might be recipe titles)
                headings = soup.find_all(['h2', 'h3', 'h4'])
                recipe_heading_count = 0
                
                for heading in headings[:20]:  # Check first 20 headings
                    heading_text = heading.get_text().lower()
                    if any(word in heading_text for word in ['recipe', 'chicken', 'pasta', 'salad', 'cake', 'soup']):
                        recipe_heading_count += 1
                
                # If we find 3+ recipe-like headings, likely a list page
                if recipe_heading_count >= 3:
                    return "list"
                
                # Count links to recipe pages
                recipe_links = 0
                links = soup.find_all('a', href=True)
                for link in links[:50]:  # Check first 50 links
                    href = link.get('href', '').lower()
                    if any(pattern in href for pattern in ['recipe', '/recipes/', '.html']):
                        recipe_links += 1
                
                # High number of recipe links suggests list page
                if recipe_links >= 10:
                    return "list"
                    
            except Exception:
                pass  # HTML parsing failed, continue to Tier 4
        
        # TIER 4: Content Length Heuristic (final fallback)
        word_count = len(content.split())
        if word_count > 3000:  # Very long content often indicates list pages
            # Check for recipe-specific patterns in long content
            recipe_indicators = content_lower.count('ingredients') + content_lower.count('instructions') + content_lower.count('directions')
            if recipe_indicators <= 2:  # Few recipe indicators in long content = likely list
                return "list"
    
    # Default to recipe if uncertain
    return "recipe"


# Initialize the advanced list parser
list_parser = ListParser()

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


async def extract_list_with_firecrawl(url: str, firecrawl_key: str, max_urls: int = 5) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Use FireCrawl to reliably extract individual recipe URLs from list pages.
    
    Uses FireCrawl's LLM capabilities to identify and extract recipe links with high accuracy.
    
    Args:
        url: The list page URL to process
        firecrawl_key: FireCrawl API key
        max_urls: Maximum recipe URLs to extract
        
    Returns:
        List of extracted recipe URL dictionaries
    """
    if not firecrawl_key:
        return []
    
    try:
        from firecrawl import Firecrawl
        app = Firecrawl(api_key=firecrawl_key)
        
        # Use FireCrawl's JSON extraction with prompt
        result = app.scrape(
            url,
            formats=[{
                "type": "json",
                "prompt": f"Extract up to {max_urls} individual recipe links from this list page. Return a JSON object with a 'recipes' array. Each recipe should have 'title', 'url', and 'description' fields. Only return direct links to specific recipes, NOT category pages or navigation links."
            }]
        )
        
        # Data is in result.json, not result.extract
        if result and hasattr(result, 'json') and result.json:
            recipes = result.json.get('recipes', [])
            
            formatted_recipes = []
            for recipe in recipes[:max_urls]:
                if recipe.get('url') and recipe.get('title'):
                    # Convert relative URLs to absolute
                    recipe_url = recipe['url']
                    if not recipe_url.startswith('http'):
                        from urllib.parse import urljoin
                        recipe_url = urljoin(url, recipe_url)
                    
                    formatted_recipes.append({
                        'title': recipe['title'],
                        'url': recipe_url,
                        'snippet': recipe.get('description', 'Recipe from list extraction'),
                        'source': 'firecrawl_list_extraction',
                        'type': 'recipe'
                    })
            
            return formatted_recipes
        
    except Exception as e:
        print(f"FireCrawl list extraction failed for {url}: {e}")
        return []
    
    return []


async def expand_urls_with_lists(initial_results: List[Dict], firecrawl_key: str = None, max_total_urls: int = 60) -> List[Dict]:
    """
    OPTIMIZED: Smart URL expansion using cached HTML for efficient processing.
    
    Takes initial search results and expands any list pages into individual recipe URLs.
    Uses HTML Cache Manager to batch fetch HTML and eliminate redundant requests.
    
    Args:
        initial_results: List of search result dictionaries from SerpAPI
        firecrawl_key: FireCrawl API key for scraping non-priority sites
        max_total_urls: Maximum total URLs to return (default 60)
        
    Returns:
        Expanded list of individual recipe URLs with safety metadata
    """
    expanded_urls = []
    fp1_failures = []  # Track Content_Scraping_Failure_Point
    processed_count = 0
    list_urls_processed = 0  # Counter for strategic list processing
    
    # Get HTML cache manager with FireCrawl fallback
    html_cache = get_html_cache(firecrawl_key)
    
    # Step 1: Batch fetch all URLs for efficient processing
    all_urls = [result.get("url", "") for result in initial_results if result.get("url")]
    print(f"🚀 Batch fetching HTML for {len(all_urls)} URLs...")
    
    await html_cache.batch_fetch(all_urls)
    
    # Step 2: Process URLs using cached HTML
    for result in initial_results:
        # Stop if we've reached our URL limit
        if len(expanded_urls) >= max_total_urls:
            break
            
        url = result.get("url", "")
        title = result.get("title", "")
        
        if not url:
            continue
        
        try:
            # OPTIMIZED: Use cached HTML for accurate classification
            html_content = html_cache.get_html(url)
            
            if not html_content:
                # HTML fetch failed, track as failure
                fp1_failures.append({
                    "url": url,
                    "title": title,
                    "error": "HTML fetch failed",
                    "failure_point": "Content_Scraping_Failure_Point"
                })
                continue
            
            # Enhanced classification using cached HTML content
            page_type = detect_page_type(url, title, html_content)
            print(f"🚀 Enhanced classification: {url} → {page_type}")
            
            if page_type == "recipe":
                # Individual recipe identified - add directly
                result_copy = result.copy()
                result_copy["type"] = "recipe"
                expanded_urls.append(result_copy)
                
            elif page_type == "list":
                # List page identified - use cached HTML for list extraction
                list_urls_processed += 1
                
                # Cap list processing to avoid rate limits and control costs
                if list_urls_processed > 6:
                    print(f"⚠️  Skipping list URL (processed 6 max): {url}")
                    continue
                
                remaining_slots = max_total_urls - len(expanded_urls)
                max_extract = min(5, remaining_slots)  # Extract up to 5 or remaining slots
                
                if max_extract > 0:
                    print(f"🎯 Extracting recipes from cached HTML: {url}")
                    # Use our advanced list parser with cached HTML
                    extracted_urls = await extract_recipe_urls_from_list(url, html_content, max_extract)
                    
                    # Add extracted URLs to our pool
                    for extracted_url in extracted_urls:
                        extracted_url["type"] = "recipe"  # Mark as recipe for safety
                        extracted_url["google_position"] = result.get("google_position", 999)
                        expanded_urls.append(extracted_url)
                        
                        # Stop if we hit the limit while processing this list
                        if len(expanded_urls) >= max_total_urls:
                            break
                
                # Note: Original list URL is NOT added to expanded_urls (filtered out)
            
        except Exception as e:
            print(f"Failed to process URL {url}: {e}")
            # CONTENT SCRAPING FAILURE POINT: Can't determine if list or recipe - track and discard
            fp1_failures.append({
                "url": url,
                "title": title,
                "error": str(e),
                "failure_point": "Content_Scraping_Failure_Point"
            })
            # Don't add URL to expanded_urls - let it be filtered out entirely
        
        processed_count += 1
    
    # SAFETY CHECK: Filter out any URLs that might still be marked as lists
    safe_urls = [url for url in expanded_urls if url.get("type") == "recipe"]
    
    print(f"URL Expansion: {len(initial_results)} initial → {len(safe_urls)} expanded (processed {processed_count})")
    
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
            print("SerpAPI request timed out. Retrying with shorter timeout...")
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
                print("SerpAPI retry also timed out. Network connectivity issue.")
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "error": "SerpAPI requests timed out. Check network connectivity."
                }
        except Exception as e:
            print(f"SerpAPI request failed: {e}")
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": f"Search failed: {str(e)}"
            }
        
        # Extract organic results
        organic_results = data.get("organic_results", [])
        
        # DEBUG: Show original SerpAPI results BEFORE blacklist filtering
        print(f"\n=== DEBUG: Original SerpAPI Results (Before Filtering) ===")
        print(f"Total raw results: {len(organic_results)}")
        for i, result in enumerate(organic_results[:30], 1):  # Show first 15
            url = result.get("link", "")
            title = result.get("title", "No title")
            print(f"{i}. {title[:80]}...")
            print(f"   URL: {url}")
            # Show if this will be blocked
            is_blocked = any(blocked_site in url.lower() for blocked_site in BLOCKED_SITES)
            if is_blocked:
                print(f"   ⚠️  WILL BE BLOCKED")
        print("=" * 60)
        
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
        ingredients_text = ", ".join(recipe.get("ingredients", [])[:10])  # First 10 ingredients
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
    # Reset cache between requests to prevent pollution
    reset_html_cache()
    
    # Step 1: Search for recipes using SerpAPI (gets up to 30 URLs after blacklist filtering)
    search_results = await search_recipes_serpapi(ctx, query)
    
    # DEBUG: Show initial URLs from SerpAPI
    print(f"\n=== DEBUG: After Blacklist Filtering ===")
    print(f"Total results: {len(search_results.get('results', []))}")
    for i, result in enumerate(search_results.get('results', []), 1):  # Show ALL, not just first 10
        print(f"{i}. {result.get('title', 'No title')[:80]}...")
        print(f"   URL: {result.get('url', 'No URL')}")
    print("=" * 50)
    
    if not search_results.get("results"):
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No recipes found for your search"
        }
    
    # Step 1.5: Batch prefetch HTML for all URLs
    html_cache = get_html_cache(ctx.deps.firecrawl_key)
    all_urls = [result.get("url") for result in search_results.get("results", []) if result.get("url")]
    if all_urls:
        await html_cache.batch_fetch(all_urls)
    
    # Step 2: Smart URL Expansion (process list pages → extract individual recipe URLs)
    # This is where the magic happens - converts list pages into individual recipe URLs
    expanded_results, fp1_failures = await expand_urls_with_lists(
        search_results["results"], 
        firecrawl_key=ctx.deps.firecrawl_key,
        max_total_urls=60
    )
    
    if not expanded_results:
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No valid recipes found after processing search results"
        }
    
    # Step 4: Priority Site Pre-Processing
    from .early_exit_manager import PriorityURLOrdering
    
    priority_orderer = PriorityURLOrdering()
    priority_ordered_results = priority_orderer.order_urls_by_priority(expanded_results)
    
    # Separate priority sites from non-priority sites
    priority_sites = []
    non_priority_sites = []
    
    for result in priority_ordered_results:
        url = result.get('url', '').lower()
        is_priority = any(site in url for site in PRIORITY_SITES)
        
        if is_priority:
            priority_sites.append(result)
        else:
            non_priority_sites.append(result)
    
    print(f"🎯 Priority sites found: {len(priority_sites)}")
    print(f"📊 Non-priority sites: {len(non_priority_sites)}")
    
    # Step 5: Progressive parsing with priority site preference
    early_exit_manager = EarlyExitManager(
        quality_threshold=0.7,
        min_recipes=max_recipes,
        max_recipes=max_recipes + 2,
        firecrawl_key=ctx.deps.firecrawl_key
    )
    
    # Process priority sites first
    if priority_sites:
        print("🏆 Processing priority sites first...")
        high_quality_recipes, all_parsed_recipes = await early_exit_manager.progressive_parse_with_exit(
            priority_sites,
            query
        )
        
        # If we didn't get enough high-quality recipes, supplement with non-priority sites
        if len(high_quality_recipes) < max_recipes and non_priority_sites:
            print(f"🔄 Need more recipes, processing non-priority sites...")
            early_exit_manager.reset_stats()  # Reset for second round
            
            additional_recipes, additional_parsed = await early_exit_manager.progressive_parse_with_exit(
                non_priority_sites,
                query
            )
            
            # Combine results
            high_quality_recipes.extend(additional_recipes)
            all_parsed_recipes.extend(additional_parsed)
    else:
        # Fallback: process all non-priority sites if no priority sites found
        print("⚠️ No priority sites found, processing all results...")
        high_quality_recipes, all_parsed_recipes = await early_exit_manager.progressive_parse_with_exit(
            priority_ordered_results[:25],
            query
        )
    
    # Use high quality recipes as final result (no need for Stage 2 reranking)
    final_ranked_recipes = high_quality_recipes
    
    # Track failed parses from Early Exit Manager stats
    stats = early_exit_manager.get_stats()
    failed_parses = []  # Early Exit Manager handles failure tracking internally
    
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
 



