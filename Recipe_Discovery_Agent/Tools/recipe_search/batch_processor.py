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
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from Dependencies import RecipeDeps

# Session context now in Dependencies - no imports needed

# Import all modularized stages
from Tools.Recipe_Search_Stages.stage_1_web_search import search_recipes_serpapi, search_recipes_google_custom, search_recipes_parallel_priority
from Tools.Recipe_Search_Stages.stage_2_url_ranking import rerank_results_with_llm
from Tools.Recipe_Search_Stages.stage_3_url_classification import classify_urls_batch
from Tools.Recipe_Search_Stages.stage_4_recipe_parsing import parse_recipe
from Tools.Recipe_Search_Stages.stage_5_nutrition_normalization import normalize_nutrition_data
from Tools.Recipe_Search_Stages.stage_6_requirements_verification import verify_recipes_meet_requirements
from Tools.Recipe_Search_Stages.stage_7_relevance_ranking import rank_qualified_recipes_by_relevance
from Tools.Recipe_Search_Stages.stage_8_list_processing import expand_urls_with_lists, ListParser
from Tools.Recipe_Search_Stages.stage_9_final_formatting import (
    format_recipes_for_ios, 
    create_minimal_recipes_for_agent, 
    create_failed_parse_report
)
from urllib.parse import urlparse
from Tools.Recipe_Search_Stages.utils.constants import PRIORITY_SITES, BLOCKED_SITES

# Import parsers for nutrition processing
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list

