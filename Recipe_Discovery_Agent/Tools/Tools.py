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
import json


def normalize_nutrition_data(recipe):
    """
    Convert all nutrition formats to simple string array for consistency.
    This ensures all recipes have nutrition data in the same format regardless of parsing source.
    """
    unified = []
    
    # Priority 1: From structured format (JSON-LD parsed)
    if recipe.get('structured_nutrition'):
        for item in recipe['structured_nutrition']:
            if isinstance(item, dict) and item.get('amount') and item.get('name'):
                amount = str(item['amount']).strip()
                unit = str(item.get('unit', '')).strip()
                name = str(item['name']).strip().lower()
                
                # Normalize common nutrition names
                if name in ['protein', 'fat', 'carbs', 'carbohydrates']:
                    unified.append(f"{amount}{unit} {name}")
                elif name in ['calories', 'kcal']:
                    unified.append(f"{amount} calories")
                elif name == 'sodium':
                    unified.append(f"{amount}{unit} sodium")
                elif name == 'fiber':
                    unified.append(f"{amount}{unit} fiber")
    
    # Priority 2: From raw format (HTML parsed)
    elif recipe.get('nutrition') and isinstance(recipe['nutrition'], list):
        for item in recipe['nutrition']:
            if isinstance(item, str) and item.strip():
                # Clean up the string format
                cleaned = item.strip()
                # Normalize "kcal" to "calories"
                cleaned = cleaned.replace('kcal calories', 'calories').replace('kcal', 'calories')
                unified.append(cleaned)
    
    # Store the unified format
    recipe['unified_nutrition'] = unified
    return recipe

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


