"""
RecipeParsingTool - Individual Recipe Page Parsing
Exact copy of hybrid_recipe_parser logic for parsing individual recipe URLs.
"""

import asyncio
import httpx
import time
import json
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import logfire

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from shared_tools.nutrition_formatter import extract_nutrition_from_json_ld, extract_nutrition_from_html


def extract_from_json_ld(soup: BeautifulSoup, url: str) -> Optional[Dict]:
    """EXACT COPY of extract_from_json_ld from structured_extractor.py"""
    json_scripts = soup.find_all('script', type='application/ld+json')
    
    for script in json_scripts:
        try:
            data = json.loads(script.string)
            
            # Handle both single objects and arrays
            if isinstance(data, list):
                items = data
            else:
                items = [data]
            
            for item in items:
                # Look for Recipe type
                if item.get('@type') == 'Recipe' or (isinstance(item.get('@type'), list) and 'Recipe' in item.get('@type')):
                    recipe_data = {
                        'title': item.get('name', ''),
                        'ingredients': [],
                        'instructions': [],
                        'nutrition': [],
                        'cook_time': '',
                        'prep_time': '',
                        'servings': '',
                        'image_url': ''
                    }
                    
                    # Extract ingredients
                    recipe_ingredients = item.get('recipeIngredient', [])
                    if recipe_ingredients:
                        recipe_data['ingredients'] = recipe_ingredients
                    
                    # Extract instructions  
                    instructions = item.get('recipeInstructions', [])
                    instruction_text = []
                    for instruction in instructions:
                        if isinstance(instruction, dict):
                            text = instruction.get('text', '')
                            if text:
                                instruction_text.append(text)
                        elif isinstance(instruction, str):
                            instruction_text.append(instruction)
                    recipe_data['instructions'] = instruction_text
                    
                    # Extract nutrition
                    nutrition_info = item.get('nutrition')
                    if nutrition_info:
                        recipe_data['nutrition'] = extract_nutrition_from_json_ld(nutrition_info)
                    
                    # Extract timing
                    if item.get('cookTime'):
                        recipe_data['cook_time'] = item.get('cookTime')
                    if item.get('prepTime'):
                        recipe_data['prep_time'] = item.get('prepTime')
                    if item.get('totalTime'):
                        recipe_data['cook_time'] = item.get('totalTime')
                    
                    # Extract servings
                    yield_val = item.get('recipeYield') or item.get('yield')
                    if yield_val:
                        if isinstance(yield_val, list):
                            recipe_data['servings'] = str(yield_val[0])
                        else:
                            recipe_data['servings'] = str(yield_val)
                    
                    # Extract image
                    image = item.get('image')
                    if image:
                        if isinstance(image, list) and image:
                            image = image[0]
                        if isinstance(image, dict):
                            recipe_data['image_url'] = image.get('url', '')
                        elif isinstance(image, str):
                            recipe_data['image_url'] = image
                    
                    # Only return if we have minimum required data
                    if recipe_data['title'] and recipe_data['ingredients']:
                        return recipe_data
                        
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return None


