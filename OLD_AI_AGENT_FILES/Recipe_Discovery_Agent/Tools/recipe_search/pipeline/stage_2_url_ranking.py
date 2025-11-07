"""
Stage 2: URL Ranking
Ranks search results by priority site quality.

This module handles the initial ranking of search results before processing.
"""

import httpx
from typing import List, Dict
from Tools.recipe_search.pipeline.utils.constants import PRIORITY_SITES


async def rerank_results_with_llm(results: List[Dict], query: str, openai_key: str, top_k: int = 10) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Rank search results by priority site quality.
    Priority sites (allrecipes, simplyrecipes, etc.) come first, then others.
    
    Args:
        results: List of search results to rerank
        query: Original user query (unused but kept for compatibility)
        openai_key: OpenAI API key (unused but kept for compatibility)
        top_k: Number of top results to return after reranking
    
    Returns:
        Reranked list of results with priority sites first
    """
    if not results:
        return []
    
    # Sort by priority sites first, then others
    priority_results = []
    non_priority_results = []
    
    for result in results:
        url = result.get('url', '').lower()
        is_priority = any(priority_site in url for priority_site in PRIORITY_SITES)
        
        if is_priority:
            # Find which priority site this is and assign index for sorting
            priority_index = 999
            for i, priority_site in enumerate(PRIORITY_SITES):
                if priority_site in url:
                    priority_index = i
                    break
            result['_priority_index'] = priority_index
            priority_results.append(result)
        else:
            non_priority_results.append(result)
    
    # Sort priority results by their index in PRIORITY_SITES
    priority_results.sort(key=lambda x: x.get('_priority_index', 999))
    
    # Combine: priority sites first, then non-priority
    ranked_results = priority_results + non_priority_results
    
    return ranked_results[:top_k]