async def search_and_process_recipes_tool(ctx: RunContext[RecipeDeps], query: str, needed_count: int = 5, requirements: Dict = None) -> Dict:
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
    
    # Stage 1: Web Search with Google Custom Search fallback
    stage1_start = time.time()
    search_results = await search_recipes_serpapi(ctx, query, number=40)
    
    raw_results = search_results.get("results", [])
    
    # FALLBACK: Use Google Custom Search if SerpAPI returns < 20 results
    search_method = "SerpAPI only"
    if len(raw_results) < 20:
        print(f"⚠️  SerpAPI returned only {len(raw_results)} results, using Google Custom Search fallback...")
        
        try:
            google_results = await search_recipes_google_custom(ctx, query, number=40)
            google_urls = google_results.get("results", [])
            
            # Combine SerpAPI and Google results, avoiding duplicates
            existing_urls = {result.get("url") for result in raw_results}
            for google_result in google_urls:
                if google_result.get("url") not in existing_urls:
                    raw_results.append(google_result)
            
            print(f"🔄 Combined results: {len(raw_results)} URLs total (SerpAPI + Google Custom Search)")
            search_method = "SerpAPI + Google Custom Search"
            
        except Exception as e:
            print(f"⚠️  Google Custom Search fallback failed: {e}")
            print(f"📊 Continuing with {len(raw_results)} URLs from SerpAPI only")
    
    stage1_time = time.time() - stage1_start
    
    if not raw_results:
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No search results found from either search API"
        }
    
    print(f"📊 Stage 1: Web Search - Found {len(raw_results)} URLs - {stage1_time:.2f}s")
    print(f"🔍 Search method used: {search_method}")
    
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
    
    # Initialize timing accumulators for stages 3-6
    total_stage3_time = 0
    total_stage4_time = 0
    total_stage5_time = 0
    total_stage6_time = 0
    
    # Stage 3: URL Expansion and Batch Setup
    stage3_start = time.time()
    
    # Now begin the batch processing logic (formerly from process_recipe_batch_tool)
    batch_size = 10
    urls = ranked_urls  # Use ranked URLs directly
    user_query = query  # Use the query parameter for consistency
    
    try:
        all_recipes = []
        all_fp1_failures = []
        all_failed_parses = []
        qualified_recipes = []  # Track verified recipes globally
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
        
        stage3_batch_setup_time = time.time() - stage3_start
        total_stage3_time += stage3_batch_setup_time
        print(f"📊 Stage 3A: Batch Setup - {stage3_batch_setup_time:.2f}s")
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
        stage3_classify_start = time.time()
        try:
            batch_classifications = await classify_urls_batch(current_batch, ctx.deps.openai_key)
            batch_classification_map = {c.url: c for c in batch_classifications}
        except Exception as e:
            print(f"   ⚠️  Batch classification failed: {e}")
            print(f"   ⚠️  Treating all batch URLs as recipe URLs")
            batch_classification_map = {}
        
        stage3_classify_time = time.time() - stage3_classify_start
        total_stage3_time += stage3_classify_time
        print(f"   📊 Stage 3B: URL Classification - {stage3_classify_time:.2f}s")
        
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
            print(f"   🔍 List URLs identified:")
            for list_url_dict in batch_list_urls:
                list_url = list_url_dict.get('url', '')
                list_title = list_url_dict.get('title', 'No title')
                classification = batch_classification_map.get(list_url)
                confidence = classification.confidence if classification else 0.0
                print(f"     - {list_title[:60]}... → {list_url}")
                print(f"       Confidence: {confidence:.2f}")
        
        # Only process recipe URLs
        urls_to_process = batch_recipe_urls
        
        # Stage 3C: URL Expansion - SKIPPED (all list URLs deferred to backlog)
        # Since we defer all list URLs, we never need to expand in regular batches
        stage3_expansion_start = time.time()
        expanded_results = urls_to_process
        fp1_failures = []
        stage3_expansion_time = time.time() - stage3_expansion_start
        total_stage3_time += stage3_expansion_time
        print(f"📊 Batch {batch_count} - Stage 3C: URL Expansion - Skipped (list URLs deferred) - {stage3_expansion_time:.3f}s")
        
        if not expanded_results:
            print(f"⚠️  Batch {batch_count} - No URLs after expansion, skipping")
            all_fp1_failures.extend(fp1_failures)
            continue
        
        # Stage 4: Recipe Scraping for this batch with 25-second timeout (temporarily increased for debugging)
        stage4_start = time.time()
        successful_parses = []
        failed_parses = []
        
        # Create tasks for parallel processing
        parsing_tasks = []
        result_mapping = []  # Track which task corresponds to which result

        for result in expanded_results:
            url = result.get("url")
            if url:
                task = asyncio.wait_for(parse_recipe(url, ctx.deps.openai_key), timeout=25.0)
                parsing_tasks.append(task)
                result_mapping.append(result)

        # Execute all parsing in parallel
        if parsing_tasks:
            parsed_data = await asyncio.gather(*parsing_tasks, return_exceptions=True)
            
            # Process results
            for i, data in enumerate(parsed_data):
                result = result_mapping[i]
                url = result.get("url")
                
                if isinstance(data, asyncio.TimeoutError):
                    # Defer slow URLs to backlog for later processing
                    print(f"   ⏰ Timeout (25s): Deferring slow URL to backlog: {url}")
                    url_backlog.append(result)
                elif isinstance(data, Exception):
                    # Track other exceptions as failed parses
                    failed_parses.append({
                        "result": result,
                        "error": str(data),
                        "failure_point": "Recipe_Parsing_Exception"
                    })
                elif isinstance(data, dict) and not data.get("error"):
                    # Add search metadata
                    data["search_title"] = result.get("title", "")
                    data["search_snippet"] = result.get("snippet", "")
                    # Normalize nutrition data to unified format
                    data = normalize_nutrition_data(data)
                    successful_parses.append(data)
                else:
                    # Track failed parse
                    failed_parses.append({
                        "result": result,
                        "error": data.get("error", "Unknown error") if isinstance(data, dict) else str(data),
                        "failure_point": "Recipe_Parsing_Failure_Point"
                    })
        
        # Parse nutrition data for successful recipes
        for recipe in successful_parses:
            raw_nutrition = recipe.get("nutrition", [])
            recipe["structured_nutrition"] = parse_nutrition_list(raw_nutrition)
        
        stage4_time = time.time() - stage4_start
        batch_total_time = time.time() - batch_total_start
        
        print(f"📊 Batch {batch_count} - Stage 4: Recipe Scraping - Successfully parsed {len(successful_parses)} recipes - {stage4_time:.2f}s")
        print(f"⏱️  Batch {batch_count} Total Time: {batch_total_time:.2f}s")
        
        # Accumulate stage timing
        total_stage4_time += stage4_time
        
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
            # Phase 1: Verify recipes meet requirements
            qualified_recipes = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            # Phase 2: Rank qualified recipes by relevance  
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking after batch {batch_count} - Ranking {len(final_ranked_recipes)} qualified recipes - {stage5_time:.2f}s")
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
        
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
        
        stage3_backlog_start = time.time()
        # Process backlog URLs (these are primarily list URLs)
        # Process from a copy and remove items as we process them
        backlog_copy = url_backlog.copy()
        for backlog_url_dict in backlog_copy:
            if len(final_ranked_recipes) >= needed_count:
                print(f"   ✅ Found enough final recipes, stopping backlog processing")
                break
                
            url = backlog_url_dict.get('url', '')
            print(f"   🔄 Processing backlog URL: {url}")
            
            # IMMEDIATELY remove from original backlog so it can't be considered again
            url_backlog.remove(backlog_url_dict)
            
            # Stage 3: Expand list URL
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    html_content = response.text
                
                # Use ListParser to extract recipe URLs
                print(f"      🔍 Using ListParser on: {url}")
                print(f"      📄 HTML content size: {len(html_content)} chars")
                intelligent_parser = ListParser(ctx.deps.openai_key)
                extracted_recipes = await intelligent_parser.extract_recipe_urls(
                    url, 
                    html_content, 
                    max_urls=4  # Extract 4 recipe URLs per list URL
                )
                print(f"      📊 ListParser returned {len(extracted_recipes) if extracted_recipes else 0} URLs")
                
                if extracted_recipes:
                    print(f"      ✅ Extracted {len(extracted_recipes)} recipes from list URL")
                    print(f"      📋 DEBUG: Extracted URLs from {url}:")
                    for i, recipe_dict in enumerate(extracted_recipes):
                        extracted_url = recipe_dict.get("url", "")
                        extracted_title = recipe_dict.get("title", "No title")
                        print(f"        {i+1}. {extracted_title}")
                        print(f"           URL: {extracted_url}")
                        # Check if extracted URL looks like a list URL
                        if any(indicator in extracted_url.lower() for indicator in ['collection', 'category', 'recipes/', '/recipes', 'roundup', 'list']):
                            print(f"           ⚠️  WARNING: This looks like a LIST URL, not a recipe URL!")
                    
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
                                # Normalize nutrition data to unified format
                                data = normalize_nutrition_data(data)
                                all_recipes.append(data)
                                print(f"      ✅ Successfully parsed recipe {len(all_recipes)}/{needed_count}")
                            else:
                                print(f"      ❌ Failed to parse: {extracted_recipes[i].get('url', '')}")
                        
                        # Run verification on ONLY the newly parsed recipes from this backlog URL
                        if requirements and extracted_data:
                            new_recipes = []
                            for i, data in enumerate(extracted_data):
                                if isinstance(data, dict) and not data.get("error"):
                                    new_recipes.append(data)
                            
                            if new_recipes:
                                # Phase 1: Verify ONLY the new recipes (not all recipes)
                                newly_qualified = await verify_recipes_meet_requirements(new_recipes, requirements, ctx.deps.openai_key, user_query)
                                qualified_recipes.extend(newly_qualified)  # Add to global qualified list
                                
                                # Check if we have enough qualified recipes to stop
                                if len(qualified_recipes) >= needed_count:
                                    print(f"      ✅ Found {len(qualified_recipes)} qualified recipes (needed {needed_count}), stopping backlog processing")
                                    break
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
        
        stage3_backlog_time = time.time() - stage3_backlog_start
        total_stage3_time += stage3_backlog_time
        print(f"📋 Backlog processing complete: {len(all_recipes)} total recipes")
        print(f"   📊 Stage 3D: Backlog Processing - {stage3_backlog_time:.2f}s")
        
        # Stage 5: Final Ranking after backlog processing
        stage5_start = time.time()
        if len(qualified_recipes) > 0:
            # Phase 2: Rank qualified recipes by relevance (verification already done)
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        elif len(all_recipes) > 1:
            # Fallback: verify all recipes if no qualified recipes found yet
            qualified_recipes = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking after backlog - Ranking {len(final_ranked_recipes)} qualified recipes - {stage5_time:.2f}s")
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
    
    # Ensure final_ranked_recipes is defined (in case no batches or backlog processing occurred)
    if 'final_ranked_recipes' not in locals():
        final_ranked_recipes = all_recipes
    
    # Stage 6: Final Formatting
    stage6_start = time.time()
    formatted_recipes = []
    for recipe in final_ranked_recipes[:needed_count]:
        # Keep ingredients as raw strings for instant display
        # Shopping conversion will happen in background after recipe save
        raw_ingredients = recipe.get("ingredients", [])
        # Convert to simple display format for iOS app
        structured_ingredients = [{"ingredient": ing} for ing in raw_ingredients] if raw_ingredients else []
        
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
    
    # Accumulate stage timing
    total_stage6_time += stage6_time
    
    # Performance summary
    total_time = time.time() - total_pipeline_start
    print(f"\n⏱️  COMPLETE PIPELINE PERFORMANCE:")
    print(f"   Total Time: {total_time:.2f}s")
    print(f"   Stage 1 (Web Search): {stage1_time:.2f}s ({(stage1_time/total_time)*100:.1f}%)")
    print(f"   Stage 2 (Initial Ranking): {stage2_time:.2f}s ({(stage2_time/total_time)*100:.1f}%)")
    print(f"   Stage 3 (URL Expansion): {total_stage3_time:.2f}s ({(total_stage3_time/total_time)*100:.1f}%)")
    print(f"   Stage 4 (Recipe Scraping): {total_stage4_time:.2f}s ({(total_stage4_time/total_time)*100:.1f}%)")
    print(f"   Stage 5 (Final Ranking): {total_stage5_time:.2f}s ({(total_stage5_time/total_time)*100:.1f}%)")
    print(f"   Stage 6 (Final Formatting): {total_stage6_time:.2f}s ({(total_stage6_time/total_time)*100:.1f}%)")
    
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
    print(f"🍳 FINAL {len(formatted_recipes)} RECIPES SELECTED:")
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


