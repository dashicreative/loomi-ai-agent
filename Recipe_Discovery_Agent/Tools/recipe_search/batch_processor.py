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
import logfire

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from Dependencies import RecipeDeps

# Session context now in Dependencies - no imports needed

# Import all modularized stages
from Tools.recipe_search.pipeline.stage_1_web_search import search_recipes_serpapi, search_recipes_google_custom, search_recipes_parallel_priority
from Tools.recipe_search.pipeline.stage_2_url_ranking import rerank_results_with_llm
from Tools.recipe_search.pipeline.stage_3_url_classification import classify_urls_batch
from parsers.recipe_parser import parse_recipe
from Tools.recipe_search.pipeline.stage_5_nutrition_normalization import normalize_nutrition_data
from Tools.recipe_search.pipeline.stage_6_requirements_verification import verify_recipes_meet_requirements
from Tools.recipe_search.pipeline.stage_7_relevance_ranking import rank_qualified_recipes_by_relevance
from Tools.recipe_search.pipeline.stage_8_list_processing import expand_urls_with_lists, ListParser
# STAGE 8B IMPORTS (TEMPORARILY DISABLED - reverting to 9a/9b)
# from Tools.recipe_search.pipeline.stage_8b_unified_formatting import (
#     format_recipes_unified_async, 
#     create_minimal_recipes_for_agent, 
#     create_failed_parse_report
# )
from Tools.recipe_search.pipeline.stage_9c_final_formatting import (
    format_recipes_for_ios, 
    create_minimal_recipes_for_agent, 
    create_failed_parse_report
)
from Tools.recipe_search.pipeline.stage_9b_ingredient_categorization import categorize_uncategorized_ingredients_parallel
from urllib.parse import urlparse
from Tools.recipe_search.pipeline.utils.constants import PRIORITY_SITES, BLOCKED_SITES


def merge_recipes_with_deduplication(existing_recipes: List[Dict], new_recipes: List[Dict]) -> List[Dict]:
    """Merge new recipes with existing ones, deduplicating by source_url."""
    existing_urls = {recipe.get('source_url', '') for recipe in existing_recipes}
    merged = existing_recipes.copy()
    
    # DEBUG: Track merge details
    print(f"🔍 DEBUG MERGE FUNCTION: Existing URLs: {list(existing_urls)[:5]}{'...' if len(existing_urls) > 5 else ''}")
    
    added_count = 0
    skipped_count = 0
    
    for recipe in new_recipes:
        recipe_url = recipe.get('source_url', '')
        if recipe_url and recipe_url not in existing_urls:
            merged.append(recipe)
            existing_urls.add(recipe_url)
            added_count += 1
            print(f"🔍 DEBUG MERGE: ADDED {recipe_url}")
        else:
            skipped_count += 1
            print(f"🔍 DEBUG MERGE: SKIPPED {recipe_url} (duplicate or empty)")
    
    print(f"🔍 DEBUG MERGE RESULT: Added {added_count}, Skipped {skipped_count}, Total: {len(merged)}")
    return merged

# Import parsers for nutrition processing
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list

# Import modular components
from Tools.recipe_search.stage_logger import PipelineStageLogger




