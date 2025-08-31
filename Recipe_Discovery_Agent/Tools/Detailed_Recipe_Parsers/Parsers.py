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
import os
from .ingredient_parser import parse_ingredients_list


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


async def universal_recipe_parser(url: str, openai_key: str) -> Dict:
    """
    Universal recipe parser using hybrid HTML + GPT-3.5 approach.
    
    Designed to handle ANY recipe site with robust error handling and validation.
    Replaces all custom parsers for testing purposes.
    """
    if not openai_key:
        return {'error': 'OpenAI API key required for universal parsing', 'source_url': url}
    
    try:
        # Step 1: Fast HTML scraping with robust error handling
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        
        # Step 2: Clean and prepare content for LLM
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
            
        # Get text content with some structure preserved
        clean_content = soup.get_text(separator='\n', strip=True)
        
        # Limit content size to control costs
        max_chars = 15000  # ~3750 tokens
        if len(clean_content) > max_chars:
            clean_content = clean_content[:max_chars] + "...[content truncated]"
        
        # Step 3: LLM extraction with iOS app requirements
        prompt = f"""You are extracting recipe data from a webpage for an iOS app. Extract the following information:

SITE-SPECIFIC PARSING HINTS:
- If URL contains "seriouseats.com": 
  * Ingredients: Look for <li> elements with spans containing data attributes "data-ingredient-quantity", "data-ingredient-unit", "data-ingredient-name"
  * Images: Look for images with "data-src" attribute, especially those with "recipe-hero" or "butter-basted" in the filename
  * The ingredients section is usually marked with class "structured-ingredients__list"
- If URL contains "thepioneerwoman.com": 
  * Ingredients: Look for <li> elements with class "css-1uta69o e12sb1172" containing <strong> tags for quantities/units and <p> tags for ingredient names
  * Images: Check both "data-src" and "src" attributes, look for lazy-loaded images
  * Nutrition: Look for popup dialog with class "css-1x8cba8 e1aqnky27" or "ecif9ag8" containing <span> elements with nutrition values like "Calories1277", "Fat103 g", "Protein44 g", "Carbohydrates10 g" - extract the numeric values and units

REQUIRED FIELDS (must find ALL or mark as failed):
1. INGREDIENTS: Extract as STRUCTURED objects with shopping-aware parsing.
   
   CRITICAL: Parse each ingredient using STORE-FOCUSED logic FIRST:
   
   STORE QUANTITY/UNIT CONVERSION RULES (HIGHEST PRIORITY):
   - Fresh herbs (parsley, cilantro, basil, etc.) → store_quantity: "1", store_unit: "count" (sold as bunches)
   - Bottled liquids (vinegar, oils, extracts, etc.) → store_quantity: "1", store_unit: "count" (sold as bottles)
   - "X cloves garlic" → store_quantity: "1", store_unit: "count", amount: "X cloves" (people buy heads not cloves)
   - "Juice from half a lime" → store_quantity: "1", store_unit: "count", amount: "0.5" (round up whole items)
   - Maintain weight units for common grocery items: "1 pound skirt steak" → store_quantity: "1", store_unit: "lb"
   - Use "count" only for vague quantities: "3-4 pieces flank steak" → store_quantity: "4", store_unit: "count"
   - Ranges "1.5 to 2 lb beef" → store_quantity: "1.75", store_unit: "lb" (average ranges)
   - Nested measurements "1 (14.5 oz) can tomatoes" → store_quantity: "1", store_unit: "count", amount: "14.5 oz"
   - Packaged items (flour, sugar) → store_quantity: "1", store_unit: "count" (sold in bags)
   - "salt and pepper to taste" → Split into 2 items, store_quantity: "1", store_unit: "count", pantry_staple: true, optional: true
   
   OTHER FIELD PARSING (ALONGSIDE STORE LOGIC):
   - alternatives: Split "milk or almond milk" → alternatives: ["almond milk"]
   - additional_context: Prep state ("melted", "minced", "softened", "store-bought", "for garnish")
   - optional: true for "to taste"/garnish/serving items
   - disqualified: true for "see recipe"/homemade/cross-references
   - pantry_staple: true for salt/pepper/oil/flour/sugar/basic spices
   - original: Original text exactly as written
   
   BASIC QUANTITY/UNIT (SIMPLE EXTRACTION - DO LAST):
   - quantity: Recipe quantity as written (copy from original)
   - unit: Recipe unit as written (copy from original)
   - ingredient: Clean name without prep instructions
   
2. IMAGE: Find the main recipe image URL (usually the first large image, thumbnail, or hero image)
   - Skip video thumbnails if present
   - Look for image with recipe name or food photo
   - Return full URL, not relative path
   
3. NUTRITION (extract EXACT text for these 4):
   - Calories: (e.g., "250 calories" or "250 kcal")
   - Protein: (e.g., "30g protein")
   - Carbs: (e.g., "15g carbohydrates" or "15g carbs")  
   - Fat: (e.g., "10g fat")

OPTIONAL FIELDS (include if found):
- title: Recipe name
- cook_time: Total or cook time
- prep_time: Preparation time  
- servings: Number of servings

Return JSON format:
{{
  "status": "success",
  "title": "Recipe Title",
  "ingredients": [
    {{
      "quantity": "2",
      "unit": "cups",
      "ingredient": "flour",
      "store_quantity": "1",
      "store_unit": "count",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": true,
      "optional": false,
      "disqualified": false,
      "original": "2 cups flour"
    }},
    {{
      "quantity": "4",
      "unit": "cloves",
      "ingredient": "garlic",
      "store_quantity": "1",
      "store_unit": "count",
      "amount": "4 cloves",
      "size": null,
      "additional_context": "minced",
      "alternatives": [],
      "pantry_staple": false,
      "optional": false,
      "disqualified": false,
      "original": "4 cloves garlic, minced"
    }},
    {{
      "quantity": "2",
      "unit": "tablespoons",
      "ingredient": "red wine vinegar",
      "store_quantity": "1",
      "store_unit": "count",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": false,
      "optional": false,
      "disqualified": false,
      "original": "2 tablespoons red wine vinegar"
    }}
  ],
  "nutrition": ["250 calories", "30g protein", "15g carbs", "10g fat"],
  "image_url": "https://example.com/image.jpg",
  "cook_time": "30 minutes",
  "prep_time": "15 minutes",
  "servings": "4"
}}

If any REQUIRED field is missing, return:
{{
  "status": "failed",
  "missing_required": ["ingredients", "image_url"],
  "error": "Missing required fields"
}}

Content to analyze:
{clean_content}"""

        # Step 4: Call GPT-3.5
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a recipe extraction specialist. Return only valid JSON with all required fields."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
            )
        
        if response.status_code != 200:
            return {'error': f'LLM API error: {response.status_code}', 'source_url': url}
        
        data = response.json()
        llm_response = data['choices'][0]['message']['content'].strip()
        
        # Step 5: Parse JSON response
        try:
            # Clean up response in case LLM added extra text
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            import json
            recipe_data = json.loads(llm_response)
            
            # Step 6: Validate required fields
            if recipe_data.get('status') == 'failed':
                return {
                    'error': f"Missing required fields: {recipe_data.get('missing_required', [])}",
                    'source_url': url
                }
            
            # Double-check validation with our own validator
            is_valid, missing_fields = validate_recipe_data(recipe_data)
            if not is_valid:
                return {
                    'error': f"Validation failed: missing {missing_fields}",
                    'source_url': url
                }
            
            # Step 7: Format for consistency with other parsers
            formatted_recipe = {
                'title': recipe_data.get('title', ''),
                'ingredients': recipe_data.get('ingredients', []),
                'instructions': recipe_data.get('instructions', []),
                'nutrition': recipe_data.get('nutrition', []),
                'cook_time': recipe_data.get('cook_time', ''),
                'prep_time': recipe_data.get('prep_time', ''),
                'servings': recipe_data.get('servings', ''),
                'image_url': recipe_data.get('image_url', ''),
                'source_url': url
            }
            
            return formatted_recipe
                
        except json.JSONDecodeError as e:
            return {'error': f'JSON parsing failed: {e}', 'source_url': url}
        
    except Exception as e:
        return {'error': f'Universal parsing failed: {e}', 'source_url': url}


