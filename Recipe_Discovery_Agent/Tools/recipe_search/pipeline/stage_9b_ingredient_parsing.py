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
    
    # STAGE 1: Parallel spacing fixes (5 concurrent LLM calls)
    print("✂️  Stage 1: Parallel spacing fixes...")
    spacing_start = time.time()
    
    spaced_recipes = await _fix_spacing_all_recipes_parallel(recipes, api_key)
    
    spacing_time = time.time() - spacing_start
    print(f"   ✅ Spacing fixes completed: {spacing_time:.2f}s")
    
    # STAGE 2: Parallel ingredient labeling (5 concurrent LLM calls)
    print("🏷️  Stage 2: Parallel ingredient labeling...")
    labeling_start = time.time()
    
    labeled_recipes = await _label_all_ingredients_parallel(spaced_recipes, api_key)
    
    labeling_time = time.time() - labeling_start
    print(f"   ✅ Labeling completed: {labeling_time:.2f}s")
    
    # STAGE 3: Parallel hybrid parsing (regex + focused LLM)
    print("🔧 Stage 3: Parallel hybrid parsing...")
    parsing_start = time.time()
    
    parsed_recipes = await _parse_all_ingredients_parallel(labeled_recipes, api_key)
    
    parsing_time = time.time() - parsing_start
    total_time = time.time() - total_start
    
    print(f"   ✅ Parsing completed: {parsing_time:.2f}s")
    print(f"🎉 Total ingredient processing: {total_time:.2f}s")
    print("=" * 60)
    
    return parsed_recipes


