"""
Recipe Discovery Tools - Orchestrator
Coordinates all recipe search stages in a modular pipeline.
"""

from pydantic_ai import RunContext
from typing import Dict, List, Optional
import asyncio
import time
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from Dependencies import RecipeDeps

# Import all modularized stages
from .Recipe_Search_Stages.stage_1_web_search import search_recipes_serpapi, search_recipes_google_custom
from .Recipe_Search_Stages.stage_2_url_ranking import rerank_results_with_llm
from .Recipe_Search_Stages.stage_3_url_classification import classify_urls_batch
from .Recipe_Search_Stages.stage_4_recipe_parsing import parse_recipe
from .Recipe_Search_Stages.stage_5_nutrition_normalization import normalize_nutrition_data
from .Recipe_Search_Stages.stage_6_requirements_verification import verify_recipes_meet_requirements
from .Recipe_Search_Stages.stage_7_relevance_ranking import rank_qualified_recipes_by_relevance
from .Recipe_Search_Stages.stage_8_list_processing import expand_urls_with_lists, ListParser
from .Recipe_Search_Stages.stage_9_final_formatting import (
    format_recipes_for_ios, 
    create_minimal_recipes_for_agent, 
    create_failed_parse_report
)
from .Recipe_Search_Stages.utils.constants import PRIORITY_SITES, BLOCKED_SITES

# Import parsers for nutrition processing
from .Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list


