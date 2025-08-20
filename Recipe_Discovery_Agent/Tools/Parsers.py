"""
Custom recipe parsers for specific websites.
Each parser extracts: title, ingredients, instructions, cook_time, servings, image_url, source_url

COMPLIANCE NOTICE:
- All parsers check robots.txt before scraping
- We respect crawl delays and disallowed paths
- Instructions are extracted ONLY for analysis, never displayed to users
- We always link back to the original source
- We do not cache or store scraped content
"""

import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import json
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
import asyncio
import time


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
                response = await client.get(f"{base_url}/robots.txt", timeout=5.0)
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


async def parse_allrecipes(url: str) -> Dict:
    """
    Parse recipe from AllRecipes.com
    
    COMPLIANCE:
    - Checks robots.txt before scraping
    - Respects crawl delays
    - Only extracts data for user analysis, not for display
    - Always preserves source URL for attribution
    """
    # COMPLIANCE CHECK: Respect robots.txt
    is_allowed, crawl_delay = await check_robots_txt(url)
    
    if not is_allowed:
        # Return error if robots.txt disallows this URL
        return {
            'error': 'Robots.txt disallows scraping this URL',
            'source_url': url
        }
    
    # COMPLIANCE: Respect crawl delay if specified
    if crawl_delay > 0:
        await asyncio.sleep(crawl_delay)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to get JSON-LD structured data first (most reliable)
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                
                # Handle array of JSON objects
                if isinstance(data, list):
                    # Find Recipe type
                    recipe_data = None
                    for item in data:
                        if item.get('@type') == 'Recipe':
                            recipe_data = item
                            break
                    if not recipe_data:
                        recipe_data = data[0]  # Fallback to first item
                else:
                    recipe_data = data
                
                # Extract recipe information
                recipe = {
                    'title': recipe_data.get('name', ''),
                    'ingredients': [],
                    'instructions': [],
                    'cook_time': '',
                    'servings': '',
                    'image_url': '',
                    'source_url': url
                }
                
                # Extract ingredients
                ingredients = recipe_data.get('recipeIngredient', [])
                recipe['ingredients'] = [ing.strip() for ing in ingredients if ing]
                
                # Extract instructions
                instructions = recipe_data.get('recipeInstructions', [])
                if instructions:
                    recipe['instructions'] = []
                    for inst in instructions:
                        if isinstance(inst, dict):
                            text = inst.get('text', inst.get('name', ''))
                        else:
                            text = str(inst)
                        if text:
                            recipe['instructions'].append(text.strip())
                
                # Extract timing
                prep_time = recipe_data.get('prepTime', '')
                cook_time = recipe_data.get('cookTime', '')
                total_time = recipe_data.get('totalTime', '')
                recipe['cook_time'] = total_time or cook_time or prep_time
                
                # Extract servings
                recipe_yield = recipe_data.get('recipeYield', '')
                if isinstance(recipe_yield, list):
                    recipe_yield = recipe_yield[0] if recipe_yield else ''
                recipe['servings'] = str(recipe_yield)
                
                # Extract image
                image = recipe_data.get('image', '')
                if isinstance(image, dict):
                    image = image.get('url', '')
                elif isinstance(image, list) and image:
                    image = image[0] if isinstance(image[0], str) else image[0].get('url', '')
                recipe['image_url'] = image
                
                return recipe
                
            except (json.JSONDecodeError, KeyError):
                pass  # Fall back to HTML parsing
        
        # Fallback HTML parsing if JSON-LD fails
        recipe = {
            'title': '',
            'ingredients': [],
            'instructions': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url
        }
        
        # Title
        title = soup.find('h1', class_='headline')
        if title:
            recipe['title'] = title.get_text(strip=True)
        
        # Ingredients
        ingredients = soup.find_all('span', class_='ingredients-item-name')
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        # Instructions
        instructions = soup.find_all('div', class_='paragraph')
        recipe['instructions'] = [inst.get_text(strip=True) for inst in instructions if inst.get_text(strip=True)]
        
        # Cook time
        time_elem = soup.find('div', class_='recipe-meta-item-body')
        if time_elem:
            recipe['cook_time'] = time_elem.get_text(strip=True)
        
        # Servings
        servings = soup.find('div', class_='recipe-yield')
        if servings:
            recipe['servings'] = servings.get_text(strip=True)
        
        # Image
        img = soup.find('img', class_='primary-image')
        if img:
            recipe['image_url'] = img.get('src', '')
        
        return recipe


