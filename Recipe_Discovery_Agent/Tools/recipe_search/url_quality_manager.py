"""
Batch Processing Logic

Handles complex interleaved batching with priority site ordering and domain distribution
for optimal recipe discovery performance.
"""

from typing import Dict, List
from urllib.parse import urlparse
from collections import defaultdict


def create_priority_ranked_urls(urls: List[Dict], priority_sites: List[str]) -> List[Dict]:
    """
    Rank URLs by priority sites before any processing.
    
    Args:
        urls: List of URL dictionaries from search results
        priority_sites: List of priority site domains
        
    Returns:
        URLs ranked with priority sites first
    """
    priority_ranked_urls = []
    non_priority_urls = []
    
    for url_dict in urls:
        url = url_dict.get('url', '').lower()
        found_priority = False
        
        # Check if this URL is from a priority site
        for i, priority_site in enumerate(priority_sites):
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
    return priority_ranked_urls + non_priority_urls


def create_interleaved_batches(urls: List[Dict], priority_sites: List[str], batch_size: int = 10) -> List[List[Dict]]:
    """
    Create interleaved batches using round-robin distribution with priority site ordering.
    
    Args:
        urls: List of URL dictionaries to batch
        priority_sites: List of priority site domains  
        batch_size: Maximum URLs per batch
        
    Returns:
        List of batches with domain diversity
    """
    # Group URLs by domain for round-robin distribution
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
        is_priority = any(priority_site in domain for priority_site in priority_sites)
        if is_priority:
            # Find exact priority index for proper ordering
            for i, priority_site in enumerate(priority_sites):
                if priority_site in domain:
                    priority_domains.append((i, domain))
                    break
        else:
            other_domains.append(domain)
    
    # Sort priority domains by their order in priority_sites
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
    return all_batches


def print_batch_domain_distribution(batch: List[Dict], batch_number: int):
    """
    Print domain distribution for a batch for debugging.
    
    Args:
        batch: List of URL dictionaries in the batch
        batch_number: Batch number for logging
    """
    print(f"🚨 BATCH {batch_number}: Processing {len(batch)} interleaved URLs")
    
    # Show domain distribution in this batch
    batch_domains = {}
    for url_dict in batch:
        url = url_dict.get('url', '')
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            batch_domains[domain] = batch_domains.get(domain, 0) + 1
        except:
            batch_domains['unknown'] = batch_domains.get('unknown', 0) + 1
    
    print(f"   Domain distribution: {', '.join(f'{d}:{c}' for d, c in batch_domains.items())}")


def print_site_breakdown_analysis(ranked_urls: List[Dict], priority_sites: List[str]):
    """
    Print detailed site breakdown analysis for debugging.
    
    Args:
        ranked_urls: List of ranked URL dictionaries
        priority_sites: List of priority site domains
    """
    print(f"\n📊 SITE BREAKDOWN ANALYSIS:")
    priority_site_counts = {}
    other_site_counts = {}
    
    for url_dict in ranked_urls:
        url = url_dict.get('url', '')
        try:
            domain = urlparse(url).netloc.lower().replace('www.', '')
            
            # Check if it's a priority site
            is_priority = any(priority_site in domain for priority_site in priority_sites)
            if is_priority:
                priority_site_counts[domain] = priority_site_counts.get(domain, 0) + 1
            else:
                other_site_counts[domain] = other_site_counts.get(domain, 0) + 1
        except:
            other_site_counts['unknown'] = other_site_counts.get('unknown', 0) + 1
    
    # Print priority sites first
    for priority_site in priority_sites:
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


def print_url_processing_summary(total_urls_to_process: int, urls_processed_count: int, 
                                url_backlog_count: int, final_recipes_count: int):
    """
    Print final URL processing summary for debugging.
    
    Args:
        total_urls_to_process: Total URLs available for processing
        urls_processed_count: URLs actually processed
        url_backlog_count: Number of backlog URLs processed
        final_recipes_count: Final number of recipes found
    """
    print(f"🚨 FINAL URL PROCESSING SUMMARY:")
    print(f"   Total URLs available: {total_urls_to_process}")
    print(f"   URLs actually processed: {urls_processed_count}")
    print(f"   Backlog URLs processed: {url_backlog_count}")
    print(f"   Final recipes found: {final_recipes_count}")
    if urls_processed_count < total_urls_to_process:
        print(f"   ⚠️  Only processed {urls_processed_count}/{total_urls_to_process} URLs - stopped early or hit limits")


def print_performance_summary(total_time: float, stage_times: Dict[str, float]):
    """
    Print complete pipeline performance summary.
    
    Args:
        total_time: Total pipeline execution time
        stage_times: Dictionary of stage names to execution times
    """
    print(f"\n⏱️  COMPLETE PIPELINE PERFORMANCE:")
    print(f"   Total Time: {total_time:.2f}s")
    
    for stage_name, stage_time in stage_times.items():
        percentage = (stage_time/total_time)*100 if total_time > 0 else 0
        print(f"   {stage_name}: {stage_time:.2f}s ({percentage:.1f}%)")