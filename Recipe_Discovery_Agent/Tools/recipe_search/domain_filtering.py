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
        else:
            percentage = recipe.get('nutrition_match_percentage', 0)
    
    return diversified_recipes