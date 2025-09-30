"""
Stage 9A: Parallel Ingredient Parsing
Advanced hybrid parsing system that combines speed and accuracy.

Architecture:
1. LLM Spacing: 5 parallel calls to fix spacing issues from HTML parsing
2. Parallel Labeling: 5 concurrent LLM calls to label ingredients as "simple" or "complex"
3. Hybrid Processing: Simple ingredients → regex parsing, Complex ingredients → focused LLM parsing
4. Parallel Execution: All 5 recipes processed simultaneously for maximum speed

Performance: ~3-4 seconds total for ingredient processing
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
    # DEBUG: Track input to Stage 9A main function
    print(f"🔍 DEBUG STAGE 9A MAIN: Received {len(recipes)} recipes")
    for i, recipe in enumerate(recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG STAGE 9A MAIN INPUT {i+1}: {url} - {title}")
    
    if not recipes:
        return recipes
        
    api_key = openai_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("⚠️  No OpenAI API key found - using basic ingredient parsing")
        return _fallback_basic_parsing(recipes)
    
    print(f"\n🔄 STAGE 9B: Parallel Ingredient Processing ({len(recipes)} recipes)")
    print("=" * 60)
    
    total_start = time.time()
    
    # STAGE 1: LLM spacing fixes (5 parallel calls)
    print("🔧 Stage 1: LLM spacing fixes...")
    spacing_start = time.time()
    
    spaced_recipes = await process_all_spacing_llm_parallel(recipes, api_key)
    
    # DEBUG: Check after spacing
    print(f"🔍 DEBUG STAGE 9A SPACING: After spacing - {len(spaced_recipes)} recipes")
    for i, recipe in enumerate(spaced_recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG STAGE 9A SPACING {i+1}: {url} - {title}")
    
    spacing_time = time.time() - spacing_start
    print(f"   ✅ Spacing fixes completed: {spacing_time:.2f}s")
    
    # STAGE 2: Parallel ingredient labeling (5 concurrent LLM calls)
    print("🏷️  Stage 2: Parallel ingredient labeling...")
    labeling_start = time.time()
    
    labeled_recipes = await _label_all_ingredients_parallel(spaced_recipes, api_key)
    
    # DEBUG: Check after labeling
    print(f"🔍 DEBUG STAGE 9A LABELING: After labeling - {len(labeled_recipes)} recipes")
    for i, recipe in enumerate(labeled_recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG STAGE 9A LABELING {i+1}: {url} - {title}")
    
    labeling_time = time.time() - labeling_start
    print(f"   ✅ Labeling completed: {labeling_time:.2f}s")
    
    # STAGE 3: Parallel hybrid parsing (regex + focused LLM)
    print("🔧 Stage 3: Parallel hybrid parsing...")
    parsing_start = time.time()
    
    parsed_recipes = await _parse_all_ingredients_parallel(labeled_recipes, api_key)
    
    # DEBUG: Check after parsing
    print(f"🔍 DEBUG STAGE 9A PARSING: After parsing - {len(parsed_recipes)} recipes")
    for i, recipe in enumerate(parsed_recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG STAGE 9A PARSING {i+1}: {url} - {title}")
    
    parsing_time = time.time() - parsing_start
    total_time = time.time() - total_start
    
    print(f"   ✅ Parsing completed: {parsing_time:.2f}s")
    print(f"🎉 Total ingredient processing: {total_time:.2f}s")
    print("=" * 60)
    
    # DEBUG: Final Stage 9A output check
    print(f"🔍 DEBUG STAGE 9A FINAL: Returning {len(parsed_recipes)} recipes")
    for i, recipe in enumerate(parsed_recipes):
        url = recipe.get('source_url', 'NO_URL')
        title = recipe.get('title', 'NO_TITLE')[:50]
        print(f"🔍 DEBUG STAGE 9A FINAL {i+1}: {url} - {title}")
    
    return parsed_recipes


async def fix_ingredient_spacing_llm(ingredients: List[str], api_key: str) -> List[str]:
    """
    Fix spacing issues for a list of ingredients using LLM.
    Singular focus: correct spacing in ingredient strings from HTML parsing.
    """
    if not ingredients or not api_key:
        return ingredients
    
    # Create simple prompt focused ONLY on spacing
    ingredients_text = "\n".join([f"- {ing}" for ing in ingredients])
    
    prompt = f"""Fix spacing issues in these ingredient strings. Return the exact same strings with corrected spacing.

