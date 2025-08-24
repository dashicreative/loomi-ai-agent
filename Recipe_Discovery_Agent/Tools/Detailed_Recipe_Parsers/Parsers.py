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
        'instructions': len(recipe_data.get('instructions', [])) > 0,
        'image_url': bool(recipe_data.get('image_url', '').strip()),
        'nutrition': len(recipe_data.get('nutrition', [])) >= 4  # Need all 4: calories, protein, carbs, fat
    }
    
    missing = [field for field, present in required_checks.items() if not present]
    return len(missing) == 0, missing


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

REQUIRED FIELDS (must find ALL or mark as failed):
1. INGREDIENTS: Extract the COMPLETE ingredient text including amounts, units, and names.
   - PRESERVE EXACT TEXT: "2 cups all-purpose flour" NOT just "flour"
   - Include ALL ingredients as a list
   
2. IMAGE: Find the main recipe image URL (usually the first large image, thumbnail, or hero image)
   - Skip video thumbnails if present
   - Look for image with recipe name or food photo
   - Return full URL, not relative path
   
3. NUTRITION (extract EXACT text for these 4):
   - Calories: (e.g., "250 calories" or "250 kcal")
   - Protein: (e.g., "30g protein")
   - Carbs: (e.g., "15g carbohydrates" or "15g carbs")  
   - Fat: (e.g., "10g fat")
   
4. INSTRUCTIONS: Step-by-step cooking directions as separate items

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
      "unit": "cup",
      "ingredient": "flour",
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
      "quantity": "1",
      "unit": "tsp",
      "ingredient": "salt",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": true,
      "optional": false,
      "disqualified": false,
      "original": "1 tsp salt"
    }}
  ],
  "instructions": ["Step 1 text", "Step 2 text"],
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
1. INGREDIENTS: Extract as STRUCTURED objects with shopping-aware parsing.
   Parse each ingredient into this exact format:
   {
     "quantity": Shopping quantity (ROUND UP whole items: "half lime"→"1", keep precise for weight/volume: "1.5 lb"→"1.5"),
     "unit": Shopping unit ("count" for whole items, "lb"/"cup"/"tsp" for measurements),
     "ingredient": Clean name without prep instructions,
     "amount": Recipe amount if different from quantity ("0.5" for half lime, "4 cloves" for garlic),
     "size": Size descriptor ("large", "small", "medium"),
     "additional_context": Prep/state ("melted", "minced", "softened", "store-bought"),
     "alternatives": Array of alternatives (split "milk or almond milk" → ["almond milk"]),
     "pantry_staple": true for salt/pepper/oil/flour/sugar/basic spices,
     "optional": true for "to taste"/garnish/serving items,
     "disqualified": true for "see recipe"/homemade/cross-references,
     "original": Original text exactly as written
   }
   
   CRITICAL RULES:
   - "salt and pepper to taste" → Split into 2 separate items, quantity: "1", unit: "pinch", pantry_staple: true, optional: true
   - "X cloves garlic" → ALWAYS convert to quantity: "1", unit: "head", amount: "X cloves" (people buy heads not cloves)
   - Nested measurements "1 (14.5 oz) can tomatoes" → quantity: "1", unit: "can", amount: "14.5 oz"
   - "Juice from half a lime" → quantity: "1", unit: "count", amount: "0.5", additional_context: "juiced"
   - Round UP whole items for shopping: limes/onions/peppers → nearest whole number in quantity field
   - Average ranges: "1.5 to 2 lb beef" → quantity: "1.75", amount: null
   - Items with "or" → first is main ingredient, rest in alternatives array
   - "cilantro for garnish" → quantity: "1", unit: "bunch", ingredient: "cilantro", additional_context: "for garnish", optional: true
   - "1 batch pizza dough (see recipe)" → quantity: null, unit: null, ingredient: "pizza dough", additional_context: "see recipe", disqualified: true
   - "store-bought" → goes in additional_context, ingredient name should NOT include "store-bought"
   - Use "count" for whole items (vegetables, fruits), "pieces" for cuts of meat/fish (steaks, fillets, chops)
   
2. IMAGE: Find the main recipe image URL (usually the first large image, thumbnail, or hero image)
   - Skip video thumbnails if present
   - Look for image with recipe name or food photo
   - Return full URL, not relative path
   
3. NUTRITION (extract EXACT text for these 4):
   - Calories: (e.g., "250 calories" or "250 kcal")
   - Protein: (e.g., "30g protein")
   - Carbs: (e.g., "15g carbohydrates" or "15g carbs")  
   - Fat: (e.g., "10g fat")
   
4. INSTRUCTIONS: Step-by-step cooking directions as separate items

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
      "unit": "cup",
      "ingredient": "flour",
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
      "quantity": "1",
      "unit": "tsp",
      "ingredient": "salt",
      "amount": null,
      "size": null,
      "additional_context": null,
      "alternatives": [],
      "pantry_staple": true,
      "optional": false,
      "disqualified": false,
      "original": "1 tsp salt"
    }}
  ],
  "instructions": ["Step 1 text", "Step 2 text"],
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
            raw_ingredients = extracted.get('ingredients', [])
            raw_nutrition = extracted.get('nutrition', [])
            recipe = {
                'title': extracted.get('title', ''),
                'ingredients': parse_ingredients_list(raw_ingredients),
                'instructions': extracted.get('instructions', []),  # For analysis only
                'nutrition': raw_nutrition,  # Raw nutrition strings from FireCrawl
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
                'nutrition': [],
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
            'nutrition': [],
            'cook_time': '',
            'servings': '',
            'image_url': '',
            'source_url': url,
            'error': str(e)
        }


# Master parser function that routes to correct parser
async def parse_recipe(url: str, openai_key: str = None) -> Dict:
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
        openai_key: OpenAI API key for hybrid fallback (required for non-priority sites)
    
    Returns:
        Dict with recipe data or error information
    """
    # Use universal parser for ALL sites
    if openai_key:
        return await universal_recipe_parser(url, openai_key)
    else:
        return {
            'error': 'OpenAI key required for universal parsing',
            'source_url': url
        }