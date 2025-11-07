"""
Hybrid recipe parsing coordinator.

This module orchestrates the multi-tiered parsing approach, trying fast
extraction methods first before falling back to LLM processing if needed.
"""

import httpx
import time
from bs4 import BeautifulSoup
from typing import Dict
import logfire
from ..extraction.structured_extractor import extract_from_json_ld, extract_from_structured_html


async def hybrid_recipe_parser(url: str, openai_key: str) -> Dict:
    """
    Hybrid recipe parser: Fast HTML parsing + LLM ingredient processing.
    
    Multi-tiered approach:
    1. JSON-LD extraction (fastest, most reliable)
    2. Structured HTML parsing (fast, site-specific)
    3. Mini-LLM call for ingredient processing only
    
    Target: 2-3 seconds vs current 5-15 seconds
    
    Args:
        url: Recipe URL to parse
        openai_key: OpenAI API key for processing
        
    Returns:
        Dict with recipe data or error information
    """
    if not openai_key:
        return {'error': 'OpenAI API key required', 'source_url': url}
    
    parse_start = time.time()
    
    try:
        # Step 1: Fast HTML scraping
        http_start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        http_time = time.time() - http_start
        
        # Step 2: BeautifulSoup parsing
        soup_start = time.time()
        soup = BeautifulSoup(html_content, 'html.parser')
        soup_time = time.time() - soup_start
        
        # Tier 1: Try JSON-LD first (fastest and most reliable)
        jsonld_start = time.time()
        recipe_data = extract_from_json_ld(soup, url)
        jsonld_time = time.time() - jsonld_start
        
        extraction_method = None
        if recipe_data:
            extraction_method = "json_ld"
            
            # Tier 2: Try structured HTML parsing
            html_start = time.time()
            recipe_data = extract_from_structured_html(soup, url)
            html_time = time.time() - html_start
            
            if recipe_data:
                extraction_method = "structured_html"
        
        if not recipe_data:
            total_time = time.time() - parse_start
            return {'error': 'No recipe data found in HTML', 'source_url': url}
        
        # Step 3: Keep raw ingredients for instant recipe discovery
        # Shopping conversion moved to background processing after recipe save
        raw_ingredients = recipe_data.get('ingredients', [])
        
        recipe_data['source_url'] = url
        total_time = time.time() - parse_start
        # Only log if parsing took unusually long (performance bottleneck)
        if total_time > 5.0:
            logfire.warn("slow_recipe_parse",
                         url=url,
                         total_time=total_time,
                         extraction_method=extraction_method)
        return recipe_data
        
    except Exception as e:
        total_time = time.time() - parse_start
        # Downgrade 403 Forbidden to warning (expected for sites that block crawling)
        if "403" in str(e) or "Forbidden" in str(e):
            logfire.warn("site_blocks_crawling",
                         url=url,
                         total_time=total_time,
                         error=str(e))
        else:
            logfire.error("recipe_parse_exception",
                          url=url,
                          total_time=total_time,
                          error=str(e))
        return {'error': f'Hybrid parsing failed: {str(e)}', 'source_url': url}