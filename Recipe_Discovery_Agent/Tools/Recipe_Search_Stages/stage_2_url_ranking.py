"""
Stage 2: URL Ranking
Uses LLM to rank search results by relevance to user query.

This module handles the initial ranking of search results before processing.
"""

import httpx
from typing import List, Dict


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