def extract_from_structured_html(soup: BeautifulSoup, url: str) -> Optional[Dict]:
    """EXACT COPY of extract_from_structured_html from structured_extractor.py"""
    recipe_data = {
        'title': '',
        'ingredients': [],
        'instructions': [],
        'nutrition': [],
        'cook_time': '',
        'prep_time': '',
        'servings': '',
        'image_url': ''
    }
    
    # Extract title - try multiple selectors
    title_selectors = [
        'h1.recipe-title',
        'h1[class*="recipe"]',
        'h1[class*="title"]',
        '.recipe-header h1',
        '.recipe-title',
        'h1'
    ]
    
    for selector in title_selectors:
        title_elem = soup.select_one(selector)
        if title_elem:
            recipe_data['title'] = title_elem.get_text(strip=True)
            break
    
    # Extract ingredients - try multiple selectors
    ingredient_selectors = [
        '.recipe-ingredients li',
        '.ingredients li',
        '[class*="ingredient"] li',
        '.recipe-ingredient',
        '[itemprop="recipeIngredient"]'
    ]
    
    for selector in ingredient_selectors:
        ingredients = soup.select(selector)
        if ingredients:
            recipe_data['ingredients'] = [ing.get_text(strip=True) for ing in ingredients if ing.get_text(strip=True)]
            break
    
    # Extract instructions - try multiple selectors  
    instruction_selectors = [
        '.recipe-instructions li',
        '.instructions li', 
        '.recipe-method li',
        '[class*="instruction"] li',
        '[itemprop="recipeInstructions"]'
    ]
    
    for selector in instruction_selectors:
        instructions = soup.select(selector)
        if instructions:
            recipe_data['instructions'] = [inst.get_text(strip=True) for inst in instructions if inst.get_text(strip=True)]
            break
    
    # Extract nutrition using existing function
    recipe_data['nutrition'] = extract_nutrition_from_html(soup)
    
    # Extract image with validation
    def is_valid_recipe_image(src_url: str, img_elem) -> bool:
        if not src_url:
            return False
        if '.svg' in src_url.lower() or 'icon' in src_url.lower():
            return False
        reject_keywords = ['arrow', 'button', 'nav', 'menu', 'logo', 'social', 'pinterest', 'facebook']
        if any(keyword in src_url.lower() for keyword in reject_keywords):
            return False
        return True
    
    # Try to find recipe image
    hero_selectors = [
        'meta[property="og:image"]',
        '.recipe-hero img',
        '.recipe-image img',
        'img[class*="hero"]'
    ]
    
    for selector in hero_selectors:
        if 'meta[property="og:image"]' in selector:
            meta_elem = soup.select_one(selector)
            if meta_elem:
                src = meta_elem.get('content')
                if src and is_valid_recipe_image(src, meta_elem):
                    if src.startswith('/'):
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    recipe_data['image_url'] = src
                    break
        else:
            img_elem = soup.select_one(selector)
            if img_elem:
                src = img_elem.get('src') or img_elem.get('data-src')
                if src and is_valid_recipe_image(src, img_elem):
                    if src.startswith('/'):
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    recipe_data['image_url'] = src
                    break
    
    # Extract timing and servings
    timing_text = soup.get_text().lower()
    
    # Cook time patterns
    cook_patterns = [
        r'cook time:?\s*(\d+(?:-\d+)?\s*(?:minutes?|mins?|hours?|hrs?))',
        r'cooking:?\s*(\d+(?:-\d+)?\s*(?:minutes?|mins?|hours?|hrs?))',
        r'total time:?\s*(\d+(?:-\d+)?\s*(?:minutes?|mins?|hours?|hrs?))'
    ]
    
    for pattern in cook_patterns:
        match = re.search(pattern, timing_text)
        if match:
            recipe_data['cook_time'] = match.group(1)
            break
    
    # Servings patterns
    serving_patterns = [
        r'serves:?\s*(\d+(?:-\d+)?)',
        r'servings:?\s*(\d+(?:-\d+)?)',
        r'yield:?\s*(\d+(?:-\d+)?)'
    ]
    
    for pattern in serving_patterns:
        match = re.search(pattern, timing_text)
        if match:
            recipe_data['servings'] = match.group(1)
            break
    
    # Only return if we have minimum required data
    if recipe_data['title'] and recipe_data['ingredients']:
        return recipe_data
    
    return None


def normalize_nutrition_data(recipe_data: Dict) -> Dict:
    """Normalize nutrition data to unified format (passthrough for now)."""
    return recipe_data


