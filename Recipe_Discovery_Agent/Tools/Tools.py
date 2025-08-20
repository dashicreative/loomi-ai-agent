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
# SUPPLEMENTAL FUNCTIONS: Quality Checks for Unknown Sites
# These are NOT agent tools - they are internal helper functions
# =============================================================================

def passes_quality_check(url: str, content: str) -> bool:
    """
    SUPPLEMENTAL FUNCTION: Strict quality check for unknown recipe sites.
    
    Checks for essential elements needed for the iOS app:
    1. Recipe images (for app photo display)
    2. Clear recipe name/title
    3. Structured ingredient list (JSON-LD → HTML lists → text patterns)
    
    Philosophy: Better to reject good sites than accept bad ones.
    
    Args:
        url: Recipe page URL
        content: HTML content of the page
        
    Returns:
        True if site passes all quality checks, False otherwise
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # CRITERION 1: Image presence (essential for app)
        has_recipe_image = False
        images = soup.find_all('img')
        for img in images:
            alt_text = (img.get('alt', '') + ' ' + img.get('src', '')).lower()
            # Look for food/recipe related images
            if any(keyword in alt_text for keyword in [
                'recipe', 'food', 'dish', 'meal', 'cooking', 'baked', 'fried',
                'salad', 'soup', 'pasta', 'chicken', 'beef', 'dessert', 'cake'
            ]):
                has_recipe_image = True
                break
        
        if not has_recipe_image:
            return False
            
        # CRITERION 2: Recipe name/title presence
        has_recipe_name = False
        # Check common title locations
        title_elements = soup.find_all(['h1', 'h2', 'title'])
        for element in title_elements:
            title_text = element.get_text().lower()
            if any(keyword in title_text for keyword in [
                'recipe', 'how to make', 'easy', 'homemade', 'baked', 'grilled'
            ]) or len(title_text) > 10:  # Reasonable recipe title length
                has_recipe_name = True
                break
                
        if not has_recipe_name:
            return False
            
        # CRITERION 3: Ingredient list detection (tiered approach)
        has_ingredients = False
        
        # Tier 1: JSON-LD recipe schema
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                import json
                data = json.loads(json_ld.string)
                if isinstance(data, list):
                    data = data[0] if data else {}
                if data.get('@type') == 'Recipe' and data.get('recipeIngredient'):
                    has_ingredients = True
            except:
                pass
        
        # Tier 2: HTML lists with ingredient-like content
        if not has_ingredients:
            lists = soup.find_all(['ul', 'ol'])
            for lst in lists:
                items = lst.find_all('li')
                ingredient_count = 0
                for item in items:
                    text = item.get_text().lower()
                    # Look for quantity + unit patterns
                    if any(pattern in text for pattern in [
                        'cup', 'tsp', 'tbsp', 'ounce', 'pound', 'gram', 'liter',
                        'large', 'medium', 'small', 'piece', 'slice', 'clove',
                        'scoop', 'dash', 'pinch'  # Include common cooking terms
                    ]) and any(char.isdigit() for char in text):
                        ingredient_count += 1
                
                if ingredient_count >= 3:  # At least 3 ingredients with quantities
                    has_ingredients = True
                    break
        
        # Tier 3: Text patterns for ingredients
        if not has_ingredients:
            page_text = soup.get_text().lower()
            # Look for common ingredient patterns in text
            import re
            ingredient_patterns = [
                r'\d+\s+(cup|cups|tsp|tbsp|ounce|pound|gram|liter)',
                r'\d+\s+(large|medium|small|whole)',
                r'\d+\s+(piece|pieces|slice|slices|clove|cloves)',
                r'\d+\s+scoop',  # Include scoop and other cooking terms
                r'pinch of',
                r'dash of'
            ]
            
            pattern_matches = 0
            for pattern in ingredient_patterns:
                if re.search(pattern, page_text):
                    pattern_matches += 1
                    if pattern_matches >= 2:  # At least 2 different patterns
                        has_ingredients = True
                        break
        
        return has_ingredients
        
    except Exception as e:
        print(f"Quality check failed for {url}: {e}")
        return False


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
                    # Priority site - use direct HTTP scraping, fallback to FireCrawl on 403
                    try:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()
                        content = response.text[:10000]  # First 10k chars for detection
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 403 and firecrawl_key:
                            # 403 on priority site - fallback to FireCrawl
                            from firecrawl import FirecrawlApp
                            app = FirecrawlApp(api_key=firecrawl_key)
                            firecrawl_result = app.scrape(url, formats=['markdown'])
                            content = getattr(firecrawl_result, 'markdown', '')[:10000] if firecrawl_result else ''
                        else:
                            raise  # Re-raise other errors
                else:
                    # Non-priority site - use FireCrawl to avoid 403 errors
                    if firecrawl_key:
                        from firecrawl import FirecrawlApp
                        app = FirecrawlApp(api_key=firecrawl_key)
                        firecrawl_result = app.scrape(url, formats=['markdown'])
                        content = getattr(firecrawl_result, 'markdown', '')[:10000] if firecrawl_result else ''
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
                        # Ensure content is a string for HTML parsing
                        content_str = str(content) if content else ''
                        extracted_urls = await extract_recipe_urls_from_list(url, content_str, max_extract)
                        
                        # Add extracted URLs to our pool
                        for extracted_url in extracted_urls:
                            extracted_url["type"] = "recipe"  # Mark as recipe for safety
                            # Get metadata from original search result (not FireCrawl result)
                            extracted_url["google_position"] = result.get("google_position", 999)
                            expanded_urls.append(extracted_url)
                            
                            # Stop if we hit the limit while processing this list
                            if len(expanded_urls) >= max_total_urls:
                                break
                    
                    # Note: Original list URL is NOT added to expanded_urls (filtered out)
                
            except Exception as e:
                print(f"Failed to process URL {url}: {e}")
                # On error, do a quick title-based detection to avoid adding list URLs
                page_type = detect_page_type(url, title, "")  # Use title-only detection
                if page_type == "recipe":
                    # Only add if it appears to be an individual recipe
                    result_copy = result.copy()
                    result_copy["type"] = "recipe"
                    expanded_urls.append(result_copy)
                # If it appears to be a list, skip it entirely (don't add to expanded_urls)
            
            processed_count += 1
    
    # SAFETY CHECK: Filter out any URLs that might still be marked as lists
    safe_urls = [url for url in expanded_urls if url.get("type") == "recipe"]
    
    print(f"URL Expansion: {len(initial_results)} initial → {len(safe_urls)} expanded (processed {processed_count})")
    
    return safe_urls[:max_total_urls]  # Final cap to be absolutely sure




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
    # Step 1: Search for recipes using SerpAPI (gets up to 30 URLs after blacklist filtering)
    search_results = await search_recipes_serpapi(ctx, query)
    
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
    
    # STAGE 1: Initial LLM ranking by title + snippet relevance
    stage1_ranked_results = await rerank_results_with_llm(
        expanded_results,
        query,
        ctx.deps.openai_key,
        top_k=len(expanded_results)  # Rank ALL results for fallback capability
    )
    
    # Step 4: Parse ALL 30 URLs for Stage 2 ranking (LLM needs ingredient data)
    # Process all Stage 1 ranked results to give LLM full ingredient information
    candidates_to_parse = stage1_ranked_results[:25]  # Parse top 25 for Stage 2 ranking
    
    # Step 5: Parse all candidates (with smart quality checking for unknown sites)
    extraction_tasks = []
    successful_parses = []
    failed_parses = []
    
    for result in candidates_to_parse:
        url = result.get("url")
        if url:
            task = parse_recipe(url, ctx.deps.firecrawl_key)
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
                    "error": str(data) if isinstance(data, Exception) else data.get("error", "Unknown error")
                })
        
        # ELEGANT FAILURE HANDLING: Only quality check failed parses if < 3 successful recipes
        if len(successful_parses) < 3 and failed_parses:
            print(f"Only {len(successful_parses)} successful parses, quality checking {len(failed_parses)} failed sites...")
            
            for failed_parse in failed_parses:
                url = failed_parse["result"].get("url", "")
                
                # Skip priority sites (they shouldn't fail, and if they do, quality check won't help)
                is_priority_site = any(priority_site in url.lower() for priority_site in PRIORITY_SITES)
                if is_priority_site:
                    continue
                
                # Quality check unknown sites that failed parsing
                try:
                    from firecrawl import FirecrawlApp
                    app = FirecrawlApp(api_key=ctx.deps.firecrawl_key)
                    firecrawl_result = app.scrape(url, formats=['html'])
                    content = getattr(firecrawl_result, 'html', '') if firecrawl_result else ''
                    
                    if not passes_quality_check(url, content):
                        print(f"Quality check failed for failed parse: {url}")
                        # Remove from failed_parses so we don't retry parsing
                        continue
                    else:
                        print(f"Quality check passed for failed parse: {url} - will retry parsing")
                        # Could implement retry logic here, but for now just log
                        
                except Exception as e:
                    print(f"Quality check error for {url}: {e}")
                
                # Stop quality checking if we have enough successful recipes now
                if len(successful_parses) >= 3:
                    break
        
        extracted_recipes = successful_parses
    
    # STAGE 2: Deep content ranking using full recipe data
    if len(extracted_recipes) > 1:  # Only re-rank if we have multiple recipes
        final_ranked_recipes = await rerank_with_full_recipe_data(
            extracted_recipes,
            query,
            ctx.deps.openai_key
        )
    else:
        final_ranked_recipes = extracted_recipes
    
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
    
    # Track failed parses for business reporting
    failed_parse_report = {
        "total_failed": len(failed_parses),
        "failed_urls": [fp["result"].get("url", "") for fp in failed_parses]
    }
    
    return {
        "results": formatted_recipes,
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "_failed_parse_report": failed_parse_report  # For business analytics
    }
 



