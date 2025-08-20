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
from firecrawl import FirecrawlApp


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
                
                # FIX: Handle both list and dict JSON-LD structures
                if isinstance(data, list):
                    # Find Recipe type in list
                    recipe_data = None
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
                            recipe_data = item
                            break
                    if recipe_data:
                        data = recipe_data
                    else:
                        data = data[0] if data else {}
                elif isinstance(data, dict) and '@graph' in data:
                    # Handle @graph structure
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
                
                # FIX: EatingWell often has array of objects - ensure safe access
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
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
                
                # FIX: Handle both list and dict JSON-LD structures for Food Network
                if isinstance(data, list):
                    # Find Recipe type in list
                    recipe_data = None
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
                            recipe_data = item
                            break
                    if recipe_data:
                        data = recipe_data
                    else:
                        data = data[0] if data else {}
                elif isinstance(data, dict) and '@graph' in data:
                    # Handle @graph structure that Food Network uses
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
async def parse_delish(url: str) -> Dict:
    """
    Parse recipe from Delish.com
    
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
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        return recipe
async def parse_seriouseats(url: str) -> Dict:
    """
    Parse recipe from SeriousEats.com
    
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
                
                # FIX: Handle both list and dict JSON-LD structures
                if isinstance(data, list):
                    # Find Recipe type in list
                    recipe_data = None
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
                            recipe_data = item
                            break
                    if recipe_data:
                        data = recipe_data
                    else:
                        data = data[0] if data else {}
                elif isinstance(data, dict) and '@graph' in data:
                    # Handle @graph structure
                    for item in data['@graph']:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        # Serious Eats specific selectors
        ingredients = soup.find_all('li', class_='ingredient')
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        return recipe
async def parse_foodandwine(url: str) -> Dict:
    """
    Parse recipe from FoodAndWine.com
    
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
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        return recipe
async def parse_thepioneerwoman(url: str) -> Dict:
    """
    Parse recipe from ThePioneerWoman.com
    
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
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        return recipe
async def parse_food_com(url: str) -> Dict:
    """
    Parse recipe from Food.com
    
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
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        return recipe
async def parse_epicurious(url: str) -> Dict:
    """
    Parse recipe from Epicurious.com
    
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
                
                # FIX: Handle both list and dict JSON-LD structures for Epicurious
                if isinstance(data, list):
                    # Find Recipe type in list
                    recipe_data = None
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Recipe':
                            recipe_data = item
                            break
                    if recipe_data:
                        data = recipe_data
                    else:
                        data = data[0] if data else {}
                elif isinstance(data, dict) and '@graph' in data:
                    # Handle @graph structure
                    for item in data['@graph']:
                        if item.get('@type') == 'Recipe':
                            data = item
                            break
                
                recipe['title'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                
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
        
        # Epicurious specific selectors
        ingredients = soup.find_all('div', {'data-testid': 'ingredient-item'})
        recipe['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        return recipe


#Firecrawl parsing fallback
async def parse_with_firecrawl(url: str, firecrawl_key: str) -> Dict:
    """
    Fallback parser using FireCrawl for any site not in our priority list.
    
    COMPLIANCE:
    - FireCrawl handles robots.txt compliance internally
    - We specify we're extracting for analysis only
    - Instructions extracted but never displayed to users
    - Always preserves source URL for attribution
    - No content caching
    
    FireCrawl's LLM extraction provides consistent results across any recipe site.
    """
    try:
        # Initialize FireCrawl client
        app = FirecrawlApp(api_key=firecrawl_key)
        
        # Define the schema for recipe extraction
        recipe_schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The recipe title/name"
                },
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ingredients with amounts"
                },
                "instructions": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Step-by-step cooking instructions"
                },
                "cook_time": {
                    "type": "string",
                    "description": "Total time or cook time (e.g., '30 minutes')"
                },
                "servings": {
                    "type": "string",
                    "description": "Number of servings or yield"
                },
                "image_url": {
                    "type": "string",
                    "description": "URL of the main recipe image"
                }
            },
            "required": ["title", "ingredients"]
        }
        
        # Scrape with LLM extraction
        # COMPLIANCE: We use FireCrawl which respects robots.txt automatically
        result = app.scrape_url(
            url,
            params={
                'formats': ['extract'],
                'extract': {
                    'schema': recipe_schema,
                    'systemPrompt': 'Extract recipe information. This is for analysis only to help users find recipes, not for display. We will link back to the original source.'
                }
            }
        )
        
        # Extract the data from FireCrawl response
        if result and 'extract' in result:
            extracted = result['extract']
            
            # Format the response
            recipe = {
                'title': extracted.get('title', ''),
                'ingredients': extracted.get('ingredients', []),
                'instructions': extracted.get('instructions', []),  # For analysis only
                'cook_time': extracted.get('cook_time', ''),
                'servings': extracted.get('servings', ''),
                'image_url': extracted.get('image_url', ''),
                'source_url': url  # COMPLIANCE: Always preserve source
            }
            
            return recipe
        else:
            # If extraction fails, return minimal data with error
            return {
                'title': 'Recipe extraction failed',
                'ingredients': [],
                'instructions': [],
                'cook_time': '',
                'servings': '',
                'image_url': '',
                'source_url': url,
                'error': 'FireCrawl extraction failed'
            }
            
    except Exception as e:
        # Return error response if FireCrawl fails
        return {
            'title': 'Recipe extraction error',
            'ingredients': [],
            'instructions': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url,
            'error': str(e)
        }


# Master parser function that routes to correct parser
async def parse_recipe(url: str, firecrawl_key: str = None) -> Dict:
    """
    Parse a recipe from any supported site.
    
    COMPLIANCE GUARANTEE:
    - Priority sites: Check robots.txt before scraping
    - Other sites: Use FireCrawl which handles compliance
    - We respect crawl delays specified in robots.txt
    - Instructions are extracted for analysis only, NEVER displayed to users
    - We always provide attribution via source_url
    - No content is cached or stored permanently
    
    This demonstrates our good faith effort to comply with:
    - Website Terms of Service
    - Copyright law (fair use for analysis)
    - robots.txt guidelines
    
    Args:
        url: The recipe URL to parse
        firecrawl_key: API key for FireCrawl fallback (required for non-priority sites)
    
    Returns:
        Dict with recipe data or error information
    """
    # Try custom parsers first for priority sites
    if 'allrecipes.com' in url:
        return await parse_allrecipes(url)
    elif 'simplyrecipes.com' in url:
        return await parse_simplyrecipes(url)
    elif 'eatingwell.com' in url:
        return await parse_eatingwell(url)
    elif 'foodnetwork.com' in url:
        return await parse_foodnetwork(url)
    elif 'delish.com' in url:
        return await parse_delish(url)
    elif 'seriouseats.com' in url:
        return await parse_seriouseats(url)
    elif 'foodandwine.com' in url:
        return await parse_foodandwine(url)
    elif 'thepioneerwoman.com' in url:
        return await parse_thepioneerwoman(url)
    elif 'food.com' in url:
        return await parse_food_com(url)
    elif 'epicurious.com' in url:
        return await parse_epicurious(url)
    else:
        # Use FireCrawl for any other site
        if firecrawl_key:
            return await parse_with_firecrawl(url, firecrawl_key)
        else:
            return {
                'error': 'Site not supported and no FireCrawl key provided',
                'source_url': url
            }