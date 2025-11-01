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
            reordered_recipes = self._reorder_priority_sites_to_top(recipes_with_images, recipe_urls)
            print(f"   ⭐ STEP 5: {self._count_priority_sites_in_top_5(reordered_recipes)} priority sites in top 5")
            
            # STEP 6: Store in session memory and create summaries  
            recipe_summaries = self._store_recipes_and_create_summaries(reordered_recipes)
            print(f"   💾 STEP 6: Stored {len(recipe_summaries)} recipes in session memory")
            
            # DEBUG: Print ALL recipes in raw form (before final formatting)
            print("\n" + "="*80)
            print("🔍 DEBUG: Raw Recipe Data After Step 6 (Before Final Formatting)")
            print("="*80)
            new_recipe_ids = [summary["recipe_id"] for summary in recipe_summaries]
            
            # Count extraction methods
            extraction_methods = {}
            for recipe_id in new_recipe_ids:
                if recipe_id in self.deps.recipe_memory:
                    method = self.deps.recipe_memory[recipe_id].get('extraction_method', 'unknown')
                    extraction_methods[method] = extraction_methods.get(method, 0) + 1
            
            print(f"📊 EXTRACTION METHOD BREAKDOWN ({len(new_recipe_ids)} recipes):")
            for method, count in extraction_methods.items():
                print(f"   🔧 {method}: {count} recipes")
            print()
            
            for i, recipe_id in enumerate(new_recipe_ids):  # Show ALL recipes
                if recipe_id in self.deps.recipe_memory:
                    recipe = self.deps.recipe_memory[recipe_id]
                    print(f"\n📋 RECIPE {i+1} (ID: {recipe_id}):")
                    print(f"   📍 Source: {recipe.get('source_url', 'Unknown')}")
                    print(f"   🔧 Extraction Method: {recipe.get('extraction_method', 'Unknown')}")
                    print(f"   📝 Title: {recipe.get('title', 'No Title')}")
                    
                    # Enhanced image display - show images array with categorization
                    images = recipe.get('images', [])
                    if images:
                        # Count by type
                        image_counts = {}
                        for img in images:
                            img_type = img.get('type', 'unknown')
                            image_counts[img_type] = image_counts.get(img_type, 0) + 1
                        
                        # Create summary string
                        type_summary = ', '.join([f"{count} {img_type}" for img_type, count in image_counts.items()])
                        print(f"   🖼️ Images: {len(images)} total ({type_summary})")
                        
                        # Show main image URL for reference
                        main_image = next((img for img in images if img.get('type') == 'main'), images[0] if images else None)
                        if main_image:
                            print(f"      Main: {main_image.get('url', '')[:80]}{'...' if len(main_image.get('url', '')) > 80 else ''}")
                    else:
                        print(f"   🖼️ Images: No images found")
                    
                    # DEBUG: Show BEFORE/AFTER comparison for ingredients
                    raw_ingredients = recipe.get('_metadata', {}).get('raw', {}).get('ingredients', [])
                    processed_ingredients = recipe.get('ingredients', [])
                    
                    print(f"   🧄 INGREDIENTS COMPARISON:")
                    print(f"      📥 RAW ({len(raw_ingredients)}): {raw_ingredients}")
                    
                    print(f"      📤 PROCESSED ({len(processed_ingredients)}):")
                    if processed_ingredients and isinstance(processed_ingredients[0], dict):
                        # Show ALL structured ingredients
                        for j, ingredient in enumerate(processed_ingredients, 1):
                            quantity = ingredient.get('quantity', '')
                            unit = ingredient.get('unit', '')
                            name = ingredient.get('ingredient', '')
                            context = ingredient.get('additional_context', '')
                            category = ingredient.get('category', '')
                            
                            # Format display
                            amount_str = f"{quantity} {unit}".strip() if quantity or unit else "—"
                            context_str = f" ({context})" if context else ""
                            category_str = f"[{category}]" if category else "[]"
                            print(f"         {j}. {amount_str} {name}{context_str} {category_str}")
                    else:
                        # Still raw strings
                        for j, ingredient in enumerate(processed_ingredients, 1):
                            ingredient_str = ingredient if isinstance(ingredient, str) else str(ingredient)
                            print(f"         {j}. {ingredient_str} [RAW]")
                    print(f"   📋 Instructions ({len(recipe.get('instructions', []))}):")
                    for j, instruction in enumerate(recipe.get('instructions', [])[:3], 1):  # Show first 3 instructions
                        print(f"      {j}. {instruction[:100]}{'...' if len(instruction) > 100 else ''}")
                    if len(recipe.get('instructions', [])) > 3:
                        print(f"      ... and {len(recipe.get('instructions', [])) - 3} more instructions")
                    print(f"   👥 Servings: {recipe.get('servings', 'Unknown')}")
                    
                    # DEBUG: Show BEFORE/AFTER comparison for nutrition
                    raw_nutrition = recipe.get('_metadata', {}).get('raw', {}).get('nutrition')
                    processed_nutrition = recipe.get('nutrition')
                    
                    print(f"   📊 NUTRITION COMPARISON:")
                    print(f"      📥 RAW: {raw_nutrition}")
                    if processed_nutrition and isinstance(processed_nutrition, dict):
                        # Format structured nutrition nicely
                        nutrition_parts = []
                        for key, value in processed_nutrition.items():
                            if value > 0:  # Only show non-zero values
                                nutrition_parts.append(f"{key}={value}")
                        print(f"      📤 PROCESSED: {', '.join(nutrition_parts)}")
                    else:
                        print(f"      📤 PROCESSED: {processed_nutrition}")
                    
                    # DEBUG: Show BEFORE/AFTER comparison for timing
                    raw_cook = recipe.get('_metadata', {}).get('raw', {}).get('cook_time')
                    raw_prep = recipe.get('_metadata', {}).get('raw', {}).get('prep_time')
                    processed_cook = recipe.get('cookTime')
                    processed_prep = recipe.get('prepTime')
                    processed_ready = recipe.get('readyInMinutes')
                    
                    print(f"   ⏰ TIMING COMPARISON:")
                    print(f"      📥 RAW: cook_time=\"{raw_cook}\", prep_time=\"{raw_prep}\"")
                    print(f"      📤 PROCESSED: cookTime={processed_cook}, prepTime={processed_prep}, readyInMinutes={processed_ready}")
                    
                    # DEBUG: Show ALL fields in recipe to identify missing nutrition
                    print(f"   🔍 ALL FIELDS: {list(recipe.keys())}")
            print("="*80)
            print("🔍 End Debug Output")
            print("="*80 + "\n")
            
            # STEP 6b: INTEGRATED FINAL FORMATTING - TEMPORARILY DISABLED FOR DEBUGGING
            print(f"   🚀 STEP 6b: Integrated final formatting... DISABLED FOR DEBUGGING")
            formatting_start = time.time()
            
            # Get recipe IDs that were just stored
            new_recipe_ids = [summary["recipe_id"] for summary in recipe_summaries]
            
            # COMMENTED OUT FOR DEBUGGING - Call optimized final formatting if we have recipes
            # if new_recipe_ids and self.deps.openai_key:
            #     from shared_tools.final_formatting import format_recipes_for_app_optimized
            #     
            #     # Get app-ready formatted recipes
            #     formatted_response = await format_recipes_for_app_optimized(
            #         agent_response="",  # No agent response needed here
            #         recipe_ids=new_recipe_ids,
            #         recipe_memory=self.deps.recipe_memory,
            #         openai_key=self.deps.openai_key
            #     )
            #     
            #     # Replace raw recipes with formatted recipes in session memory
            #     formatted_recipes = formatted_response.get("recipes", [])
            #     for formatted_recipe in formatted_recipes:
            #         recipe_id = formatted_recipe.get("id")
            #         if recipe_id and recipe_id in self.deps.recipe_memory:
            #             # Get original metadata
            #             original_recipe = self.deps.recipe_memory[recipe_id]
            #             
            #             # Replace with formatted recipe while preserving essential metadata
            #             self.deps.recipe_memory[recipe_id] = {
            #                 **formatted_recipe,  # Formatted recipe data (ingredients, nutrition, etc.)
            #                 "recipe_id": recipe_id,
            #                 "search_mode": original_recipe.get("search_mode", "discovery"),
            #                 "user_position": original_recipe.get("user_position", 0),
            #                 "shown_to_user": original_recipe.get("shown_to_user", True),
            #                 "timestamp": original_recipe.get("timestamp", time.time()),
            #                 "is_formatted": True,
            #                 "source_url": formatted_recipe.get("sourceUrl", original_recipe.get("source_url", "")),
            #                 "image_url": formatted_recipe.get("image", original_recipe.get("image_url", ""))
            #             }
            #     
            #     formatting_time = time.time() - formatting_start
            #     print(f"   ✅ STEP 6b: Formatted {len(formatted_recipes)} recipes in {formatting_time:.2f}s")
            # else:
            #     formatting_time = 0
            #     print(f"   ⚠️ STEP 6b: Skipped formatting (no OpenAI key or no recipes)")
            
            # TEMPORARY: Skip formatting for debugging
            formatting_time = 0
            print(f"   ⚠️ STEP 6b: Skipped formatting for debugging")
            
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
                "backlog_list_urls": list_urls,
                
                # Performance and debugging data
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
    
    async def _classify_with_early_exit(self, urls: List[Dict], target_count: int) -> tuple:
        """
        TRUE ITERATIVE BATCHING: Fetch & classify in chunks until target reached.
        
        Strategy:
        1. Fetch content for 20 URLs at a time
        2. Classify this batch to find recipe URLs
        3. If recipe_count < target, fetch next batch of 20 URLs
        4. Continue until recipe_count >= target OR no more URLs
        """
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