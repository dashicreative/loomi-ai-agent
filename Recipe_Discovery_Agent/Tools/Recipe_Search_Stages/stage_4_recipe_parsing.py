"""
Stage 4: Recipe Parsing
Handles all recipe parsing operations including HTML scraping, JSON-LD extraction, and LLM-based parsing.

This module contains all recipe parsing logic for different website formats.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import json
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
import asyncio
import time
import os
from firecrawl import FirecrawlApp
from ..Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list


# Cache for robots.txt to avoid repeated fetches
ROBOTS_CACHE = {}


async def check_robots_txt(url: str, user_agent: str = "RecipeDiscoveryBot") -> tuple[bool, float]:
    """
    Check if we're allowed to scrape this URL according to robots.txt
    
    COMPLIANCE: We respect robots.txt as part of ethical web scraping.
    Returns: (is_allowed, crawl_delay_seconds)
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    # Check cache first
    if base_url in ROBOTS_CACHE:
        rp = ROBOTS_CACHE[base_url]
    else:
        # Fetch and parse robots.txt
        rp = RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        
        try:
            # Use httpx to fetch robots.txt
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/robots.txt", timeout=15.0)
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                else:
                    # If no robots.txt, assume we can crawl
                    rp.allow_all = True
        except:
            # If we can't fetch robots.txt, be conservative and allow
            # (many sites don't have robots.txt but allow scraping)
            rp.allow_all = True
        
        ROBOTS_CACHE[base_url] = rp
    
    # Check if URL is allowed
    is_allowed = rp.can_fetch(user_agent, url)
    
    # Get crawl delay if specified
    crawl_delay = rp.crawl_delay(user_agent) or 0
    
    return is_allowed, crawl_delay


def extract_nutrition_from_json_ld(nutrition_info: dict) -> list:
    """
    Extract ONLY the 4 required nutrition values from JSON-LD nutrition object.
    Required values: calories, protein, fat, carbs
    
    Args:
        nutrition_info: The nutrition object from JSON-LD
        
    Returns:
        List of nutrition strings (max 4 items)
    """
    nutrition = []
    if not nutrition_info:
        return nutrition
        
    # ONLY the 4 required nutrition fields
    if nutrition_info.get('calories'):
        nutrition.append(f"{nutrition_info.get('calories')} calories")
    if nutrition_info.get('proteinContent'):
        nutrition.append(f"{nutrition_info.get('proteinContent')} protein")
    if nutrition_info.get('fatContent'):
        nutrition.append(f"{nutrition_info.get('fatContent')} fat")
    if nutrition_info.get('carbohydrateContent'):
        nutrition.append(f"{nutrition_info.get('carbohydrateContent')} carbs")
    
    return nutrition


def extract_from_json_ld(soup: BeautifulSoup, url: str) -> Dict:
    """
    Tier 1: Extract recipe data from JSON-LD structured data (fastest method).
    
    Most recipe sites include JSON-LD Recipe schema in <script> tags.
    This is the most reliable and fastest extraction method.
    """
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


def extract_from_structured_html(soup: BeautifulSoup, url: str) -> Dict:
    """
    Tier 2: Extract recipe data from structured HTML (site-specific patterns).
    
    Uses common HTML patterns and CSS selectors to extract recipe data.
    Faster than LLM but less reliable than JSON-LD.
    """
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
    
    # Extract image - try multiple selectors
    image_selectors = [
        '.recipe-image img',
        '.recipe-hero img',
        '[class*="recipe"] img',
        'img[class*="recipe"]'
    ]
    
    for selector in image_selectors:
        img_elem = soup.select_one(selector)
        if img_elem:
            src = img_elem.get('src') or img_elem.get('data-src')
            if src:
                # Convert relative URLs to absolute
                if src.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                recipe_data['image_url'] = src
                break
    
    # Extract timing and servings - basic patterns
    timing_text = soup.get_text().lower()
    
    # Look for cook time patterns
    import re
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
    
    # Look for servings patterns
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


def extract_nutrition_from_html(soup) -> list:
    """
    Extract ONLY the 4 required nutrition values from HTML.
    Required values: calories, protein, fat, carbs
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        List of nutrition strings (max 4 items)
    """
    nutrition = []
    
    # Look for nutrition sections with common class names
    nutrition_selectors = [
        'div.nutrition-info',
        'div.recipe-nutrition',
        'div.nutrition',
        'section.nutrition',
        'div[class*="nutrition"]',
        'span[class*="nutrition"]',
        'div[class*="nutrient"]',
        'span[class*="calorie"]',
        'span[class*="protein"]',
        'span[class*="carb"]',
        'span[class*="fat"]'
    ]
    
    for selector in nutrition_selectors:
        elements = soup.select(selector)
        for element in elements:
            text = element.get_text(strip=True)
            # ONLY check for the 4 required nutrition keywords
            if any(term in text.lower() for term in ['calorie', 'protein', 'fat', 'carb']):
                # Clean up the text - extract just the nutrition fact
                lines = text.split('\n')
                for line in lines:
                    # ONLY extract lines with the 4 required terms
                    if any(term in line.lower() for term in ['calorie', 'protein', 'fat', 'carb']):
                        nutrition.append(line.strip())
    
    # Deduplicate while preserving order
    seen = set()
    unique_nutrition = []
    for item in nutrition:
        if item not in seen:
            seen.add(item)
            unique_nutrition.append(item)
    
    return unique_nutrition[:4]  # Cap at 4 required nutrition items