async def parse_recipe_with_hybrid_approach(url: str, openai_key: str) -> Dict:
    """
    Hybrid approach for recipe parsing: HTML scraping + GPT-3.5 extraction.
    
    Designed for non-priority sites as a FireCrawl replacement.
    Includes pass/fail validation for iOS app requirements.
    """
    if not openai_key:
        return {'error': 'OpenAI API key required for hybrid parsing', 'source_url': url}
    
    try:
        # Step 1: Fast HTML scraping
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
        
        # Step 2: Clean and prepare content for LLM
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
            
        # Get text content with some structure preserved
        clean_content = soup.get_text(separator='\n', strip=True)
        
        # Limit content size to control costs
        max_chars = 15000  # ~3750 tokens
        if len(clean_content) > max_chars:
            clean_content = clean_content[:max_chars] + "...[content truncated]"
        
        # Step 3: LLM extraction with specific recipe requirements
        prompt = f"""You are extracting recipe data from a webpage. Extract the following information:

REQUIRED FIELDS (must find ALL or mark as failed):
1. INGREDIENTS: Extract as STRUCTURED objects with TWO-STEP parsing.
   Parse each ingredient into this exact format:
   {
     "quantity": Recipe quantity exactly as written,
     "unit": Recipe unit exactly as written, 
     "ingredient": Clean name without prep instructions,
     "store_quantity": Shopping quantity (converted for practical shopping),
     "store_unit": Shopping unit (converted for practical shopping),
     "amount": Recipe amount if different from store quantity,
     "size": Size descriptor ("large", "small", "medium"),
     "additional_context": Prep/state ("melted", "minced", "softened", "store-bought"),
     "alternatives": Array of alternatives (split "milk or almond milk" → ["almond milk"]),
     "pantry_staple": true ONLY for salt/pepper/oil/flour/sugar/basic spices,
     "optional": true for "to taste"/garnish/serving items,
     "disqualified": true for "see recipe"/homemade/cross-references,
     "original": Original text exactly as written
   }
   
   STEP 1 - DIRECT RECIPE PARSING (quantity, unit, ingredient):
   - Parse exactly what the recipe says: "4 cloves garlic" → quantity: "4", unit: "cloves", ingredient: "garlic"
   - "half a lime" → quantity: "half", unit: null, ingredient: "lime" 
   - "1 1/2 to 2 pounds beef" → quantity: "1 1/2 to 2", unit: "pounds", ingredient: "beef"
   - "salt and pepper to taste" → Split into 2 items: ("salt", "to taste", null) and ("pepper", "to taste", null)
   - Remove prep instructions from ingredient name: "garlic, minced" → ingredient: "garlic"
   
   STEP 2 - STORE CONVERSION (store_quantity, store_unit):
   - Garlic cloves → store_quantity: "1", store_unit: "count" (buy 1 head)
   - Half lime → store_quantity: "1", store_unit: "count" (buy 1 lime - ALWAYS round UP)
   - Small liquid amounts → store_quantity: "1", store_unit: "count" (buy 1 bottle/container)
   - Examples: "1/4 cup vinegar" → store_quantity: "1", store_unit: "count" (buy 1 bottle)
   - Examples: "2 tbsp Worcestershire" → store_quantity: "1", store_unit: "count" (buy 1 bottle)
   - Packaged items → store_quantity: "1", store_unit: "count" (flour/sugar sold in bags, not by cup)
   - Weight/volume for bulk items → keep precise: "1.5 lb beef" → store_quantity: "1.5", store_unit: "lb"
   - Whole items → store_unit: "count", ALWAYS round UP: "half onion" → store_quantity: "1", store_unit: "count"
   - "to taste" items → store_quantity: "1", store_unit: "pinch"
   
   CRITICAL ROUNDING RULE: If recipe needs fraction of a whole item or small amount of liquid/seasoning, ALWAYS round store_quantity UP to "1" with store_unit: "count"
   
   METADATA RULES:
   - pantry_staple: true ONLY for salt, pepper, cooking oil, flour, sugar, dried spices/herbs
   - optional: true for "to taste", "for garnish", "for serving"
   - disqualified: true for "(see recipe)", "homemade", cross-references → store_quantity: null, store_unit: null
   
2. IMAGE: Find the main recipe image URL (usually the first large image, thumbnail, or hero image)
   - Skip video thumbnails if present
   - Look for image with recipe name or food photo
   - Return full URL, not relative path
   
3. NUTRITION (extract EXACT text for these 4):
   - Calories: (e.g., "250 calories" or "250 kcal")
   - Protein: (e.g., "30g protein")
   - Carbs: (e.g., "15g carbohydrates" or "15g carbs")  
   - Fat: (e.g., "10g fat")

OPTIONAL FIELDS (include if found):
- title: Recipe name
- cook_time: Total or cook time
- prep_time: Preparation time  
- servings: Number of servings

Return JSON format:
{{
  "status": "success",
  "title": "Recipe Title",
  "ingredients": [
    {{
      "quantity": "2",
      "unit": "cups",
      "ingredient": "flour",
      "store_quantity": "2",
      "store_unit": "cups",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": true,
      "optional": false,
      "disqualified": false,
      "original": "2 cups flour"
    }},
    {{
      "quantity": "4",
      "unit": "cloves",
      "ingredient": "garlic",
      "store_quantity": "1",
      "store_unit": "count",
      "amount": "4 cloves",
      "size": null,
      "additional_context": "minced",
      "alternatives": [],
      "pantry_staple": false,
      "optional": false,
      "disqualified": false,
      "original": "4 cloves garlic, minced"
    }},
    {{
      "quantity": "1/4",
      "unit": "cup",
      "ingredient": "vinegar",
      "store_quantity": "1",
      "store_unit": "count",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": false,
      "optional": false,
      "disqualified": false,
      "original": "1/4 cup white wine vinegar"
    }}
  ],
  "nutrition": ["250 calories", "30g protein", "15g carbs", "10g fat"],
  "image_url": "https://example.com/image.jpg",
  "cook_time": "30 minutes",
  "prep_time": "15 minutes",
  "servings": "4"
}}

If any REQUIRED field is missing, return:
{{
  "status": "failed",
  "missing_required": ["ingredients", "image_url"],
  "error": "Missing required fields"
}}

Content to analyze:
{clean_content}"""

        # Step 4: Call GPT-3.5
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a recipe extraction specialist. Return only valid JSON with all required fields."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
            )
        
        if response.status_code != 200:
            return {'error': f'LLM API error: {response.status_code}', 'source_url': url}
        
        data = response.json()
        llm_response = data['choices'][0]['message']['content'].strip()
        
        # Step 5: Parse JSON response
        try:
            # Clean up response in case LLM added extra text
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            import json
            recipe_data = json.loads(llm_response)
            
            # Step 6: Validate required fields
            if recipe_data.get('status') == 'failed':
                return {
                    'error': f"Missing required fields: {recipe_data.get('missing_required', [])}",
                    'source_url': url
                }
            
            # Double-check validation with our own validator
            is_valid, missing_fields = validate_recipe_data(recipe_data)
            if not is_valid:
                return {
                    'error': f"Validation failed: missing {missing_fields}",
                    'source_url': url
                }
            
            # Step 7: Format for consistency with other parsers
            formatted_recipe = {
                'title': recipe_data.get('title', ''),
                'ingredients': recipe_data.get('ingredients', []),
                'instructions': recipe_data.get('instructions', []),
                'nutrition': recipe_data.get('nutrition', []),
                'cook_time': recipe_data.get('cook_time', ''),
                'prep_time': recipe_data.get('prep_time', ''),
                'servings': recipe_data.get('servings', ''),
                'image_url': recipe_data.get('image_url', ''),
                'source_url': url
            }
            
            return formatted_recipe
                
        except json.JSONDecodeError as e:
            return {'error': f'JSON parsing failed: {e}', 'source_url': url}
        
    except Exception as e:
        return {'error': f'Hybrid parsing failed: {e}', 'source_url': url}


#Firecrawl parsing fallback


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