async def search_and_process_recipes_tool(ctx: RunContext[RecipeDeps], query: str, needed_count: int = 5, requirements: Dict = None, exclude_urls: List[str] = None) -> Dict:
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
    # Session Context Management - Proper Pydantic AI Pattern
    session = ctx.deps.session
    session.search_history.append(query)
    
    total_pipeline_start = time.time()
    
    # Initialize structured stage logger
    stage_logger = PipelineStageLogger(session.session_id, query)
    
    # Start pipeline logging with session correlation
    logfire.info("search_started", 
                 query=query, 
                 session_id=session.session_id,
                 needed_count=needed_count,
                 has_requirements=bool(requirements))
    
    # Get URLs to exclude (from session or passed explicitly)
    urls_to_exclude = set()
    if exclude_urls:
        urls_to_exclude.update(exclude_urls)
    # Add all previously shown URLs from session
    urls_to_exclude.update(session.shown_recipe_urls)
    
    if urls_to_exclude:
        logfire.debug("excluding_previous_urls", count=len(urls_to_exclude))
    
    # Stage 1: Priority Parallel Search System
    stage_logger.start_stage(1, "web_search")
    stage1_start = time.time()
    search_results = await search_recipes_parallel_priority(ctx, query)
    raw_results = search_results.get("results", [])
    
    # DEBUG: Track search results
    print(f"🔍 DEBUG: Raw search results: {len(raw_results)} total")
    unique_search_urls = set(r.get('url', '') for r in raw_results)
    print(f"🔍 DEBUG: Unique search URLs: {len(unique_search_urls)}")
    
    # Filter out excluded URLs
    if urls_to_exclude:
        filtered_results = [r for r in raw_results if r.get('url') not in urls_to_exclude]
        print(f"   Filtered: {len(raw_results)} → {len(filtered_results)} URLs (excluded {len(raw_results) - len(filtered_results)})")
        raw_results = filtered_results
        
        # DEBUG: Track after filtering
        unique_filtered_urls = set(r.get('url', '') for r in filtered_results)
        print(f"🔍 DEBUG: Unique filtered URLs: {len(unique_filtered_urls)}")
    
    stage1_time = time.time() - stage1_start
    stage_logger.complete_stage(1, 
                                urls_found=len(raw_results),
                                priority_urls=search_results.get('priority_count', 0),
                                general_urls=search_results.get('general_count', 0))
    
    if not raw_results:
        logfire.error("search_no_results", query=query, session_id=session.session_id)
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No search results found from parallel search system"
        }
    
    logfire.info("stage_completed",
                 stage="web_search",
                 duration=stage1_time,
                 urls_found=len(raw_results),
                 priority_urls=search_results.get('priority_count', 0),
                 general_urls=search_results.get('general_count', 0),
                 session_id=session.session_id)
    
    # Stage 2: Initial Ranking
    stage_logger.start_stage(2, "url_ranking")
    stage2_start = time.time()
    ranked_urls = await rerank_results_with_llm(
        raw_results, 
        query, 
        ctx.deps.openai_key, 
        top_k=60  # Handle larger result set from parallel search
    )
    stage2_time = time.time() - stage2_start
    
    # Calculate domain distribution for logging
    priority_site_counts = {}
    other_site_counts = {}
    
    for url_dict in ranked_urls:
        url = url_dict.get('url', '')
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            is_priority = any(priority_site in domain for priority_site in PRIORITY_SITES)
            if is_priority:
                priority_site_counts[domain] = priority_site_counts.get(domain, 0) + 1
            else:
                other_site_counts[domain] = other_site_counts.get(domain, 0) + 1
        except:
            other_site_counts['unknown'] = other_site_counts.get('unknown', 0) + 1
    
    total_unique_domains = len(priority_site_counts) + len(other_site_counts)
    
    stage_logger.complete_stage(2,
                                urls_ranked=len(ranked_urls),
                                unique_domains=total_unique_domains,
                                priority_sites_count=len(priority_site_counts))
    
    logfire.info("stage_completed",
                 stage="url_ranking", 
                 duration=stage2_time,
                 urls_ranked=len(ranked_urls),
                 unique_domains=total_unique_domains,
                 priority_sites=dict(priority_site_counts),
                 session_id=session.session_id)
    
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
        final_ranked_recipes = []  # Initialize early to prevent overwrites
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
    
    # INTERLEAVED BATCHING: Group URLs by domain for round-robin distribution
    from collections import defaultdict
    urls_by_domain = defaultdict(list)
    
    for url_dict in urls:
        url = url_dict.get('url', '')
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            urls_by_domain[domain].append(url_dict)
        except:
            urls_by_domain['unknown'].append(url_dict)
    
    # Sort domains by priority (priority sites first, then others)
    priority_domains = []
    other_domains = []
    
    for domain in urls_by_domain.keys():
        is_priority = any(priority_site in domain for priority_site in PRIORITY_SITES)
        if is_priority:
            # Find exact priority index for proper ordering
            for i, priority_site in enumerate(PRIORITY_SITES):
                if priority_site in domain:
                    priority_domains.append((i, domain))
                    break
        else:
            other_domains.append(domain)
    
    # Sort priority domains by their order in PRIORITY_SITES
    priority_domains.sort(key=lambda x: x[0])
    ordered_domains = [domain for _, domain in priority_domains] + sorted(other_domains)
    
    # Create interleaved batches using round-robin with 2 URLs per domain
    all_batches = []
    domain_indices = {domain: 0 for domain in ordered_domains}  # Track position in each domain's list
    
    while any(domain_indices[domain] < len(urls_by_domain[domain]) for domain in ordered_domains):
        current_batch = []
        urls_taken_this_round = {domain: 0 for domain in ordered_domains}
        
        # Round-robin: Take up to 2 URLs from each domain
        while len(current_batch) < batch_size:
            added_any = False
            
            for domain in ordered_domains:
                if len(current_batch) >= batch_size:
                    break
                    
                # Take up to 2 URLs from this domain (if available)
                urls_to_take = min(2 - urls_taken_this_round[domain], 
                                  len(urls_by_domain[domain]) - domain_indices[domain],
                                  batch_size - len(current_batch))
                
                if urls_to_take > 0:
                    for _ in range(urls_to_take):
                        current_batch.append(urls_by_domain[domain][domain_indices[domain]])
                        domain_indices[domain] += 1
                        urls_taken_this_round[domain] += 1
                    added_any = True
            
            # If we couldn't add any URLs in this round, we're done
            if not added_any:
                break
        
        if current_batch:
            all_batches.append(current_batch)
    
    logfire.debug("batch_creation_completed", 
                  batch_count=len(all_batches), 
                  domain_count=len(ordered_domains),
                  session_id=session.session_id)
    
    # Process each interleaved batch
    for batch_idx, current_batch in enumerate(all_batches):
        batch_count = batch_idx + 1
        
        
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
        
        # Only process recipe URLs
        urls_to_process = batch_recipe_urls
        
        # Stage 3C: URL Expansion - SKIPPED (all list URLs deferred to backlog)
        stage3_expansion_start = time.time()
        expanded_results = urls_to_process
        fp1_failures = []
        stage3_expansion_time = time.time() - stage3_expansion_start
        total_stage3_time += stage3_expansion_time
        
        if not expanded_results:
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
                    # Downgrade 403 Forbidden to warning (expected for sites that block crawling)
                    error_str = str(data)
                    if "403" in error_str or "Forbidden" in error_str:
                        logfire.warn("site_blocks_crawling", url=url, error=error_str[:200], session_id=session.session_id)
                    else:
                        logfire.error("recipe_parse_failure", url=url, error=error_str[:200], session_id=session.session_id)
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
        
        logfire.info("stage_completed",
                     stage="recipe_scraping",
                     duration=stage4_time,
                     recipes_parsed=len(successful_parses),
                     session_id=session.session_id)
        
        # Accumulate stage timing
        total_stage4_time += stage4_time
        
        # DEBUG: Track batch parsing results
        print(f"🔍 DEBUG BATCH {batch_count}: Parsed {len(successful_parses)} recipes")
        if successful_parses:
            batch_urls = [r.get('source_url', 'NO_URL') for r in successful_parses]
            print(f"🔍 DEBUG BATCH {batch_count}: URLs parsed: {batch_urls}")
            batch_titles = [r.get('title', 'NO_TITLE')[:30] for r in successful_parses]
            print(f"🔍 DEBUG BATCH {batch_count}: Titles: {batch_titles}")
        
        # Add batch results to overall collections
        all_recipes.extend(successful_parses)
        all_fp1_failures.extend(fp1_failures)
        all_failed_parses.extend(failed_parses)
        
        # Stage 5: Final Ranking after each batch
        stage5_start = time.time()
        
        if len(successful_parses) > 0:
            # Phase 1: Verify ONLY newly parsed recipes from this batch (avoid redundant processing)
            batch_qualified, batch_processed = await verify_recipes_meet_requirements(successful_parses, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes.extend(batch_qualified)
            all_processed_recipes.extend(batch_processed)  # Accumulate all processed recipes
            
            # Phase 2: Merge accumulated qualified recipes with existing (no diversity filter)
            
            # DEBUG: Track merge operation
            print(f"🔍 DEBUG MERGE BATCH {batch_count}: Before merge - existing: {len(final_ranked_recipes)}, new: {len(qualified_recipes)}")
            if qualified_recipes:
                new_urls = [r.get('source_url', 'NO_URL') for r in qualified_recipes]
                print(f"🔍 DEBUG MERGE BATCH {batch_count}: New URLs to merge: {new_urls}")
            
            final_ranked_recipes = merge_recipes_with_deduplication(final_ranked_recipes, qualified_recipes)
            
            print(f"🔍 DEBUG MERGE BATCH {batch_count}: After merge - total: {len(final_ranked_recipes)}")
            merged_urls = [r.get('source_url', 'NO_URL') for r in final_ranked_recipes]
            print(f"🔍 DEBUG MERGE BATCH {batch_count}: Final URLs: {merged_urls}")
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
        
        # Domain-aware early exit: Check AFTER domain diversity is applied
        unique_domains = len(set(recipe.get('source_url', '').split('/')[2] for recipe in final_ranked_recipes if recipe.get('source_url')))
        
        if len(final_ranked_recipes) >= needed_count and unique_domains >= 3:
            logfire.info("early_exit_triggered", 
                         recipes_found=len(final_ranked_recipes),
                         unique_domains=unique_domains,
                         urls_processed=urls_processed_count,
                         session_id=session.session_id)
            break
    
    # Process url_backlog if we still need more recipes
    if len(final_ranked_recipes) < needed_count and url_backlog:
        logfire.debug("backlog_processing_started",
                      needed_count=needed_count - len(final_ranked_recipes),
                      backlog_urls=len(url_backlog),
                      session_id=session.session_id)
        stage3_backlog_start = time.time()
        # Process backlog URLs (these are primarily list URLs)
        backlog_copy = url_backlog.copy()
        for backlog_idx, backlog_url_dict in enumerate(backlog_copy):
            # Check if we have enough recipes (no diversity requirement)
            if len(qualified_recipes) >= needed_count:
                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                
                if len(temp_relevance_ranked) >= needed_count:
                    break
                
            url = backlog_url_dict.get('url', '')
            
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
                                
                                # Check if we have enough FINAL recipes to stop (no diversity filter)
                                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                                
                                if len(temp_relevance_ranked) >= needed_count:
                                    logfire.debug("backlog_early_exit", recipes_found=len(temp_final_recipes), session_id=session.session_id)
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
        
        # Stage 5: Final Ranking after backlog processing
        stage5_start = time.time()
        if len(qualified_recipes) > 0:
            # Phase 2: Rank qualified recipes by relevance and merge with existing (no diversity filter)
            relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
            
            # DEBUG: Track backlog merge
            print(f"🔍 DEBUG BACKLOG MERGE: Before merge - existing: {len(final_ranked_recipes)}, new: {len(relevance_ranked)}")
            if relevance_ranked:
                new_urls = [r.get('source_url', 'NO_URL') for r in relevance_ranked]
                print(f"🔍 DEBUG BACKLOG MERGE: New URLs to merge: {new_urls}")
            
            final_ranked_recipes = merge_recipes_with_deduplication(final_ranked_recipes, relevance_ranked)
            
            print(f"🔍 DEBUG BACKLOG MERGE: After merge - total: {len(final_ranked_recipes)}")
        elif len(all_recipes) > 1:
            # Fallback: verify all recipes if no qualified recipes found yet
            fallback_qualified, fallback_processed = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes = fallback_qualified
            all_processed_recipes.extend(fallback_processed)  # Accumulate processed recipes
            relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
            
            # DEBUG: Track fallback merge
            print(f"🔍 DEBUG FALLBACK MERGE: Before merge - existing: {len(final_ranked_recipes)}, new: {len(relevance_ranked)}")
            
            final_ranked_recipes = merge_recipes_with_deduplication(final_ranked_recipes, relevance_ranked)
            
            print(f"🔍 DEBUG FALLBACK MERGE: After merge - total: {len(final_ranked_recipes)}")
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
    
    # Ensure final_ranked_recipes is defined
    if 'final_ranked_recipes' not in locals():
        final_ranked_recipes = all_recipes
    
    # Log processing summary
    logfire.debug("url_processing_summary",
                  total_urls_available=total_urls_to_process,
                  urls_processed=urls_processed_count,
                  final_recipes=len(final_ranked_recipes),
                  session_id=session.session_id)

    # FALLBACK: Fill remaining slots with closest matches if needed (after ALL URLs exhausted)
    fallback_used = False
    exact_match_count = len(final_ranked_recipes)
    
    if len(final_ranked_recipes) < needed_count and 'all_processed_recipes' in locals() and all_processed_recipes:
        remaining_slots = needed_count - len(final_ranked_recipes)
        logfire.debug("fallback_initiated", 
                      remaining_slots=remaining_slots, 
                      needed_count=needed_count,
                      session_id=session.session_id)
        
        # Get recipes with percentage data, excluding ones already in final list
        final_recipe_urls = {recipe.get('source_url', '') for recipe in final_ranked_recipes}
        available_closest = [
            recipe for recipe in all_processed_recipes 
            if recipe.get('source_url', '') not in final_recipe_urls 
            and recipe.get('nutrition_match_percentage', 0) > 0
        ]
        
        # Sort by percentage match (highest first)
        available_closest.sort(key=lambda r: r.get('nutrition_match_percentage', 0), reverse=True)
        
        # Add top closest matches to fill remaining slots (no diversity filter)
        closest_matches = available_closest[:remaining_slots]
        
        # DEBUG: Track closest matches addition
        print(f"🔍 DEBUG CLOSEST MATCHES: Adding {len(closest_matches)} closest matches")
        if closest_matches:
            closest_urls = [r.get('source_url', 'NO_URL') for r in closest_matches]
            print(f"🔍 DEBUG CLOSEST MATCHES: URLs being added: {closest_urls}")
        
        final_ranked_recipes.extend(closest_matches)
        
        print(f"🔍 DEBUG CLOSEST MATCHES: Final count after extend: {len(final_ranked_recipes)}")
        
        
        logfire.info("fallback_applied",
                     final_count=len(final_ranked_recipes),
                     closest_matches_added=len(closest_matches),
                     session_id=session.session_id)
        fallback_used = True

    # Stage 6: Final Formatting using modular function
    stage6_start = time.time()
    
    
    # STAGE 9A: Advanced ingredient parsing
    try:
        from Tools.recipe_search.pipeline.stage_9a_ingredient_parsing import process_all_recipe_ingredients
        
        # Debug: Show domain distribution before Stage 9
        domain_counts = {}
        for recipe in final_ranked_recipes[:needed_count]:
            source_url = recipe.get('source_url', '')
            if source_url:
                try:
                    domain = urlparse(source_url).netloc.lower().replace('www.', '')
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                except:
                    domain_counts['unknown'] = domain_counts.get('unknown', 0) + 1
            else:
                domain_counts['no_url'] = domain_counts.get('no_url', 0) + 1
        
        print(f"\n📊 DOMAIN DISTRIBUTION ENTERING STAGE 9 ({len(final_ranked_recipes[:needed_count])} recipes):")
        for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {domain}: {count} recipes")
        
        print("\n🔧 STAGE 9A: Advanced Ingredient Processing")
        stage9a_start = time.time()
        
        # DEBUG: Check what we're about to pass to Stage 9A
        recipes_for_stage9 = final_ranked_recipes[:needed_count]
        print(f"🔍 DEBUG STAGE 9A INPUT: Slicing {len(final_ranked_recipes)} recipes to {len(recipes_for_stage9)} for Stage 9A")
        for i, recipe in enumerate(recipes_for_stage9):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG STAGE 9A INPUT {i+1}: {url} - {title}")
        
        # Check for duplicates in Stage 9A input
        stage9a_urls = [r.get('source_url', '') for r in recipes_for_stage9]
        unique_stage9a_urls = set(stage9a_urls)
        if len(stage9a_urls) != len(unique_stage9a_urls):
            print(f"🚨 DEBUG STAGE 9A INPUT: DUPLICATE URLS! {len(stage9a_urls)} total vs {len(unique_stage9a_urls)} unique")
            from collections import Counter
            url_counts = Counter(stage9a_urls)
            duplicates = {url: count for url, count in url_counts.items() if count > 1}
            print(f"🚨 DEBUG STAGE 9A DUPLICATES: {duplicates}")
        
        # Process ingredients in parallel for final recipes
        final_recipes_with_ingredients = await process_all_recipe_ingredients(recipes_for_stage9)
        
        # DEBUG: Check Stage 9A output
        print(f"🔍 DEBUG STAGE 9A OUTPUT: Received {len(final_recipes_with_ingredients)} recipes from Stage 9A")
        for i, recipe in enumerate(final_recipes_with_ingredients):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG STAGE 9A OUTPUT {i+1}: {url} - {title}")
        
        # Check for duplicates in Stage 9A output
        stage9a_output_urls = [r.get('source_url', '') for r in final_recipes_with_ingredients]
        unique_stage9a_output_urls = set(stage9a_output_urls)
        if len(stage9a_output_urls) != len(unique_stage9a_output_urls):
            print(f"🚨 DEBUG STAGE 9A OUTPUT: CORRUPTION DETECTED! {len(stage9a_output_urls)} total vs {len(unique_stage9a_output_urls)} unique")
            from collections import Counter
            url_counts = Counter(stage9a_output_urls)
            duplicates = {url: count for url, count in url_counts.items() if count > 1}
            print(f"🚨 DEBUG STAGE 9A CORRUPTION: {duplicates}")
        
        stage9a_time = time.time() - stage9a_start
        print(f"   ✅ Advanced ingredient parsing completed: {stage9a_time:.2f}s")
        
        # STAGE 9B: Ingredient categorization
        print("\n🏷️ STAGE 9B: Ingredient Categorization")
        stage9b_start = time.time()
        
        # DEBUG: Check Stage 9B input
        print(f"🔍 DEBUG STAGE 9B INPUT: Sending {len(final_recipes_with_ingredients)} recipes to Stage 9B")
        for i, recipe in enumerate(final_recipes_with_ingredients):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG STAGE 9B INPUT {i+1}: {url} - {title}")
        
        # Categorize ingredients using hybrid keyword + LLM approach
        final_recipes_with_categories = await categorize_uncategorized_ingredients_parallel(
            final_recipes_with_ingredients, 
            ctx.deps.openai_key
        )
        
        # DEBUG: Check Stage 9B output
        print(f"🔍 DEBUG STAGE 9B OUTPUT: Received {len(final_recipes_with_categories)} recipes from Stage 9B")
        for i, recipe in enumerate(final_recipes_with_categories):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG STAGE 9B OUTPUT {i+1}: {url} - {title}")
        
        # Check for duplicates in Stage 9B output
        stage9b_output_urls = [r.get('source_url', '') for r in final_recipes_with_categories]
        unique_stage9b_output_urls = set(stage9b_output_urls)
        if len(stage9b_output_urls) != len(unique_stage9b_output_urls):
            print(f"🚨 DEBUG STAGE 9B OUTPUT: CORRUPTION DETECTED! {len(stage9b_output_urls)} total vs {len(unique_stage9b_output_urls)} unique")
            from collections import Counter
            url_counts = Counter(stage9b_output_urls)
            duplicates = {url: count for url, count in url_counts.items() if count > 1}
            print(f"🚨 DEBUG STAGE 9B CORRUPTION: {duplicates}")
        
        stage9b_time = time.time() - stage9b_start
        print(f"   ✅ Ingredient categorization completed: {stage9b_time:.2f}s")
        
        # STAGE 9C: Final formatting (with categorized ingredients)
        print("\n📱 STAGE 9C: Final iOS Formatting")
        stage9c_start = time.time()
        
        # DEBUG: Check what goes into formatting
        print(f"🔍 DEBUG STAGE 9C INPUT: Sending {len(final_recipes_with_categories)} recipes to formatting")
        for i, recipe in enumerate(final_recipes_with_categories):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG STAGE 9C INPUT {i+1}: {url} - {title}")
        
        formatted_recipes = format_recipes_for_ios(final_recipes_with_categories, needed_count, fallback_used, exact_match_count)
        
        stage9c_time = time.time() - stage9c_start
        print(f"   ✅ Final formatting completed: {stage9c_time:.2f}s")
        
    except Exception as e:
        print(f"⚠️  Stage 9A-C pipeline failed, using basic formatting: {e}")
        # Fallback to basic formatting without categorization
        formatted_recipes = format_recipes_for_ios(final_ranked_recipes, needed_count, fallback_used, exact_match_count)
    
    # STAGE 8B: Unified Formatting and Ingredient Processing (TEMPORARILY DISABLED - reverted to 9a/9b)
    # try:
    #     from Tools.recipe_search.pipeline.stage_8b_unified_formatting import format_recipes_unified_async
    #     print("\n🔧 STAGE 8B: Unified Formatting and Ingredient Processing")
    #     stage8b_start = time.time()
    #     
    #     # Process ingredients and format in unified approach
    #     formatted_recipes = await format_recipes_unified_async(final_ranked_recipes[:needed_count], needed_count, fallback_used, exact_match_count)
    #     
    #     stage8b_time = time.time() - stage8b_start
    #     print(f"   ✅ Unified processing completed: {stage8b_time:.2f}s")
    #     
    # except Exception as e:
    #     print(f"⚠️  Stage 8b failed, using basic formatting: {e}")
    #     # Fallback to basic formatting using Stage 9a
    #     formatted_recipes = format_recipes_for_ios(final_ranked_recipes, needed_count, fallback_used, exact_match_count)
    
    # DEBUG: Track final recipes before formatting
    print(f"\n🔍 DEBUG FINAL PRE-FORMAT: {len(final_ranked_recipes)} recipes entering formatting")
    for i, recipe in enumerate(final_ranked_recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG PRE-FORMAT {i+1}: {url} - {title}")
    
    # Check for duplicate URLs before formatting
    pre_format_urls = [r.get('source_url', '') for r in final_ranked_recipes]
    unique_pre_format_urls = set(pre_format_urls)
    if len(pre_format_urls) != len(unique_pre_format_urls):
        print(f"🚨 DEBUG DUPLICATE ALERT: {len(pre_format_urls)} total vs {len(unique_pre_format_urls)} unique URLs before formatting!")
        from collections import Counter
        url_counts = Counter(pre_format_urls)
        duplicates = {url: count for url, count in url_counts.items() if count > 1}
        print(f"🚨 DEBUG DUPLICATES: {duplicates}")
    
    # Print FINAL formatted output after Stage 9 completion
    import json
    print(f"\n🎯 FINAL FORMATTED OUTPUT (Post-Stage 9):")
    print("=" * 60)
    print(f"Number of formatted recipes: {len(formatted_recipes)}")
    
    # DEBUG: Check for duplicates in formatted output
    formatted_urls = [r.get('sourceUrl', 'NO_URL') for r in formatted_recipes]
    unique_formatted_urls = set(formatted_urls)
    if len(formatted_urls) != len(unique_formatted_urls):
        print(f"🚨 DEBUG DUPLICATE ALERT: {len(formatted_urls)} total vs {len(unique_formatted_urls)} unique URLs in formatted output!")
        from collections import Counter
        url_counts = Counter(formatted_urls)
        duplicates = {url: count for url, count in url_counts.items() if count > 1}
        print(f"🚨 DEBUG FORMATTED DUPLICATES: {duplicates}")
    
    # Print all recipes for verification
    for i, recipe in enumerate(formatted_recipes):
        print(f"\n🔍 RECIPE {i+1} FINAL STRUCTURE:")
        print(json.dumps(recipe, indent=2))
        if i < len(formatted_recipes) - 1:  # Add separator between recipes
            print("-" * 40)
    print("=" * 60)
    
    # Track failures for reporting
    failed_parse_report = create_failed_parse_report(all_fp1_failures, all_failed_parses)
    stage6_time = time.time() - stage6_start
    
    
    # Accumulate stage timing
    total_stage6_time += stage6_time
    
    # Performance summary
    total_time = time.time() - total_pipeline_start
    
    # Update session context with new recipes
    session.update_current_batch(formatted_recipes)
    
    # Print final formatted recipes JSON for iOS app (COMMENTED OUT to analyze pre-stage-9 data)
    # import json
    # print(f"\n🍽️ FINAL FORMATTED RECIPES JSON FOR iOS APP:")
    # print("=" * 60)
    # print(json.dumps(formatted_recipes, indent=2))
    # print("=" * 60)
    
    # Create minimal context for agent using modular function
    agent_context = create_minimal_recipes_for_agent(formatted_recipes)
    
    # Log structured pipeline summary
    pipeline_summary = stage_logger.log_pipeline_summary(
        total_recipes=len(formatted_recipes),
        fallback_used=fallback_used
    )
    
    # Log final pipeline completion with key metrics
    logfire.info("search_completed",
                 query=query,
                 session_id=session.session_id,
                 total_time=total_time,
                 recipes_found=len(formatted_recipes),
                 exact_matches=agent_context["exact_matches"],
                 closest_matches=agent_context["closest_matches"],
                 fallback_used=agent_context["fallback_used"],
                 stage_timings={
                     "web_search": stage1_time,
                     "url_ranking": stage2_time,
                     "url_expansion": total_stage3_time,
                     "recipe_scraping": total_stage4_time,
                     "final_ranking": total_stage5_time,
                     "formatting": total_stage6_time
                 })
    
    return {
        "results": agent_context["recipes"],  # Minimal context for agent
        "full_recipes": formatted_recipes,  # Full data for iOS
        "totalResults": len(formatted_recipes),
        "searchQuery": query,
        "exact_matches": agent_context["exact_matches"],
        "closest_matches": agent_context["closest_matches"], 
        "fallback_used": agent_context["fallback_used"],
        "_failed_parse_report": failed_parse_report,
        # TODO: UI INTEGRATION POINT
        # Frontend should store and reuse this session_id for all subsequent calls
        "session_id": session.session_id,  # For frontend tracking
        "session_info": {
            "total_shown_urls": len(session.shown_recipe_urls),
            "saved_meals_count": len(session.saved_meals),
            "search_count": len(session.search_history)
        }
    }