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

LABELING RULES (refined for measurement prioritization):
SIMPLE ingredients have single, clear measurements:
- Basic quantities: "2 cups flour", "1 lb chicken", "3 eggs"  
- Single measurements: "1/2 cup milk", "2 tablespoons butter"
- Clear units: "1 teaspoon vanilla"

COMPLEX ingredients require intelligent parsing (ALWAYS label as complex):
- **Multiple measurements**: "12 ounces fresh fruit (about 2 cups)" 
- **Parenthetical measurements**: "8 3/4 ounces graham crackers (about 2 cups)"
- **Weight + volume combos**: "12 ounces heavy cream (about 1 1/2 cups)"
- **Package + unit descriptions**: "2 (8-ounce) packages cream cheese"
- **Nested measurements**: "1 (14.5 oz) can diced tomatoes"
- **Compound ingredients**: "salt and pepper to taste"
- **Alternative ingredients**: "milk or almond milk"
- **Vague quantities**: "3-4 pieces flank steak"
- **Range measurements**: "1.5 to 2 lb beef"
- **Cross-references**: "see recipe for marinade"

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
            parsed_ingredients[original_index] = parsed
        else:
            print(f"⚠️  Missing mapping for {map_key}")
    
    # Place complex results  
    for i, parsed in enumerate(complex_results):
        map_key = f"complex_{i}"
        if map_key in ingredient_map:
            original_index = ingredient_map[map_key]
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
    Fast regex-based parsing for simple ingredients.
    Based on proven patterns from original processor.
    """
    parsed = []
    
    for ingredient in ingredients:
        # Initialize with complete structure (ensures consistency with complex parsing)
        result = {
            "quantity": None,
            "unit": None, 
            "ingredient": ingredient,
            "store_quantity": "1",
            "store_unit": "count",
            "amount": None,
            "size": None,
            "additional_context": None,
            "alternatives": [],
            "pantry_staple": False,
            "optional": False,
            "disqualified": False,
            "original": ingredient
        }
        
        # Pattern 1: "2 cups flour" or "1 lb chicken"
        pattern1 = re.match(r'(\d+(?:\.\d+)?)\s+(\w+)\s+(.+)', ingredient.strip())
        if pattern1:
            quantity, unit, ingredient_name = pattern1.groups()
            
            # Smart store unit conversion for simple ingredients
            store_unit = unit
            if unit in ["cups", "tablespoons", "teaspoons", "tbsp", "tsp"]:
                # Volume measurements for dry goods → count (bags/containers)
                if any(dry in ingredient_name.lower() for dry in ["flour", "sugar", "salt", "pepper", "spice"]):
                    store_unit = "count"
                else:
                    store_unit = unit  # Keep volume for liquids
            elif unit in ["lb", "lbs", "pound", "pounds", "oz", "ounce", "ounces"]:
                store_unit = unit  # Keep weight units
            
            result.update({
                "quantity": quantity,
                "unit": unit,
                "ingredient": ingredient_name.strip(),
                "store_quantity": quantity,
                "store_unit": store_unit
            })
        
        # Pattern 2: "1/2 cup milk" (fractional measurements)
        pattern2 = re.match(r'(\d+/\d+)\s+(\w+)\s+(.+)', ingredient.strip())  
        if pattern2:
            quantity, unit, ingredient_name = pattern2.groups()
            
            # For fractional measurements, usually buy whole units
            store_unit = "count" if unit in ["cups", "tablespoons", "teaspoons"] else unit
            
            result.update({
                "quantity": quantity,
                "unit": unit,
                "ingredient": ingredient_name.strip(),
                "store_quantity": "1",
                "store_unit": store_unit
            })
        
        # Enhanced detection for simple ingredients
        ingredient_lower = ingredient.lower()
        
        # Check for pantry staples
        pantry_items = ["salt", "pepper", "oil", "flour", "sugar", "vanilla", "butter", "baking powder", "baking soda"]
        if any(item in ingredient_lower for item in pantry_items):
            result["pantry_staple"] = True
            
        # Check for optional items
        if any(phrase in ingredient_lower for phrase in ["to taste", "optional", "if desired", "for garnish"]):
            result["optional"] = True
            
        # Check for alternatives (basic detection)
        if " or " in ingredient_lower:
            parts = ingredient.split(" or ")
            if len(parts) == 2:
                result["ingredient"] = parts[0].strip()
                result["alternatives"] = [parts[1].strip()]
                
        # Check for additional context (basic prep instructions)
        prep_words = ["melted", "softened", "minced", "chopped", "diced", "sliced"]
        for prep in prep_words:
            if prep in ingredient_lower:
                result["additional_context"] = prep
            
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
    
    # Focused prompt for complex ingredients with smart measurement prioritization
    prompt = f"""Parse these COMPLEX ingredients into structured JSON format.

