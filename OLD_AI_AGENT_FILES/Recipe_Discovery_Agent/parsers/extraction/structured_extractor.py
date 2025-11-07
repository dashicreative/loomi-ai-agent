"""
Structured data extraction from HTML pages.

This module handles extraction of recipe data from both JSON-LD structured data
and HTML elements using CSS selectors.
"""

import json
import re
from bs4 import BeautifulSoup
from typing import Dict, Optional
from urllib.parse import urlparse


def extract_from_json_ld(soup: BeautifulSoup, url: str) -> Optional[Dict]:
    """
    Tier 1: Extract recipe data from JSON-LD structured data (fastest method).
    
    Most recipe sites include JSON-LD Recipe schema in <script> tags.
    This is the most reliable and fastest extraction method.
    
    Args:
        soup: BeautifulSoup parsed HTML
        url: Recipe URL for context
        
    Returns:
        Dict with recipe data or None if not found
    """
    from ..formatting.nutrition_formatter import extract_nutrition_from_json_ld
    
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
    """
    Tier 2: Extract recipe data from structured HTML (site-specific patterns).
    
    Uses common HTML patterns and CSS selectors to extract recipe data.
    Faster than LLM but less reliable than JSON-LD.
    
    Args:
        soup: BeautifulSoup parsed HTML
        url: Recipe URL for context
        
    Returns:
        Dict with recipe data or None if not found
    """
    from ..formatting.nutrition_formatter import extract_nutrition_from_html
    
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
    
    # Extract image with improved selectors and validation
    def is_valid_recipe_image(src_url: str, img_elem) -> bool:
        """Validate if image is appropriate for recipe display."""
        if not src_url:
            return False
            
        # Reject SVG icons and UI elements
        if '.svg' in src_url.lower() or 'icon' in src_url.lower():
            return False
            
        # Reject clearly non-food images
        reject_keywords = ['arrow', 'button', 'nav', 'menu', 'logo', 'social', 'pinterest', 'facebook']
        if any(keyword in src_url.lower() for keyword in reject_keywords):
            return False
            
        # Check image dimensions if available
        width = img_elem.get('width')
        height = img_elem.get('height')
        if width and height:
            try:
                w, h = int(width), int(height)
                # Reject very small images (likely icons)
                if w < 100 or h < 100:
                    return False
            except (ValueError, TypeError):
                pass
                
        return True
    
    # Priority selectors for main recipe images
    hero_selectors = [
        'meta[property="og:image"]',  # Open Graph image (most reliable)
        '.recipe-hero img[src*="1200"]',  # Large hero images
        '.recipe-hero img[src*="750"]',   # Medium hero images  
        '.recipe-image img[src*="1200"]',
        '.recipe-image img[src*="750"]',
        'img[class*="hero"][src*="1200"]',
        'img[class*="hero"][src*="750"]',
    ]
    
    # Try Open Graph and large images first
    for selector in hero_selectors:
        if 'meta[property="og:image"]' in selector:
            meta_elem = soup.select_one(selector)
            if meta_elem:
                src = meta_elem.get('content')
                if src and is_valid_recipe_image(src, meta_elem):
                    # Convert relative URLs to absolute
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
                    # Convert relative URLs to absolute
                    if src.startswith('/'):
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    recipe_data['image_url'] = src
                    break
    
    # Fallback: try to find any large image if hero search failed
    if not recipe_data.get('image_url'):
        all_images = soup.find_all('img')
        for img in all_images:
            src = img.get('src') or img.get('data-src')
            if src and is_valid_recipe_image(src, img):
                # Prioritize images with food-related keywords or large sizes
                src_lower = src.lower()
                if any(food_word in src_lower for food_word in ['recipe', 'food', 'cook', 'dish', 'meal']):
                    # Convert relative URLs to absolute
                    if src.startswith('/'):
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    recipe_data['image_url'] = src
                    break
    
    # Extract timing and servings - basic patterns
    timing_text = soup.get_text().lower()
    
    # Look for cook time patterns
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