"""
Domain Diversity Filtering

Ensures variety in recipe sources by enforcing domain quotas while preserving
quality ranking within domain limits.
"""

from typing import Dict, List
from urllib.parse import urlparse


def apply_domain_diversity_filter(recipes: List[Dict], max_per_domain: int = 2) -> List[Dict]:
    """
    Apply domain diversity filter to ensure variety in recipe sources.
    
    Takes relevance-ranked recipes and enforces domain quotas while preserving
    quality ranking within domain limits.
    
    Args:
        recipes: List of recipes ranked by relevance/quality
        max_per_domain: Maximum recipes allowed per domain (default 2)
        
    Returns:
        Filtered list with domain diversity enforced
    """
    if not recipes:
        return recipes
    
    domain_counts = {}
    diversified_recipes = []
    
    for recipe in recipes:
        # Extract domain from source URL
        source_url = recipe.get('source_url', '')
        if not source_url:
            continue
            
        try:
            domain = urlparse(source_url).netloc.lower()
            # Remove www. prefix for consistency
            domain = domain.replace('www.', '')
        except:
            continue
        
        # Check if domain quota exceeded
        current_count = domain_counts.get(domain, 0)
        
        if current_count < max_per_domain:
            diversified_recipes.append(recipe)
            domain_counts[domain] = current_count + 1
            print(f"   📊 Added recipe from {domain} ({current_count + 1}/{max_per_domain}): {recipe.get('title', 'Unknown')[:40]}...")
        else:
            print(f"   ⚠️  Skipped recipe from {domain} (quota exceeded {max_per_domain}): {recipe.get('title', 'Unknown')[:40]}...")
    
    print(f"   🌍 Domain diversity: {len(domain_counts)} unique domains, {len(diversified_recipes)} total recipes")
    
    # DEBUG: Show actual recipes and their domains for verification
    print(f"   🔍 DOMAIN VERIFICATION:")
    for i, recipe in enumerate(diversified_recipes, 1):
        source_url = recipe.get('source_url', 'No URL')
        try:
            domain = urlparse(source_url).netloc.lower().replace('www.', '')
        except:
            domain = 'unknown'
        title = recipe.get('title', 'Unknown')[:40]
        print(f"      {i}. [{domain}] {title}...")
        print(f"         {source_url}")
    
    print(f"   🚨 RETURNING {len(diversified_recipes)} DOMAIN-FILTERED RECIPES")
    return diversified_recipes


def apply_domain_diversity_filter_with_existing(recipes: List[Dict], existing_domains: Dict[str, int], max_per_domain: int = 2) -> List[Dict]:
    """
    Apply domain diversity filter considering recipes already selected.
    
    Args:
        recipes: List of recipes to filter
        existing_domains: Dict of domain -> count from already selected recipes
        max_per_domain: Maximum recipes allowed per domain
        
    Returns:
        Filtered list respecting existing domain quotas
    """
    if not recipes:
        return recipes
    
    domain_counts = existing_domains.copy()  # Start with existing counts
    diversified_recipes = []
    
    for recipe in recipes:
        source_url = recipe.get('source_url', '')
        if not source_url:
            continue
            
        try:
            domain = urlparse(source_url).netloc.lower().replace('www.', '')
        except:
            continue
        
        current_count = domain_counts.get(domain, 0)
        
        if current_count < max_per_domain:
            diversified_recipes.append(recipe)
            domain_counts[domain] = current_count + 1
            percentage = recipe.get('nutrition_match_percentage', 0)
            print(f"   📊 Added closest match from {domain} ({current_count + 1}/{max_per_domain}): {recipe.get('title', 'Unknown')[:40]}... ({percentage}%)")
        else:
            percentage = recipe.get('nutrition_match_percentage', 0)
            print(f"   ⚠️  Skipped closest match from {domain} (quota exceeded): {recipe.get('title', 'Unknown')[:40]}... ({percentage}%)")
    
    return diversified_recipes