async def search_recipes_google_custom(ctx: RunContext[RecipeDeps], query: str, number: int = 40) -> Dict:
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
            print(f"⚠️  Google Custom Search fallback failed: {e}")
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": f"Google Custom Search failed: {str(e)}"
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


async def verify_recipes_meet_requirements(scraped_recipes: List[Dict], requirements: Dict, openai_key: str, user_query: str = "") -> List[Dict]:
    """
    Phase 1: Strict verification LLM - Binary PASS/FAIL verification only.
    Fast and focused on requirement checking.
    
    Args:
        scraped_recipes: List of recipes with full parsed data
        requirements: Strict requirements that must be met
        openai_key: OpenAI API key
        
    Returns:
        List of recipes that pass ALL requirements
    """
    if not scraped_recipes or not requirements:
        return scraped_recipes
    
    # Build verification prompt from requirements
    verification_rules = []
    
    # Add nutrition requirements
    if "nutrition" in requirements:
        nutrition_reqs = requirements["nutrition"]
        for nutrient, constraints in nutrition_reqs.items():
            if "min" in constraints:
                verification_rules.append(f"- {nutrient.upper()} must be ≥ {constraints['min']}g (check nutrition data)")
            if "max" in constraints:
                verification_rules.append(f"- {nutrient.upper()} must be ≤ {constraints['max']}g (check nutrition data)")
    
    # Add ingredient exclusions
    if "exclude_ingredients" in requirements:
        ingredients = requirements["exclude_ingredients"]
        verification_rules.append(f"- Must NOT contain: {', '.join(ingredients)} (check ingredients list)")
    
    # Add time constraints
    if "cooking_constraints" in requirements and "cook_time" in requirements["cooking_constraints"]:
        time_constraint = requirements["cooking_constraints"]["cook_time"]
        if "max" in time_constraint:
            verification_rules.append(f"- Cooking time must be ≤ {time_constraint['max']} minutes")
    
    if not verification_rules:
        return scraped_recipes  # No requirements to verify
    
    # Prepare recipe data for verification
    recipe_data = []
    for i, recipe in enumerate(scraped_recipes):
        # Get nutrition data from unified format (normalized during parsing)
        unified_nutrition = recipe.get('unified_nutrition', [])
        if unified_nutrition:
            nutrition_text = ", ".join(unified_nutrition)
        else:
            nutrition_text = "NO NUTRITION DATA AVAILABLE"
        
        recipe_data.append({
            "index": i,
            "title": recipe.get("title", "No title"),
            "nutrition": nutrition_text,
            "ingredients": recipe.get("ingredients", [])[:10],  # First 10 ingredients
            "cook_time": recipe.get("cook_time", "Not specified")
        })
        
        # DEBUG: Print what data is being sent to verification LLM
        print(f"   🔍 DEBUG Recipe {i+1}: {recipe.get('title', 'No title')}")
        print(f"      URL: {recipe.get('source_url', 'No URL')}")
        print(f"      Unified Nutrition: {nutrition_text}")
        print(f"      Original Raw Field: {recipe.get('nutrition', 'MISSING')}")
        print(f"      Original Structured Field: {recipe.get('structured_nutrition', 'MISSING')}")
        print(f"      Normalized Unified Field: {recipe.get('unified_nutrition', 'MISSING')}")
    
    verification_rules_text = "\n".join(verification_rules)
    
    prompt = f"""User's Original Query: "{user_query}"

You are verifying if recipes meet the user's EXACT requirements extracted from their query.
The user specifically asked for recipes that meet these NON-NEGOTIABLE requirements:

REQUIREMENTS TO VERIFY:
{verification_rules_text}

CRITICAL INSTRUCTIONS - FOLLOW EXACTLY:
- If a recipe shows "NO NUTRITION DATA AVAILABLE" → AUTOMATIC FAIL
- For nutrition requirements: Look for EXACT numbers (e.g., "30g protein", "25 protein")
- If nutrition shows vague text without numbers → AUTOMATIC FAIL  
- If ANY requirement is not met → AUTOMATIC FAIL
- If ingredients contain excluded items → AUTOMATIC FAIL
- ONLY return indices of recipes that have COMPLETE nutrition data AND meet ALL requirements
- When in doubt → FAIL the recipe

Recipes to verify:
{json.dumps(recipe_data, indent=2)}

Return in this exact JSON format:
{{
  "qualifying_indices": [0, 2, 4]
}}"""

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
                    {"role": "system", "content": "You are a strict recipe requirement verifier. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 500
            }
        )
        
        if response.status_code != 200:
            # If verification fails, return all recipes (fail-safe)
            return scraped_recipes
        
        try:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Parse JSON response
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            result = json.loads(llm_response.strip())
            qualifying_indices = result.get('qualifying_indices', [])
            
            # Return only qualifying recipes
            qualifying_recipes = []
            for idx in qualifying_indices:
                if 0 <= idx < len(scraped_recipes):
                    qualifying_recipes.append(scraped_recipes[idx])
            
            print(f"   ✅ Phase 1 Verification: {len(qualifying_recipes)}/{len(scraped_recipes)} recipes passed requirements")
            
            # DEBUG: Show which recipes passed/failed
            passed_indices = set(qualifying_indices)
            for i, recipe in enumerate(scraped_recipes):
                status = "✅ PASSED" if i in passed_indices else "❌ FAILED"
                print(f"      {status}: {recipe.get('title', 'No title')}")
            
            return qualifying_recipes
            
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠️  Phase 1 verification failed: {e}")
            # If parsing fails, return all recipes (fail-safe)
            return scraped_recipes


