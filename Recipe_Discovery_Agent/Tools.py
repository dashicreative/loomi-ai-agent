from pydantic_ai import RunContext
from typing import Dict, List, Optional
import httpx
import asyncio
import os
from dataclasses import dataclass
from Dependencies import RecipeDeps

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



#Agent tool to make initial web search using SerpAPI. Then ranks them based on our priority sites above
async def search_recipes(ctx: RunContext[RecipeDeps], query: str, number: int = 30) -> Dict:
    """
    Search for recipes on the web using SerpAPI.
    
    Args:
        query: The search query for recipes
        number: Number of results to return (default 30)
    
    Returns:
        Dictionary containing search results with URLs and snippets
    """
    async with httpx.AsyncClient() as client:
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
        
        response = await client.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()
        
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

#Agent tool have a lightweight LLM model like GPT3.5-turbo rank top 20 out of the 30 results further using "best match" criteria to users query
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



# TODO: Implement custom parsers for top sites
# TODO: Implement FireCrawl fallback