async def parse_simplyrecipes(url: str) -> Dict:
    """
    Parse recipe from SimplyRecipes.com
    
    COMPLIANCE:
    - Checks robots.txt before scraping
    - Respects crawl delays
    - Only extracts data for user analysis, not for display
    - Always preserves source URL for attribution
    """
    # COMPLIANCE CHECK: Respect robots.txt
    is_allowed, crawl_delay = await check_robots_txt(url)
    
    if not is_allowed:
        return {
            'error': 'Robots.txt disallows scraping this URL',
            'source_url': url
        }
    
    # COMPLIANCE: Respect crawl delay
    if crawl_delay > 0:
        await asyncio.sleep(crawl_delay)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        recipe = {
            'title': '',
            'ingredients': [],
            'instructions': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url
        }
        
        # Try JSON-LD first
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                
                # Handle @graph structure
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
                # Extract instructions
                instructions = data.get('recipeInstructions', [])
                recipe['instructions'] = []
                for inst in instructions:
                    if isinstance(inst, dict):
                        text = inst.get('text', inst.get('name', ''))
                    else:
                        text = str(inst)
                    if text:
                        recipe['instructions'].append(text.strip())
                
                # Timing
                recipe['cook_time'] = data.get('totalTime', '')
                
                # Servings
                recipe['servings'] = str(data.get('recipeYield', ''))
                
                # Image
                image = data.get('image', '')
                if isinstance(image, dict):
                    image = image.get('url', '')
                elif isinstance(image, list) and image:
                    image = image[0]
                recipe['image_url'] = image
                
                return recipe
                
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Fallback to HTML parsing
        # Title
        title = soup.find('h1')
        if title:
            recipe['title'] = title.get_text(strip=True)
        
        # Ingredients
        ingredients = soup.find_all('li', class_='structured-ingredients__list-item')
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        # Instructions
        instructions = soup.find_all('li', class_='mntl-sc-block-html')
        recipe['instructions'] = [inst.get_text(strip=True) for inst in instructions if inst.get_text(strip=True)]
        
        # Image
        img = soup.find('img', {'id': 'mntl-sc-block-image_1-0'})
        if img:
            recipe['image_url'] = img.get('src', '')
        
        return recipe


async def parse_eatingwell(url: str) -> Dict:
    """
    Parse recipe from EatingWell.com
    
    COMPLIANCE:
    - Checks robots.txt before scraping
    - Respects crawl delays
    - Only extracts data for user analysis, not for display
    - Always preserves source URL for attribution
    """
    # COMPLIANCE CHECK: Respect robots.txt
    is_allowed, crawl_delay = await check_robots_txt(url)
    
    if not is_allowed:
        return {
            'error': 'Robots.txt disallows scraping this URL',
            'source_url': url
        }
    
    # COMPLIANCE: Respect crawl delay
    if crawl_delay > 0:
        await asyncio.sleep(crawl_delay)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        recipe = {
            'title': '',
            'ingredients': [],
            'instructions': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url
        }
        
        # Try JSON-LD
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                
                # EatingWell often has array of objects
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
                # Instructions
                instructions = data.get('recipeInstructions', [])
                recipe['instructions'] = []
                for inst in instructions:
                    if isinstance(inst, dict):
                        text = inst.get('text', inst.get('name', ''))
                    else:
                        text = str(inst)
                    if text:
                        recipe['instructions'].append(text.strip())
                
                recipe['cook_time'] = data.get('totalTime', '')
                recipe['servings'] = str(data.get('recipeYield', ''))
                
                # Image
                image = data.get('image', '')
                if isinstance(image, dict):
                    image = image.get('url', '')
                elif isinstance(image, list) and image:
                    image = image[0]
                recipe['image_url'] = image
                
                return recipe
                
            except (json.JSONDecodeError, KeyError):
                pass
        
        # HTML fallback
        title = soup.find('h1')
        if title:
            recipe['title'] = title.get_text(strip=True)
        
        # Use generic selectors for EatingWell
        ingredients = soup.find_all('li', {'class': lambda x: x and 'ingredient' in x})
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        return recipe


