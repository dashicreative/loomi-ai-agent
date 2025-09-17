"""
Stage 9b: Parallel Ingredient Parsing
Advanced hybrid parsing system that combines speed and accuracy.

Architecture:
1. Parallel Labeling: 5 concurrent LLM calls to label ingredients as "simple" or "complex"
2. Hybrid Processing: Simple ingredients → regex parsing, Complex ingredients → focused LLM parsing
3. Parallel Execution: All 5 recipes processed simultaneously for maximum speed

Performance: ~3-4 seconds total (vs 40+ seconds with old approach)
"""

import asyncio
import httpx
import json
import re
import time
from typing import Dict, List, Tuple, Optional
import os


def _normalize_to_instacart_unit(unit: str) -> str:
    """
    Normalize unit variants to Instacart accepted primary units.
    Uses first variant from accepted list.
    """
    unit_lower = unit.lower()
    
    # Instacart unit mappings (use first variant)
    unit_mappings = {
        # Volume
        'cups': 'cup', 'c': 'cup',
        'tablespoons': 'tablespoon', 'tbsp': 'tablespoon', 'tb': 'tablespoon', 'tbs': 'tablespoon',
        'teaspoons': 'teaspoon', 'tsp': 'teaspoon', 'ts': 'teaspoon', 'tspn': 'teaspoon',
        'gallons': 'gallon', 'gal': 'gallon', 'gals': 'gallon',
        'pints': 'pint', 'pt': 'pint', 'pts': 'pint',
        'quarts': 'quart', 'qt': 'quart', 'qts': 'quart',
        'liters': 'liter', 'litres': 'liter', 'l': 'liter',
        'milliliters': 'milliliter', 'millilitres': 'milliliter', 'ml': 'milliliter', 'mls': 'milliliter',
        
        # Weight
        'ounces': 'ounce', 'oz': 'ounce',
        'pounds': 'pound', 'lbs': 'pound', 'lb': 'pound',
        'grams': 'gram', 'g': 'gram', 'gs': 'gram',
        'kilograms': 'kilogram', 'kg': 'kilogram', 'kgs': 'kilogram',
        
        # Count
        'cans': 'can',
        'bunches': 'bunch',
        'heads': 'head',
        'packages': 'package',
        'packets': 'packet'
    }
    
    return unit_mappings.get(unit_lower, unit_lower)


async def process_all_recipe_ingredients(recipes: List[Dict], openai_key: str = None) -> List[Dict]:
    """
    Main orchestrator: Process ingredients for all 5 recipes using parallel hybrid approach.
    
    Args:
        recipes: List of recipe dictionaries from stage 9a
        openai_key: OpenAI API key (optional, uses env if not provided)
        
    Returns:
        List of recipes with parsed ingredients in structured format
    """
    if not recipes:
        return recipes
        
    api_key = openai_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("⚠️  No OpenAI API key found - using basic ingredient parsing")
        return _fallback_basic_parsing(recipes)
    
    print(f"\n🔄 STAGE 9B: Parallel Ingredient Processing ({len(recipes)} recipes)")
    print("=" * 60)
    
    total_start = time.time()
    
    # STAGE 1: Parallel ingredient labeling (5 concurrent LLM calls)
    print("🏷️  Stage 1: Parallel ingredient labeling...")
    labeling_start = time.time()
    
    labeled_recipes = await _label_all_ingredients_parallel(recipes, api_key)
    
    labeling_time = time.time() - labeling_start
    print(f"   ✅ Labeling completed: {labeling_time:.2f}s")
    
    # STAGE 2: Parallel hybrid parsing (regex + focused LLM)
    print("🔧 Stage 2: Parallel hybrid parsing...")
    parsing_start = time.time()
    
    parsed_recipes = await _parse_all_ingredients_parallel(labeled_recipes, api_key)
    
    parsing_time = time.time() - parsing_start
    total_time = time.time() - total_start
    
    print(f"   ✅ Parsing completed: {parsing_time:.2f}s")
    print(f"🎉 Total ingredient processing: {total_time:.2f}s")
    print("=" * 60)
    
    return parsed_recipes


