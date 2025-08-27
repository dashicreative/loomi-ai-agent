from pydantic_ai import RunContext
from typing import Dict, List, Optional
import httpx
import asyncio
import os
import random
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from Dependencies import RecipeDeps
# Import the parser and ingredient parsing
from .Detailed_Recipe_Parsers.Parsers import parse_recipe
from .Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list
from .Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list
from .Detailed_Recipe_Parsers.list_parser import ListParser
from .Detailed_Recipe_Parsers.url_classifier import classify_urls_batch
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
    "epicurious.com",
    "bbcgoodfood.com"  # Added at bottom - good site but lower priority
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




# Initialize the advanced list parser (will be updated with OpenAI key during runtime)
list_parser = None


async def search_and_process_recipes_tool(ctx: RunContext[RecipeDeps], query: str, needed_count: int = 5) -> Dict:
    """
    AGENT TOOL: Complete recipe search pipeline - search, rank, expand, scrape, and format.
    
    Single tool that handles the entire recipe discovery process internally.
    Combines all stages into one seamless operation.
    
    Args:
        query: User's recipe search query
        needed_count: Number of final recipes to return (default 5)
        
    Returns:
        Dict with structured recipe data ready for agent/iOS consumption
    """
    print(f"🔍 COMPLETE RECIPE SEARCH: Processing '{query}'")
    total_pipeline_start = time.time()
    
    # Stage 1: Web Search
    stage1_start = time.time()
    search_results = await search_recipes_serpapi(ctx, query, number=40)
    stage1_time = time.time() - stage1_start
    
    raw_results = search_results.get("results", [])
    if not raw_results:
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No search results found"
        }
    
    print(f"📊 Stage 1: Web Search - Found {len(raw_results)} URLs - {stage1_time:.2f}s")
    
    # Stage 2: Initial Ranking
    stage2_start = time.time()
    ranked_urls = await rerank_results_with_llm(
        raw_results, 
        query, 
        ctx.deps.openai_key, 
        top_k=50
    )
    stage2_time = time.time() - stage2_start
    
    print(f"📊 Stage 2: Initial Ranking - Ranked {len(ranked_urls)} URLs - {stage2_time:.2f}s")
    
    # Now begin the batch processing logic (formerly from process_recipe_batch_tool)
    batch_size = 10
    urls = ranked_urls  # Use ranked URLs directly
    user_query = query  # Use the query parameter for consistency
    
    try:
        all_recipes = []
        all_fp1_failures = []
        all_failed_parses = []
        batch_count = 0
        url_backlog = []  # List URLs and slow URLs deferred for later processing
        
        # FIRST: Rank all URLs by priority sites before any processing
        print(f"📊 Initial Quality Ranking: Ordering {len(urls)} URLs by priority sites...")
        priority_ranked_urls = []
        non_priority_urls = []
        
        for url_dict in urls:
            url = url_dict.get('url', '').lower()
            found_priority = False
            
            # Check if this URL is from a priority site
            for i, priority_site in enumerate(PRIORITY_SITES):
                if priority_site in url:
                    url_dict['_priority_index'] = i
                    priority_ranked_urls.append(url_dict)
                    found_priority = True
                    break
            
            if not found_priority:
                non_priority_urls.append(url_dict)
        
        # Sort priority URLs by their order in PRIORITY_SITES list
        priority_ranked_urls.sort(key=lambda x: x.get('_priority_index', 999))
        
        # Combine: priority sites first (in order), then all others
        urls = priority_ranked_urls + non_priority_urls
        
        print(f"   ✅ Ranked: {len(priority_ranked_urls)} priority sites, {len(non_priority_urls)} others")
        if priority_ranked_urls:
            unique_sites = list(dict.fromkeys([u.get('url', '').split('/')[2] for u in priority_ranked_urls]))
            print(f"   📍 Priority sites found: {unique_sites[:5]}")
        
        # We'll classify URLs batch by batch, not all at once
        print(f"📊 Ready to process {len(urls)} URLs in batches")
    except Exception as e:
        print(f"❌ ERROR in batch processing setup: {e}")
        import traceback
        traceback.print_exc()
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": user_query,
            "error": f"Batch setup failed: {str(e)}"
        }
    
    # Process URLs in batches until we have enough recipes
    for batch_start in range(0, len(urls), batch_size):
        batch_count += 1
        batch_end = min(batch_start + batch_size, len(urls))
        current_batch = urls[batch_start:batch_end]
        
        print(f"\n🔄 Processing Batch {batch_count}: URLs {batch_start}-{batch_end-1} ({len(current_batch)} URLs)")
        batch_total_start = time.time()
        
        # Classify just the URLs in THIS batch
        print(f"   🔍 Classifying {len(current_batch)} URLs in this batch...")
        try:
            batch_classifications = await classify_urls_batch(current_batch, ctx.deps.openai_key)
            batch_classification_map = {c.url: c for c in batch_classifications}
        except Exception as e:
            print(f"   ⚠️  Batch classification failed: {e}")
            print(f"   ⚠️  Treating all batch URLs as recipe URLs")
            batch_classification_map = {}
        
        # Separate recipe URLs from list URLs in this batch
        batch_recipe_urls = []
        batch_list_urls = []
        for url_dict in current_batch:
            url = url_dict.get('url', '')
            classification = batch_classification_map.get(url)
            if classification and classification.type == 'list':
                batch_list_urls.append(url_dict)
            else:
                batch_recipe_urls.append(url_dict)
        
        # Defer ALL list URLs to backlog - don't process any now
        if batch_list_urls:
            url_backlog.extend(batch_list_urls)
            print(f"   📊 Deferring {len(batch_list_urls)} list URLs to backlog (will process only if needed)")
        
        # Only process recipe URLs
        urls_to_process = batch_recipe_urls
        
        # Stage 3: URL Expansion - SKIPPED (all list URLs deferred to backlog)
        # Since we defer all list URLs, we never need to expand in regular batches
        expanded_results = urls_to_process
        fp1_failures = []
        print(f"📊 Batch {batch_count} - Stage 3: Skipped (list URLs deferred to backlog)")
        
        if not expanded_results:
            print(f"⚠️  Batch {batch_count} - No URLs after expansion, skipping")
            all_fp1_failures.extend(fp1_failures)
            continue
        
        # Stage 4: Recipe Scraping for this batch with 5-second timeout
        stage4_start = time.time()
        successful_parses = []
        failed_parses = []
        
        # Process URLs with 5-second timeout, defer slow ones to backlog
        for result in expanded_results:
            url = result.get("url")
            if url:
                try:
                    # Apply 5-second timeout to recipe parsing
                    data = await asyncio.wait_for(
                        parse_recipe(url, ctx.deps.openai_key), 
                        timeout=5.0
                    )
                    
                    if isinstance(data, dict) and not data.get("error"):
                        # Add search metadata
                        data["search_title"] = result.get("title", "")
                        data["search_snippet"] = result.get("snippet", "")
                        successful_parses.append(data)
                    else:
                        # Track failed parse
                        failed_parses.append({
                            "result": result,
                            "error": data.get("error", "Unknown error") if isinstance(data, dict) else str(data),
                            "failure_point": "Recipe_Parsing_Failure_Point"
                        })
                        
                except asyncio.TimeoutError:
                    # Defer slow URLs to backlog for later processing
                    print(f"   ⏰ Timeout: Deferring slow URL to backlog: {url}")
                    url_backlog.append(result)
                except Exception as e:
                    # Track other exceptions as failed parses
                    failed_parses.append({
                        "result": result,
                        "error": str(e),
                        "failure_point": "Recipe_Parsing_Exception"
                    })
        
        # Parse nutrition data for successful recipes
        for recipe in successful_parses:
            raw_nutrition = recipe.get("nutrition", [])
            recipe["structured_nutrition"] = parse_nutrition_list(raw_nutrition)
        
        stage4_time = time.time() - stage4_start
        batch_total_time = time.time() - batch_total_start
        
        print(f"📊 Batch {batch_count} - Stage 4: Recipe Scraping - Successfully parsed {len(successful_parses)} recipes - {stage4_time:.2f}s")
        print(f"⏱️  Batch {batch_count} Total Time: {batch_total_time:.2f}s")
        
        if failed_parses:
            failed_urls = [fp.get("result", {}).get("url", "") for fp in failed_parses]
            print(f"❌ Batch {batch_count} failed to parse: {', '.join(failed_urls)}")
        
        # Add batch results to overall collections
        all_recipes.extend(successful_parses)
        all_fp1_failures.extend(fp1_failures)
        all_failed_parses.extend(failed_parses)
        
        # Stage 5: Final Ranking after each batch
        stage5_start = time.time()
        if len(all_recipes) > 1:
            final_ranked_recipes = await rerank_with_full_recipe_data(
                all_recipes,
                user_query,
                ctx.deps.openai_key
            )
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking after batch {batch_count} - Ranking {len(all_recipes)} total recipes - {stage5_time:.2f}s")
        
        # Early exit: if we have enough FINAL recipes after ranking, stop processing batches
        if len(final_ranked_recipes) >= needed_count:
            print(f"✅ Found {len(final_ranked_recipes)} final recipes (needed {needed_count}), stopping batch processing")
            break
        else:
            print(f"📊 Progress: {len(final_ranked_recipes)}/{needed_count} final recipes found, continuing...")
    
    # Process url_backlog if we still need more recipes
    if len(final_ranked_recipes) < needed_count and url_backlog:
        print(f"\n📋 PROCESSING URL BACKLOG: {len(url_backlog)} list URLs deferred")
        print(f"   Still need {needed_count - len(final_ranked_recipes)} more recipes")
        
        # Process backlog URLs (these are primarily list URLs)
        for backlog_url_dict in url_backlog:
            if len(final_ranked_recipes) >= needed_count:
                print(f"   ✅ Found enough final recipes, stopping backlog processing")
                break
                
            url = backlog_url_dict.get('url', '')
            print(f"   🔄 Processing backlog URL: {url}")
            
            # Stage 3: Expand list URL
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    html_content = response.text
                
                # Use ListParser to extract recipe URLs
                intelligent_parser = ListParser(ctx.deps.openai_key)
                extracted_recipes = await intelligent_parser.extract_recipe_urls(
                    url, 
                    html_content, 
                    max_urls=needed_count - len(final_ranked_recipes)  # Only get what we need
                )
                
                if extracted_recipes:
                    print(f"      ✅ Extracted {len(extracted_recipes)} recipes from list URL")
                    
                    # Stage 4: Parse the extracted recipes
                    extraction_tasks = []
                    for recipe_url_dict in extracted_recipes:
                        recipe_url = recipe_url_dict.get("url")
                        if recipe_url:
                            task = parse_recipe(recipe_url, ctx.deps.openai_key)
                            extraction_tasks.append(task)
                    
                    if extraction_tasks:
                        extracted_data = await asyncio.gather(*extraction_tasks, return_exceptions=True)
                        
                        for i, data in enumerate(extracted_data):
                            if isinstance(data, dict) and not data.get("error"):
                                data["search_title"] = extracted_recipes[i].get("title", "")
                                data["search_snippet"] = extracted_recipes[i].get("snippet", "")
                                all_recipes.append(data)
                                print(f"      ✅ Successfully parsed recipe {len(all_recipes)}/{needed_count}")
                            else:
                                print(f"      ❌ Failed to parse: {extracted_recipes[i].get('url', '')}")
                else:
                    print(f"      ⚠️ No recipes extracted from list URL")
                    
            except Exception as e:
                print(f"      ❌ Failed to process backlog URL: {e}")
                all_fp1_failures.append({
                    "url": url,
                    "title": backlog_url_dict.get('title', ''),
                    "error": str(e),
                    "failure_point": "Backlog_List_Expansion_Failure"
                })
        
        print(f"📋 Backlog processing complete: {len(all_recipes)} total recipes")
        
        # Stage 5: Final Ranking after backlog processing
        stage5_start = time.time()
        if len(all_recipes) > 1:
            final_ranked_recipes = await rerank_with_full_recipe_data(
                all_recipes,
                user_query,
                ctx.deps.openai_key
            )
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking after backlog - Ranking {len(all_recipes)} total recipes - {stage5_time:.2f}s")
    
    # Ensure final_ranked_recipes is defined (in case no batches or backlog processing occurred)
    if 'final_ranked_recipes' not in locals():
        final_ranked_recipes = all_recipes
    
    # Stage 6: Final Formatting
    stage6_start = time.time()
    formatted_recipes = []
    for recipe in final_ranked_recipes[:needed_count]:
        # Parse ingredients into structured format
        raw_ingredients = recipe.get("ingredients", [])
        structured_ingredients = parse_ingredients_list(raw_ingredients)
        
        # Parse nutrition into structured format
        raw_nutrition = recipe.get("nutrition", [])
        structured_nutrition = parse_nutrition_list(raw_nutrition)
        
        formatted_recipes.append({
            "id": len(formatted_recipes) + 1,
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,
            "nutrition": structured_nutrition,
            "_instructions_for_analysis": recipe.get("instructions", [])
        })
    
    # Track failures for reporting
    all_failures = all_fp1_failures + all_failed_parses
    failed_parse_report = {
        "total_failed": len(all_failures),
        "content_scraping_failures": len(all_fp1_failures),
        "recipe_parsing_failures": len(all_failed_parses),
        "failed_urls": [
            {
                "url": fp.get("url") or fp.get("result", {}).get("url", ""),
                "failure_point": fp.get("failure_point", "Unknown"),
                "error": fp.get("error", "Unknown error")
            }
            for fp in all_failures
        ]
    }
    stage6_time = time.time() - stage6_start
    
    print(f"📊 Stage 6: Final Formatting - Structured {len(formatted_recipes)} recipes - {stage6_time:.2f}s")
    
    # Performance summary
    total_time = time.time() - total_pipeline_start
    print(f"\n⏱️  COMPLETE PIPELINE PERFORMANCE:")
    print(f"   Total Time: {total_time:.2f}s")
    print(f"   Stage 1 (Web Search): {stage1_time:.2f}s ({(stage1_time/total_time)*100:.1f}%)")
    print(f"   Stage 2 (Initial Ranking): {stage2_time:.2f}s ({(stage2_time/total_time)*100:.1f}%)")
    # Note: Stage 3-6 timing is aggregated across batches
    
    # Create minimal context for agent
    minimal_recipes = []
    for recipe in formatted_recipes:
        minimal_recipes.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "servings": recipe["servings"],
            "readyInMinutes": recipe["readyInMinutes"],
            "ingredients": [ing["ingredient"] for ing in recipe["ingredients"][:8]],
            "nutrition": recipe.get("nutrition", [])
        })
    
    # TODO: DELETE LATER - Development debugging to see final recipe selections
    print("\n" + "="*60)
    print("🍳 FINAL 5 RECIPES SELECTED:")
    print("="*60)
    for i, recipe in enumerate(formatted_recipes[:5], 1):
        print(f"{i}. {recipe.get('title', 'Unknown Title')}")
        print(f"   URL: {recipe.get('sourceUrl', 'No URL')}")
    print("="*60 + "\n")
    # END DELETE LATER
    
    return {
        "results": minimal_recipes,  # Minimal context for agent
        "full_recipes": formatted_recipes,  # Full data for iOS
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "_failed_parse_report": failed_parse_report
    }


