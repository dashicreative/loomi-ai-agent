"""
Stage 1: Web Search
Searches for recipe URLs using SerpAPI or Google Custom Search as fallback.

This module handles the initial web search phase of the recipe discovery pipeline.
"""

import httpx
import asyncio
import sys
from pathlib import Path
from typing import Dict, List
from pydantic_ai import RunContext

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from Dependencies import RecipeDeps
from .utils.constants import BLOCKED_SITES


async def search_recipes_serpapi(ctx: RunContext[RecipeDeps], query: str, number: int = 50) -> Dict:
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
            "results": formatted_results[:50],  # Cap at 50 after filtering
            "total": len(formatted_results[:50]),
            "query": query
        }


async def search_recipes_google_custom(ctx: RunContext[RecipeDeps], query: str, number: int = 50) -> Dict:
    """
    FALLBACK FUNCTION: Search for recipes using Google Custom Search API.
    Used when SerpAPI returns insufficient results (<20 URLs).
    
    Args:
        query: The search query for recipes
        number: Number of results to return (default 40)
    
    Returns:
        Dictionary containing search results with URLs and snippets
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Add "recipe" to query if not already present
        if "recipe" not in query.lower():
            query = f"{query} recipe"
        
        # Google Custom Search API parameters
        params = {
            "key": ctx.deps.google_search_key,
            "cx": ctx.deps.google_search_engine_id,  # You'll need to add this to your .env
            "q": query,
            "num": min(number, 10),  # Google Custom Search max is 10 per request
            "hl": "en",
            "gl": "us",
            "safe": "off"
        }
        
        try:
            # Make multiple requests if we need more than 10 results
            all_results = []
            for start in range(1, number + 1, 10):  # Start at 1, increment by 10
                if len(all_results) >= number:
                    break
                    
                params["start"] = start
                response = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
                response.raise_for_status()
                data = response.json()
                
                items = data.get("items", [])
                if not items:
                    break  # No more results available
                
                # Format results to match SerpAPI format
                for item in items:
                    url = item.get("link", "")
                    
                    # Skip blocked sites entirely
                    is_blocked = any(blocked_site in url.lower() for blocked_site in BLOCKED_SITES)
                    if is_blocked:
                        continue
                    
                    all_results.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "snippet": item.get("snippet", ""),
                        "source": "google_custom_search",
                        "google_position": len(all_results) + 1
                    })
            
            return {
                "results": all_results[:number],
                "total": len(all_results[:number]),
                "query": query
            }
            
        except Exception as e:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": f"Google Custom Search failed: {str(e)}"
            }


async def search_recipes_parallel_priority(ctx: RunContext[RecipeDeps], query: str) -> Dict:
    """
    PRIORITY FUNCTION: Parallel search combining priority sites + general coverage.
    
    Strategy:
    1. Google Custom Search for priority sites only (30 results)
    2. SerpAPI for general coverage (30 results) 
    3. Combine into 60 total URLs with priority sites ranked first
    
    Args:
        query: The search query for recipes
    
    Returns:
        Dictionary containing combined search results with priority sites first
    """
    from .utils.constants import PRIORITY_SITES
    
    # Add "recipe" to query if not already present
    if "recipe" not in query.lower():
        query = f"{query} recipe"
    
    # Create priority sites query for Google Custom Search
    priority_sites_query = f"{query} (" + " OR ".join([f"site:{site}" for site in PRIORITY_SITES]) + ")"
    
    try:
        # Run both searches in parallel
        priority_task = search_recipes_google_custom(ctx, priority_sites_query, number=30)
        general_task = search_recipes_serpapi(ctx, query, number=30)
        
        priority_results, general_results = await asyncio.gather(priority_task, general_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(priority_results, Exception):
            print(f"⚠️  Priority search failed: {priority_results}")
            priority_results = {"results": [], "total": 0}
        
        if isinstance(general_results, Exception):
            print(f"⚠️  General search failed: {general_results}")
            general_results = {"results": [], "total": 0}
        
        # Extract results
        priority_urls = priority_results.get("results", [])
        general_urls = general_results.get("results", [])
        
        # Mark sources for tracking
        for url in priority_urls:
            url["search_source"] = "priority_sites"
        for url in general_urls:
            url["search_source"] = "general_search"
        
        # Remove duplicates (prioritize priority site versions)
        seen_urls = set()
        combined_results = []
        
        # Add priority site results first
        for result in priority_urls:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined_results.append(result)
        
        # Add general results (skipping duplicates)
        for result in general_urls:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                combined_results.append(result)
        
        print(f"📊 PARALLEL SEARCH RESULTS:")
        print(f"   Priority sites: {len(priority_urls)} URLs")
        print(f"   General search: {len(general_urls)} URLs") 
        print(f"   Combined total: {len(combined_results)} URLs (after deduplication)")
        
        return {
            "results": combined_results,
            "total": len(combined_results),
            "query": query,
            "priority_count": len(priority_urls),
            "general_count": len(general_urls)
        }
        
    except Exception as e:
        # Fallback to SerpAPI only if both searches fail
        print(f"⚠️  Parallel search failed, falling back to SerpAPI only: {e}")
        return await search_recipes_serpapi(ctx, query, number=50)