INGREDIENTS:
{ingredients_text}

COMMON ISSUES TO FIX:
- Missing spaces: "2Tbsp" → "2 Tbsp", "1/2cup" → "1/2 cup" 
- Missing spaces: "1tsp" → "1 tsp", "3large" → "3 large"
- Missing spaces: "cupbutter" → "cup butter", "ozheavy" → "oz heavy"

IMPORTANT: 
- Only fix spacing issues
- Keep all text exactly the same, just add missing spaces
- Don't change quantities, units, or ingredient names
- Don't remove or add any words

Return the corrected ingredients in the same order, one per line with dashes:
- [corrected ingredient 1]
- [corrected ingredient 2]
- [etc...]"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for simple spacing
                    "max_tokens": 400,
                    "temperature": 0.1,
                    "messages": [
                        {
                            "role": "system", 
                            "content": "You fix spacing issues in ingredient strings. Only add missing spaces, don't change anything else."
                        },
                        {"role": "user", "content": prompt}
                    ]
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Parse response - extract ingredients after dashes
            corrected = []
            for line in llm_response.split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    corrected.append(line[2:])  # Remove "- " prefix
            
            # Validate we got the same number back
            if len(corrected) == len(ingredients):
                return corrected
        
        # Fallback: return original ingredients if LLM fails
        return ingredients
        
    except Exception as e:
        print(f"   ⚠️  LLM spacing failed: {e}")
        return ingredients


async def process_recipe_spacing_llm(recipe: Dict, api_key: str) -> Dict:
    """
    Process spacing for all ingredients in a single recipe using LLM.
    Focus: fix spacing issues only.
    """
    ingredients = recipe.get('ingredients', [])
    if not ingredients:
        return recipe
    
    # Extract ingredient strings and preserve true originals
    ingredient_data = []
    ingredient_strings = []
    
    for ing in ingredients:
        if isinstance(ing, dict):
            # Preserve existing original if it exists, otherwise use ingredient
            true_original = ing.get('original', ing.get('ingredient', ''))
            current_ingredient = ing.get('ingredient', '')
            ingredient_data.append((true_original, current_ingredient))
            ingredient_strings.append(current_ingredient)
        else:
            ingredient_text = str(ing)
            ingredient_data.append((ingredient_text, ingredient_text))
            ingredient_strings.append(ingredient_text)
    
    # Fix spacing using LLM
    spaced_ingredient_strings = await fix_ingredient_spacing_llm(ingredient_strings, api_key)
    
    # Rebuild ingredients with corrected spacing
    spaced_ingredients = []
    for i, (true_original, _) in enumerate(ingredient_data):
        spaced_text = spaced_ingredient_strings[i] if i < len(spaced_ingredient_strings) else ingredient_strings[i]
        
        spaced_ingredients.append({
            'original': true_original,  # Preserve the TRUE original
            'spaced_formatted': spaced_text,
            'ingredient': spaced_text  # Will be parsed later
        })
    
    recipe['ingredients'] = spaced_ingredients
    return recipe