async def rank_qualified_recipes_by_relevance(qualified_recipes: List[Dict], query: str, openai_key: str) -> List[Dict]:
    """
    Phase 2: Relevance Ranking LLM - Ranks pre-qualified recipes by relevance only.
    Focused on quality and relevance ranking after requirements verification.
    
    Args:
        qualified_recipes: List of recipes that already passed requirement verification
        query: Original user query
        openai_key: OpenAI API key
        
    Returns:
        Recipes ranked by relevance to user query
    """
    if not qualified_recipes:
        return []
    
    if len(qualified_recipes) == 1:
        return qualified_recipes  # No need to rank single recipe
    
    # Build recipe summaries for relevance ranking
    detailed_recipes = []
    for i, recipe in enumerate(qualified_recipes):
        ingredients_list = recipe.get("ingredients", [])[:8]  # First 8 ingredients
        ingredients_text = ", ".join(ingredients_list) if ingredients_list else ""
        
        recipe_summary = f"""{i+1}. {recipe.get('title', 'Untitled Recipe')}
Ingredients: {ingredients_text}
Cook Time: {recipe.get('cook_time', 'Not specified')}
Servings: {recipe.get('servings', 'Not specified')}"""
        
        detailed_recipes.append(recipe_summary)
    
    recipes_text = "\n\n".join(detailed_recipes)
    
    prompt = f"""User is searching for: "{query}"

These recipes have already PASSED all requirement verification. Your job is to rank them by RELEVANCE to the user's query only.

🎯 RANKING FACTORS:
- How well the recipe matches the user's intent
- Quality and appeal of the recipe
- Cooking complexity appropriate to query
- Ingredient freshness and accessibility

🍳 PRE-QUALIFIED RECIPES TO RANK:
{recipes_text}

📋 RETURN FORMAT:
Return ONLY a comma-separated list of numbers in order of relevance (best first).
Example: "3,1,2" (if recipe 3 is most relevant, then 1, then 2)"""

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
                    {"role": "system", "content": "You are a recipe relevance ranker. Return only comma-separated numbers."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }
        )
        
        if response.status_code != 200:
            return qualified_recipes
        
        try:
            data = response.json()
            ranking_text = data['choices'][0]['message']['content'].strip()
            rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
            
            reranked = []
            for idx in rankings:
                if 0 <= idx < len(qualified_recipes):
                    reranked.append(qualified_recipes[idx])
            
            # Add any missing recipes
            for recipe in qualified_recipes:
                if recipe not in reranked:
                    reranked.append(recipe)
            
            print(f"   ✅ Phase 2 Ranking: Ranked {len(qualified_recipes)} qualified recipes by relevance")
            return reranked
            
        except (ValueError, IndexError):
            return qualified_recipes

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
                # Normalize nutrition data to unified format
                data = normalize_nutrition_data(data)
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
        # Phase 1: Verify recipes meet requirements
        qualified_recipes = await verify_recipes_meet_requirements(extracted_recipes, requirements, ctx.deps.openai_key, query)
        # Phase 2: Rank qualified recipes by relevance
        final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, query, ctx.deps.openai_key)
    else:
        final_ranked_recipes = extracted_recipes
    stage5_time = time.time() - stage5_start
    
    print(f"📊 Stage 5: Final Ranking - Returning top {min(max_recipes, len(final_ranked_recipes))} recipes - {stage5_time:.2f}s\n")
    
    # STAGE 6: Format final results for agent
    stage6_start = time.time()
    formatted_recipes = []
    for recipe in final_ranked_recipes[:max_recipes]:  # Use final ranked results
        # Keep ingredients as raw strings for instant display
        # Shopping conversion will happen in background after recipe save  
        raw_ingredients = recipe.get("ingredients", [])
        # Convert to simple display format for iOS app
        structured_ingredients = [{"ingredient": ing} for ing in raw_ingredients] if raw_ingredients else []
        
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
 