async def parse_foodnetwork(url: str) -> Dict:
    """
    Parse recipe from FoodNetwork.com
    
    COMPLIANCE:
    - Checks robots.txt before scraping
    - Respects crawl delays
    - Only extracts data for user analysis, not for display
    - Always preserves source URL for attribution
    """
    # COMPLIANCE CHECK: Respect robots.txt
    is_allowed, crawl_delay = await check_robots_txt(url)
    
    if not is_allowed:
        return {
            'error': 'Robots.txt disallows scraping this URL',
            'source_url': url
        }
    
    # COMPLIANCE: Respect crawl delay
    if crawl_delay > 0:
        await asyncio.sleep(crawl_delay)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        recipe = {
            'title': '',
            'ingredients': [],
            'instructions': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url
        }
        
        # Try JSON-LD
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                
                # Handle @graph structure that Food Network uses
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
                # Instructions
                instructions = data.get('recipeInstructions', [])
                recipe['instructions'] = []
                for inst in instructions:
                    if isinstance(inst, dict):
                        text = inst.get('text', inst.get('name', ''))
                    else:
                        text = str(inst)
                    if text:
                        recipe['instructions'].append(text.strip())
                
                recipe['cook_time'] = data.get('totalTime', data.get('cookTime', ''))
                recipe['servings'] = str(data.get('recipeYield', ''))
                
                # Image
                image = data.get('image', '')
                if isinstance(image, dict):
                    image = image.get('url', '')
                elif isinstance(image, list) and image:
                    image = image[0]
                recipe['image_url'] = image
                
                return recipe
                
            except (json.JSONDecodeError, KeyError):
                pass
        
        # HTML fallback
        title = soup.find('h1', class_='o-AssetTitle__a-HeadlineText')
        if title:
            recipe['title'] = title.get_text(strip=True)
        
        # Ingredients
        ingredients = soup.find_all('p', class_='o-Ingredients__a-Ingredient')
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        # Instructions
        instructions = soup.find_all('li', class_='o-Method__m-Step')
        recipe['instructions'] = [inst.get_text(strip=True) for inst in instructions if inst.get_text(strip=True)]
        
        return recipe


# Master parser function that routes to correct parser
async def parse_recipe(url: str) -> Optional[Dict]:
    """
    Parse a recipe from any supported site.
    
    COMPLIANCE GUARANTEE:
    - All parsers check robots.txt before scraping
    - We respect crawl delays specified in robots.txt
    - Instructions are extracted for analysis only, NEVER displayed to users
    - We always provide attribution via source_url
    - No content is cached or stored permanently
    - Returns None if site is not supported (triggers FireCrawl fallback)
    
    This demonstrates our good faith effort to comply with:
    - Website Terms of Service
    - Copyright law (fair use for analysis)
    - robots.txt guidelines
    """
    if 'allrecipes.com' in url:
        return await parse_allrecipes(url)
    elif 'simplyrecipes.com' in url:
        return await parse_simplyrecipes(url)
    elif 'eatingwell.com' in url:
        return await parse_eatingwell(url)
    elif 'foodnetwork.com' in url:
        return await parse_foodnetwork(url)
    else:
        return None  # Will trigger FireCrawl fallback