async def _fix_spacing_all_recipes_parallel(recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Stage 1: Fix ingredient spacing across all recipes in parallel.
    5 concurrent LLM calls for spacing fixes only.
    """
    spacing_tasks = []
    
    for recipe in recipes:
        task = _fix_recipe_ingredient_spacing(recipe, api_key)
        spacing_tasks.append(task)
    
    # Execute all spacing fixes in parallel
    spaced_recipes = await asyncio.gather(*spacing_tasks, return_exceptions=True)
    
    # Handle any exceptions
    results = []
    for i, result in enumerate(spaced_recipes):
        if isinstance(result, Exception):
            print(f"⚠️  Spacing fix failed for recipe {i+1}: {result}")
            # Keep original recipe unchanged
            results.append(recipes[i])
        else:
            results.append(result)
    
    return results


async def _label_all_ingredients_parallel(recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Stage 2: Label all ingredients across all recipes in parallel.
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


async def _fix_recipe_ingredient_spacing(recipe: Dict, api_key: str) -> Dict:
    """
    Fix spacing issues in ingredients for a single recipe.
    Uses LLM to add proper spaces between numbers, units, and ingredient names.
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
    
    # Create spacing fix prompt with examples
    ingredients_text = "\n".join([f"- {ing}" for ing in ingredient_strings])
    
    prompt = f"""Fix spacing in ingredient strings to follow the pattern: [quantity] [unit] [ingredient name]

TARGET PATTERN: [quantity] [unit] [ingredient name]
- Example: "1 cup flour", "2 tablespoons butter", "½ teaspoon salt"

SPACING PRINCIPLES:
- Separate numbers from units with space
- Separate units from ingredient names with space  
- Remove dots after unit abbreviations AND add space after
- Split compound words where unit+ingredient are stuck together
- Keep properly spaced ingredients unchanged

CRITICAL PATTERNS TO FIX:
"12oz.storebought" → "12 oz storebought" (remove dot, add spaces)
"1/2cupchopped" → "1/2 cup chopped" (fraction+unit+ingredient)
"6Tbsp.butter" → "6 Tbsp butter" (number+unit.+ingredient)
"½cupbutter" → "½ cup butter" (fraction+unit+ingredient)
"2tablespoonssugar" → "2 tablespoons sugar" (number+unit+ingredient)

BEFORE → AFTER EXAMPLES:
"12oz.storebought gingersnaps" → "12 oz storebought gingersnaps"
"1/2cupchopped pecans" → "1/2 cup chopped pecans"
"6Tbsp.butter, melted" → "6 Tbsp butter, melted"
"1 ½cupsgraham cracker crumbs" → "1 ½ cups graham cracker crumbs"
"¼cupfinely ground walnuts" → "¼ cup finely ground walnuts"
"1tablespooncinnamon sugar" → "1 tablespoon cinnamon sugar"
"½cupbutter, melted" → "½ cup butter, melted"
"3(8 ounce) packagescream cheese" → "3 (8 ounce) packages cream cheese"
"¾cupwhite sugar" → "¾ cup white sugar"
"1teaspoonvanilla extract" → "1 teaspoon vanilla extract"
"1cupheavy whipping cream" → "1 cup heavy whipping cream"
"3largeeggs, slightly beaten" → "3 large eggs, slightly beaten"

MORE CRITICAL EXAMPLES:
"1teaspoonvanilla" → "1 teaspoon vanilla"
"3largeeggs" → "3 large eggs"
"¾cupwhite" → "¾ cup white"
"2oz.cream" → "2 oz cream"
"1tbsp.olive" → "1 tbsp olive"

ALREADY CORRECT (no changes needed):
"4 (8 ounce) packages cream cheese"
"2 tablespoons butter, melted"
"1 cup heavy whipping cream"

INGREDIENTS TO FIX:
{ingredients_text}

Return the corrected ingredients, one per line, same order:"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for simple spacing task
                    "max_tokens": 500,
                    "temperature": 0.0,  # More deterministic
                    "messages": [
                        {"role": "system", "content": "You are an expert at fixing spacing in ingredient text. Pay special attention to: 1) removing dots after units AND adding spaces, 2) separating fractions from units, 3) splitting compound unit+ingredient words. Use the examples as guides and apply reasoning to similar patterns. Only fix spacing - don't change words, quantities, or units."},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Parse the response - split by lines and clean up
            fixed_ingredients = []
            for line in llm_response.split('\n'):
                line = line.strip()
                # Remove list markers if present
                if line.startswith('- '):
                    line = line[2:]
                elif line.startswith('• '):
                    line = line[2:]
                if line:
                    fixed_ingredients.append(line)
            
            # Update recipe with fixed ingredients if we got the right count
            if len(fixed_ingredients) == len(ingredient_strings):
                # Convert ingredients to dicts with original and spaced_formatted versions
                spaced_ingredients = []
                for i, spaced_ingredient in enumerate(fixed_ingredients):
                    original_ingredient = ingredient_strings[i]
                    spaced_ingredients.append({
                        'original': original_ingredient,
                        'spaced_formatted': spaced_ingredient,
                        'ingredient': spaced_ingredient  # Will be parsed later
                    })
                recipe['ingredients'] = spaced_ingredients
                return recipe
        
        # Fallback: return original recipe if spacing fix fails
        print(f"   ⚠️  Spacing fix failed for {recipe.get('title', 'Unknown')}")
        # Convert to dict format but keep original spacing
        fallback_ingredients = []
        for ingredient_string in ingredient_strings:
            fallback_ingredients.append({
                'original': ingredient_string,
                'spaced_formatted': ingredient_string,  # Same as original when spacing fails
                'ingredient': ingredient_string
            })
        recipe['ingredients'] = fallback_ingredients
        return recipe
        
    except Exception as e:
        print(f"   ⚠️  Spacing fix error: {e}")
        # Convert to dict format but keep original spacing
        ingredients = recipe.get('ingredients', [])
        ingredient_strings = []
        for ing in ingredients:
            if isinstance(ing, dict):
                ingredient_strings.append(ing.get('ingredient', ''))
            else:
                ingredient_strings.append(str(ing))
        
        fallback_ingredients = []
        for ingredient_string in ingredient_strings:
            fallback_ingredients.append({
                'original': ingredient_string,
                'spaced_formatted': ingredient_string,  # Same as original on error
                'ingredient': ingredient_string
            })
        recipe['ingredients'] = fallback_ingredients
        return recipe


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

COMPLEX ingredients need conversion:
- **Single items without quantity**: "Crust", "Topping", "Glaze" (needs default: "1 each" or "1 package")
- **Multiple unit patterns**: "4(8 ounce) packages cream cheese" (parenthetical + unit combo)
- **Multiple measurements in parentheses**: "2 1/2 ounces butter (about 5 tablespoons; 70 g)" (choose best unit)
- **Subjective amounts**: "salt to taste", "Kosher salt, to taste", "pepper as needed" (convert to "1 each")
- **Countable items with names as units**: "15 graham crackers", "12 cookies", "6 slices bread" (convert to packages/each)  
- **Multiple measurements**: "12 ounces fresh fruit (about 2 cups)" (needs unit selection)
- **Descriptive quantities**: "juice from 1 lemon", "half a lime" (convert to "1 each")
- **Non-standard units**: "1 dash salt", "splash of vinegar", "pinch of salt" (convert to "1 each")
- **Compound ingredients**: "salt and pepper to taste" (split and process)
- **Ranges**: "1-2 pounds beef" (convert to average)

CRITICAL: If unit NOT in accepted list OR has parenthetical measurements OR contains "to taste", mark as COMPLEX!

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
        # Extract ingredient text and preserve original/spaced_formatted fields
        if isinstance(ingredient, dict):
            original_text = ingredient.get('original', '')
            spaced_text = ingredient.get('spaced_formatted', ingredient.get('ingredient', ''))
            processed = spaced_text.strip()  # Use the LLM-spaced version for parsing
        else:
            # Fallback for string format
            original_text = str(ingredient)
            spaced_text = str(ingredient)
            processed = ingredient.strip()
        
        # Detect pantry staples
        pantry_staples = ['salt', 'pepper', 'butter', 'oil', 'olive oil', 'sugar', 'flour', 'vanilla', 'baking powder', 'baking soda']
        is_pantry_staple = any(staple in processed.lower() for staple in pantry_staples)
        
        # Initialize with simplified Instacart-compatible structure
        result = {
            "quantity": None,
            "unit": None, 
            "ingredient": processed,  # Will be updated with clean ingredient name
            "disqualified": False,
            "original": original_text,
            "spaced_formatted": spaced_text,
            "pantry_staple": is_pantry_staple
        }
        
        # SIMPLIFIED PREPROCESSING (since LLM handles spacing)
        # Only need: unicode fractions, mixed numbers, dot cleanup
        
        # Convert unicode fractions
        for unicode_frac, decimal in fraction_map.items():
            processed = processed.replace(unicode_frac, decimal)
        
        # Convert mixed numbers written as improper fractions (e.g., "11/2" → "1.5", "21/4" → "2.25")
        def convert_mixed_fraction(match):
            numerator = int(match.group(1))
            denominator = int(match.group(2))
            
            # Only convert if it looks like a mixed number (numerator > denominator and common denominators)
            if numerator > denominator and denominator in [2, 3, 4, 8]:
                whole_part = numerator // denominator
                fraction_part = numerator % denominator
                decimal_value = whole_part + (fraction_part / denominator)
                return str(decimal_value)
            else:
                # Keep as fraction if it doesn't look like a mixed number
                return f"{numerator}/{denominator}"
        
        # Apply mixed number conversion
        processed = re.sub(r'(\d+)/(\d+)', convert_mixed_fraction, processed)
        
        # Remove dots after common unit abbreviations: "tsp." → "tsp", "oz." → "oz"
        unit_abbreviations = ['tsp', 'tbsp', 'oz', 'lb', 'lbs', 'pt', 'qt', 'gal', 'ml', 'kg', 'g']
        for abbrev in unit_abbreviations:
            processed = re.sub(f'({abbrev})\\.', r'\1', processed, flags=re.IGNORECASE)
        
        # SIMPLE PARSING (since LLM pre-handled spacing)
        # Now we can use simple regex on clean, properly spaced ingredients
        
        # Simple unit extraction (since spacing is clean)
        def extract_clean_unit(text):
            """Extract unit from clean, spaced text"""
            valid_units = [
                'cup', 'cups', 'c', 'tablespoon', 'tablespoons', 'tbsp', 'tb', 'tbs', 
                'teaspoon', 'teaspoons', 'tsp', 'ts', 'tspn', 'gallon', 'gallons', 'gal', 'gals',
                'pint', 'pints', 'pt', 'pts', 'quart', 'quarts', 'qt', 'qts', 
                'liter', 'liters', 'litres', 'l', 'milliliter', 'milliliters', 'millilitres', 'ml', 'mls',
                'ounce', 'ounces', 'oz', 'pound', 'pounds', 'lb', 'lbs',
                'gram', 'grams', 'g', 'gs', 'kilogram', 'kilograms', 'kg', 'kgs',
                'can', 'cans', 'bunch', 'bunches', 'head', 'heads',
                'large', 'medium', 'small', 'each', 'package', 'packages', 'packet', 'packets'
            ]
            
            words = text.split()
            if words:
                first_word = words[0].lower()
                if first_word in valid_units:
                    return first_word, ' '.join(words[1:])
            
            return None, text
        
        # Try to extract quantity (including mixed numbers like "1 1/2")
        quantity_match = re.match(r'(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s+(.+)', processed)
        if quantity_match:
            quantity_str, remainder = quantity_match.groups()
            
            # Convert mixed numbers to decimals
            def convert_mixed_to_decimal(qty_str):
                # Handle mixed numbers like "1 1/2"
                if ' ' in qty_str and '/' in qty_str:
                    parts = qty_str.split(' ')
                    whole = int(parts[0])
                    frac_parts = parts[1].split('/')
                    numerator = int(frac_parts[0])
                    denominator = int(frac_parts[1])
                    return str(whole + (numerator / denominator))
                # Handle simple fractions like "1/2"
                elif '/' in qty_str:
                    frac_parts = qty_str.split('/')
                    numerator = int(frac_parts[0])
                    denominator = int(frac_parts[1])
                    return str(numerator / denominator)
                # Handle whole numbers and decimals
                else:
                    return qty_str
            
            converted_quantity = convert_mixed_to_decimal(quantity_str)
            
            # Extract valid unit from remainder  
            unit, remaining_ingredient = extract_clean_unit(remainder)
            
            if unit:
                # Normalize to Instacart accepted units (use first variant)
                normalized_unit = _normalize_to_instacart_unit(unit)
                
                result.update({
                    "quantity": converted_quantity,
                    "unit": normalized_unit,
                    "ingredient": remaining_ingredient.strip()
                })
        
        # Special Pattern: "N (size) packages" or "N cans" - extract count and unit
        elif re.match(r'(\d+)\s*\([^)]+\)\s*(\w+)\s+(.+)', processed):
            match = re.match(r'(\d+)\s*\([^)]+\)\s*(\w+)\s+(.+)', processed)
            quantity, unit, ingredient_name = match.groups()
            
            # Validate and normalize package-type units  
            valid_unit, _ = extract_clean_unit(unit)
            if valid_unit:
                normalized_unit = _normalize_to_instacart_unit(valid_unit)
                
                result.update({
                    "quantity": quantity,
                    "unit": normalized_unit,
                    "ingredient": ingredient_name.strip()
                })
        
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
- For multiple measurements, choose the most practical Instacart unit (tablespoon for butter, ounce for most others)
- For subjective amounts ("to taste", "half a lime"), use default quantity: "1", unit: "each" 
- Use first variant only (cup not cups, ounce not ounces)
- Add pantry_staple: true for common items (salt, butter, olive oil, pepper, sugar, flour, etc.)
- Never set disqualified: true - all items should be orderable

CONVERSION EXAMPLES:
- "Crust" → quantity: "1", unit: "each", ingredient: "pie crust", pantry_staple: false
- "Topping" → quantity: "1", unit: "package", ingredient: "topping", pantry_staple: false
- "2 1/2 ounces unsalted butter (about 5 tablespoons; 70 g)" → quantity: "5", unit: "tablespoon", ingredient: "unsalted butter", pantry_staple: true
- "Kosher salt, to taste" → quantity: "1", unit: "each", ingredient: "kosher salt", pantry_staple: true
- "12 ounces fruit (about 2 cups)" → quantity: "12", unit: "ounce", pantry_staple: false
- "juice from 1 lemon" → quantity: "1", unit: "each", ingredient: "lemon", pantry_staple: false
- "salt to taste" → quantity: "1", unit: "each", ingredient: "salt", pantry_staple: true
- "half a lime" → quantity: "1", unit: "each", ingredient: "lime", pantry_staple: false
- "2 (8-oz) packages cream cheese" → quantity: "2", unit: "package", pantry_staple: false
- "15 graham crackers" → quantity: "1", unit: "package", ingredient: "graham crackers", pantry_staple: false
- "12 cookies" → quantity: "1", unit: "package", ingredient: "cookies", pantry_staple: false
- "6 slices bread" → quantity: "1", unit: "each", ingredient: "loaf bread", pantry_staple: false

JSON FORMAT:
[{{"quantity": "amount", "unit": "instacart_unit", "ingredient": "name", "pantry_staple": boolean, "original": "text"}}]"""

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
                        {"role": "system", "content": "You convert complex ingredients to Instacart-compatible format. For single items without quantities (like 'Crust', 'Topping'), always add quantity: '1' and unit: 'each' or 'package'. For subjective amounts ('to taste', 'half a lime'), use quantity: '1' and unit: 'each'. For multiple units, choose the most practical one (tablespoon for butter). Mark common pantry items (salt, butter, oil, etc.) as pantry_staple: true. Never disqualify items - all should be orderable."},
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
            # Detect pantry staples for fallback
            pantry_staples = ['salt', 'pepper', 'butter', 'oil', 'olive oil', 'sugar', 'flour', 'vanilla', 'baking powder', 'baking soda']
            is_pantry_staple = any(staple in ingredient_text.lower() for staple in pantry_staples)
            
            parsed_ingredients.append({
                "quantity": "1",
                "unit": "each",
                "ingredient": ingredient_text,
                "original": ingredient_text,
                "pantry_staple": is_pantry_staple,
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
        
        # Normalize unit to Instacart format
        normalized_unit = _normalize_to_instacart_unit(unit) if unit else "each"
        
        parsed.append({
            "quantity": quantity or "1",
            "unit": normalized_unit,
            "ingredient": clean_ingredient,
            "pantry_staple": is_pantry,
            "original": ingredient,
            "type": "complex-fallback"
        })
    
    return parsed