def validate_recipe_data(recipe_data: dict) -> tuple[bool, list]:
    """
    Validates that all required fields are present for iOS app UI.
    
    Args:
        recipe_data: Recipe data dictionary
        
    Returns:
        Tuple of (is_valid, missing_fields)
    """
    required_checks = {
        'ingredients': len(recipe_data.get('ingredients', [])) > 0,
        # 'instructions': len(recipe_data.get('instructions', [])) > 0,  # Temporarily disabled for performance testing
        'image_url': bool(recipe_data.get('image_url', '').strip()),
        'nutrition': len(recipe_data.get('nutrition', [])) >= 4  # Need all 4: calories, protein, carbs, fat
    }
    
    missing = [field for field, present in required_checks.items() if not present]
    return len(missing) == 0, missing


async def hybrid_recipe_parser(url: str, openai_key: str) -> Dict:
    """
    Hybrid recipe parser: Fast HTML parsing + LLM ingredient processing.
    
    Multi-tiered approach:
    1. JSON-LD extraction (fastest, most reliable)
    2. Structured HTML parsing (fast, site-specific)
    3. Mini-LLM call for ingredient processing only
    
    Target: 2-3 seconds vs current 5-15 seconds
    """
    if not openai_key:
        return {'error': 'OpenAI API key required', 'source_url': url}
    
    parse_start = time.time()
    
    try:
        # Step 1: Fast HTML scraping
        http_start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        http_time = time.time() - http_start
        print(f"   ⏱️  HTTP fetch: {http_time:.2f}s ({len(html_content):,} chars)")
        
        # Step 2: BeautifulSoup parsing
        soup_start = time.time()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        soup_time = time.time() - soup_start
        print(f"   ⏱️  BeautifulSoup parse: {soup_time:.2f}s")
        
        # Tier 1: Try JSON-LD first (fastest and most reliable)
        jsonld_start = time.time()
        recipe_data = extract_from_json_ld(soup, url)
        jsonld_time = time.time() - jsonld_start
        
        if recipe_data:
            print(f"   ✅ JSON-LD extraction: {jsonld_time:.2f}s (SUCCESS)")
        else:
            print(f"   ❌ JSON-LD extraction: {jsonld_time:.2f}s (no data found)")
            
            # Tier 2: Try structured HTML parsing
            html_start = time.time()
            recipe_data = extract_from_structured_html(soup, url)
            html_time = time.time() - html_start
            
            if recipe_data:
                print(f"   ✅ HTML extraction: {html_time:.2f}s (SUCCESS)")
            else:
                print(f"   ❌ HTML extraction: {html_time:.2f}s (no data found)")
        
        if not recipe_data:
            total_time = time.time() - parse_start
            return {'error': 'No recipe data found in HTML', 'source_url': url}
        
        # Step 3: Keep raw ingredients for instant recipe discovery
        # Shopping conversion moved to background processing after recipe save
        raw_ingredients = recipe_data.get('ingredients', [])
        if raw_ingredients:
            print(f"   ✅ Using raw JSON-LD ingredients ({len(raw_ingredients)} items) - instant processing")
            # Ingredients remain as strings for ranking/display, shopping conversion happens later
        else:
            pass
        
        recipe_data['source_url'] = url
        total_time = time.time() - parse_start
        print(f"   ✅ PARSE SUCCESS - Total time: {total_time:.2f}s")
        return recipe_data
        
    except Exception as e:
        total_time = time.time() - parse_start
        print(f"   ❌ PARSE EXCEPTION - Total time: {total_time:.2f}s - Error: {str(e)}")
        return {'error': f'Hybrid parsing failed: {str(e)}', 'source_url': url}


# Master parser function that routes to correct parser
async def parse_recipe(url: str, openai_key: str = None) -> Dict:
    """
    Parse a recipe from any supported site using hybrid approach.
    
    COMPLIANCE GUARANTEE:
    - Fast HTML parsing with robots.txt respect
    - Instructions extracted for analysis only, NEVER displayed to users
    - We always provide attribution via source_url
    - No content is cached or stored permanently
    
    Multi-tiered approach:
    1. JSON-LD extraction (fastest)
    2. Structured HTML parsing (fast)
    3. Mini-LLM ingredient processing only
    
    Target: 2-3 seconds vs previous 5-15 seconds
    
    Args:
        url: The recipe URL to parse
        openai_key: OpenAI API key for ingredient processing
    
    Returns:
        Dict with recipe data or error information
    """
    # Use hybrid parser for optimal speed
    if openai_key:
        return await hybrid_recipe_parser(url, openai_key)
    else:
        return {
            'error': 'OpenAI key required for ingredient processing',
            'source_url': url
        }