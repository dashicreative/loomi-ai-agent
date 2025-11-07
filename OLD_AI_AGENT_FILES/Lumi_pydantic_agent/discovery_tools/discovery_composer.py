"""
Discovery Composer - Fast, broad recipe discovery pipeline
Search engine approach: leverage Google's relevance + minimal post-processing
"""

import time
import asyncio
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse
import sys
from pathlib import Path

# Import discovery tools
from .discovery_search_tool import WebSearchTool as DiscoverySearchTool
from .discovery_classification_tool import URLClassificationTool as DiscoveryClassificationTool  
from .discovery_parsing_tool import RecipeParsingTool as DiscoveryParsingTool

# Import simplified processors (pure regex, no LLM)
sys.path.append(str(Path(__file__).parent.parent))
from shared_tools.final_formatting.ingredient_processor_simple import process_ingredients_simple
from shared_tools.final_formatting.nutrition_processor_simple import process_nutrition_simple
from shared_tools.final_formatting.time_processor_simple import process_time_simple

# Import shared utilities
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
                result_count=search_url_count,  # This will be ignored for multi_parallel
                search_strategy="multi_parallel",  # NEW: 5 parallel pagination calls for 50 URLs
                exclude_urls=exclude_urls or self.deps.session_shown_urls
            )
            
            if not search_result["urls"]:
                return self._empty_discovery_result("No URLs found")
            
            search_elapsed = time.time() - search_start
            print(f"   🔍 STEP 1: Found {len(search_result['urls'])} URLs in {search_elapsed:.1f}s")
            
            # STEP 2: WATERFALL APPROACH - Skip classification, parse everything directly
            print(f"   🌊 STEP 2: WATERFALL PARSING - Attempting to parse all {len(search_result['urls'])} URLs directly")
            all_search_urls = search_result["urls"]  # Keep full URL objects (not just strings)
            
            if not all_search_urls:
                return self._empty_discovery_result("No valid URLs found")
            
            # STEP 3: WATERFALL PARSING - Parse all URLs (JSON-LD + recipe-scrapers funnel)  
            parse_start = time.time()
            
            # Add required 'type' field to all URLs for parser compatibility
            urls_for_parsing = []
            for url_obj in all_search_urls:
                enhanced_url = url_obj.copy()
                enhanced_url['type'] = 'recipe'  # Assume all are recipes for waterfall parsing
                enhanced_url['confidence'] = 1.0  # High confidence for parsing attempt
                urls_for_parsing.append(enhanced_url)
            
            parse_result = await self.parsing_tool.parse_recipes(
                urls=urls_for_parsing,  # URLs with required 'type' field
                parsing_depth="quick",  # Fast parsing for discovery
                timeout_seconds=12      # Aggressive timeout
            )
            
            parsed_recipes = parse_result["parsed_recipes"]
            parse_elapsed = time.time() - parse_start
            
            # WATERFALL: Store failed URLs for potential future list processing  
            successfully_parsed_urls = {recipe.get('source_url') for recipe in parsed_recipes}
            all_url_strings = [url.get('url') for url in all_search_urls if url.get('url')]
            failed_url_strings = [url for url in all_url_strings if url not in successfully_parsed_urls]
            
            # Store failed URLs in session memory for potential future list processing
            self.deps.session_failed_urls.update(failed_url_strings)
            
            print(f"   🍳 STEP 3: Parsed {len(parsed_recipes)} recipes in {parse_elapsed:.1f}s")
            print(f"   🌊 WATERFALL: {len(failed_url_strings)} URLs failed parsing → stored in session for potential list processing")
            print(f"   📊 SUCCESS RATE: {len(parsed_recipes)}/{len(all_search_urls)} URLs = {len(parsed_recipes)/len(all_search_urls)*100:.1f}%")
            print(f"   💾 SESSION: {len(self.deps.session_failed_urls)} total failed URLs tracked this session")
            
            # STEP 3.4: Capture raw data before processing (for debugging/analysis)
            raw_data_recipes = self._capture_raw_data(parsed_recipes)
            print(f"   📥 STEP 3.4: Captured raw data for {len(raw_data_recipes)} recipes")
            
            # STEP 3.5: Process ingredients into structured format (PARALLEL)
            ingredient_start = time.time()
            structured_recipes = self._process_recipe_ingredients(raw_data_recipes)
            ingredient_elapsed = time.time() - ingredient_start
            print(f"   🧄 STEP 3.5: Processed ingredients for {len(structured_recipes)} recipes in {ingredient_elapsed:.1f}s (parallel)")
            
            # STEP 3.6: Process nutrition into structured format (PARALLEL)
            nutrition_start = time.time()
            nutrition_recipes = self._process_recipe_nutrition(structured_recipes)
            nutrition_elapsed = time.time() - nutrition_start
            print(f"   📊 STEP 3.6: Processed nutrition for {len(nutrition_recipes)} recipes in {nutrition_elapsed:.1f}s (parallel)")
            
            # STEP 3.7: Process time fields into structured format (PARALLEL)
            time_start = time.time()
            time_recipes = self._process_recipe_time_fields(nutrition_recipes)
            time_elapsed = time.time() - time_start
            print(f"   ⏰ STEP 3.7: Processed time fields for {len(time_recipes)} recipes in {time_elapsed:.1f}s (parallel)")
            
            # STEP 4: Apply hard image constraint
            recipes_with_images = self._filter_recipes_with_images(time_recipes)
            print(f"   🖼️ STEP 4: {len(recipes_with_images)} recipes have images (filtered {len(time_recipes) - len(recipes_with_images)})")
            
            # STEP 5: Reorder priority sites to top (maintain search order within priorities)
            reordered_recipes = self._reorder_priority_sites_to_top(recipes_with_images, search_result["urls"])
            print(f"   ⭐ STEP 5: {self._count_priority_sites_in_top_5(reordered_recipes)} priority sites in top 5")
            
            # STEP 6: Store in session memory and create summaries  
            recipe_summaries = self._store_recipes_and_create_summaries(reordered_recipes)
            print(f"   💾 STEP 6: Stored {len(recipe_summaries)} recipes in session memory")
            
            # Simple final recipe list
            print(f"\n📋 FINAL RECIPES ({len(recipe_summaries)} found):")
            new_recipe_ids = [summary["recipe_id"] for summary in recipe_summaries]
            
            for i, recipe_id in enumerate(new_recipe_ids, 1):
                if recipe_id in self.deps.recipe_memory:
                    recipe = self.deps.recipe_memory[recipe_id]
                    title = recipe.get('title', 'No Title')
                    source = recipe.get('source_url', 'Unknown')
                    print(f"   {i}. {title}")
                    print(f"      {source}")
            
            # Skip final formatting for now
            formatting_time = 0
            
            # Calculate total timing
            total_elapsed = time.time() - self.deps.query_start_time
            
            # Get recipe IDs for API response
            recipe_ids = [summary["recipe_id"] for summary in recipe_summaries]
            
            result = {
                # Production API response data
                "mode": "discovery",
                "action": "return_all_discovered", 
                "recipe_ids": recipe_ids,
                "message": f"Found {len(recipe_summaries)} recipes ready for browsing",
                
                # Legacy data (for backward compatibility)
                "recipe_summaries": recipe_summaries,
                "backlog_list_urls": [],  # No longer classifying lists separately
                
                # Performance and debugging data
                "discovery_stats": {
                    "urls_searched": len(search_result["urls"]),
                    "urls_attempted_parsing": len(all_search_urls),
                    "recipes_parsed": len(parsed_recipes),
                    "recipes_with_images": len(recipes_with_images),
                    "final_recipe_count": len(recipe_summaries)
                },
                "timing_info": {
                    "total_seconds": round(total_elapsed, 1),
                    "search_seconds": round(search_elapsed, 1),
                    "classify_seconds": 0.0,  # Skipped classification in waterfall approach
                    "parse_seconds": round(parse_elapsed, 1),
                    "formatting_seconds": round(formatting_time, 1),
                    "recipes_per_second": round(len(recipe_summaries) / total_elapsed, 2) if total_elapsed > 0 else 0
                },
                "quality_assessment": self._assess_discovery_quality(len(recipe_summaries), total_elapsed),
                "formatting_integrated": True  # Flag for CLI to know formatting is already done
            }
            
            pipeline_elapsed = time.time() - pipeline_start
            print(f"✅ DISCOVERY PIPELINE COMPLETE: {len(recipe_summaries)} recipes ready for browsing")
            print(f"⚡ PERFORMANCE: {total_elapsed:.1f}s | {'✅ FAST' if total_elapsed <= 8 else '⚠️ SLOW'} (target ≤8s)")
            
            return result
            
        except Exception as e:
            pipeline_elapsed = time.time() - pipeline_start
            print(f"❌ [DISCOVERY] Pipeline failed after {pipeline_elapsed:.1f}s: {e}")
            return self._empty_discovery_result(f"Discovery pipeline error: {str(e)}")
    
    # COMMENTED OUT: Old classification approach replaced by waterfall parsing
    # async def _classify_with_early_exit(self, urls: List[Dict], target_count: int) -> tuple:
    #     """
    #     TRUE ITERATIVE BATCHING: Fetch & classify in chunks until target reached.
    #     
    #     Strategy:
    #     1. Fetch content for 20 URLs at a time
    #     2. Classify this batch to find recipe URLs
    #     3. If recipe_count < target, fetch next batch of 20 URLs
    #     4. Continue until recipe_count >= target OR no more URLs
    #     """
        recipe_urls = []
        list_urls = []
        batch_size = 20  # URLs to fetch and process per iteration (aligned with Google API pagination)
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
            if batch_number > 10:  # Max 10 batches = 200 URLs processed
                print(f"   ⚠️ SAFETY STOP: Processed {batch_number-1} batches, found {len(recipe_urls)} recipes")
                break
        
        if len(recipe_urls) < target_count:
            print(f"   📊 FINAL RESULT: Found {len(recipe_urls)} recipes (target: {target_count}) after processing {url_index} URLs")
        
        return recipe_urls, list_urls
    
    
    async def _classify_all_urls(self, urls: List[Dict]) -> tuple:
        """
        Classify ALL URLs without early exit batching.
        Process all URLs we found from our enhanced search to maximize results.
        """
        recipe_urls = []
        list_urls = []
        batch_size = 20  # Process in parallel batches for efficiency
        
        print(f"   📦 PROCESSING: All {len(urls)} URLs in parallel batches (no early exit)")
        
        # Process URLs in batches of 20 for parallel efficiency
        for batch_start in range(0, len(urls), batch_size):
            batch_end = min(batch_start + batch_size, len(urls))
            current_batch_urls = urls[batch_start:batch_end]
            batch_number = (batch_start // batch_size) + 1
            
            print(f"   📦 BATCH {batch_number}: Processing {len(current_batch_urls)} URLs (positions {batch_start+1}-{batch_end})...")
            
            # Fetch content for this batch
            content_samples = await self.classification_tool._fetch_content_samples(current_batch_urls)
            
            # Classify all URLs in this batch in parallel (same as before)
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
            
            print(f"   📊 BATCH {batch_number}: Found {batch_recipes_found} recipes, {batch_lists_found} lists")
        
        print(f"   🎯 FINAL RESULT: Found {len(recipe_urls)} recipes total from all {len(urls)} URLs")
        return recipe_urls, list_urls
    
    
    def _filter_recipes_with_images(self, recipes: List[Dict]) -> List[Dict]:
        """
        Hard constraint: Filter out recipes without images.
        Images are critical for app visual experience.
        Enhanced to work with new images array format.
        """
        def has_images(recipe):
            # Check new images array first
            images = recipe.get('images', [])
            if images:
                return True
            # Fallback to legacy image_url for backward compatibility
            return bool(recipe.get('image_url'))
        
        return [recipe for recipe in recipes if has_images(recipe)]
    
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
            
            # Restructure recipe for clean app format before storing
            clean_recipe = self._restructure_recipe_for_app(recipe_with_context)
            
            # Store clean recipe in memory
            self.deps.recipe_memory[recipe_id] = clean_recipe
            
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
    
    def _restructure_recipe_for_app(self, recipe: Dict) -> Dict:
        """
        Restructure recipe into clean app format with metadata separation.
        Removes duplicates, organizes data for production API response.
        """
        # Get captured raw data (from Step 3.4)
        raw_ingredients = recipe.get('ingredients_raw', [])
        raw_nutrition = recipe.get('nutrition_raw')
        raw_cook_time = recipe.get('cook_time_raw') 
        raw_prep_time = recipe.get('prep_time_raw')
        
        # Get alternative units (from ingredient processing)
        ingredient_alternatives = recipe.get('ingredient_alternatives', {})
        
        # Clean main app-ready structure (remove duplicates)
        clean_recipe = {
            # Core recipe data
            "title": recipe.get("title"),
            "source_url": recipe.get("source_url"),
            "servings": recipe.get("servings"),
            "description": recipe.get("description"),
            "author": recipe.get("author"),
            "keywords": recipe.get("keywords", []),
            "datePublished": recipe.get("datePublished"),
            
            # Processed timing (keep only clean versions)
            "cookTime": recipe.get("cookTime"),
            "prepTime": recipe.get("prepTime"), 
            "readyInMinutes": recipe.get("readyInMinutes"),
            
            # Structured data (already processed)
            "ingredients": recipe.get("ingredients", []),
            "nutrition": recipe.get("nutrition", {}),
            "images": recipe.get("images", []),
            "instructions": recipe.get("instructions", []),
            
            # Metadata for debugging and analysis
            "_metadata": {
                "raw": {
                    "cook_time": raw_cook_time,
                    "prep_time": raw_prep_time,
                    "ingredients": raw_ingredients,
                    "nutrition": raw_nutrition
                },
                "alternatives": {
                    "ingredient_units": ingredient_alternatives
                },
                "processing": {
                    "extraction_method": recipe.get("extraction_method"),
                    "ingredient_parser": "simple_v1.0",
                    "nutrition_parser": "simple_v1.0", 
                    "time_parser": "simple_v1.0",
                    "processed_at": time.time(),
                    "performance": {
                        "ingredients_count": len(recipe.get("ingredients", [])),
                        "nutrition_fields": len([k for k, v in recipe.get("nutrition", {}).items() if v > 0]),
                        "images_count": len(recipe.get("images", []))
                    }
                },
                "session": {
                    "recipe_id": recipe.get("recipe_id"),
                    "search_mode": recipe.get("search_mode", "discovery"),
                    "user_position": recipe.get("user_position"),
                    "shown_to_user": recipe.get("shown_to_user"),
                    "timestamp": recipe.get("timestamp")
                }
            }
        }
        
        # Remove None values to keep JSON clean
        clean_recipe = {k: v for k, v in clean_recipe.items() if v is not None}
        
        return clean_recipe
    
    def _capture_raw_data(self, recipes: List[Dict]) -> List[Dict]:
        """
        Capture raw data before processing for debugging and analysis.
        Adds raw_ingredients and raw_nutrition to each recipe.
        """
        recipes_with_raw_data = []
        
        for recipe in recipes:
            # Capture raw ingredients (before processing)
            raw_ingredients = recipe.get('ingredients', [])
            
            # Capture raw nutrition (before processing)
            raw_nutrition = recipe.get('nutrition')
            
            # Capture raw timing (before processing)
            raw_cook_time = recipe.get('cook_time')
            raw_prep_time = recipe.get('prep_time')
            
            # Add raw data storage to recipe
            recipe_with_raw = recipe.copy()
            recipe_with_raw['ingredients_raw'] = raw_ingredients
            recipe_with_raw['nutrition_raw'] = raw_nutrition
            recipe_with_raw['cook_time_raw'] = raw_cook_time
            recipe_with_raw['prep_time_raw'] = raw_prep_time
            
            recipes_with_raw_data.append(recipe_with_raw)
        
        return recipes_with_raw_data
    
    def _process_recipe_ingredients(self, recipes: List[Dict]) -> List[Dict]:
        """
        Process ingredients for all recipes into structured format using parallel processing.
        NO LLM CALLS - Pure regex parsing enables full parallelization.
        """
        if not recipes:
            return recipes
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def process_single_recipe(recipe: Dict) -> Dict:
            """Process ingredients for a single recipe."""
            ingredients = recipe.get('ingredients', [])
            
            if not ingredients:
                return recipe
            
            # Convert ingredients to strings if they're not already
            ingredient_strings = []
            for ing in ingredients:
                if isinstance(ing, dict):
                    ingredient_strings.append(ing.get('ingredient', str(ing)))
                else:
                    ingredient_strings.append(str(ing))
            
            try:
                # Process ingredients using pure regex processor (NO LLM)
                structured_ingredients, alternatives_map = process_ingredients_simple(ingredient_strings)
                
                # Update recipe with structured ingredients and alternatives
                updated_recipe = recipe.copy()
                updated_recipe['ingredients'] = structured_ingredients
                
                # Store alternatives for metadata capture
                if alternatives_map:
                    updated_recipe['ingredient_alternatives'] = alternatives_map
                
                return updated_recipe
                
            except Exception as e:
                print(f"   ⚠️ Ingredient processing failed for {recipe.get('title', 'Unknown')}: {e}")
                return recipe
        
        # Process all recipes in parallel (since no LLM calls)
        processed_recipes = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=min(len(recipes), 8)) as executor:
            # Submit all recipe processing tasks
            future_to_recipe = {executor.submit(process_single_recipe, recipe): recipe for recipe in recipes}
            
            # Collect results as they complete
            for future in as_completed(future_to_recipe):
                try:
                    processed_recipe = future.result()
                    processed_recipes.append(processed_recipe)
                except Exception as e:
                    original_recipe = future_to_recipe[future]
                    print(f"   ⚠️ Parallel processing failed for {original_recipe.get('title', 'Unknown')}: {e}")
                    processed_recipes.append(original_recipe)
        
        return processed_recipes
    
    
    def _process_recipe_nutrition(self, recipes: List[Dict]) -> List[Dict]:
        """
        Process nutrition for all recipes into structured format using parallel processing.
        NO LLM CALLS - Pure regex parsing enables full parallelization.
        """
        if not recipes:
            return recipes
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def process_single_recipe_nutrition(recipe: Dict) -> Dict:
            """Process nutrition for a single recipe."""
            nutrition_data = recipe.get('nutrition')
            
            try:
                # Process nutrition using pure regex processor (NO LLM)
                structured_nutrition = process_nutrition_simple(nutrition_data)
                
                # Update recipe with structured nutrition
                updated_recipe = recipe.copy()
                updated_recipe['nutrition'] = structured_nutrition
                return updated_recipe
                
            except Exception as e:
                print(f"   ⚠️ Nutrition processing failed for {recipe.get('title', 'Unknown')}: {e}")
                return recipe
        
        # Process all recipes in parallel (since no LLM calls)
        processed_recipes = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=min(len(recipes), 8)) as executor:
            # Submit all recipe nutrition processing tasks
            future_to_recipe = {executor.submit(process_single_recipe_nutrition, recipe): recipe for recipe in recipes}
            
            # Collect results as they complete
            for future in as_completed(future_to_recipe):
                try:
                    processed_recipe = future.result()
                    processed_recipes.append(processed_recipe)
                except Exception as e:
                    original_recipe = future_to_recipe[future]
                    print(f"   ⚠️ Parallel nutrition processing failed for {original_recipe.get('title', 'Unknown')}: {e}")
                    processed_recipes.append(original_recipe)
        
        return processed_recipes
    
    
    def _process_recipe_time_fields(self, recipes: List[Dict]) -> List[Dict]:
        """
        Process time fields for all recipes into structured format using parallel processing.
        NO LLM CALLS - Pure regex parsing enables full parallelization.
        """
        if not recipes:
            return recipes
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def process_single_recipe_time(recipe: Dict) -> Dict:
            """Process time fields for a single recipe."""
            try:
                # Process time fields using pure regex processor (NO LLM)
                structured_recipe = process_time_simple(recipe)
                return structured_recipe
                
            except Exception as e:
                print(f"   ⚠️ Time processing failed for {recipe.get('title', 'Unknown')}: {e}")
                return recipe
        
        # Process all recipes in parallel (since no LLM calls)
        processed_recipes = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=min(len(recipes), 8)) as executor:
            # Submit all recipe time processing tasks
            future_to_recipe = {executor.submit(process_single_recipe_time, recipe): recipe for recipe in recipes}
            
            # Collect results as they complete
            for future in as_completed(future_to_recipe):
                try:
                    processed_recipe = future.result()
                    processed_recipes.append(processed_recipe)
                except Exception as e:
                    original_recipe = future_to_recipe[future]
                    print(f"   ⚠️ Parallel time processing failed for {original_recipe.get('title', 'Unknown')}: {e}")
                    processed_recipes.append(original_recipe)
        
        return processed_recipes
    
    
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