from pydantic_ai import RunContext
from typing import Dict, List, Optional
import httpx
import asyncio
import os
from dataclasses import dataclass
from Dependencies import RecipeDeps
# Import the parser
from .Parsers import parse_recipe

"""Complete Data Flow:

  User Query
      ↓
  search_and_extract_recipes()  ← **Main Agent Tool**
      ↓
  1. search_recipes_serpapi()     ← Get 30 URLs from web
      ↓
  2. rerank_results_with_llm()    ← LLM picks best 10 URLs
      ↓
  3. parse_recipe() (parallel)    ← Extract recipe data from top 5
      ↓
  4. Format for agent             ← Structure data for user display
      ↓
  Agent Response
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




async def search_recipes_serpapi(ctx: RunContext[RecipeDeps], query: str, number: int = 30) -> Dict:
    """
    Search for recipes on the web using SerpAPI.
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
    Use GPT-3.5-turbo to rerank search results based on relevance to user query.
    
    Args:
        results: List of search results to rerank
        query: Original user query
        openai_key: OpenAI API key
        top_k: Number of top results to return after reranking
    
    Returns:
        Reranked list of results
    """
    if not results:
        return []
    
    # Prepare prompt for LLM
    recipe_list = "\n".join([
        f"{i+1}. {r['title']} - {r['snippet'][:100]}..."
        for i, r in enumerate(results[:20])  # Limit to 20 for token efficiency
    ])
    
    prompt = f"""User is searching for: "{query}"

    Rank these recipes by relevance (best match first). Consider:   
    - Exact match to query terms
    - Dietary requirements mentioned
    - Complexity/simplicity if mentioned
    - Cooking method if specified

    Recipes:
    {recipe_list}

    Return ONLY a comma-separated list of numbers in order of relevance (e.g., "3,1,5,2,4...")
    Best match first. Include at least {min(top_k, len(results))} rankings."""

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
                "max_tokens": 100
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
                if 0 <= idx < len(results) and results[idx] not in reranked:
                    reranked.append(results[idx])
            
            # Add any missing recipes from the original list
            for result in results:
                if result not in reranked and len(reranked) < top_k:
                    reranked.append(result)
            
            return reranked[:top_k]
            
        except (ValueError, IndexError):
            # If parsing fails, return original order
            return results[:top_k]



#Primary 
async def search_and_extract_recipes(ctx: RunContext[RecipeDeps], query: str, max_recipes: int = 5) -> Dict:
    """
    Complete recipe discovery flow: Search → Rerank → Scrape → Extract
    
    This is the main tool that the agent will use for recipe discovery.
    Replaces the old Spoonacular search_recipes function.
    
    Args:
        query: User's search query
        max_recipes: Maximum number of recipes to return with full details (default 5)
    
    Returns:
        Dictionary with structured recipe data ready for agent processing
    """
    # Step 1: Search for recipes using SerpAPI
    search_results = await search_recipes_serpapi(ctx, query, number=30)
    
    if not search_results.get("results"):
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No recipes found for your search"
        }
    
    # Step 2: Rerank results using LLM for best matches
    reranked_results = await rerank_results_with_llm(
        search_results["results"],
        query,
        ctx.deps.openai_key,
        top_k=10  # Get top 10 for extraction
    )
    
    # Step 3: Extract recipe details from top results (parallel)
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
    
    # Step 4: Format final results for agent
    formatted_recipes = []
    for recipe in extracted_recipes:
        formatted_recipes.append({
            "id": len(formatted_recipes) + 1,  # Simple ID generation
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": recipe.get("ingredients", []),
            # Instructions are available for agent analysis but won't be displayed
            "_instructions_for_analysis": recipe.get("instructions", [])
        })
    
    return {
        "results": formatted_recipes,
        "totalResults": len(formatted_recipes),
        "searchQuery": query
    }
 



