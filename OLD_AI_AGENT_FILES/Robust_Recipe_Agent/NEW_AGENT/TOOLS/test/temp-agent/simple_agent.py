"""
Simplified Recipe Discovery Agent with Three Pillar Intelligence
Tests 4 core tools with Speed/Quality/Accuracy optimization and performance scoring.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, List
import json
import re

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from web_search_tool import WebSearchTool
from url_classification_tool import URLClassificationTool  
from recipe_parsing_tool import RecipeParsingTool
from list_parsing_tool import ListParsingTool
from performance_scorer import AgentPerformanceScorer, SessionPerformanceTracker


class SimpleRecipeAgent:
    """
    Intelligent agent with Three Pillar optimization and performance learning.
    Speed > Quality > Accuracy with reactive checkpoints and session adaptation.
    """
    
    def __init__(self, serpapi_key: str, openai_key: str, google_key: str = None, google_cx: str = None):
        self.search_tool = WebSearchTool(serpapi_key, google_key, google_cx)
        self.classification_tool = URLClassificationTool(openai_key)
        self.recipe_parsing_tool = RecipeParsingTool(openai_key)
        self.list_parsing_tool = ListParsingTool(openai_key)
        
        # Performance intelligence
        self.scorer = AgentPerformanceScorer()
        self.session_tracker = SessionPerformanceTracker()
        
        # Agent state
        self.query_start_time = None
        self.session_shown_urls = set()
        self.current_recipes = []  # Track recipes found during search
        
        # Session recipe memory bank
        self.session_recipe_bank = []  # Store all good recipes from session searches
        self.session_queries = []  # Track queries for context
    
    async def find_recipes(self, user_query: str, target_count: int = 4) -> Dict:
        """
        Intelligent recipe discovery with Three Pillar optimization and reactive checkpoints.
        Speed > Quality > Accuracy with performance learning.
        """
        self.query_start_time = time.time()
        self.current_recipes = []
        
        # STEP 1: Analyze user intent and set initial dials
        print(f"\n🤖 Loomi: Analyzing your request: '{user_query}'...")
        initial_strategy = self._analyze_user_intent(user_query, target_count)
        
        print(f"🎯 Strategy: {initial_strategy['speed_approach']} speed, {initial_strategy['quality_approach']} quality")
        
        try:
            # STEP 2: Execute search with intelligent parameters
            print(f"🔍 Searching {initial_strategy['url_count']} URLs from {initial_strategy['search_strategy']} sources...")
            search_result = await self.search_tool.search(
                query=user_query,
                result_count=initial_strategy['url_count'],
                search_strategy=initial_strategy['search_strategy'],
                exclude_urls=self.session_shown_urls
            )
            
            if not search_result["urls"]:
                return self._handle_no_results(user_query)
            
            print(f"   Found {search_result['total_found']} URLs ({search_result['source_distribution']['priority']} from trusted sites)")
            
            # CHECKPOINT: Early timing assessment
            elapsed = time.time() - self.query_start_time
            if elapsed > 5:  # If search itself is slow
                print(f"   ⏱️ Search took {elapsed:.1f}s - optimizing remaining steps...")
            
            # STEP 3: Classify URLs
            print("🏷️ Classifying URLs...")
            classification_result = await self.classification_tool.classify_urls(search_result["urls"])
            
            classified_urls = classification_result["classified_urls"]
            recipe_urls = [url for url in classified_urls if url.get("type") == "recipe"]
            list_urls = [url for url in classified_urls if url.get("type") == "list"]
            
            print(f"   Found: {len(recipe_urls)} individual recipes, {len(list_urls)} collections")
            
            # STEP 4: Parse with reactive monitoring
            await self._parse_with_reactive_monitoring(
                recipe_urls, list_urls, user_query, target_count, initial_strategy
            )
            
            # STEP 5: Finalize results with performance scoring
            return await self._finalize_with_scoring(user_query, target_count)
            
        except Exception as e:
            print(f"❌ Agent error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e), "recipes": []}
    
    def _analyze_user_intent(self, user_query: str, target_count: int) -> Dict:
        """
        Analyze user query to set initial Three Pillar dial positions.
        Uses natural language understanding, not rigid rules.
        """
        query_lower = user_query.lower()
        
        # Speed indicators
        speed_terms = ['quick', 'fast', 'easy', 'simple', 'tonight', 'right now', 'need something', 'urgent']
        speed_priority = any(term in query_lower for term in speed_terms) or target_count == 1
        
        # Quality indicators  
        quality_terms = ['beautiful', 'impressive', 'restaurant-quality', 'special', 'birthday', 'celebration', 'guests', 'amazing', 'perfect']
        quality_emphasis = any(term in query_lower for term in quality_terms)
        
        # Accuracy/constraint indicators
        accuracy_terms = ['gluten-free', 'vegan', 'dairy-free', 'protein', 'calories', 'keto', 'diabetic', 'no nuts', 'allergy']
        constraint_count = sum(1 for term in accuracy_terms if term in query_lower)
        high_accuracy_need = constraint_count >= 2
        
        # Session learning adaptation
        session_insights = self.session_tracker.get_session_insights()
        avg_speed = session_insights.get("session_averages", {}).get("speed", 85)
        
        # Set dials based on user intent and session performance
        if speed_priority:
            speed_approach = "conservative"
            url_count = 12 if target_count <= 2 else 18
            search_strategy = "priority_only"
        elif high_accuracy_need:
            speed_approach = "standard" 
            url_count = min(target_count * 6, 35)  # More URLs for complex constraints
            search_strategy = "priority_only"  # Start with priority, expand later if needed
        elif quality_emphasis:
            speed_approach = "standard"
            url_count = min(target_count * 5, 25) 
            search_strategy = "priority_only"
        else:
            # Balanced approach - ALWAYS start with priority_only
            speed_approach = "standard"
            url_count = min(target_count * 5, 25)
            search_strategy = "priority_only"  # Always start with priority sites, expand only at 20s+ threshold
        
        return {
            "speed_approach": speed_approach,
            "quality_approach": "high" if quality_emphasis else "balanced",  
            "accuracy_approach": "strict" if high_accuracy_need else "flexible",
            "url_count": url_count,
            "search_strategy": search_strategy,
            "user_priorities": {
                "speed_priority": speed_priority,
                "quality_emphasis": quality_emphasis, 
                "accuracy_critical": high_accuracy_need
            }
        }
    
    async def _parse_with_reactive_monitoring(self, recipe_urls: List, list_urls: List, user_query: str, target_count: int, strategy: Dict):
        """Parse recipes with reactive 20s/40s/60s checkpoints."""
        
        # Parse individual recipes first (priority sites)
        if recipe_urls:
            print(f"🍳 Parsing {len(recipe_urls)} recipe pages...")
            recipe_parse_result = await self.recipe_parsing_tool.parse_recipes(
                urls=recipe_urls,
                parsing_depth="standard",
                timeout_seconds=15  # Aggressive timeout for speed
            )
            
            self.current_recipes.extend(recipe_parse_result["parsed_recipes"])
            print(f"   ✅ Successfully parsed {len(recipe_parse_result['parsed_recipes'])} recipes")
        
        # 20-SECOND CHECKPOINT
        elapsed = time.time() - self.query_start_time
        if elapsed >= 20:
            await self._handle_20s_checkpoint(elapsed, target_count, strategy)
            if len(self.current_recipes) >= target_count:
                return  # User satisfied with current results
        
        # Process lists if needed and time allows
        if list_urls and len(self.current_recipes) < target_count and elapsed < 35:
            needed = target_count - len(self.current_recipes)
            print(f"📋 Extracting recipes from {len(list_urls)} collections (need {needed} more)...")
            
            list_extract_result = await self.list_parsing_tool.extract_recipe_urls_from_lists(
                urls=list_urls,
                max_recipes_per_list=max(needed // len(list_urls), 2)
            )
            
            extracted_urls = list_extract_result["extracted_recipe_urls"]
            if extracted_urls:
                print(f"   Found {len(extracted_urls)} additional recipe URLs")
                
                # 40-SECOND CHECKPOINT
                elapsed = time.time() - self.query_start_time
                if elapsed >= 40:
                    should_continue = await self._handle_40s_checkpoint(elapsed, user_query)
                    if not should_continue:
                        return
                
                print(f"🍳 Parsing {len(extracted_urls)} extracted recipes...")
                extracted_parse_result = await self.recipe_parsing_tool.parse_recipes(
                    urls=extracted_urls,
                    parsing_depth="quick",  # Faster parsing for extracted URLs
                    timeout_seconds=10
                )
                
                self.current_recipes.extend(extracted_parse_result["parsed_recipes"])
                print(f"   ✅ Parsed {len(extracted_parse_result['parsed_recipes'])} additional recipes")
        
        # Final time check
        elapsed = time.time() - self.query_start_time
        if elapsed >= 60:
            await self._handle_60s_finalization(elapsed)
    
    async def _handle_20s_checkpoint(self, elapsed: float, target_count: int, strategy: Dict):
        """Handle 20-second reactive checkpoint."""
        current_count = len(self.current_recipes)
        quality_count = len([r for r in self.current_recipes if self._is_high_quality_recipe(r)])
        
        print(f"\n⏰ 20-second checkpoint: Found {current_count} recipes ({quality_count} high-quality)")
        
        if current_count >= 2 and quality_count >= 1:
            print(f"📊 Good progress! Continuing search to find {target_count - current_count} more...")
        else:
            print(f"📈 Expanding search strategy for better results...")
            # Strategy will be used in next search iteration
    
    async def _handle_40s_checkpoint(self, elapsed: float, user_query: str) -> bool:
        """Handle 40-second critical checkpoint - get user guidance."""
        current_count = len(self.current_recipes)
        
        print(f"\n⏰ 40-second checkpoint: Found {current_count} recipes so far")
        
        if current_count >= 2:
            # Show preview of current best recipes
            top_recipes = self.current_recipes[:2] 
            print(f"\\n🍽️ Current best options:")
            for i, recipe in enumerate(top_recipes, 1):
                title = recipe.get('title', 'Unknown')[:50]
                domain = self._extract_domain(recipe.get('source_url', ''))
                print(f"   {i}. {title} (from {domain})")
            
            print(f"\\n❓ Should I present these {current_count} recipes now, or keep searching for more?")
            print(f"   (Continuing may take another 20-30 seconds)")
            
            # In a real agent, this would wait for user input
            # For testing, continue automatically but log the decision point
            print(f"   🤖 [Test mode: Continuing search for full target count]")
            return True
        else:
            print(f"   📈 Only found {current_count} recipes - continuing search...")
            return True
    
    async def _handle_60s_finalization(self, elapsed: float):
        """Handle 60+ second finalization - present best available."""
        current_count = len(self.current_recipes)
        print(f"\\n⏰ 60+ seconds elapsed ({elapsed:.1f}s) - presenting best {current_count} recipes found")
    
    def _is_high_quality_recipe(self, recipe: Dict) -> bool:
        """Quick quality assessment for reactive decisions."""
        domain = self._extract_domain(recipe.get('source_url', ''))
        has_image = bool(recipe.get('image_url'))
        ingredient_count = len(recipe.get('ingredients', []))
        
        return (domain in self.scorer.priority_sites and has_image and ingredient_count >= 5)
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url.lower())
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"
    
    async def _finalize_with_scoring(self, user_query: str, target_count: int) -> Dict:
        """Finalize results with performance scoring and session learning."""
        elapsed = time.time() - self.query_start_time
        final_recipes = self.current_recipes[:target_count]
        
        # Prepare result structure
        result = {
            "recipes": final_recipes,
            "total_found": len(final_recipes),
            "search_time": f"{elapsed:.1f} seconds",
            "agent_summary": f"Found {len(final_recipes)} recipes in {elapsed:.1f} seconds"
        }
        
        # Performance scoring
        overall_score = self.scorer.score_overall_search(user_query, result, elapsed, target_count)
        individual_scores = self.scorer.score_individual_recipes(final_recipes, user_query)
        
        # Session learning
        self.session_tracker.add_search_score(overall_score)
        
        # Add performance data to result
        result["performance"] = {
            "overall_score": {
                "speed": overall_score.speed,
                "quality": overall_score.quality,
                "accuracy": overall_score.accuracy,
                "overall": overall_score.overall,
                "grade": self._get_grade(overall_score.overall)
            },
            "individual_scores": [
                {
                    "domain": score.site_domain,
                    "quality": score.quality_score,
                    "accuracy": score.accuracy_score,
                    "completeness": score.completeness_score
                }
                for score in individual_scores
            ],
            "session_insights": self.session_tracker.get_session_insights()
        }
        
        # Update session state
        for recipe in final_recipes:
            self.session_shown_urls.add(recipe.get("source_url", ""))
        
        # Print performance summary
        self._print_performance_summary(overall_score)
        
        return result
    
    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 90: return "A"
        elif score >= 80: return "B"
        elif score >= 70: return "C"
        elif score >= 60: return "D"
        else: return "F"
    
    def _print_performance_summary(self, score):
        """Print performance summary for debugging."""
        print(f"\\n📊 PERFORMANCE: Speed: {score.speed}%, Quality: {score.quality}%, Accuracy: {score.accuracy}%")
        print(f"🏆 Overall Grade: {self._get_grade(score.overall)} ({score.overall}%)")
    
    def _handle_no_results(self, user_query: str) -> Dict:
        """Handle case when no URLs are found."""
        elapsed = time.time() - self.query_start_time
        return {
            "error": "No recipe URLs found", 
            "recipes": [],
            "search_time": f"{elapsed:.1f} seconds",
            "suggestion": "Try a broader search term or remove some constraints"
        }
    
    def _prepare_final_result(self, recipes: List[Dict]) -> Dict:
        """Legacy method - now handled by _finalize_with_scoring."""
        elapsed = time.time() - self.query_start_time
        
        return {
            "recipes": recipes,
            "total_found": len(recipes),
            "search_time": f"{elapsed:.1f} seconds",
            "agent_summary": f"Found {len(recipes)} high-quality recipes in {elapsed:.1f} seconds"
        }
    
    def print_recipe_details(self, recipe: Dict):
        """Print complete recipe details for user."""
        print("\n" + "="*80)
        print(f"🍽️ {recipe.get('title', 'Unknown Recipe')}")
        print("="*80)
        print(f"📸 Image: {recipe.get('image_url', 'No image')}")
        print(f"🔗 Source: {recipe.get('source_url', 'Unknown')}")
        print(f"⏰ Cook Time: {recipe.get('cook_time', 'Not specified')}")
        print(f"🍽️ Servings: {recipe.get('servings', 'Not specified')}")
        
        # Ingredients
        ingredients = recipe.get('ingredients', [])
        print(f"\n📝 Ingredients ({len(ingredients)} items):")
        for i, ingredient in enumerate(ingredients[:10], 1):  # Show first 10
            print(f"  {i}. {ingredient}")
        if len(ingredients) > 10:
            print(f"  ... and {len(ingredients) - 10} more ingredients")
        
        # Instructions
        instructions = recipe.get('instructions', [])
        print(f"\n👨‍🍳 Instructions ({len(instructions)} steps):")
        for i, instruction in enumerate(instructions[:5], 1):  # Show first 5 steps
            print(f"  {i}. {instruction}")
        if len(instructions) > 5:
            print(f"  ... and {len(instructions) - 5} more steps")
        
        # Nutrition  
        nutrition = recipe.get('nutrition', [])
        if nutrition:
            print(f"\n🥗 Nutrition:")
            for nutrient in nutrition[:4]:  # Show first 4
                print(f"  • {nutrient}")
        
        print("="*80)


# Agent testing function
async def test_agent_interaction(query: str, target_recipes: int = 4) -> Dict:
    """Test agent with a single query."""
    # Load API keys
    serpapi_key = os.getenv("SERPAPI_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")  
    google_key = os.getenv("GOOGLE_SEARCH_KEY")
    google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    if not serpapi_key or not openai_key:
        return {"error": "Missing API keys (SERPAPI_KEY or OPENAI_API_KEY)"}
    
    # Create agent
    agent = SimpleRecipeAgent(serpapi_key, openai_key, google_key, google_cx)
    
    # Execute search
    result = await agent.find_recipes(query, target_recipes)
    
    return result