async def process_all_spacing_llm_parallel(recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Process spacing for all recipes using 5 parallel LLM calls.
    Each recipe gets one LLM call to fix spacing for all its ingredients.
    """
    if not api_key:
        print("⚠️  No OpenAI API key - skipping LLM spacing")
        return recipes
    
    # Create tasks for parallel processing (one per recipe)
    spacing_tasks = []
    for recipe in recipes:
        task = process_recipe_spacing_llm(recipe, api_key)
        spacing_tasks.append(task)
    
    # Execute all spacing fixes in parallel
    results = await asyncio.gather(*spacing_tasks, return_exceptions=True)
    
    # Handle exceptions
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"⚠️  LLM spacing failed for recipe {i+1}: {result}")
            # Fallback: preserve originals without spacing fixes
            original_recipe = recipes[i]
            ingredients = original_recipe.get('ingredients', [])
            fallback_ingredients = []
            
            for ing in ingredients:
                if isinstance(ing, dict):
                    true_original = ing.get('original', ing.get('ingredient', ''))
                    ingredient_text = ing.get('ingredient', '')
                else:
                    true_original = str(ing)
                    ingredient_text = str(ing)
                    
                fallback_ingredients.append({
                    'original': true_original,  # Preserve TRUE original
                    'spaced_formatted': ingredient_text,  # Same as current on error
                    'ingredient': ingredient_text
                })
            
            original_recipe['ingredients'] = fallback_ingredients
            final_results.append(original_recipe)
        else:
            final_results.append(result)
    
    return final_results


async def _label_all_ingredients_parallel(recipes: List[Dict], api_key: str) -> List[Dict]:
    """
    Stage 2: Label all ingredients across all recipes in parallel.
    5 concurrent LLM calls for speed.
    """
    labeling_tasks = []
    
    for i, recipe in enumerate(recipes):
        print(f"   📝 Starting labeling for recipe {i+1}: {recipe.get('title', 'Unknown')}")
        task = _label_recipe_ingredients(recipe, api_key)
        labeling_tasks.append(task)
    
    # Execute all labeling in parallel
    labeled_recipes = await asyncio.gather(*labeling_tasks, return_exceptions=True)
    
    # Handle any exceptions
    results = []
    for i, result in enumerate(labeled_recipes):
        if isinstance(result, Exception):
            recipe_title = recipes[i].get('title', 'Unknown')
            print(f"💥 PARALLEL EXCEPTION for recipe {i+1} ({recipe_title}): {result}")
            print(f"      Exception type: {type(result).__name__}")
            # Keep original recipe with basic labeling
            results.append(_fallback_ingredient_labeling(recipes[i]))
        else:
            print(f"   ✅ Recipe {i+1} labeling completed successfully")
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
    
    print(f"   🔍 Extracted {len(ingredient_strings)} ingredient strings:")
    for i, ing_str in enumerate(ingredient_strings):
        print(f"      {i+1}. '{ing_str}'")
    
    # Create robust labeling prompt with few-shot examples and validation
    ingredients_text = "\n".join([f"- {ing}" for ing in ingredient_strings])
    
    prompt = f"""Label each ingredient as "simple" or "complex" for parsing difficulty.

CRITICAL TRAINING EXAMPLES (learn these patterns):

Example 1:
Input ingredients:
- 2 cups flour
- 4 whole eggs  
- 1 box graham crackers
Expected output: ["simple", "complex", "complex"]
Reasoning: "cups" is accepted unit = simple, "whole eggs" has descriptor = complex, "box" not accepted unit = complex

Example 2:
Input ingredients:
- 3 each eggs
- 1 pound butter
- one box of graham crackers
Expected output: ["simple", "simple", "complex"] 
Reasoning: "each" accepted = simple, "pound" accepted = simple, "box" not accepted = complex

Example 3:
Input ingredients:
- 15 graham crackers
- salt to taste
- 2 tablespoons olive oil
Expected output: ["complex", "complex", "simple"]
Reasoning: no unit specified = complex, "to taste" = complex, "tablespoons" accepted = simple

NOW LABEL THESE {len(ingredient_strings)} INGREDIENTS (return exactly {len(ingredient_strings)} labels):
{ingredients_text}

ACCEPTED INSTACART UNITS ONLY:
cup, tablespoon, teaspoon, ounce, pound, gram, kilogram, gallon, liter, pint, quart, can, each, bunch, head, large, medium, small, package

SIMPLE PATTERN: [number] [accepted_unit] [ingredient_name]
✓ "2 cups flour" ✓ "3 each eggs" ✓ "1 pound chicken" ✓ "1 tablespoon salt" ✓ "2 cans tomatoes"

COMPLEX PATTERNS (mark as complex):
✗ "4 whole eggs" → has "whole" descriptor, needs "each"
✗ "1 box graham crackers" → "box" not in accepted units  
✗ "one box of graham crackers" → "box" not in accepted units
✗ "15 graham crackers" → no unit specified
✗ "salt to taste" → subjective amount
✗ "juice from 1 lemon" → descriptive quantity
✗ "Crust" → single item without quantity
✗ "1 jar sauce" → "jar" not accepted unit
✗ "1 bottle oil" → "bottle" not accepted unit
✗ "1 container yogurt" → "container" not accepted unit
✗ "4(8 ounce) packages cream cheese" → parenthetical + unit combo
✗ "2 1/2 ounces butter (about 5 tablespoons; 70 g)" → multiple measurements
✗ "12 cookies" → no unit, item count
✗ "6 slices bread" → no standard unit
✗ "12 ounces fresh fruit (about 2 cups)" → multiple measurements
✗ "half a lime" → descriptive quantity
✗ "1 dash salt" → non-standard unit
✗ "splash of vinegar" → non-standard unit
✗ "pinch of salt" → non-standard unit
✗ "salt and pepper to taste" → compound + subjective
✗ "1-2 pounds beef" → range

CRITICAL DETECTION RULES:
- If you see "box", "jar", "bottle", "container", "whole", "dash", "pinch", "splash" → COMPLEX
- If you see "to taste", "as needed", "if desired" → COMPLEX  
- If no unit specified (just count + ingredient) → COMPLEX
- If parentheses with measurements → COMPLEX
- If descriptive words before ingredient → COMPLEX

Return JSON object with labels array: {{"labels": ["simple", "complex", "simple", ...]}}
Order must match ingredient list exactly."""

    try:
        print(f"   🔄 Labeling {len(ingredient_strings)} ingredients...")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            request_start = time.time()
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for labeling
                    "max_tokens": 1000,  # Doubled for recipes with 20+ ingredients
                    "temperature": 0.3,  # Higher for better pattern recognition
                    "response_format": {"type": "json_object"},  # Force JSON output
                    "messages": [
                        {"role": "system", "content": "You are a precise ingredient labeling system. Follow the rules EXACTLY as specified. Return only valid JSON with exactly the requested number of labels."},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            request_time = time.time() - request_start
            print(f"   ⏱️  API call took {request_time:.2f}s, status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Parse JSON object response
            try:
                response_obj = json.loads(llm_response)
                labels = response_obj.get('labels', [])
                
                # Validate labels match ingredient count
                if len(labels) == len(ingredient_strings):
                    # Response validation - catch obvious mistakes
                    validated_labels = []
                    corrections_made = 0
                    
                    for i, (ingredient, label) in enumerate(zip(ingredient_strings, labels)):
                        ingredient_lower = ingredient.lower()
                        corrected_label = label
                        
                        # Force complex for known problematic patterns
                        if (('whole' in ingredient_lower or 
                             'box' in ingredient_lower or
                             'jar' in ingredient_lower or
                             'bottle' in ingredient_lower or
                             'container' in ingredient_lower or
                             'stick' in ingredient_lower or  # "1 stick butter"
                             'sticks' in ingredient_lower or
                             'clove' in ingredient_lower or  # "2 cloves garlic"
                             'cloves' in ingredient_lower or
                             'one' in ingredient_lower or
                             'two' in ingredient_lower or
                             'dash' in ingredient_lower or
                             'pinch' in ingredient_lower or
                             'splash' in ingredient_lower or
                             'to taste' in ingredient_lower or
                             'as needed' in ingredient_lower) and label == "simple"):
                            
                            corrected_label = "complex"
                            print(f"   🔧 CORRECTED: '{ingredient}' → complex (pattern)")
                            corrections_made += 1
                        
                        # Force complex for single words without quantities (Crust, Filling, etc.)
                        import re
                        if (re.match(r'^[A-Za-z]+$', ingredient.strip()) and label == "simple"):
                            corrected_label = "complex" 
                            print(f"   🔧 CORRECTED: '{ingredient}' → complex (single-word)")
                            corrections_made += 1
                        
                        # Force complex for parenthetical measurements
                        if ('(' in ingredient_lower and ')' in ingredient_lower and label == "simple"):
                            corrected_label = "complex"
                            print(f"   🔧 CORRECTED: '{ingredient}' → complex (parentheses)")
                            corrections_made += 1
                        
                        # Force complex for count-only patterns (no units)
                        if (re.match(r'^\d+\s+\w+', ingredient_lower) and 
                            not any(unit in ingredient_lower for unit in ['cup', 'tablespoon', 'teaspoon', 'ounce', 'pound', 'gram', 'gallon', 'liter', 'pint', 'quart', 'can', 'each', 'bunch', 'head', 'package']) and 
                            label == "simple"):
                            
                            corrected_label = "complex"
                            print(f"   🔧 CORRECTED: '{ingredient}' → complex (count-only)")
                            corrections_made += 1
                        
                        validated_labels.append(corrected_label)
                    
                    if corrections_made > 0:
                        print(f"   ✅ Validation fixed {corrections_made} mislabels")
                    
                    # Add validated labels to recipe
                    recipe['ingredient_labels'] = validated_labels
                    return recipe
                else:
                    print(f"   💥 VALIDATION FAILED:")
                    print(f"      Expected {len(ingredient_strings)} labels, got {len(labels)}")
                    print(f"      Labels: {labels}")
                    print(f"   🔍 DEBUGGING MISMATCH:")
                    print(f"      Raw LLM response: {llm_response}")
                    print(f"   🔍 INGREDIENT vs LABEL MAPPING:")
                    for i, ingredient in enumerate(ingredient_strings):
                        if i < len(labels):
                            print(f"      {i+1:2d}. '{ingredient}' → {labels[i]}")
                        else:
                            print(f"      {i+1:2d}. '{ingredient}' → *** MISSING LABEL ***")
                    
                    # Don't mask the problem - let it fall through to actual debugging
            except json.JSONDecodeError as json_err:
                print(f"   💥 JSON DECODE FAILED:")
                print(f"      Error: {json_err}")
                print(f"      Raw response: {llm_response[:200]}...")
                print(f"      Response length: {len(llm_response)} chars")
                pass
        else:
            # Non-200 status code
            print(f"   💥 API ERROR:")
            print(f"      Status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"      Error: {error_data}")
            except:
                print(f"      Raw response: {response.text[:200]}...")
        
        # Fallback if labeling fails
        print(f"   🔄 FALLING BACK TO SIMPLE LABELING for recipe: {recipe.get('title', 'Unknown')}")
        return _fallback_ingredient_labeling(recipe)
        
    except Exception as e:
        print(f"   💥 EXCEPTION in ingredient labeling:")
        print(f"      Error type: {type(e).__name__}")
        print(f"      Error message: {str(e)}")
        print(f"      Recipe: {recipe.get('title', 'Unknown')}")
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
    
    # DEBUG: Check what we're working with
    print(f"🔍 DEBUG PARSE EXCEPTION HANDLING: Processing {len(parsed_recipes)} results")
    print(f"🔍 DEBUG PARSE EXCEPTION HANDLING: Have {len(labeled_recipes)} labeled recipes")
    
    for i, result in enumerate(parsed_recipes):
        if isinstance(result, Exception):
            print(f"⚠️  Parsing failed for recipe {i+1}: {result}")
            
            # DEBUG: Show what we're substituting
            original_recipe = labeled_recipes[i]
            original_url = original_recipe.get('source_url', 'NO_URL')
            original_title = original_recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG SUBSTITUTION: Recipe {i+1} failed, substituting with: {original_url} - {original_title}")
            
            # Keep original recipe with basic ingredients
            results.append(labeled_recipes[i])
        else:
            # DEBUG: Show successful parse
            if isinstance(result, dict):
                result_url = result.get('source_url', 'NO_URL')
                result_title = result.get('title', 'NO_TITLE')[:50]
                print(f"🔍 DEBUG SUCCESS: Recipe {i+1} parsed successfully: {result_url} - {result_title}")
            
            results.append(result)
    
    # DEBUG: Final results check
    print(f"🔍 DEBUG PARSE FINAL: Returning {len(results)} results")
    for i, recipe in enumerate(results):
        if isinstance(recipe, dict):
            url = recipe.get('source_url', 'NO_URL')
            title = recipe.get('title', 'NO_TITLE')[:50]
            print(f"🔍 DEBUG PARSE RESULT {i+1}: {url} - {title}")
    
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
            "pantry_staple": is_pantry_staple,
            "category": None  # Will be filled by Stage 9B categorization
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
- "1 box crackers" → quantity: "1", unit: "package", ingredient: "crackers", pantry_staple: false
- "4 whole eggs" → quantity: "4", unit: "each", ingredient: "eggs", pantry_staple: false

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
        print(f"   ⚠️  Error type: {type(e).__name__}")
        print(f"   ⚠️  Error details: {str(e)[:200]}")
        return _fallback_complex_parsing(ingredients)


def _fallback_ingredient_labeling(recipe: Dict) -> Dict:
    """Fallback: Label all ingredients as complex (safer than simple)."""
    ingredients = recipe.get('ingredients', [])
    
    print(f"   🔧 FALLBACK: Marking all {len(ingredients)} ingredients as COMPLEX")
    
    # Mark everything as complex - LLM parsing handles all cases better than regex
    recipe['ingredient_labels'] = ["complex"] * len(ingredients)
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
                "category": None,  # Will be filled by Stage 9B categorization
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
            "category": None,  # Will be filled by Stage 9B categorization
            "type": "complex-fallback"
        })
    
    return parsed