COMPLEX INGREDIENTS TO PROCESS:
{ingredients_text}

MEASUREMENT PRIORITIZATION RULES (CRITICAL - choose the right measurement for shopping):

**Multiple Measurements - Choose Primary Shopping Unit:**
- "12 ounces fresh fruit (about 2 cups)" → store_quantity: "12", store_unit: "ounces" (buy fruit by weight)
- "8 3/4 ounces graham crackers (about 2 cups)" → store_quantity: "8.75", store_unit: "ounces" (buy crackers by weight)  
- "12 ounces heavy cream (about 1 1/2 cups)" → store_quantity: "12", store_unit: "ounces" (buy cream by weight)
- "2 (8-ounce) packages cream cheese" → store_quantity: "2", store_unit: "count", amount: "8-ounce packages"

**Shopping Logic by Category:**
- **Produce/Meat**: Always use weight (ounces, pounds) over volume
- **Liquids**: Use weight for dairy/cream, volume for water-based
- **Packaged Items**: Use package count when specified in parentheses
- **Pantry Staples**: Use "count" for bottles/bags/containers

**Standard Conversions:**
- Fresh herbs → store_quantity: "1", store_unit: "count" (bunches)
- "X cloves garlic" → store_quantity: "1", store_unit: "count" (heads), amount: "X cloves"
- "Juice from 1 lemon" → store_quantity: "1", store_unit: "count" (whole lemons)
- Ranges "1.5 to 2 lb" → store_quantity: "1.75", store_unit: "lb" (average)
- Canned items "1 (14.5 oz) can" → store_quantity: "1", store_unit: "count", amount: "14.5 oz"

**Other Field Rules:**
- alternatives: ["alternative ingredient"] for "X or Y" patterns
- additional_context: Prep instructions ("melted", "softened", "at room temperature")
- optional: true ONLY for "to taste", "for garnish", "if desired"
- disqualified: true ONLY for clear cross-references like "see recipe", never for common store items
- pantry_staple: true for salt, pepper, oil, flour, sugar, vanilla, baking basics
- original: Keep exact original text

**Required JSON Structure (ALL ingredients must have ALL fields):**
[
  {{
    "quantity": "recipe amount",
    "unit": "recipe unit", 
    "ingredient": "clean name",
    "store_quantity": "shopping amount",
    "store_unit": "shopping unit",
    "amount": "additional size info",
    "size": "package size descriptor", 
    "additional_context": "prep instructions",
    "alternatives": ["alt1", "alt2"],
    "pantry_staple": boolean,
    "optional": boolean,
    "disqualified": boolean,
    "original": "exact original text"
  }}
]

Return valid JSON array in exact ingredient order."""

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for focused parsing
                    "max_tokens": 1500,
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
                "quantity": None,
                "unit": None,
                "ingredient": ingredient_text,
                "store_quantity": "1", 
                "store_unit": "count",
                "original": ingredient_text
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
        
        parsed.append({
            "quantity": quantity,
            "unit": unit,
            "ingredient": clean_ingredient,
            "store_quantity": quantity or "1",
            "store_unit": unit if unit and unit not in ["cups", "tablespoons", "teaspoons"] else "count",
            "amount": None,
            "size": None,
            "additional_context": None,
            "alternatives": [],
            "pantry_staple": is_pantry,
            "optional": is_optional,
            "disqualified": False,  # Never disqualify in fallback
            "original": ingredient
        })
    
    return parsed