"""
Hybrid recipe parsing coordinator.

This module orchestrates the multi-tiered parsing approach, trying fast
extraction methods first before falling back to LLM processing if needed.
"""

import httpx
import time
from bs4 import BeautifulSoup
from typing import Dict
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
        print(f"   ⏱️  HTTP fetch: {http_time:.2f}s ({len(html_content):,} chars)")
        
        # Step 2: BeautifulSoup parsing
        soup_start = time.time()
        soup = BeautifulSoup(html_content, 'html.parser')
        soup_time = time.time() - soup_start
        print(f"   ⏱️  BeautifulSoup parse: {soup_time:.2f}s")
        
        # Tier 1: Try JSON-LD first (fastest and most reliable)
        jsonld_start = time.time()
        recipe_data = extract_from_json_ld(soup, url)
        jsonld_time = time.time() - jsonld_start
        
        if recipe_data:
            print(f"   ✅ JSON-LD extraction: {jsonld_time:.2f}s (SUCCESS)")
        else:
            print(f"   ❌ JSON-LD extraction: {jsonld_time:.2f}s (no data found)")
            
            # Tier 2: Try structured HTML parsing
            html_start = time.time()
            recipe_data = extract_from_structured_html(soup, url)
            html_time = time.time() - html_start
            
            if recipe_data:
                print(f"   ✅ HTML extraction: {html_time:.2f}s (SUCCESS)")
            else:
                print(f"   ❌ HTML extraction: {html_time:.2f}s (no data found)")
        
        if not recipe_data:
            total_time = time.time() - parse_start
            return {'error': 'No recipe data found in HTML', 'source_url': url}
        
        # Step 3: Keep raw ingredients for instant recipe discovery
        # Shopping conversion moved to background processing after recipe save
        raw_ingredients = recipe_data.get('ingredients', [])
        if raw_ingredients:
            print(f"   ✅ Using raw JSON-LD ingredients ({len(raw_ingredients)} items) - instant processing")
            # Ingredients remain as strings for ranking/display, shopping conversion happens later
        else:
            pass
        
        recipe_data['source_url'] = url
        total_time = time.time() - parse_start
        print(f"   ✅ PARSE SUCCESS - Total time: {total_time:.2f}s")
        return recipe_data
        
    except Exception as e:
        total_time = time.time() - parse_start
        print(f"   ❌ PARSE EXCEPTION - Total time: {total_time:.2f}s - Error: {str(e)}")
        return {'error': f'Hybrid parsing failed: {str(e)}', 'source_url': url}