class RecipeParsingTool:
    """
    Individual recipe parsing tool.
    Exact copy of hybrid_recipe_parser logic with multiple URL support.
    """
    
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
        self.query_start_time = None
    
    async def parse_recipes(
        self, 
        urls: List[Dict],  # Enriched URL objects from classification
        parsing_depth: str = "standard",  # "quick|standard|thorough"
        timeout_seconds: int = 25
    ) -> Dict:
        """
        Parse multiple individual recipe URLs in parallel.
        EXACT COPY of Stage 4 recipe parsing logic from batch_processor.py
        
        Args:
            urls: List of enriched URL objects (must have type='recipe')
            parsing_depth: Parsing timeout/depth control
            timeout_seconds: Timeout per URL (5-30 seconds)
            
        Returns:
            Dict with parsed recipes and failure information
        """
        if not self.query_start_time:
            self.query_start_time = time.time()
        
        start_time = time.time()
        
        if not urls:
            return self._empty_result()
        
        # Filter to only recipe URLs (ignore list URLs)
        recipe_urls = [url_obj for url_obj in urls if url_obj.get('type') == 'recipe']
        
        if not recipe_urls:
            return {
                "parsed_recipes": [],
                "failed_urls": [],
                "skipped_urls": urls,  # All were non-recipe URLs
                "parse_quality": "none",
                "processing_stats": {
                    "total_attempted": 0,
                    "successful_parses": 0,
                    "failed_parses": 0,
                    "timeouts": 0
                },
                "_timing": self._get_timing_info(time.time() - self.query_start_time, len(urls))
            }
        
        print(f"🍳 Parsing {len(recipe_urls)} individual recipe URLs...")
        
        # EXACT COPY: Create tasks for parallel processing
        parsing_tasks = []
        result_mapping = []
        successful_parses = []
        failed_parses = []
        timeout_count = 0

        for url_obj in recipe_urls:
            url = url_obj.get("url")
            if url:
                # EXACT COPY: Wrap with timeout (from batch_processor.py line 406)
                task = asyncio.wait_for(
                    self._parse_single_recipe(url, url_obj), 
                    timeout=float(timeout_seconds)
                )
                parsing_tasks.append(task)
                result_mapping.append(url_obj)

        # EXACT COPY: Execute all parsing in parallel  
        if parsing_tasks:
            parsed_data = await asyncio.gather(*parsing_tasks, return_exceptions=True)
            
            # EXACT COPY: Process results (from batch_processor.py lines 415-448)
            for i, data in enumerate(parsed_data):
                url_obj = result_mapping[i]
                url = url_obj.get("url")
                
                if isinstance(data, asyncio.TimeoutError):
                    # Track timeout
                    timeout_count += 1
                    failed_parses.append({
                        "url_object": url_obj,
                        "error": f"Parsing timeout after {timeout_seconds}s",
                        "failure_point": "Recipe_Parsing_Timeout"
                    })
                elif isinstance(data, Exception):
                    # Track other exceptions
                    error_str = str(data)
                    if "403" in error_str or "Forbidden" in error_str:
                        # Expected for sites that block crawling
                        pass
                    failed_parses.append({
                        "url_object": url_obj,
                        "error": str(data),
                        "failure_point": "Recipe_Parsing_Exception"
                    })
                elif isinstance(data, dict) and not data.get("error"):
                    # EXACT COPY: Add search metadata (lines 436-441)
                    data["search_title"] = url_obj.get("title", "")
                    data["search_snippet"] = url_obj.get("snippet", "")
                    # Normalize nutrition data to unified format
                    data = normalize_nutrition_data(data)
                    successful_parses.append(data)
                else:
                    # Track failed parse
                    failed_parses.append({
                        "url_object": url_obj,
                        "error": data.get("error", "Unknown error") if isinstance(data, dict) else str(data),
                        "failure_point": "Recipe_Parsing_Failure_Point"
                    })
        
        # Calculate timing and quality assessment
        elapsed = time.time() - self.query_start_time
        parse_quality = self._assess_parse_quality(successful_parses, failed_parses, timeout_count)
        
        return {
            "parsed_recipes": successful_parses,
            "failed_urls": failed_parses,
            "parse_quality": parse_quality,
            "processing_stats": {
                "total_attempted": len(recipe_urls),
                "successful_parses": len(successful_parses),
                "failed_parses": len(failed_parses),
                "timeouts": timeout_count,
                "success_rate": round(len(successful_parses) / len(recipe_urls), 2) if recipe_urls else 0
            },
            "_timing": self._get_timing_info(elapsed, len(recipe_urls))
        }
    
    async def _parse_single_recipe(self, url: str, url_obj: Dict) -> Dict:
        """
        EXACT COPY of hybrid_recipe_parser function.
        Parse individual recipe URL using multi-tiered approach.
        """
        parse_start = time.time()
        
        try:
            # Step 1: Fast HTML scraping (EXACT COPY)
            http_start = time.time()
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                html_content = response.text
            http_time = time.time() - http_start
            
            # Step 2: BeautifulSoup parsing (EXACT COPY)
            soup_start = time.time()
            soup = BeautifulSoup(html_content, 'html.parser')
            soup_time = time.time() - soup_start
            
            # Tier 1: Try JSON-LD first (fastest and most reliable) (EXACT COPY)
            jsonld_start = time.time()
            recipe_data = extract_from_json_ld(soup, url)
            jsonld_time = time.time() - jsonld_start
            
            extraction_method = None
            if recipe_data:
                extraction_method = "json_ld"
            else:
                # Tier 2: Try structured HTML parsing (EXACT COPY)
                html_start = time.time()
                recipe_data = extract_from_structured_html(soup, url)
                html_time = time.time() - html_start
                
                if recipe_data:
                    extraction_method = "structured_html"
            
            if not recipe_data:
                total_time = time.time() - parse_start
                return {'error': 'No recipe data found in HTML', 'source_url': url}
            
            # Step 3: Keep raw ingredients (EXACT COPY)
            raw_ingredients = recipe_data.get('ingredients', [])
            
            recipe_data['source_url'] = url
            total_time = time.time() - parse_start
            
            # Only log if parsing took unusually long (EXACT COPY)
            if total_time > 5.0:
                logfire.warn("slow_recipe_parse",
                             url=url,
                             total_time=total_time,
                             extraction_method=extraction_method)
            return recipe_data
            
        except Exception as e:
            total_time = time.time() - parse_start
            # Downgrade 403 Forbidden to warning (EXACT COPY)
            if "403" in str(e) or "Forbidden" in str(e):
                logfire.warn("site_blocks_crawling",
                             url=url,
                             total_time=total_time,
                             error=str(e))
            else:
                logfire.error("recipe_parse_exception",
                              url=url,
                              total_time=total_time,
                              error=str(e))
            return {'error': f'Hybrid parsing failed: {str(e)}', 'source_url': url}
    
    def _assess_parse_quality(self, successful: List, failed: List, timeouts: int) -> str:
        """Assess overall parsing quality."""
        total = len(successful) + len(failed)
        if total == 0:
            return "none"
        
        success_rate = len(successful) / total
        if success_rate >= 0.8:
            return "excellent"
        elif success_rate >= 0.6:
            return "good"
        elif success_rate >= 0.4:
            return "acceptable"
        else:
            return "poor"
    
    def _get_timing_info(self, elapsed: float, url_count: int) -> Dict:
        """Generate timing information."""
        return {
            "elapsed_since_query": round(elapsed, 1),
            "elapsed_readable": f"{int(elapsed)} seconds",
            "time_status": self._get_time_status(elapsed),
            "recommended_action": self._get_recommended_action(elapsed, url_count),
            "urls_per_second": round(url_count / elapsed, 1) if elapsed > 0 else 0
        }
    
    def _get_time_status(self, elapsed: float) -> str:
        """Time status assessment."""
        if elapsed > 60:
            return "exceeded"
        elif elapsed > 30:
            return "approaching_limit"
        else:
            return "on_track"
    
    def _get_recommended_action(self, elapsed: float, url_count: int) -> str:
        """Recommended action based on timing."""
        if elapsed > 60:
            return "ask_user"
        elif elapsed > 30 and url_count < 3:
            return "pivot"
        else:
            return "continue"
    
    def _empty_result(self) -> Dict:
        """Empty result structure."""
        return {
            "parsed_recipes": [],
            "failed_urls": [],
            "parse_quality": "none",
            "processing_stats": {
                "total_attempted": 0,
                "successful_parses": 0,
                "failed_parses": 0,
                "timeouts": 0,
                "success_rate": 0.0
            },
            "_timing": {
                "elapsed_since_query": 0.0,
                "elapsed_readable": "0 seconds",
                "time_status": "on_track",
                "recommended_action": "continue",
                "urls_per_second": 0.0
            }
        }


# Agent integration function
async def execute_recipe_parsing_tool(context: Dict) -> Dict:
    """Agent-callable wrapper for RecipeParsingTool."""
    input_params = context.get("input", {})
    deps = context.get("deps", {})
    
    # Initialize tool
    tool = RecipeParsingTool(openai_key=deps.get("openai_key"))
    
    # Execute parsing
    return await tool.parse_recipes(
        urls=input_params.get("urls", []),
        parsing_depth=input_params.get("parsing_depth", "standard"),
        timeout_seconds=input_params.get("timeout_seconds", 25)
    )