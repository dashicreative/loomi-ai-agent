"""
Early Exit Manager for progressive recipe processing.
Stops processing as soon as quality threshold is met to optimize performance.
"""
from typing import List, Dict, Optional, Tuple
import asyncio
import logging
from .quality_scorer import RecipeQualityScorer, QualityScore
from .Detailed_Recipe_Parsers.Parsers import parse_recipe

# Set up logging
logger = logging.getLogger(__name__)


class EarlyExitManager:
    """Manages early exit decisions during progressive recipe processing"""
    
    def __init__(
        self,
        quality_threshold: float = 0.7,
        min_recipes: int = 5,
        max_recipes: int = 8,
        max_attempts: int = 15,
        firecrawl_key: Optional[str] = None
    ):
        """
        Initialize Early Exit Manager
        
        Args:
            quality_threshold: Minimum quality score to accept a recipe (0.0-1.0)
            min_recipes: Minimum high-quality recipes before considering early exit
            max_recipes: Maximum recipes to collect before forced exit
            max_attempts: Maximum URLs to attempt parsing (prevents infinite processing)
            firecrawl_key: FireCrawl API key for recipe parsing
        """
        self.quality_threshold = quality_threshold
        self.min_recipes = min_recipes
        self.max_recipes = max_recipes
        self.max_attempts = max_attempts
        self.firecrawl_key = firecrawl_key
        
        # Initialize quality scorer
        self.quality_scorer = RecipeQualityScorer()
        
        # Statistics tracking
        self.stats = {
            'total_attempted': 0,
            'successful_parses': 0,
            'failed_parses': 0,
            'high_quality_found': 0,
            'low_quality_rejected': 0,
            'binary_check_failures': 0,
            'early_exit_triggered': False,
            'processing_time': 0.0
        }
    
    async def progressive_parse_with_exit(
        self, 
        url_list: List[Dict], 
        query: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Progressive parsing with early exit when quality threshold is met.
        
        Args:
            url_list: List of URL dictionaries with 'url', 'title', 'snippet'
            query: User search query for relevance scoring
            
        Returns:
            Tuple of (high_quality_recipes, all_parsed_recipes)
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting progressive parsing for {len(url_list)} URLs")
        logger.info(f"Target: {self.min_recipes}-{self.max_recipes} recipes with quality ≥{self.quality_threshold}")
        
        high_quality_recipes = []
        all_parsed_recipes = []
        
        # Reset stats for this run
        self.stats.update({
            'total_attempted': 0,
            'successful_parses': 0,
            'failed_parses': 0,
            'high_quality_found': 0,
            'low_quality_rejected': 0,
            'binary_check_failures': 0,
            'early_exit_triggered': False
        })
        
        for i, url_info in enumerate(url_list[:self.max_attempts]):
            url = url_info.get('url', '')
            if not url:
                continue
                
            self.stats['total_attempted'] += 1
            
            logger.debug(f"Processing URL {i+1}/{len(url_list)}: {url}")
            
            # Parse the recipe
            try:
                recipe_data = await parse_recipe(url, self.firecrawl_key)
                
                if recipe_data.get('error'):
                    self.stats['failed_parses'] += 1
                    logger.debug(f"Parsing failed for {url}: {recipe_data.get('error')}")
                    continue
                
                self.stats['successful_parses'] += 1
                
                # Add search metadata
                recipe_data['search_title'] = url_info.get('title', '')
                recipe_data['search_snippet'] = url_info.get('snippet', '')
                recipe_data['source_url'] = url
                
                # Score the recipe
                quality_score = self.quality_scorer.score_recipe(recipe_data, query)
                
                # Add quality score to recipe data
                recipe_data['_quality_score'] = quality_score.total_score
                recipe_data['_quality_details'] = quality_score.details
                recipe_data['_has_required_data'] = quality_score.has_required_data
                
                all_parsed_recipes.append(recipe_data)
                
                # Check binary requirements first
                if not quality_score.has_required_data:
                    self.stats['binary_check_failures'] += 1
                    logger.debug(f"Recipe failed binary check: {quality_score.details.get('rejected', 'missing required fields')}")
                    continue
                
                # Check quality threshold
                if quality_score.total_score >= self.quality_threshold:
                    self.stats['high_quality_found'] += 1
                    high_quality_recipes.append(recipe_data)
                    
                    logger.info(f"✅ High-quality recipe found: {recipe_data.get('title', 'No title')[:50]}... "
                              f"(score: {quality_score.total_score:.3f})")
                    
                    # Check early exit conditions
                    if self._should_exit_early(high_quality_recipes, all_parsed_recipes):
                        self.stats['early_exit_triggered'] = True
                        logger.info(f"🎯 EARLY EXIT: Found {len(high_quality_recipes)} high-quality recipes after {i+1} attempts")
                        break
                else:
                    self.stats['low_quality_rejected'] += 1
                    logger.debug(f"Recipe below quality threshold: {quality_score.total_score:.3f} < {self.quality_threshold}")
                
            except Exception as e:
                self.stats['failed_parses'] += 1
                logger.warning(f"Exception parsing {url}: {str(e)}")
                continue
            
            # Safety check: stop if failure rate is too high
            if not self._should_continue_processing():
                logger.warning("Stopping due to high failure rate")
                break
        
        # Record processing time
        self.stats['processing_time'] = time.time() - start_time
        
        # Log final statistics
        self._log_final_stats(high_quality_recipes, all_parsed_recipes)
        
        return high_quality_recipes, all_parsed_recipes
    
    def _should_exit_early(self, high_quality_recipes: List[Dict], all_recipes: List[Dict]) -> bool:
        """
        Determine if we should exit early based on current results.
        
        Args:
            high_quality_recipes: List of recipes meeting quality threshold
            all_recipes: List of all successfully parsed recipes
            
        Returns:
            True if should exit early, False to continue processing
        """
        # Must have minimum number of high-quality recipes
        if len(high_quality_recipes) < self.min_recipes:
            return False
        
        # Force exit if we've reached maximum recipes
        if len(high_quality_recipes) >= self.max_recipes:
            return True
        
        # Early exit if we have enough high-quality recipes and good success rate
        if len(high_quality_recipes) >= self.min_recipes:
            total_attempted = self.stats['total_attempted']
            if total_attempted >= 8:  # Need reasonable sample size
                success_rate = self.stats['successful_parses'] / total_attempted
                quality_rate = len(high_quality_recipes) / max(self.stats['successful_parses'], 1)
                
                # Exit early if we have good success and quality rates
                if success_rate >= 0.6 and quality_rate >= 0.4:
                    logger.debug(f"Early exit conditions met: success_rate={success_rate:.2f}, quality_rate={quality_rate:.2f}")
                    return True
        
        return False
    
    def _should_continue_processing(self) -> bool:
        """
        Check if we should continue processing based on failure rates.
        
        Returns:
            True if should continue, False if failure rate too high
        """
        total_attempted = self.stats['total_attempted']
        
        # Always continue for first few attempts
        if total_attempted < 5:
            return True
        
        # Stop if failure rate is too high
        if total_attempted >= 10:
            success_rate = self.stats['successful_parses'] / total_attempted
            if success_rate < 0.3:  # Less than 30% success
                logger.warning(f"High failure rate detected: {success_rate:.2f} < 0.30")
                return False
        
        return True
    
    def _log_final_stats(self, high_quality_recipes: List[Dict], all_recipes: List[Dict]):
        """Log final processing statistics"""
        stats = self.stats
        
        logger.info(f"\n📊 Early Exit Processing Complete:")
        logger.info(f"   Attempted: {stats['total_attempted']}")
        logger.info(f"   Successful parses: {stats['successful_parses']}")
        logger.info(f"   Failed parses: {stats['failed_parses']}")
        logger.info(f"   High quality found: {stats['high_quality_found']}")
        logger.info(f"   Binary check failures: {stats['binary_check_failures']}")
        logger.info(f"   Low quality rejected: {stats['low_quality_rejected']}")
        logger.info(f"   Early exit triggered: {stats['early_exit_triggered']}")
        logger.info(f"   Processing time: {stats['processing_time']:.2f}s")
        
        if stats['total_attempted'] > 0:
            success_rate = stats['successful_parses'] / stats['total_attempted']
            logger.info(f"   Success rate: {success_rate:.1%}")
            
        if stats['successful_parses'] > 0:
            quality_rate = stats['high_quality_found'] / stats['successful_parses']
            logger.info(f"   Quality rate: {quality_rate:.1%}")
    
    def get_stats(self) -> Dict:
        """Get processing statistics"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics for new processing run"""
        self.stats.update({
            'total_attempted': 0,
            'successful_parses': 0,
            'failed_parses': 0,
            'high_quality_found': 0,
            'low_quality_rejected': 0,
            'binary_check_failures': 0,
            'early_exit_triggered': False,
            'processing_time': 0.0
        })


class PriorityURLOrdering:
    """Helper class for ordering URLs by priority for optimal early exit"""
    
    def __init__(self, priority_sites: List[str] = None):
        """Initialize with priority sites list"""
        try:
            from .Tools import PRIORITY_SITES
            self.priority_sites = priority_sites or PRIORITY_SITES
        except ImportError:
            self.priority_sites = priority_sites or [
                "allrecipes.com", "simplyrecipes.com", "eatingwell.com",
                "foodnetwork.com", "delish.com", "seriouseats.com"
            ]
    
    def order_urls_by_priority(self, url_list: List[Dict]) -> List[Dict]:
        """
        Order URLs to maximize early exit probability.
        
        Priority order:
        1. Priority sites first (higher success probability)
        2. URLs with recipe-specific keywords in title
        3. Remaining URLs by Google ranking
        
        Args:
            url_list: List of URL dictionaries
            
        Returns:
            Reordered list optimized for early exit
        """
        priority_urls = []
        recipe_keyword_urls = []
        other_urls = []
        
        recipe_keywords = ['recipe', 'how to make', 'cooking', 'bake', 'prepare']
        
        for url_info in url_list:
            url = url_info.get('url', '').lower()
            title = url_info.get('title', '').lower()
            
            # Check if from priority site
            is_priority_site = any(site in url for site in self.priority_sites)
            
            # Check if has recipe keywords in title
            has_recipe_keywords = any(keyword in title for keyword in recipe_keywords)
            
            if is_priority_site:
                priority_urls.append(url_info)
            elif has_recipe_keywords:
                recipe_keyword_urls.append(url_info)
            else:
                other_urls.append(url_info)
        
        # Sort each group by Google position (lower = better)
        priority_urls.sort(key=lambda x: x.get('google_position', 999))
        recipe_keyword_urls.sort(key=lambda x: x.get('google_position', 999))
        other_urls.sort(key=lambda x: x.get('google_position', 999))
        
        # Combine in priority order
        return priority_urls + recipe_keyword_urls + other_urls