async def search_and_process_recipes_tool(ctx: RunContext[RecipeDeps], query: str, needed_count: int = 5, requirements: Dict = None) -> Dict:
    """
    AGENT TOOL: Complete recipe search pipeline orchestrator.
    
    Coordinates all stages of the recipe discovery process using modular components.
    
    Args:
        query: User's recipe search query
        needed_count: Number of final recipes to return (default 5)
        requirements: Requirements dictionary for filtering
        
    Returns:
        Dict with structured recipe data ready for agent/iOS consumption
    """
    total_pipeline_start = time.time()
    
    # Stage 1: Web Search with Google Custom Search fallback
    stage1_start = time.time()
    search_results = await search_recipes_serpapi(ctx, query, number=40)
    
    raw_results = search_results.get("results", [])
    
    # FALLBACK: Use Google Custom Search if SerpAPI returns < 20 results
    if len(raw_results) < 20:
        try:
            google_results = await search_recipes_google_custom(ctx, query, number=40)
            google_urls = google_results.get("results", [])
            
            # Combine SerpAPI and Google results, avoiding duplicates
            existing_urls = {result.get("url") for result in raw_results}
            for google_result in google_urls:
                if google_result.get("url") not in existing_urls:
                    raw_results.append(google_result)
            
        except Exception as e:
            pass
    
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
    
    # Begin batch processing logic
    batch_size = 10
    urls = ranked_urls
    user_query = query
    
    try:
        all_recipes = []
        all_fp1_failures = []
        all_failed_parses = []
        qualified_recipes = []
        all_processed_recipes = []  # Track all recipes with percentage data for fallback
        batch_count = 0
        url_backlog = []
        
        # FIRST: Rank all URLs by priority sites before any processing
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
        
        stage3_batch_setup_time = time.time() - stage3_start
        total_stage3_time += stage3_batch_setup_time
        print(f"📊 Stage 3A: Batch Setup - {stage3_batch_setup_time:.2f}s")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": user_query,
            "error": f"Batch setup failed: {str(e)}"
        }
    
    # URL TRACKING: Initialize counters for progress tracking
    total_urls_to_process = len(urls)
    urls_processed_count = 0
    
    # Process URLs in batches until we have enough recipes
    for batch_start in range(0, len(urls), batch_size):
        batch_count += 1
        batch_end = min(batch_start + batch_size, len(urls))
        current_batch = urls[batch_start:batch_end]
        
        print(f"🚨 BATCH {batch_count}: Processing URLs {batch_start+1}-{batch_end} of {len(urls)} total URLs")
        print(f"   Current batch size: {len(current_batch)} URLs")
        
        batch_total_start = time.time()
        
        # Classify just the URLs in THIS batch
        stage3_classify_start = time.time()
        try:
            batch_classifications = await classify_urls_batch(current_batch, ctx.deps.openai_key)
            batch_classification_map = {c.url: c for c in batch_classifications}
        except Exception as e:
            batch_classification_map = {}
        
        stage3_classify_time = time.time() - stage3_classify_start
        total_stage3_time += stage3_classify_time
        print(f"📊 Stage 3B: URL Classification - {stage3_classify_time:.2f}s")
        
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
            print(f"🚨 BATCH {batch_count}: Deferred {len(batch_list_urls)} list URLs to backlog")
        
        # Only process recipe URLs
        urls_to_process = batch_recipe_urls
        print(f"🚨 BATCH {batch_count}: Processing {len(urls_to_process)} recipe URLs from this batch")
        
        # Stage 3C: URL Expansion - SKIPPED (all list URLs deferred to backlog)
        stage3_expansion_start = time.time()
        expanded_results = urls_to_process
        fp1_failures = []
        stage3_expansion_time = time.time() - stage3_expansion_start
        total_stage3_time += stage3_expansion_time
        print(f"📊 Stage 3C: URL Expansion - Skipped (list URLs deferred) - {stage3_expansion_time:.3f}s")
        
        if not expanded_results:
            print(f"🚨 BATCH {batch_count}: No recipe URLs to process in this batch, moving to next batch")
            all_fp1_failures.extend(fp1_failures)
            continue
        
        # Stage 4: Recipe Scraping for this batch
        stage4_start = time.time()
        successful_parses = []
        failed_parses = []
        
        # Create tasks for parallel processing
        parsing_tasks = []
        result_mapping = []

        for result in expanded_results:
            url = result.get("url")
            if url:
                # URL TRACKING: Show progress for each URL being processed
                urls_processed_count += 1
                print(f"🚨 URL PROGRESS: Processing URL {urls_processed_count}/{total_urls_to_process} - {result.get('title', 'No title')[:50]}...")
                
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
                    url_backlog.append(result)
                elif isinstance(data, Exception):
                    # Track other exceptions as failed parses
                    print(f"🚨 URL FAILED: {url} - Exception: {str(data)[:100]}")
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
        
        print(f"📊 Stage 4: Recipe Scraping - Successfully parsed {len(successful_parses)} recipes - {stage4_time:.2f}s")
        
        # Accumulate stage timing
        total_stage4_time += stage4_time
        
        # Add batch results to overall collections
        all_recipes.extend(successful_parses)
        all_fp1_failures.extend(fp1_failures)
        all_failed_parses.extend(failed_parses)
        
        # Stage 5: Final Ranking after each batch
        stage5_start = time.time()
        
        if len(all_recipes) > 1:
            # Phase 1: Verify recipes meet requirements (two-tier system)
            batch_qualified, batch_processed = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes = batch_qualified
            all_processed_recipes.extend(batch_processed)  # Accumulate all processed recipes
            
            # Phase 2: Rank qualified recipes by relevance  
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking - Ranking {len(final_ranked_recipes)} qualified recipes - {stage5_time:.2f}s")
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
        
        # Early exit: if we have enough FINAL recipes after ranking, stop processing batches
        if len(final_ranked_recipes) >= needed_count:
            print(f"🚨 EARLY EXIT: Found {len(final_ranked_recipes)} recipes (needed {needed_count}) after processing {urls_processed_count}/{total_urls_to_process} URLs")
            break
        else:
            print(f"🚨 BATCH {batch_count} COMPLETE: Have {len(final_ranked_recipes)}/{needed_count} recipes, continuing to next batch...")
    
    # Process url_backlog if we still need more recipes
    if len(final_ranked_recipes) < needed_count and url_backlog:
        print(f"🚨 BACKLOG PROCESSING: Need {needed_count - len(final_ranked_recipes)} more recipes. Processing {len(url_backlog)} backlog URLs after main batch processing.")
        
        # DEBUG: Print clean list of backlog URLs
        print(f"\n🚨 DEBUG BACKLOG URL LIST ({len(url_backlog)} URLs):")
        for i, url_data in enumerate(url_backlog, 1):
            url = url_data.get('url', 'No URL')
            title = url_data.get('title', 'No title')[:60]
            print(f"   {i:2}. {title}")
            print(f"       {url}")
        print()
        stage3_backlog_start = time.time()
        # Process backlog URLs (these are primarily list URLs)
        backlog_copy = url_backlog.copy()
        for backlog_idx, backlog_url_dict in enumerate(backlog_copy):
            if len(qualified_recipes) >= needed_count:
                break
                
            url = backlog_url_dict.get('url', '')
            print(f"🚨 BACKLOG URL {backlog_idx + 1}/{len(url_backlog)}: Processing {backlog_url_dict.get('title', 'No title')[:50]}...")
            
            # IMMEDIATELY remove from original backlog so it can't be considered again
            url_backlog.remove(backlog_url_dict)
            
            # Stage 3: Expand list URL
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    html_content = response.text
                
                # Use ListParser to extract recipe URLs
                intelligent_parser = ListParser(ctx.deps.openai_key)
                extracted_recipes = await intelligent_parser.extract_recipe_urls(
                    url, 
                    html_content, 
                    max_urls=10
                )
                
                if extracted_recipes:
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
                        
                        # Run verification on ONLY the newly parsed recipes from this backlog URL
                        if requirements and extracted_data:
                            new_recipes = []
                            for i, data in enumerate(extracted_data):
                                if isinstance(data, dict) and not data.get("error"):
                                    new_recipes.append(data)
                            
                            if new_recipes:
                                # Phase 1: Verify ONLY the new recipes (not all recipes) 
                                newly_qualified, newly_processed = await verify_recipes_meet_requirements(new_recipes, requirements, ctx.deps.openai_key, user_query)
                                qualified_recipes.extend(newly_qualified)
                                all_processed_recipes.extend(newly_processed)  # Accumulate processed recipes
                                
                                # Check if we have enough qualified recipes to stop
                                if len(qualified_recipes) >= needed_count:
                                    break
                    
            except Exception as e:
                all_fp1_failures.append({
                    "url": url,
                    "title": backlog_url_dict.get('title', ''),
                    "error": str(e),
                    "failure_point": "Backlog_List_Expansion_Failure"
                })
        
        stage3_backlog_time = time.time() - stage3_backlog_start
        total_stage3_time += stage3_backlog_time
        print(f"📊 Stage 3D: Backlog Processing - {stage3_backlog_time:.2f}s")
        
        # Stage 5: Final Ranking after backlog processing
        stage5_start = time.time()
        if len(qualified_recipes) > 0:
            # Phase 2: Rank qualified recipes by relevance (verification already done)
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        elif len(all_recipes) > 1:
            # Fallback: verify all recipes if no qualified recipes found yet
            fallback_qualified, fallback_processed = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes = fallback_qualified
            all_processed_recipes.extend(fallback_processed)  # Accumulate processed recipes
            final_ranked_recipes = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking after backlog - Ranking {len(final_ranked_recipes)} qualified recipes - {stage5_time:.2f}s")
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
    
    # Ensure final_ranked_recipes is defined
    if 'final_ranked_recipes' not in locals():
        final_ranked_recipes = all_recipes
    
    # URL TRACKING: Final summary
    print(f"🚨 FINAL URL PROCESSING SUMMARY:")
    print(f"   Total URLs available: {total_urls_to_process}")
    print(f"   URLs actually processed: {urls_processed_count}")
    print(f"   Backlog URLs processed: {len(url_backlog) if 'url_backlog' in locals() else 0}")
    print(f"   Final recipes found: {len(final_ranked_recipes)}")
    if urls_processed_count < total_urls_to_process:
        print(f"   ⚠️  Only processed {urls_processed_count}/{total_urls_to_process} URLs - stopped early or hit limits")

    # FALLBACK: Fill remaining slots with closest matches if needed (after ALL URLs exhausted)
    if len(final_ranked_recipes) < needed_count and 'all_processed_recipes' in locals() and all_processed_recipes:
        remaining_slots = needed_count - len(final_ranked_recipes)
        print(f"\n🔄 CLOSEST MATCH FALLBACK:")
        print(f"   Need {remaining_slots} more recipes to reach {needed_count}")
        
        # Get recipes with percentage data, excluding ones already in final list
        final_recipe_urls = {recipe.get('source_url', '') for recipe in final_ranked_recipes}
        available_closest = [
            recipe for recipe in all_processed_recipes 
            if recipe.get('source_url', '') not in final_recipe_urls 
            and recipe.get('nutrition_match_percentage', 0) > 0
        ]
        
        # Sort by percentage match (highest first)
        available_closest.sort(key=lambda r: r.get('nutrition_match_percentage', 0), reverse=True)
        
        # Add top closest matches to fill remaining slots
        closest_matches = available_closest[:remaining_slots]
        final_ranked_recipes.extend(closest_matches)
        
        print(f"   Added {len(closest_matches)} closest matches:")
        for i, recipe in enumerate(closest_matches, 1):
            percentage = recipe.get('nutrition_match_percentage', 0)
            title = recipe.get('title', 'Unknown')[:50]
            print(f"      {i}. {title} ({percentage}% match)")
        
        print(f"🚨 FINAL RECIPE COUNT AFTER FALLBACK: {len(final_ranked_recipes)}")

    # Stage 6: Final Formatting using modular function
    stage6_start = time.time()
    formatted_recipes = format_recipes_for_ios(final_ranked_recipes, needed_count)
    
    # Track failures for reporting
    failed_parse_report = create_failed_parse_report(all_fp1_failures, all_failed_parses)
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
    
    # Create minimal context for agent using modular function
    minimal_recipes = create_minimal_recipes_for_agent(formatted_recipes)
    
    # Final recipe selection display
    print("\n" + "="*60)
    print(f"🍳 FINAL {len(formatted_recipes)} RECIPES SELECTED:")
    print("="*60)
    for i, recipe in enumerate(formatted_recipes[:5], 1):
        print(f"{i}. {recipe.get('title', 'Unknown Title')}")
        print(f"   URL: {recipe.get('sourceUrl', 'No URL')}")
    print("="*60 + "\n")
    
    return {
        "results": minimal_recipes,  # Minimal context for agent
        "full_recipes": formatted_recipes,  # Full data for iOS
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "_failed_parse_report": failed_parse_report
    }