# Removed process_recipe_batch_tool - functionality merged into search_and_process_recipes_tool


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
            
            import json
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
    print(f"🔍 Classifying {len(initial_results)} URLs in batch...")
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
    
    # STAGE 5A: Recipe Filtering - Remove insufficient recipes
    substage5a_start = time.time()
    filtered_recipes = []
    
    for recipe in scraped_recipes:
        # Check required fields
        has_title = bool(recipe.get("title", "").strip())
        has_image = bool(recipe.get("image_url", "").strip())
        has_ingredients = bool(recipe.get("ingredients", []))
        has_nutrition = bool(recipe.get("nutrition", []))
        
        # Check required nutrition fields (calories, protein, fat, carbs)
        nutrition_data = recipe.get("nutrition", [])
        required_nutrition = {"calories", "protein", "fat", "carbs"}
        found_nutrition = set()
        
        for nutrition_item in nutrition_data:
            if isinstance(nutrition_item, str):
                # Handle string format like "250 calories"
                nutrition_lower = nutrition_item.lower()
                for req_nutrient in required_nutrition:
                    if req_nutrient in nutrition_lower:
                        found_nutrition.add(req_nutrient)
            elif isinstance(nutrition_item, dict):
                # Handle structured format
                nutrient_name = nutrition_item.get("name", "").lower()
                if nutrient_name in required_nutrition:
                    found_nutrition.add(nutrient_name)
        
        has_required_nutrition = len(found_nutrition) >= 4
        
        # Only keep recipes that meet ALL criteria
        if has_title and has_image and has_ingredients and has_required_nutrition:
            filtered_recipes.append(recipe)
        else:
            missing_fields = []
            if not has_title: missing_fields.append("title")
            if not has_image: missing_fields.append("image")
            if not has_ingredients: missing_fields.append("ingredients")
            if not has_required_nutrition: 
                missing_nutrition = required_nutrition - found_nutrition
                missing_fields.append(f"nutrition({','.join(missing_nutrition)})")
            
            print(f"   ❌ Filtered out recipe '{recipe.get('title', 'Untitled')}' - Missing: {', '.join(missing_fields)}")
    
    print(f"   ✅ Recipe filtering: {len(filtered_recipes)}/{len(scraped_recipes)} recipes passed validation")
    substage5a_time = time.time() - substage5a_start
    
    if not filtered_recipes:
        return []
    
    # STAGE 5B: Data Preparation
    substage5b_start = time.time()
    detailed_recipes = []
    for i, recipe in enumerate(filtered_recipes):
        # Build comprehensive recipe summary for LLM analysis
        ingredients_list = recipe.get("ingredients", [])[:10]  # First 10 ingredients
        # Extract full ingredient amounts from structured format
        ingredients_text = ", ".join([f"{ing.get('quantity', '')} {ing.get('unit', '')} {ing.get('ingredient', '')}" for ing in ingredients_list if ing.get('ingredient')])
        instructions_preview = " ".join(recipe.get("instructions", [])[:2])[:1000]  # First 2 steps, expanded context
        
        # Build nutrition text from structured nutrition data
        structured_nutrition = recipe.get("structured_nutrition", [])
        nutrition_text = ", ".join([f"{n.get('amount', '')} {n.get('unit', '')} {n.get('name', '')}" for n in structured_nutrition if n.get('name')])
        
        recipe_summary = f"""{i+1}. {recipe.get('title', 'Untitled Recipe')}
Ingredients: {ingredients_text}
Nutrition: {nutrition_text}
Cook Time: {recipe.get('cook_time', 'Not specified')}
Servings: {recipe.get('servings', 'Not specified')}
Instructions Preview: {instructions_preview}..."""
        
        detailed_recipes.append(recipe_summary)
    substage5b_time = time.time() - substage5b_start
    
    # STAGE 5C: Prompt Construction  
    substage5c_start = time.time()
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
    6. RECIPE TYPE MATCHING - EXCLUSION RULE: 
       - If query asks for "[food] recipe" (e.g., "steak recipe"), EXCLUDE from consideration any recipes that are primarily marinades, sauces, or dressings
       - These recipes CANNOT appear in the final ranking unless user specifically asks for them (e.g., "steak marinade recipe")
       - Examples: "steak recipe" → EXCLUDE any steak marinades, "chicken recipe" → EXCLUDE chicken marinades/sauces
       - Only rank actual cooking recipes that prepare the main food item

    Additional factors:
    - NUTRITION REQUIREMENTS: ONLY use the provided nutrition values (calories, protein, carbs, fat) - DO NOT estimate or guess nutrition from ingredients
    - Dietary requirements (high protein, low carb, etc.) - use exact nutrition numbers provided
    - Time constraints (quick, under 30 minutes, etc.)
    - Meal type appropriateness

    Recipes with full details:
    {recipes_text}

    Return ONLY a comma-separated list of numbers in order of relevance (e.g., "3,1,5,2,4...")
    Best match first based on the COMPLETE recipe content."""
    substage5c_time = time.time() - substage5c_start

    # STAGE 5D: LLM API Call
    substage5d_start = time.time()
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
            # If LLM fails, return filtered recipes in original order
            return filtered_recipes
        
        data = response.json()
        ranking_text = data['choices'][0]['message']['content'].strip()
    substage5d_time = time.time() - substage5d_start
        
    # STAGE 5E: Response Processing
    substage5e_start = time.time()
    # Parse the ranking
    try:
        rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
        reranked = []
        
        # Add recipes in the ranked order
        for idx in rankings:
            if 0 <= idx < len(filtered_recipes) and filtered_recipes[idx] not in reranked:
                reranked.append(filtered_recipes[idx])
        
        # Add any missing recipes
        for recipe in filtered_recipes:
            if recipe not in reranked:
                reranked.append(recipe)
        
        return reranked
        
    except (ValueError, IndexError):
        # If parsing fails, return filtered recipes in original order
        return filtered_recipes
    finally:
        substage5e_time = time.time() - substage5e_start
        
        # Print Stage 5 sub-timings
        print(f"   🔍 Stage 5A (Recipe Filtering): {substage5a_time:.3f}s")
        print(f"   🔍 Stage 5B (Data Prep): {substage5b_time:.3f}s")
        print(f"   🔍 Stage 5C (Prompt Build): {substage5c_time:.3f}s") 
        print(f"   🔍 Stage 5D (LLM API Call): {substage5d_time:.3f}s")
        print(f"   🔍 Stage 5E (Response Parse): {substage5e_time:.3f}s")



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
    # PERFORMANCE TIMING: Start total timer
    total_start = time.time()
    
    # STAGE 1: Search for recipes using SerpAPI
    stage1_start = time.time()
    search_results = await search_recipes_serpapi(ctx, query)
    stage1_time = time.time() - stage1_start
    
    # Clean stage summary with priority sites count
    results = search_results.get('results', [])
    priority_count = sum(1 for result in results if any(priority_site in result.get('url', '').lower() for priority_site in PRIORITY_SITES))
    print(f"\n📊 Stage 1: Web Search - Found {len(results)} URLs ({priority_count} from priority sites) - {stage1_time:.2f}s")
    
    if not search_results.get("results"):
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No recipes found for your search"
        }
    
    # STAGE 2: Smart URL Expansion (process list pages → extract individual recipe URLs)
    stage2_start = time.time()
    expanded_results, fp1_failures = await expand_urls_with_lists(
        search_results["results"], 
        openai_key=ctx.deps.openai_key,
        max_total_urls=60
    )
    stage2_time = time.time() - stage2_start
    
    print(f"📊 Stage 2: URL Expansion - {len(search_results.get('results', []))} → {len(expanded_results)} URLs - {stage2_time:.2f}s")
    
    if not expanded_results:
        return {
            "results": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No valid recipes found after processing search results"
        }
    
    # STAGE 3: Initial ranking by priority sites (quality over relevance)
    stage3_start = time.time()
    priority_urls = []
    non_priority_urls = []
    
    # Separate priority sites from non-priority sites and rank by PRIORITY_SITES order
    for result in expanded_results:
        url = result.get('url', '').lower()
        # Use more precise matching to avoid substring issues (e.g., bbcgoodfood.com containing food.com)
        if any(f"//{priority_site}" in url or f".{priority_site}" in url for priority_site in PRIORITY_SITES):
            # Find which priority site this URL belongs to and add its index for sorting
            for i, priority_site in enumerate(PRIORITY_SITES):
                if f"//{priority_site}" in url or f".{priority_site}" in url:
                    result['_priority_index'] = i
                    priority_urls.append(result)
                    break
        else:
            non_priority_urls.append(result)
    
    # Sort priority URLs by their order in PRIORITY_SITES list (lower index = higher priority)
    priority_urls.sort(key=lambda x: x.get('_priority_index', 999))
    
    # Combine: priority sites first (in PRIORITY_SITES order), then non-priority sites
    stage1_ranked_results = priority_urls + non_priority_urls
    stage3_time = time.time() - stage3_start
    
    print(f"📊 Stage 3: Initial Ranking - Selected top {min(15, len(stage1_ranked_results))} URLs for scraping - {stage3_time:.2f}s")
    
    # STAGE 4: Parse recipes for full data extraction
    stage4_start = time.time()
    candidates_to_parse = stage1_ranked_results[:15]  # Parse top 15 for Stage 2 ranking
    
    # Build extraction tasks
    extraction_tasks = []
    successful_parses = []
    failed_parses = []
    
    for result in candidates_to_parse:
        url = result.get("url")
        if url:
            task = parse_recipe(url, ctx.deps.openai_key)
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
                    "error": str(data) if isinstance(data, Exception) else data.get("error", "Unknown error"),
                    "failure_point": "Recipe_Parsing_Failure_Point"
                })
        
        # No more quality checking - failed parses are simply tracked for reporting
        
        # Parse nutrition data immediately after successful extraction
        for recipe in successful_parses:
            raw_nutrition = recipe.get("nutrition", [])
            recipe["structured_nutrition"] = parse_nutrition_list(raw_nutrition)
        
        extracted_recipes = successful_parses
    stage4_time = time.time() - stage4_start
    
    print(f"📊 Stage 4: Recipe Scraping - Successfully parsed {len(extracted_recipes)} recipes - {stage4_time:.2f}s")
    
    # Print failed URLs
    if failed_parses:
        failed_urls = [fp.get("result", {}).get("url", "") for fp in failed_parses]
        print(f"❌ Failed to parse: {', '.join(failed_urls)}")
    
    # STAGE 5: Deep content ranking using full recipe data
    stage5_start = time.time()
    if len(extracted_recipes) > 1:  # Only re-rank if we have multiple recipes
        final_ranked_recipes = await rerank_with_full_recipe_data(
            extracted_recipes,
            query,
            ctx.deps.openai_key
        )
    else:
        final_ranked_recipes = extracted_recipes
    stage5_time = time.time() - stage5_start
    
    print(f"📊 Stage 5: Final Ranking - Returning top {min(max_recipes, len(final_ranked_recipes))} recipes - {stage5_time:.2f}s\n")
    
    # STAGE 6: Format final results for agent
    stage6_start = time.time()
    formatted_recipes = []
    for recipe in final_ranked_recipes[:max_recipes]:  # Use final ranked results
        # Parse raw ingredient strings into structured format
        raw_ingredients = recipe.get("ingredients", [])
        structured_ingredients = parse_ingredients_list(raw_ingredients)
        
        # Parse raw nutrition strings into structured format
        raw_nutrition = recipe.get("nutrition", [])
        structured_nutrition = parse_nutrition_list(raw_nutrition)
        
        formatted_recipes.append({
            "id": len(formatted_recipes) + 1,  # Simple ID generation
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,  # Now structured!
            "nutrition": structured_nutrition,  # Now structured!
            # Instructions are available for agent analysis but won't be displayed
            "_instructions_for_analysis": recipe.get("instructions", [])
        })
    
    # Track all failure points for business reporting
    all_failures = fp1_failures + failed_parses  # Combine Content_Scraping and Recipe_Parsing failures
    failed_parse_report = {
        "total_failed": len(all_failures),
        "content_scraping_failures": len(fp1_failures),
        "recipe_parsing_failures": len(failed_parses),
        "failed_urls": [
            {
                "url": fp.get("url") or fp.get("result", {}).get("url", ""),
                "failure_point": fp.get("failure_point", "Unknown"),
                "error": fp.get("error", "Unknown error")
            }
            for fp in all_failures
        ]
    }
    stage6_time = time.time() - stage6_start
    
    print(f"📊 Stage 6: Final Formatting - Structured {len(formatted_recipes)} recipes for iOS - {stage6_time:.2f}s")
    print(f"🎯 RETURNING TO AGENT - Agent will now generate response...")
    
    # PERFORMANCE SUMMARY
    total_time = time.time() - total_start
    print(f"\n⏱️  PERFORMANCE SUMMARY:")
    print(f"   Total Time: {total_time:.2f}s")
    print(f"   Stage 1 (Web Search): {stage1_time:.2f}s ({(stage1_time/total_time)*100:.1f}%)")
    print(f"   Stage 2 (URL Expansion): {stage2_time:.2f}s ({(stage2_time/total_time)*100:.1f}%)")
    print(f"   Stage 3 (Initial Ranking): {stage3_time:.2f}s ({(stage3_time/total_time)*100:.1f}%)")
    print(f"   Stage 4 (Recipe Scraping): {stage4_time:.2f}s ({(stage4_time/total_time)*100:.1f}%)")
    print(f"   Stage 5 (Final Ranking): {stage5_time:.2f}s ({(stage5_time/total_time)*100:.1f}%)")
    print(f"   Stage 6 (Final Formatting): {stage6_time:.2f}s ({(stage6_time/total_time)*100:.1f}%)")
    
    # Create minimal context for agent (reduce 101s response time)
    minimal_recipes = []
    for recipe in formatted_recipes:
        minimal_recipes.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "servings": recipe["servings"],
            "readyInMinutes": recipe["readyInMinutes"],
            "ingredients": [ing["ingredient"] for ing in recipe["ingredients"][:8]],  # Just ingredient names, first 8
            "nutrition": recipe.get("nutrition", [])  # Small nutrition data
        })
    
    return {
        "results": minimal_recipes,  # Minimal context for agent
        "full_recipes": formatted_recipes,  # Full data for iOS (passed through unchanged)
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "_failed_parse_report": failed_parse_report  # For business analytics
    }
 



