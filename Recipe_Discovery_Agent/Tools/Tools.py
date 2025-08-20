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
from .Parsers import parse_recipe
from ingredient_parser import parse_ingredients_list
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
    "epicurious.com"
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
    if any(pattern in url_lower for pattern in ['/best-', '/top-', '/roundup', '/collection', '/ideas', '/ways']):
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


async def extract_recipe_urls_from_list(url: str, content: str, max_urls: int = 5) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Extract individual recipe URLs from a list page.
    
    Args:
        url: The list page URL
        content: HTML content of the list page
        max_urls: Maximum URLs to extract (default 5)
        
    Returns:
        List of recipe URL dictionaries with metadata
    """
    try:
        soup = BeautifulSoup(content, 'html.parser')
        recipe_urls = []
        
        # Find all links that might be recipes
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            
            # Skip empty or very short links
            if not href or len(link_text) < 5:
                continue
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            elif not href.startswith('http'):
                continue
            
            # Look for recipe-like URLs and link text
            href_lower = href.lower()
            text_lower = link_text.lower()
            
            recipe_indicators = [
                'recipe' in href_lower or 'recipe' in text_lower,
                any(food in text_lower for food in ['chicken', 'pasta', 'salad', 'cake', 'soup', 'bread', 'cookies']),
                len(link_text) > 10 and len(link_text) < 100,  # Reasonable recipe title length
                href_lower.endswith('.html') or '/recipes/' in href_lower
            ]
            
            # If at least 2 indicators match, consider it a recipe URL
            if sum(recipe_indicators) >= 2:
                recipe_urls.append({
                    "title": link_text,
                    "url": href,
                    "snippet": f"Recipe from {url}",
                    "source": "extracted_from_list",
                    "type": "recipe"
                })
            
            # Stop when we have enough URLs
            if len(recipe_urls) >= max_urls:
                break
        
        # Randomly sample if we have more than requested
        if len(recipe_urls) > max_urls:
            recipe_urls = random.sample(recipe_urls, max_urls)
        
        return recipe_urls
        
    except Exception as e:
        print(f"Failed to extract URLs from list page {url}: {e}")
        return []


async def expand_urls_with_lists(initial_results: List[Dict], firecrawl_key: str = None, max_total_urls: int = 60) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Smart URL expansion that processes list pages to extract individual recipes.
    
    Takes initial search results and expands any list pages into individual recipe URLs.
    Caps total URLs at max_total_urls and ensures no list URLs reach the ranking stage.
    
    Args:
        initial_results: List of search result dictionaries from SerpAPI
        firecrawl_key: FireCrawl API key for scraping non-priority sites
        max_total_urls: Maximum total URLs to return (default 60)
        
    Returns:
        Expanded list of individual recipe URLs with safety metadata
    """
    expanded_urls = []
    processed_count = 0
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for result in initial_results:
            # Stop if we've reached our URL limit
            if len(expanded_urls) >= max_total_urls:
                break
                
            url = result.get("url", "")
            title = result.get("title", "")
            
            if not url:
                continue
            
            try:
                # Check if this is a priority site - use direct scraping
                is_priority_site = any(priority_site in url.lower() for priority_site in PRIORITY_SITES)
                
                if is_priority_site:
                    # Priority site - use direct HTTP scraping
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    content = response.text[:10000]  # First 10k chars for detection
                else:
                    # Non-priority site - use FireCrawl to avoid 403 errors
                    if firecrawl_key:
                        from firecrawl import FirecrawlApp
                        app = FirecrawlApp(api_key=firecrawl_key)
                        result = app.scrape_url(url, params={'formats': ['markdown']})
                        content = result.get('markdown', '')[:10000] if result else ''
                    else:
                        # No FireCrawl key - try direct scraping as fallback
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()
                        content = response.text[:10000]
                
                # Detect page type using our tiered system
                page_type = detect_page_type(url, title, content)
                
                if page_type == "recipe":
                    # Individual recipe - add directly
                    result_copy = result.copy()
                    result_copy["type"] = "recipe"
                    expanded_urls.append(result_copy)
                    
                elif page_type == "list":
                    # List page - extract recipe URLs
                    remaining_slots = max_total_urls - len(expanded_urls)
                    max_extract = min(5, remaining_slots)  # Extract up to 5 or remaining slots
                    
                    if max_extract > 0:
                        extracted_urls = await extract_recipe_urls_from_list(url, content, max_extract)
                        
                        # Add extracted URLs to our pool
                        for extracted_url in extracted_urls:
                            extracted_url["type"] = "recipe"  # Mark as recipe for safety
                            extracted_url["google_position"] = result.get("google_position", 999)
                            extracted_url["site_priority"] = result.get("site_priority", 999)
                            expanded_urls.append(extracted_url)
                            
                            # Stop if we hit the limit while processing this list
                            if len(expanded_urls) >= max_total_urls:
                                break
                    
                    # Note: Original list URL is NOT added to expanded_urls (filtered out)
                
            except Exception as e:
                print(f"Failed to process URL {url}: {e}")
                # On error, treat as individual recipe to be safe
                result_copy = result.copy()
                result_copy["type"] = "recipe"
                expanded_urls.append(result_copy)
            
            processed_count += 1
    
    # SAFETY CHECK: Filter out any URLs that might still be marked as lists
    safe_urls = [url for url in expanded_urls if url.get("type") == "recipe"]
    
    print(f"URL Expansion: {len(initial_results)} initial → {len(safe_urls)} expanded (processed {processed_count})")
    
    return safe_urls[:max_total_urls]  # Final cap to be absolutely sure