async def _label_all_ingredients_parallel(recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Stage 1: Label all ingredients across all recipes in parallel.
    5 concurrent LLM calls for speed.
    """
    labeling_tasks = []
    
    for recipe in recipes:
        task = _label_recipe_ingredients(recipe, api_key)
        labeling_tasks.append(task)
    
    # Execute all labeling in parallel
    labeled_recipes = await asyncio.gather(*labeling_tasks, return_exceptions=True)
    
    # Handle any exceptions
    results = []
    for i, result in enumerate(labeled_recipes):
        if isinstance(result, Exception):
            print(f"⚠️  Labeling failed for recipe {i+1}: {result}")
            # Keep original recipe with basic labeling
            results.append(_fallback_ingredient_labeling(recipes[i]))
        else:
            results.append(result)
    
    return results


async def _label_recipe_ingredients(recipe: Dict, api_key: str) -> Dict:
    """
    Label ingredients for a single recipe as "simple" or "complex".
    Uses refined prompt from original ingredient_processor.py.
    """
    ingredients = recipe.get('ingredients', [])
    if not ingredients:
        return recipe
    
    # Extract ingredient strings
    ingredient_strings = []
    for ing in ingredients:
        if isinstance(ing, dict):
            ingredient_strings.append(ing.get('ingredient', ''))
        else:
            ingredient_strings.append(str(ing))
    
    # Create focused labeling prompt based on original processor logic
    ingredients_text = "\n".join([f"- {ing}" for ing in ingredient_strings])
    
    prompt = f"""Label each ingredient as either "simple" or "complex" for parsing difficulty.

INGREDIENTS:
{ingredients_text}

LABELING RULES (Instacart unit compatibility):
SIMPLE ingredients use accepted Instacart units:
- Accepted units: cup, tablespoon, teaspoon, ounce, pound, gram, kilogram, gallon, liter, pint, quart, can, each, bunch, head, large, medium, small, package
- Examples: "2 cups flour", "1 pound chicken", "3 each eggs", "1 tablespoon salt", "2 cans tomatoes"
- Must have EXACT unit match - no ingredient names as units

COMPLEX ingredients need conversion or are subjective:
- **Multiple unit patterns**: "4(8 ounce) packages cream cheese" (parenthetical + unit combo)
- **Countable items with names as units**: "15 graham crackers", "12 cookies", "6 slices bread" (convert to packages/each)  
- **Multiple measurements**: "12 ounces fresh fruit (about 2 cups)" (needs unit selection)
- **Subjective amounts**: "salt to taste", "pepper as needed" (mark disqualified)
- **Descriptive quantities**: "juice from 1 lemon" (convert to "each")
- **Non-standard units**: "splash of vinegar", "pinch of salt" (convert or disqualify)
- **Compound ingredients**: "salt and pepper to taste" (split and process)
- **Ranges**: "1-2 pounds beef" (convert to average)
- **Cross-references**: "see recipe notes" (mark disqualified)

CRITICAL: If unit NOT in accepted list OR has parenthetical measurements, mark as COMPLEX!

Return JSON array: ["simple", "complex", "simple", ...]
Order must match ingredient list exactly."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for labeling
                    "max_tokens": 200,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Extract JSON array
            if '[' in llm_response and ']' in llm_response:
                start = llm_response.find('[')
                end = llm_response.rfind(']') + 1
                json_str = llm_response[start:end]
                labels = json.loads(json_str)
                
                # Validate labels match ingredient count
                if len(labels) == len(ingredient_strings):
                    # Add labels to recipe
                    recipe['ingredient_labels'] = labels
                    return recipe
        
        # Fallback if labeling fails
        return _fallback_ingredient_labeling(recipe)
        
    except Exception as e:
        print(f"   ⚠️  Ingredient labeling failed: {e}")
        return _fallback_ingredient_labeling(recipe)


async def _parse_all_ingredients_parallel(labeled_recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Stage 2: Parse all recipes' ingredients in parallel using hybrid approach.
    """
    parsing_tasks = []
    
    for recipe in labeled_recipes:
        task = _parse_single_recipe_ingredients(recipe, api_key)
        parsing_tasks.append(task)
    
    # Execute all parsing in parallel  
    parsed_recipes = await asyncio.gather(*parsing_tasks, return_exceptions=True)
    
    # Handle any exceptions
    results = []
    for i, result in enumerate(parsed_recipes):
        if isinstance(result, Exception):
            print(f"⚠️  Parsing failed for recipe {i+1}: {result}")
            # Keep original recipe with basic ingredients
            results.append(labeled_recipes[i])
        else:
            results.append(result)
    
    return results


async def _parse_single_recipe_ingredients(recipe: Dict, api_key: str) -> Dict:
    """
    Parse ingredients for a single recipe using hybrid approach.
    Simple ingredients → regex parsing, Complex ingredients → focused LLM.
    """
    ingredients = recipe.get('ingredients', [])
    labels = recipe.get('ingredient_labels', [])
    
    if not ingredients or not labels or len(ingredients) != len(labels):
        return recipe
    
    # Separate ingredients by complexity
    simple_ingredients = []
    complex_ingredients = []
    ingredient_map = {}  # Track original indices
    
    for i, (ingredient, label) in enumerate(zip(ingredients, labels)):
        ingredient_text = ingredient.get('ingredient', '') if isinstance(ingredient, dict) else str(ingredient)
        
        if label == "simple":
            simple_ingredients.append(ingredient_text)
            ingredient_map[f"simple_{len(simple_ingredients)-1}"] = i
        else:
            complex_ingredients.append(ingredient_text) 
            ingredient_map[f"complex_{len(complex_ingredients)-1}"] = i
    
    # Process simple and complex ingredients in parallel
    tasks = []
    
    async def empty_result():
        return []
    
    if simple_ingredients:
        tasks.append(_parse_simple_ingredients(simple_ingredients))
    else:
        tasks.append(empty_result())
        
    if complex_ingredients:
        tasks.append(_parse_complex_ingredients(complex_ingredients, api_key))
    else:
        tasks.append(empty_result())
    
    simple_results, complex_results = await asyncio.gather(*tasks)
    
    # Reconstruct ingredients in original order
    parsed_ingredients = [None] * len(ingredients)
    
    # Place simple results
    for i, parsed in enumerate(simple_results):
        map_key = f"simple_{i}"
        if map_key in ingredient_map:
            original_index = ingredient_map[map_key]
            # Add debugging type field
            parsed["type"] = "simple"
            parsed_ingredients[original_index] = parsed
        else:
            print(f"⚠️  Missing mapping for {map_key}")
    
    # Place complex results  
    for i, parsed in enumerate(complex_results):
        map_key = f"complex_{i}"
        if map_key in ingredient_map:
            original_index = ingredient_map[map_key]
            # Add debugging type field
            parsed["type"] = "complex"
            parsed_ingredients[original_index] = parsed
        else:
            print(f"⚠️  Missing mapping for {map_key}")
    
    # Update recipe with parsed ingredients
    recipe['ingredients'] = [ing for ing in parsed_ingredients if ing is not None]
    
    # Clean up temporary fields
    if 'ingredient_labels' in recipe:
        del recipe['ingredient_labels']
    
    return recipe


async def _parse_simple_ingredients(ingredients: List[str]) -> List[Dict]:
    """
    Robust regex-based parsing for simple ingredients.
    Handles unicode fractions, missing spaces, and complex patterns.
    """
    parsed = []
    
    # Unicode fraction mappings
    fraction_map = {
        '½': '0.5', '¼': '0.25', '¾': '0.75', '⅐': '0.143', '⅑': '0.111', 
        '⅒': '0.1', '⅓': '0.333', '⅔': '0.667', '⅕': '0.2', '⅖': '0.4',
        '⅗': '0.6', '⅘': '0.8', '⅙': '0.167', '⅚': '0.833', '⅛': '0.125',
        '⅜': '0.375', '⅝': '0.625', '⅞': '0.875'
    }
    
    for ingredient in ingredients:
        # Initialize with simplified Instacart-compatible structure
        result = {
            "quantity": None,
            "unit": None, 
            "ingredient": ingredient,
            "disqualified": False,
            "original": ingredient
        }
        
        # Preprocess: Convert unicode fractions and fix missing spaces
        processed = ingredient.strip()
        
        # Convert unicode fractions
        for unicode_frac, decimal in fraction_map.items():
            processed = processed.replace(unicode_frac, decimal)
        
        # Add spaces between numbers and letters (handles "1tablespoon" → "1 tablespoon")
        processed = re.sub(r'(\d+(?:\.\d+)?(?:/\d+)?)([a-zA-Z])', r'\1 \2', processed)
        
        # Handle mixed patterns like "1 0.5cupsgraham" → "1.5 cupsgraham"
        # Combine adjacent numbers separated by space
        processed = re.sub(r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)([a-zA-Z])', 
                          lambda m: str(float(m.group(1)) + float(m.group(2))) + m.group(3), processed)
        
        # Extract valid Instacart unit from potentially mashed text
        def extract_valid_unit(text_after_quantity):
            """Extract the first valid Instacart unit from text, return (unit, remaining_text)"""
            # All accepted Instacart units (including variants)
            valid_units = [
                'cup', 'cups', 'c',
                'tablespoon', 'tablespoons', 'tbsp', 'tb', 'tbs', 
                'teaspoon', 'teaspoons', 'tsp', 'ts', 'tspn',
                'gallon', 'gallons', 'gal', 'gals',
                'pint', 'pints', 'pt', 'pts',
                'quart', 'quarts', 'qt', 'qts', 
                'liter', 'liters', 'litres', 'l',
                'milliliter', 'milliliters', 'millilitres', 'ml', 'mls',
                'ounce', 'ounces', 'oz',
                'pound', 'pounds', 'lb', 'lbs',
                'gram', 'grams', 'g', 'gs',
                'kilogram', 'kilograms', 'kg', 'kgs',
                'can', 'cans', 'bunch', 'bunches', 'head', 'heads',
                'large', 'medium', 'small', 'each',
                'package', 'packages', 'packet', 'packets'
            ]
            
            text_lower = text_after_quantity.lower()
            
            # Find the longest matching unit at the start with word boundaries
            best_match = None
            for unit in sorted(valid_units, key=len, reverse=True):  # Check longer units first
                if text_lower.startswith(unit):
                    # Ensure it's a complete word - next char must be non-alphabetic or end of string
                    if len(text_after_quantity) == len(unit) or not text_after_quantity[len(unit)].isalpha():
                        best_match = unit
                        break
            
            if best_match:
                remaining = text_after_quantity[len(best_match):].strip()
                return best_match, remaining
            
            return None, text_after_quantity
        
        # Try to extract quantity and parse remaining text for valid unit
        quantity_match = re.match(r'(\d+(?:\.\d+)?(?:/\d+)?)\s+(.+)', processed)
        if quantity_match:
            quantity_str, remainder = quantity_match.groups()
            
            # Extract valid unit from remainder
            unit, remaining_ingredient = extract_valid_unit(remainder)
            
            if unit:
                # Normalize to Instacart accepted units (use first variant)
                normalized_unit = _normalize_to_instacart_unit(unit)
                
                result.update({
                    "quantity": quantity_str,
                    "unit": normalized_unit,
                    "ingredient": remaining_ingredient.strip()
                })
        
        # Special Pattern: "N (size) packages" or "N cans" - extract count and unit
        elif re.match(r'(\d+)\s*\([^)]+\)\s*(\w+)\s+(.+)', processed):
            match = re.match(r'(\d+)\s*\([^)]+\)\s*(\w+)\s+(.+)', processed)
            quantity, unit, ingredient_name = match.groups()
            
            # Validate and normalize package-type units
            valid_unit, _ = extract_valid_unit(unit)
            if valid_unit:
                normalized_unit = _normalize_to_instacart_unit(valid_unit)
                
                result.update({
                    "quantity": quantity,
                    "unit": normalized_unit,
                    "ingredient": ingredient_name.strip()
                })
        
        # Check for subjective/optional items that should be disqualified
        ingredient_lower = ingredient.lower()
        if any(phrase in ingredient_lower for phrase in ["to taste", "as needed", "optional", "if desired"]):
            result["disqualified"] = True
            
        parsed.append(result)
    
    return parsed


async def _parse_complex_ingredients(ingredients: List[str], api_key: str) -> List[Dict]:
    """
    Focused LLM parsing for complex ingredients only.
    Uses refined prompt from original processor.
    """
    if not ingredients:
        return []
    
    ingredients_text = "\n".join([f"- {ing}" for ing in ingredients])
    
    # Focused prompt for complex ingredients - convert to Instacart units
    prompt = f"""Convert complex ingredients to Instacart-compatible format.

INGREDIENTS TO PROCESS:
{ingredients_text}

CONVERSION RULES:
- Convert to accepted Instacart units: cup, tablespoon, teaspoon, ounce, pound, gram, can, each, bunch, head, package
- For multiple measurements, choose the most practical Instacart unit
- For subjective amounts ("to taste"), set disqualified: true
- Use first variant only (cup not cups, ounce not ounces)

CONVERSION EXAMPLES:
- "12 ounces fruit (about 2 cups)" → quantity: "12", unit: "ounce" 
- "juice from 1 lemon" → quantity: "1", unit: "each", ingredient: "lemon"
- "salt to taste" → disqualified: true
- "2 (8-oz) packages cream cheese" → quantity: "2", unit: "package"
- "15 graham crackers" → quantity: "1", unit: "package", ingredient: "graham crackers" (crackers sold in packages)
- "12 cookies" → quantity: "1", unit: "package", ingredient: "cookies" (cookies sold in packages)  
- "6 slices bread" → quantity: "1", unit: "each", ingredient: "loaf bread" (buy whole loaf)

JSON FORMAT:
[{{"quantity": "amount", "unit": "instacart_unit", "ingredient": "name", "disqualified": boolean, "original": "text"}}]"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for focused parsing
                    "max_tokens": 800,       # Reduced tokens for simpler output
                    "temperature": 0.1,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Extract JSON array
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            parsed_ingredients = json.loads(llm_response)
            
            # Validate structure
            if isinstance(parsed_ingredients, list):
                return parsed_ingredients
                
        # Fallback for complex ingredients
        return _fallback_complex_parsing(ingredients)
        
    except Exception as e:
        print(f"   ⚠️  Complex ingredient parsing failed: {e}")
        return _fallback_complex_parsing(ingredients)


def _fallback_ingredient_labeling(recipe: Dict) -> Dict:
    """Fallback: Label all ingredients as simple for regex processing."""
    ingredients = recipe.get('ingredients', [])
    recipe['ingredient_labels'] = ["simple"] * len(ingredients)
    return recipe


def _fallback_basic_parsing(recipes: List[Dict]) -> List[Dict]:
    """Fallback: Basic parsing when no API key available."""
    for recipe in recipes:
        ingredients = recipe.get('ingredients', [])
        parsed_ingredients = []
        
        for ingredient in ingredients:
            ingredient_text = ingredient.get('ingredient', '') if isinstance(ingredient, dict) else str(ingredient)
            parsed_ingredients.append({
                "quantity": "1",
                "unit": "each",
                "ingredient": ingredient_text,
                "disqualified": False,
                "original": ingredient_text,
                "type": "fallback"
            })
        
        recipe['ingredients'] = parsed_ingredients
    
    return recipes


def _fallback_complex_parsing(ingredients: List[str]) -> List[Dict]:
    """
    Improved fallback: Consistent structure with basic measurement extraction.
    Ensures all ingredients have the same complete structure.
    """
    parsed = []
    
    for ingredient in ingredients:
        # Try basic measurement extraction
        quantity = None
        unit = None
        clean_ingredient = ingredient
        
        # Simple regex for basic quantity extraction
        import re
        quantity_match = re.match(r'(\d+(?:\.\d+)?(?:/\d+)?)\s*(\w+)?\s+(.+)', ingredient.strip())
        if quantity_match:
            quantity = quantity_match.group(1)
            unit = quantity_match.group(2) or ""
            clean_ingredient = quantity_match.group(3).strip()
        
        # Determine pantry staple status
        pantry_items = ["salt", "pepper", "oil", "flour", "sugar", "vanilla", "butter"]
        is_pantry = any(item in ingredient.lower() for item in pantry_items)
        
        # Determine if optional
        is_optional = any(phrase in ingredient.lower() for phrase in ["to taste", "optional", "if desired", "for garnish"])
        
        # Normalize unit to Instacart format
        normalized_unit = _normalize_to_instacart_unit(unit) if unit else "each"
        
        parsed.append({
            "quantity": quantity or "1",
            "unit": normalized_unit,
            "ingredient": clean_ingredient,
            "disqualified": is_optional,  # Disqualify optional items
            "original": ingredient,
            "type": "complex-fallback"
        })
    
    return parsed