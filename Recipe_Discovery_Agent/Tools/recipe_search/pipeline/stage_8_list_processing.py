"""
Stage 8: List Processing
Handles processing of list pages to extract individual recipe URLs.

This module contains all list processing operations including URL expansion and extraction.
"""

import httpx
import asyncio
import json
from typing import Dict, List
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ...Detailed_Recipe_Parsers.list_parser import ListParser
from ...Detailed_Recipe_Parsers.url_classifier import classify_urls_batch


# Initialize the advanced list parser (will be updated with OpenAI key during runtime)
list_parser = None


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


async def extract_list_with_hybrid_approach(url: str, openai_key: str, max_urls: int = 10):
    """
    Hybrid approach: Fast HTML scraping + GPT-3.5 extraction.
    Mimics FireCrawl's structured extraction but much faster and cheaper.
    """
    if not openai_key:
        return []
    
    try:
        # Step 1: Fast HTML scraping
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        
        # Step 2: Clean and prepare content for LLM
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
            
        # Get text content with some structure preserved
        clean_content = soup.get_text(separator='\n', strip=True)
        
        # Limit content size to control costs
        max_chars = 15000  # ~3750 tokens
        if len(clean_content) > max_chars:
            clean_content = clean_content[:max_chars] + "...[content truncated]"
        
        # Step 3: LLM extraction with improved guidance
        prompt = f"""You are analyzing a recipe list page. Extract up to {max_urls} individual recipe links.

GUIDANCE:
- Only extract items that have actual clickable URLs in the content
- Do NOT extract text-only suggestions like "Five eggs" or "Greek yogurt" that have no links
- Use the EXACT URLs that appear in the content - do not modify or invent URLs
- Look for recipe links that lead to individual recipe pages
- Skip items that are just ingredient combinations without actual recipe links

Extract recipes in this JSON format:
{{
  "recipes": [
    {{
      "title": "recipe title from the content",
      "url": "exact URL found in the content", 
      "description": "description with nutrition info if available"
    }}
  ]
}}

Content to analyze:
{clean_content}"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a recipe extraction specialist. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
            )
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        llm_response = data['choices'][0]['message']['content'].strip()
        
        # Parse JSON response
        try:
            # Clean up response in case LLM added extra text
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            recipe_data = json.loads(llm_response)
            recipes = recipe_data.get('recipes', [])
            
            formatted_recipes = []
            for recipe in recipes[:max_urls]:
                if recipe.get('url') and recipe.get('title'):
                    recipe_url = recipe['url'].strip()
                    
                    # Basic URL cleanup
                    if not recipe_url.startswith('http'):
                        from urllib.parse import urljoin
                        recipe_url = urljoin(url, recipe_url)
                    
                    formatted_recipes.append({
                        'title': recipe['title'],
                        'url': recipe_url,
                        'snippet': recipe.get('description', 'Recipe from hybrid extraction'),
                        'source': 'hybrid_extraction',
                        'type': 'recipe'
                    })
            
            return formatted_recipes
                
        except json.JSONDecodeError:
            return []
        
    except Exception:
        return []


async def expand_urls_with_lists(initial_results: List[Dict], openai_key: str = None, max_total_urls: int = 60) -> List[Dict]:
    """
    SUPPLEMENTAL FUNCTION: Smart URL expansion that processes list pages to extract individual recipes.
    
    Uses batch classification for efficient URL type detection, then expands list pages
    into individual recipe URLs while filtering out irrelevant content.
    
    Args:
        initial_results: List of search result dictionaries from SerpAPI
        openai_key: OpenAI API key for classification and extraction
        max_total_urls: Maximum total URLs to return (default 60)
        
    Returns:
        Expanded list of individual recipe URLs with safety metadata
    """
    if not initial_results or not openai_key:
        return [], []
    
    # Step 1: Batch classify all URLs at once (much faster than individual classification)
    classifications = await classify_urls_batch(initial_results, openai_key)
    
    # Create a mapping of URL to classification for easy lookup
    classification_map = {c.url: c for c in classifications}
    
    expanded_urls = []
    fp1_failures = []  # Track failures
    list_urls_processed = 0  # Counter for strategic list processing
    
    # Step 2: Process URLs based on their classification
    for result in initial_results:
        # Stop if we've reached our URL limit
        if len(expanded_urls) >= max_total_urls:
            break
            
        url = result.get("url", "")
        title = result.get("title", "")
        
        if not url:
            continue
        
        # Get classification for this URL
        classification = classification_map.get(url)
        if not classification:
            # No classification available - skip
            fp1_failures.append({
                "url": url,
                "title": title,
                "error": "No classification available",
                "failure_point": "Classification_Failure_Point"
            })
            continue
        
        # Process based on classification type
        if classification.type == "recipe":
            # Individual recipe - add directly
            result_copy = result.copy()
            result_copy["type"] = "recipe"
            result_copy["classification_confidence"] = classification.confidence
            expanded_urls.append(result_copy)
            
        elif classification.type == "list":
            # List page - extract individual recipes
            list_urls_processed += 1
            
            # Cap list processing to avoid rate limits and control costs
            if list_urls_processed > 6:
                continue
            
            remaining_slots = max_total_urls - len(expanded_urls)
            max_extract = min(5, remaining_slots)  # Extract up to 5 or remaining slots
            
            if max_extract > 0:
                try:
                    # Fetch the list page content first
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()
                        html_content = response.text
                    
                    # Initialize ListParser with OpenAI key for intelligent filtering
                    intelligent_parser = ListParser(openai_key)
                    extracted_urls = await intelligent_parser.extract_recipe_urls(url, html_content, max_extract)
                    
                    # Add extracted URLs to our pool
                    for extracted_url in extracted_urls:
                        extracted_url["type"] = "recipe"  # Mark as recipe
                        extracted_url["google_position"] = result.get("google_position", 999)
                        extracted_url["from_list"] = url  # Track source list
                        expanded_urls.append(extracted_url)
                        
                        # Stop if we hit the limit while processing this list
                        if len(expanded_urls) >= max_total_urls:
                            break
                            
                except Exception as e:
                    fp1_failures.append({
                        "url": url,
                        "title": title,
                        "error": str(e),
                        "failure_point": "List_Extraction_Failure_Point"
                    })
        
        else:
            # Other types (blog, social, other) - filter out entirely
            # These don't move forward to the next stage
            pass
    
    # SAFETY CHECK: Ensure only recipe URLs are returned
    safe_urls = [url for url in expanded_urls if url.get("type") == "recipe"]
    
    return safe_urls[:max_total_urls], fp1_failures  # Return both expanded URLs and FP1 failures