# Import modular components
from .domain_filtering import apply_domain_diversity_filter, apply_domain_diversity_filter_with_existing




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
    total_pipeline_start = time.time()
    
    # Session Context Management - Proper Pydantic AI Pattern
    session = ctx.deps.session
    session.search_history.append(query)
    
    # Get URLs to exclude (from session or passed explicitly)
    urls_to_exclude = set()
    if exclude_urls:
        urls_to_exclude.update(exclude_urls)
    # Add all previously shown URLs from session
    urls_to_exclude.update(session.shown_recipe_urls)
    
    if urls_to_exclude:
        print(f"🚫 Excluding {len(urls_to_exclude)} previously shown URLs from search")
    
    # Stage 1: Priority Parallel Search System
    stage1_start = time.time()
    search_results = await search_recipes_parallel_priority(ctx, query)
    raw_results = search_results.get("results", [])
    
    # Filter out excluded URLs
    if urls_to_exclude:
        filtered_results = [r for r in raw_results if r.get('url') not in urls_to_exclude]
        print(f"   Filtered: {len(raw_results)} → {len(filtered_results)} URLs (excluded {len(raw_results) - len(filtered_results)})")
        raw_results = filtered_results
    
    stage1_time = time.time() - stage1_start
    
    if not raw_results:
        return {
            "results": [],
            "full_recipes": [],
            "totalResults": 0,
            "searchQuery": query,
            "error": "No search results found from parallel search system"
        }
    
    print(f"📊 Stage 1: Priority Parallel Search - Found {len(raw_results)} URLs - {stage1_time:.2f}s")
    print(f"   Priority sites: {search_results.get('priority_count', 0)} URLs")
    print(f"   General search: {search_results.get('general_count', 0)} URLs")
    
    # Stage 2: Initial Ranking
    stage2_start = time.time()
    ranked_urls = await rerank_results_with_llm(
        raw_results, 
        query, 
        ctx.deps.openai_key, 
        top_k=60  # Handle larger result set from parallel search
    )
    stage2_time = time.time() - stage2_start
    
    print(f"📊 Stage 2: Initial Ranking - Ranked {len(ranked_urls)} URLs - {stage2_time:.2f}s")
    
    # Print site breakdown after ranking
    print(f"\n📊 SITE BREAKDOWN ANALYSIS:")
    priority_site_counts = {}
    other_site_counts = {}
    
    for url_dict in ranked_urls:
        url = url_dict.get('url', '')
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            
            # Check if it's a priority site
            is_priority = any(priority_site in domain for priority_site in PRIORITY_SITES)
            if is_priority:
                priority_site_counts[domain] = priority_site_counts.get(domain, 0) + 1
            else:
                other_site_counts[domain] = other_site_counts.get(domain, 0) + 1
        except:
            other_site_counts['unknown'] = other_site_counts.get('unknown', 0) + 1
    
    # Print priority sites first
    for priority_site in PRIORITY_SITES:
        if priority_site in priority_site_counts:
            print(f"   {priority_site}: {priority_site_counts[priority_site]} URLs")
    
    # Print detailed breakdown of other sites
    if other_site_counts:
        total_other = sum(other_site_counts.values())
        print(f"   other: {total_other} URLs")
        for domain, count in sorted(other_site_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"      └─ {domain}: {count} URLs")
    
    total_unique_domains = len(priority_site_counts) + len(other_site_counts)
    print(f"   Total unique domains: {total_unique_domains}")
    print()
    
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
    
    print(f"🔄 INTERLEAVED BATCHING: Created {len(all_batches)} diverse batches from {len(ordered_domains)} domains")
    
    # Process each interleaved batch
    for batch_idx, current_batch in enumerate(all_batches):
        batch_count = batch_idx + 1
        
        print(f"🚨 BATCH {batch_count}: Processing {len(current_batch)} interleaved URLs")
        # Show domain distribution in this batch
        batch_domains = {}
        for url_dict in current_batch:
            url = url_dict.get('url', '')
            try:
                domain = urlparse(url).netloc.lower().replace('www.', '')
                batch_domains[domain] = batch_domains.get(domain, 0) + 1
            except:
                batch_domains['unknown'] = batch_domains.get('unknown', 0) + 1
        print(f"   Domain distribution: {', '.join(f'{d}:{c}' for d, c in batch_domains.items())}")
        
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
        
        if len(successful_parses) > 0:
            # Phase 1: Verify ONLY newly parsed recipes from this batch (avoid redundant processing)
            batch_qualified, batch_processed = await verify_recipes_meet_requirements(successful_parses, requirements, ctx.deps.openai_key, user_query)
            qualified_recipes.extend(batch_qualified)
            all_processed_recipes.extend(batch_processed)  # Accumulate all processed recipes
            
            # Phase 2: Apply domain diversity to accumulated qualified recipes
            print(f"🚨 DEBUG MAIN BATCH - BEFORE DOMAIN FILTER: {len(qualified_recipes)} recipes")
            final_ranked_recipes = apply_domain_diversity_filter(qualified_recipes, max_per_domain=2)
            print(f"🚨 DEBUG MAIN BATCH - AFTER DOMAIN FILTER: {len(final_ranked_recipes)} recipes")
        else:
            final_ranked_recipes = all_recipes
        stage5_time = time.time() - stage5_start
        
        print(f"📊 Stage 5: Final Ranking - Ranking {len(final_ranked_recipes)} qualified recipes - {stage5_time:.2f}s")
        
        # Accumulate stage timing
        total_stage5_time += stage5_time
        
        # Domain-aware early exit: Check AFTER domain diversity is applied
        unique_domains = len(set(recipe.get('source_url', '').split('/')[2] for recipe in final_ranked_recipes if recipe.get('source_url')))
        
        if len(final_ranked_recipes) >= needed_count and unique_domains >= 3:
            print(f"🚨 EARLY EXIT: Found {len(final_ranked_recipes)} recipes from {unique_domains} domains (needed {needed_count}) after processing {urls_processed_count}/{total_urls_to_process} URLs")
            break
        elif len(final_ranked_recipes) >= needed_count:
            print(f"🚨 DIVERSITY CHECK: Have {len(final_ranked_recipes)} recipes but only {unique_domains} domains (need 3+), continuing processing...")
        else:
            print(f"🚨 BATCH {batch_count} COMPLETE: Have {len(final_ranked_recipes)}/{needed_count} recipes from {unique_domains} domains, continuing...")
    
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
            # Check if we have enough DIVERSE recipes (not just qualified recipes)
            if len(qualified_recipes) >= needed_count:
                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                temp_final_recipes = apply_domain_diversity_filter(temp_relevance_ranked, max_per_domain=2)
                unique_domains = len(set(recipe.get('source_url', '').split('/')[2] for recipe in temp_final_recipes if recipe.get('source_url')))
                
                if len(temp_final_recipes) >= needed_count and unique_domains >= 3:
                    print(f"🚨 BACKLOG EARLY EXIT: Found {len(temp_final_recipes)} diverse recipes from {unique_domains} domains")
                    break
                else:
                    print(f"🚨 BACKLOG CONTINUE: Have {len(temp_final_recipes)} recipes from {unique_domains} domains, need more diversity...")
            else:
                print(f"🚨 BACKLOG CONTINUE: Have {len(qualified_recipes)}/{needed_count} qualified recipes, need more...")
                
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
                                
                                # Apply domain diversity and check if we have enough FINAL recipes to stop
                                temp_relevance_ranked = await rank_qualified_recipes_by_relevance(qualified_recipes, user_query, ctx.deps.openai_key)
                                temp_final_recipes = apply_domain_diversity_filter(temp_relevance_ranked, max_per_domain=2)
                                
                                if len(temp_final_recipes) >= needed_count:
                                    print(f"🚨 BACKLOG EARLY EXIT: Found {len(temp_final_recipes)} diverse recipes after domain filtering")
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
    fallback_used = False
    exact_match_count = len(final_ranked_recipes)
    
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
        
        print(f"   Added {len(closest_matches)} closest matches:")
        for i, recipe in enumerate(closest_matches, 1):
            percentage = recipe.get('nutrition_match_percentage', 0)
            title = recipe.get('title', 'Unknown')[:50]
            print(f"      {i}. {title} ({percentage}% match)")
        
        print(f"🚨 FINAL RECIPE COUNT AFTER FALLBACK: {len(final_ranked_recipes)}")
        fallback_used = True

    # Stage 6: Final Formatting using modular function
    stage6_start = time.time()
    formatted_recipes = format_recipes_for_ios(final_ranked_recipes, needed_count, fallback_used, exact_match_count)
    
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
    
    # Update session context with new recipes
    session.update_current_batch(formatted_recipes)
    
    # Create minimal context for agent using modular function
    agent_context = create_minimal_recipes_for_agent(formatted_recipes)
    
    # Final recipe selection display
    print("\n" + "="*60)
    print(f"🍳 FINAL {len(formatted_recipes)} RECIPES SELECTED:")
    print("="*60)
    for i, recipe in enumerate(formatted_recipes[:5], 1):
        print(f"{i}. {recipe.get('title', 'Unknown Title')}")
        print(f"   URL: {recipe.get('sourceUrl', 'No URL')}")
    print("="*60 + "\n")
    
    # Print full formatted data structure for iOS
    print("\n" + "="*60)
    print("📱 IOS APP DATA STRUCTURE:")
    print("="*60)
    import json
    ios_data = {
        "recipes": formatted_recipes,
        "metadata": {
            "totalResults": len(formatted_recipes),
            "searchQuery": query,
            "exact_matches": agent_context["exact_matches"],
            "closest_matches": agent_context["closest_matches"],
            "fallback_used": agent_context["fallback_used"]
        }
    }
    print(json.dumps(ios_data, indent=2))
    print("="*60 + "\n")
    
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