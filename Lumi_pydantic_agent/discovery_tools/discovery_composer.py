"""
Discovery Composer - Fast, broad recipe discovery pipeline
Search engine approach: leverage Google's relevance + minimal post-processing
"""

import time
import asyncio
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

# Import discovery tools
from .discovery_search_tool import WebSearchTool as DiscoverySearchTool
from .discovery_classification_tool import URLClassificationTool as DiscoveryClassificationTool  
from .discovery_parsing_tool import RecipeParsingTool as DiscoveryParsingTool

# Import shared utilities
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from shared_tools.performance_scorer import AgentPerformanceScorer


class DiscoveryComposer:
    """
    Fast, exploratory recipe discovery pipeline.
    Search engine approach: speed + variety over precision.
    
    Target: ≤8 seconds, 15+ varied results
    Strategy: Minimal filtering, leverage Google's relevance ranking
    """
    
    def __init__(self, deps):
        """Initialize with agent dependencies."""
        self.deps = deps
        
        # Initialize discovery tools
        self.search_tool = DiscoverySearchTool(
            serpapi_key=deps.serpapi_key, 
            google_key=deps.google_key, 
            google_cx=deps.google_cx
        )
        self.classification_tool = DiscoveryClassificationTool(deps.openai_key)
        self.parsing_tool = DiscoveryParsingTool(deps.openai_key)
        self.scorer = AgentPerformanceScorer()
        
        # Priority sites for reordering (matches current list)
        self.priority_sites = [
            'allrecipes.com', 'simplyrecipes.com', 'seriouseats.com',
            'food52.com', 'budgetbytes.com', 'bonappetit.com',
            'cookinglight.com', 'eatingwell.com', 'thekitchn.com',
            'skinnytaste.com', 'minimalistbaker.com'
        ]
    
    async def discover_recipes(
        self,
        query: str,
        target_recipe_count: int = 15,
        search_url_count: int = 45,
        exclude_urls: Optional[Set[str]] = None
    ) -> Dict:
        """
        Main discovery pipeline: Search → Classify with Early Exit → Parse → Filter → Reorder
        
        Args:
            query: User search query
            target_recipe_count: Target number of individual recipes (default 15)
            search_url_count: Initial URLs to search (default 45) 
            exclude_urls: URLs to exclude from search
            
        Returns:
            Simplified result structure optimized for discovery browsing
        """
        pipeline_start = time.time()
        print(f"🚀 DISCOVERY PIPELINE: {search_url_count} URLs → {target_recipe_count} recipes")
        
        if not self.deps.query_start_time:
            self.deps.query_start_time = time.time()
        
        try:
            # STEP 1: Search for URLs (increased volume)
            search_start = time.time()
            search_result = await self.search_tool.search(
                query=query,
                result_count=search_url_count,
                search_strategy="mixed",  # Balanced approach for discovery
                exclude_urls=exclude_urls or self.deps.session_shown_urls
            )
            
            if not search_result["urls"]:
                return self._empty_discovery_result("No URLs found")
            
            search_elapsed = time.time() - search_start
            print(f"   🔍 STEP 1: Found {len(search_result['urls'])} URLs in {search_elapsed:.1f}s")
            
            # STEP 2: Classify URLs with Early Exit at target recipe count
            classify_start = time.time()
            recipe_urls, list_urls = await self._classify_with_early_exit(
                search_result["urls"], 
                target_recipe_count
            )
            
            classify_elapsed = time.time() - classify_start
            print(f"   📋 STEP 2: Found {len(recipe_urls)} recipes, {len(list_urls)} lists in {classify_elapsed:.1f}s (early exit)")
            
            if not recipe_urls:
                return self._empty_discovery_result("No individual recipe URLs found")
            
            # STEP 3: Parse all found recipe URLs
            parse_start = time.time()
            parse_result = await self.parsing_tool.parse_recipes(
                urls=recipe_urls,
                parsing_depth="quick",  # Fast parsing for discovery
                timeout_seconds=12      # Aggressive timeout
            )
            
            parsed_recipes = parse_result["parsed_recipes"]
            parse_elapsed = time.time() - parse_start
            print(f"   🍳 STEP 3: Parsed {len(parsed_recipes)} recipes in {parse_elapsed:.1f}s")
            
            # STEP 4: Apply hard image constraint
            recipes_with_images = self._filter_recipes_with_images(parsed_recipes)
            print(f"   🖼️ STEP 4: {len(recipes_with_images)} recipes have images (filtered {len(parsed_recipes) - len(recipes_with_images)})")
            
            # STEP 5: Reorder priority sites to top (maintain search order within priorities)
            reordered_recipes = self._reorder_priority_sites_to_top(recipes_with_images, recipe_urls)
            print(f"   ⭐ STEP 5: {self._count_priority_sites_in_top_5(reordered_recipes)} priority sites in top 5")
            
            # STEP 6: Store in session memory and create summaries
            recipe_summaries = self._store_recipes_and_create_summaries(reordered_recipes)
            
            # Calculate total timing
            total_elapsed = time.time() - self.deps.query_start_time
            
            result = {
                "recipe_summaries": recipe_summaries,
                "backlog_list_urls": list_urls,
                "discovery_stats": {
                    "urls_searched": len(search_result["urls"]),
                    "recipes_classified": len(recipe_urls),
                    "recipes_parsed": len(parsed_recipes),
                    "recipes_with_images": len(recipes_with_images),
                    "final_recipe_count": len(recipe_summaries)
                },
                "timing_info": {
                    "total_seconds": round(total_elapsed, 1),
                    "search_seconds": round(search_elapsed, 1),
                    "classify_seconds": round(classify_elapsed, 1),
                    "parse_seconds": round(parse_elapsed, 1),
                    "recipes_per_second": round(len(recipe_summaries) / total_elapsed, 2) if total_elapsed > 0 else 0
                },
                "quality_assessment": self._assess_discovery_quality(len(recipe_summaries), total_elapsed)
            }
            
            pipeline_elapsed = time.time() - pipeline_start
            print(f"✅ DISCOVERY PIPELINE COMPLETE: {len(recipe_summaries)} recipes ready for browsing")
            print(f"⚡ PERFORMANCE: {total_elapsed:.1f}s | {'✅ FAST' if total_elapsed <= 8 else '⚠️ SLOW'} (target ≤8s)")
            
            return result
            
        except Exception as e:
            pipeline_elapsed = time.time() - pipeline_start
            print(f"❌ [DISCOVERY] Pipeline failed after {pipeline_elapsed:.1f}s: {e}")
            return self._empty_discovery_result(f"Discovery pipeline error: {str(e)}")
    
    async def _classify_with_early_exit(self, urls: List[Dict], target_count: int) -> tuple:
        """
        TRUE ITERATIVE BATCHING: Fetch & classify in chunks until target reached.
        
        Strategy:
        1. Fetch content for 12 URLs at a time
        2. Classify this batch to find recipe URLs
        3. If recipe_count < target, fetch next batch of 12 URLs
        4. Continue until recipe_count >= target OR no more URLs
        """
        recipe_urls = []
        list_urls = []
        batch_size = 12  # URLs to fetch and process per iteration
        url_index = 0
        batch_number = 1
        
        print(f"   📦 ITERATIVE BATCHING: Processing {batch_size} URLs per batch until {target_count} recipes found")
        
        while len(recipe_urls) < target_count and url_index < len(urls):
            # Determine batch of URLs to process
            batch_end = min(url_index + batch_size, len(urls))
            current_batch_urls = urls[url_index:batch_end]
            
            print(f"   📦 BATCH {batch_number}: Fetching content for {len(current_batch_urls)} URLs (positions {url_index+1}-{batch_end})...")
            
            # Fetch content for this batch
            content_samples = await self.classification_tool._fetch_content_samples(current_batch_urls)
            
            # Classify all URLs in this batch in parallel
            classification_tasks = [
                self.classification_tool._classify_single_url(sample) 
                for sample in content_samples
            ]
            batch_results = await asyncio.gather(*classification_tasks, return_exceptions=True)
            
            # Process classification results
            batch_recipes_found = 0
            batch_lists_found = 0
            
            for i, classification in enumerate(batch_results):
                if isinstance(classification, Exception):
                    continue
                    
                original_url = current_batch_urls[i]
                enriched_url = original_url.copy()
                enriched_url.update({
                    'type': classification.type,
                    'confidence': classification.confidence,
                    'classification_method': 'llm' if classification.confidence > 0.5 else 'fallback',
                    'classification_signals': classification.signals
                })
                
                if classification.type == "recipe":
                    recipe_urls.append(enriched_url)
                    batch_recipes_found += 1
                elif classification.type == "list":
                    list_urls.append(enriched_url)
                    batch_lists_found += 1
            
            print(f"   📊 BATCH {batch_number}: Found {batch_recipes_found} recipes, {batch_lists_found} lists | Total: {len(recipe_urls)} recipes")
            
            # Check if we've reached our target
            if len(recipe_urls) >= target_count:
                print(f"   🎯 TARGET REACHED: Found {len(recipe_urls)} recipes (target: {target_count}) after {batch_number} batches")
                break
            
            # Move to next batch
            url_index += batch_size
            batch_number += 1
            
            # Safety check to avoid infinite loops
            if batch_number > 10:  # Max 10 batches = 120 URLs processed
                print(f"   ⚠️ SAFETY STOP: Processed {batch_number-1} batches, found {len(recipe_urls)} recipes")
                break
        
        if len(recipe_urls) < target_count:
            print(f"   📊 FINAL RESULT: Found {len(recipe_urls)} recipes (target: {target_count}) after processing {url_index} URLs")
        
        return recipe_urls, list_urls
    
    def _filter_recipes_with_images(self, recipes: List[Dict]) -> List[Dict]:
        """
        Hard constraint: Filter out recipes without images.
        Images are critical for app visual experience.
        """
        return [recipe for recipe in recipes if recipe.get('image_url')]
    
    def _reorder_priority_sites_to_top(self, recipes: List[Dict], original_recipe_urls: List[Dict]) -> List[Dict]:
        """
        Reorder recipes to put first 5 priority sites at the top.
        Maintains search order within priority and non-priority groups.
        """
        # Create mapping of URL to original search position
        url_to_position = {}
        for i, url_obj in enumerate(original_recipe_urls):
            url_to_position[url_obj.get('url', '')] = i
        
        # Separate priority and non-priority recipes with their original positions
        priority_recipes = []
        non_priority_recipes = []
        
        for recipe in recipes:
            source_url = recipe.get('source_url', '')
            domain = self._extract_domain_from_url(source_url)
            original_position = url_to_position.get(source_url, 999)
            
            recipe_with_position = (recipe, original_position)
            
            if any(priority_site in domain for priority_site in self.priority_sites):
                priority_recipes.append(recipe_with_position)
            else:
                non_priority_recipes.append(recipe_with_position)
        
        # Sort each group by original search position to maintain Google's relevance
        priority_recipes.sort(key=lambda x: x[1])
        non_priority_recipes.sort(key=lambda x: x[1])
        
        # Take first 5 priority recipes, then fill with non-priority
        reordered = []
        
        # Add first 5 priority recipes
        for recipe, _ in priority_recipes[:5]:
            reordered.append(recipe)
        
        # Add remaining non-priority recipes
        for recipe, _ in non_priority_recipes:
            reordered.append(recipe)
        
        # Add any remaining priority recipes (beyond first 5)
        for recipe, _ in priority_recipes[5:]:
            reordered.append(recipe)
        
        return reordered
    
    def _store_recipes_and_create_summaries(self, recipes: List[Dict]) -> List[Dict]:
        """
        Store recipes in session memory and create simplified summaries.
        Discovery mode: minimal metadata, focus on browsing experience.
        """
        recipe_summaries = []
        
        for i, recipe in enumerate(recipes):
            # Generate unique recipe ID
            self.deps.recipe_counter += 1
            recipe_id = f"session_recipe_{self.deps.recipe_counter:03d}"
            
            # Add discovery context to recipe
            recipe_with_context = recipe.copy()
            recipe_with_context.update({
                "recipe_id": recipe_id,
                "search_mode": "discovery",  # NEW: Tag for smart deduplication
                "user_position": i + 1,
                "shown_to_user": True,
                "timestamp": time.time()
            })
            
            # Store full recipe in memory
            self.deps.recipe_memory[recipe_id] = recipe_with_context
            
            # Update session shown URLs
            if recipe.get("source_url"):
                self.deps.session_shown_urls.add(recipe["source_url"])
            
            # Create simplified summary for discovery browsing
            domain = self._extract_domain_from_url(recipe.get('source_url', ''))
            is_priority_site = any(priority in domain for priority in self.priority_sites)
            
            recipe_summary = {
                "recipe_id": recipe_id,
                "user_position": i + 1,
                "title": recipe.get('title', ''),
                "url": recipe.get('source_url', ''),
                "image_url": recipe.get('image_url', ''),
                "source_domain": domain,
                "is_priority_site": is_priority_site,
                "cook_time": recipe.get('cook_time', ''),
                "servings": recipe.get('servings', ''),
                
                # Basic counts for browsing
                "ingredients_count": len(recipe.get('ingredients', [])),
                "instructions_count": len(recipe.get('instructions', []))
            }
            
            recipe_summaries.append(recipe_summary)
        
        print(f"   💾 STEP 6: Stored {len(recipe_summaries)} recipes in session memory")
        return recipe_summaries
    
    def _extract_domain_from_url(self, url: str) -> str:
        """Extract clean domain from URL."""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"
    
    def _count_priority_sites_in_top_5(self, recipes: List[Dict]) -> int:
        """Count how many priority sites are in the top 5 results."""
        count = 0
        for recipe in recipes[:5]:
            domain = self._extract_domain_from_url(recipe.get('source_url', ''))
            if any(priority_site in domain for priority_site in self.priority_sites):
                count += 1
        return count
    
    def _assess_discovery_quality(self, recipe_count: int, elapsed_seconds: float) -> str:
        """Simple quality assessment for discovery mode."""
        if elapsed_seconds > 12:
            return "slow"
        elif recipe_count >= 12:
            return "excellent"
        elif recipe_count >= 8:
            return "good"
        else:
            return "acceptable"
    
    def _empty_discovery_result(self, error_message: str) -> Dict:
        """Return empty result structure with error message."""
        return {
            "recipe_summaries": [],
            "backlog_list_urls": [],
            "discovery_stats": {
                "urls_searched": 0,
                "recipes_classified": 0,
                "recipes_parsed": 0,
                "recipes_with_images": 0,
                "final_recipe_count": 0
            },
            "timing_info": {
                "total_seconds": 0.0,
                "search_seconds": 0.0,
                "classify_seconds": 0.0,
                "parse_seconds": 0.0,
                "recipes_per_second": 0.0
            },
            "quality_assessment": "poor",
            "error": error_message
        }