# =============================================================================
# SUPPLEMENTAL FUNCTIONS: Search and Ranking  
# These are NOT agent tools - they are internal helper functions
# =============================================================================

async def search_recipes_serpapi(ctx: RunContext[RecipeDeps], query: str, number: int = 30) -> Dict:
    """
    SUPPLEMENTAL FUNCTION: Search for recipes on the web using SerpAPI.
    Internal function for the search step.
    
    Args:
        query: The search query for recipes
        number: Number of results to return (default 30)
    
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
        
        # Format results for processing
        formatted_results = []
        for result in organic_results:
            url = result.get("link", "")
            
            # Determine site priority (0 = highest priority, 999 = not in priority list)
            site_priority = 999
            for idx, priority_site in enumerate(PRIORITY_SITES):
                if priority_site in url:
                    site_priority = idx
                    break
            
            formatted_results.append({
                "title": result.get("title", ""),
                "url": url,
                "snippet": result.get("snippet", ""),
                "source": result.get("source", ""),
                "google_position": result.get("position", 999),
                "site_priority": site_priority
            })
        
        # Sort by site priority first, then by Google position
        formatted_results.sort(key=lambda x: (x["site_priority"], x["google_position"]))
        
        return {
            "results": formatted_results[:number],
            "total": len(formatted_results),
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
    # Step 1: Search for recipes using SerpAPI (gets 30 initial URLs)
    search_results = await search_recipes_serpapi(ctx, query, number=30)
    
    if not search_results.get("results"):
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No recipes found for your search"
        }
    
    # Step 2: Smart URL Expansion (process list pages → extract individual recipe URLs)
    # This is where the magic happens - converts list pages into individual recipe URLs
    expanded_results = await expand_urls_with_lists(
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
    
    # Step 3: Rerank expanded results using LLM for best matches (handles up to 60 URLs now)
    reranked_results = await rerank_results_with_llm(
        expanded_results,
        query,
        ctx.deps.openai_key,
        top_k=10  # Get top 10 for extraction
    )
    
    # Step 4: Extract recipe details from top results (parallel)
    extracted_recipes = []
    extraction_tasks = []
    
    # Create tasks for parallel extraction
    for result in reranked_results[:max_recipes]:
        url = result.get("url")
        if url:
            # Create extraction task
            task = parse_recipe(url, ctx.deps.firecrawl_key)
            extraction_tasks.append(task)
    
    # Execute all extractions in parallel
    if extraction_tasks:
        extracted_data = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        
        # Process extracted data
        for i, data in enumerate(extracted_data):
            if isinstance(data, dict) and not data.get("error"):
                # Add search metadata to extracted recipe
                data["search_title"] = reranked_results[i].get("title", "")
                data["search_snippet"] = reranked_results[i].get("snippet", "")
                extracted_recipes.append(data)
            elif isinstance(data, Exception):
                # Log extraction failure but continue
                print(f"Failed to extract recipe from {reranked_results[i].get('url')}: {str(data)}")
    
    # Step 5: Format final results for agent
    formatted_recipes = []
    for recipe in extracted_recipes:
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
    
    return {
        "results": formatted_recipes,
        "totalResults": len(formatted_recipes),
        "searchQuery": query
    }
 



