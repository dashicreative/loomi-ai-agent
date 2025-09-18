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
from Tools.recipe_search.pipeline.stage_9a_final_formatting import (
    format_recipes_for_ios, 
    create_minimal_recipes_for_agent, 
    create_failed_parse_report
)
from urllib.parse import urlparse
from Tools.recipe_search.pipeline.utils.constants import PRIORITY_SITES, BLOCKED_SITES

# Import parsers for nutrition processing
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list

# Import modular components
from Tools.recipe_search.domain_filtering import apply_domain_diversity_filter, apply_domain_diversity_filter_with_existing
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
    
    # Filter out excluded URLs
    if urls_to_exclude:
        filtered_results = [r for r in raw_results if r.get('url') not in urls_to_exclude]
        print(f"   Filtered: {len(raw_results)} → {len(filtered_results)} URLs (excluded {len(raw_results) - len(filtered_results)})")
        raw_results = filtered_results
    
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
            
            # Phase 2: Apply domain diversity to accumulated qualified recipes
            final_ranked_recipes = apply_domain_diversity_filter(qualified_recipes, max_per_domain=2)
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
            # Check if we have enough DIVERSE recipes (not just qualified recipes)
            if len(qualified_recipes) >= needed_count:
                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                temp_final_recipes = apply_domain_diversity_filter(temp_relevance_ranked, max_per_domain=2)
                unique_domains = len(set(recipe.get('source_url', '').split('/')[2] for recipe in temp_final_recipes if recipe.get('source_url')))
                
                if len(temp_final_recipes) >= needed_count and unique_domains >= 3:
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
                                
                                # Apply domain diversity and check if we have enough FINAL recipes to stop
                                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                                temp_final_recipes = apply_domain_diversity_filter(temp_relevance_ranked, max_per_domain=2)
                                
                                if len(temp_final_recipes) >= needed_count:
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
            # Phase 2: Rank qualified recipes by relevance with domain diversity
            relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
            final_ranked_recipes = apply_domain_diversity_filter(relevance_ranked, max_per_domain=2)
        elif len(all_recipes) > 1:
            # Fallback: verify all recipes if no qualified recipes found yet
            fallback_qualified, fallback_processed = await verify_recipes_meet_requirements(all_recipes, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes = fallback_qualified
            all_processed_recipes.extend(fallback_processed)  # Accumulate processed recipes
            relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
            final_ranked_recipes = apply_domain_diversity_filter(relevance_ranked, max_per_domain=2)
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
        
        # Apply domain diversity to closest matches, considering existing domains
        existing_domains = {}
        for recipe in final_ranked_recipes:
            source_url = recipe.get('source_url', '')
            if source_url:
                try:
                    domain = urlparse(source_url).netloc.lower().replace('www.', '')
                    existing_domains[domain] = existing_domains.get(domain, 0) + 1
                except:
                    pass
        
        # Apply domain diversity filter with existing domain awareness
        diversified_closest = apply_domain_diversity_filter_with_existing(available_closest, existing_domains, max_per_domain=2)
        
        # Add top diversified closest matches to fill remaining slots
        closest_matches = diversified_closest[:remaining_slots]
        final_ranked_recipes.extend(closest_matches)
        
        
        logfire.info("fallback_applied",
                     final_count=len(final_ranked_recipes),
                     closest_matches_added=len(closest_matches),
                     session_id=session.session_id)
        fallback_used = True

    # Stage 6: Final Formatting using modular function
    stage6_start = time.time()
    
    
    # STAGE 9B: Advanced ingredient parsing (BACK TO ORIGINAL IMPLEMENTATION)
    try:
        from Tools.recipe_search.pipeline.stage_9b_ingredient_parsing import process_all_recipe_ingredients
        print("\n🔧 STAGE 9B: Advanced Ingredient Processing")
        stage9b_start = time.time()
        
        # Process ingredients in parallel for final recipes
        final_recipes_with_ingredients = await process_all_recipe_ingredients(final_ranked_recipes[:needed_count])
        
        stage9b_time = time.time() - stage9b_start
        print(f"   ✅ Advanced ingredient parsing completed: {stage9b_time:.2f}s")
        
        # Stage 9a: Final formatting (with pre-processed ingredients)
        formatted_recipes = format_recipes_for_ios(final_recipes_with_ingredients, needed_count, fallback_used, exact_match_count)
        
    except Exception as e:
        print(f"⚠️  Stage 9b failed, using basic formatting: {e}")
        # Fallback to basic formatting
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
    
    # Print FINAL formatted output after Stage 9 completion
    import json
    print(f"\n🎯 FINAL FORMATTED OUTPUT (Post-Stage 9):")
    print("=" * 60)
    print(f"Number of formatted recipes: {len(formatted_recipes)}")
    
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