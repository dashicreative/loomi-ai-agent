"""
Store Compatibility Ingredient Processor

Background service for converting recipe ingredients from JSON-LD format 
to shopping-cart compatible format. This runs AFTER recipe discovery when 
users save recipes, ensuring instant recipe browsing while maintaining 
perfect shopping cart functionality.

Extracted from Recipe Discovery Agent pipeline for performance optimization.
"""

import httpx
import json
import os
import time
from typing import Dict, List, Optional


async def process_ingredients_with_llm(raw_ingredients: List[str], anthropic_key: str = None) -> List[Dict]:
    """
    Convert raw JSON-LD ingredients to shopping-cart compatible format.
    
    This function contains all the hard-won edge case logic and LLM prompt 
    engineering developed during recipe discovery optimization. It handles:
    - Garlic cloves → head conversion
    - Fractional items → round up logic  
    - Small liquid quantities → bottle conversion
    - Complex nested measurements
    - Alternative ingredient handling
    - Cross-reference disqualification
    
    Performance: ~8 seconds per recipe (acceptable for background processing)
    
    Args:
        raw_ingredients: List of ingredient strings from JSON-LD extraction
        anthropic_key: Optional API key, uses env var if not provided
        
    Returns:
        List of structured shopping-compatible ingredient dictionaries
    """
    if not raw_ingredients:
        return []
    
    # Get API key from environment if not provided
    api_key = anthropic_key or os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    
    # Prepare ingredient list for LLM processing
    ingredients_text = "\n".join([f"- {ing}" for ing in raw_ingredients])
    
    # Log processing details for background job monitoring
    total_ingredient_chars = sum(len(ing) for ing in raw_ingredients)
    print(f"🔄 Background conversion: {len(raw_ingredients)} ingredients ({total_ingredient_chars} chars)")
    
    # COMPREHENSIVE SHOPPING-AWARE PROMPT
    # This prompt contains all edge case logic developed during optimization
    prompt = f"""Process these recipe ingredients into structured JSON format using shopping-aware parsing logic.

INGREDIENTS TO PROCESS:
{ingredients_text}

Apply these EXACT conversion rules:

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

OTHER FIELD PARSING:
- alternatives: Split "milk or almond milk" → alternatives: ["almond milk"]
- additional_context: Prep state ("melted", "minced", "softened", "store-bought", "for garnish")
- optional: true for "to taste"/garnish/serving items
- disqualified: true for "see recipe"/homemade/cross-references
- pantry_staple: true for salt/pepper/oil/flour/sugar/basic spices
- original: Original text exactly as written

Return JSON array:
[
  {{
    "quantity": "recipe quantity",
    "unit": "recipe unit", 
    "ingredient": "clean ingredient name",
    "store_quantity": "shopping quantity",
    "store_unit": "shopping unit",
    "amount": "recipe amount if different",
    "size": "size descriptor",
    "additional_context": "prep state",
    "alternatives": ["alternative options"],
    "pantry_staple": boolean,
    "optional": boolean,
    "disqualified": boolean,
    "original": "original text"
  }}
]"""

    # Calculate prompt metrics for monitoring
    prompt_chars = len(prompt)
    estimated_tokens = prompt_chars // 4
    print(f"📊 LLM prompt: {prompt_chars:,} chars (~{estimated_tokens:,} tokens)")

    try:
        print(f"🚀 Making background LLM API call...")
        api_start = time.time()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 2000,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "user", "content": f"You are an ingredient parsing specialist. Return only valid JSON array.\n\n{prompt}"}
                    ]
                }
            )
        
        api_time = time.time() - api_start
        print(f"⏱️  Background LLM call completed: {api_time:.2f}s")
        
        if response.status_code != 200:
            print(f"❌ API error: {response.status_code} - {response.text}")
            # Return basic structure for fallback
            return [{"quantity": None, "unit": None, "ingredient": ing, "original": ing} for ing in raw_ingredients]
        
        data = response.json()
        llm_response = data['content'][0]['text'].strip()
        
        # Parse JSON response with error handling
        print(f"🔄 Parsing LLM response...")
        parse_start = time.time()
        
        if '```json' in llm_response:
            llm_response = llm_response.split('```json')[1].split('```')[0]
        elif '```' in llm_response:
            llm_response = llm_response.split('```')[1]
        
        structured_ingredients = json.loads(llm_response)
        
        # Validate structure using existing parser
        from Recipe_Discovery_Agent.Tools.Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list
        validated_ingredients = parse_ingredients_list(structured_ingredients)
        
        parse_time = time.time() - parse_start
        print(f"⏱️  Response parsing completed: {parse_time:.2f}s")
        print(f"✅ Background conversion successful: {len(validated_ingredients)} ingredients processed")
        
        return validated_ingredients
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        print(f"Raw LLM response: {llm_response[:200]}...")
        # Return basic structure for fallback
        return [{"quantity": None, "unit": None, "ingredient": ing, "original": ing} for ing in raw_ingredients]
        
    except Exception as e:
        print(f"❌ Background ingredient processing failed: {e}")
        # Return basic structure for fallback
        return [{"quantity": None, "unit": None, "ingredient": ing, "original": ing} for ing in raw_ingredients]


# TODO: Implement background job queue integration
async def queue_ingredient_conversion(recipe_id: str, raw_ingredients: List[str]) -> None:
    """
    Queue ingredient conversion for background processing.
    
    This should integrate with your background job system (Celery, Redis Queue, etc.)
    to process ingredient conversion after recipe save.
    
    Args:
        recipe_id: ID of the saved recipe
        raw_ingredients: JSON-LD ingredient strings to convert
    """
    # TODO: Integrate with background job queue
    # Example implementations:
    
    # Celery example:
    # convert_recipe_ingredients.delay(recipe_id, raw_ingredients)
    
    # Redis Queue example:
    # job = q.enqueue(convert_recipe_ingredients, recipe_id, raw_ingredients)
    
    # For now, log the conversion request
    print(f"🔄 Queued background conversion for recipe {recipe_id}: {len(raw_ingredients)} ingredients")


# TODO: Implement background job worker
async def convert_recipe_ingredients_background_job(recipe_id: str, raw_ingredients: List[str]) -> None:
    """
    Background job worker for ingredient conversion.
    
    This function should be called by your background job system to process
    ingredient conversion with proper error handling and retry logic.
    
    Args:
        recipe_id: ID of the recipe to update
        raw_ingredients: JSON-LD ingredient strings to convert
    """
    try:
        print(f"🔄 Starting background conversion for recipe {recipe_id}")
        
        # Convert ingredients to shopping format
        shopping_ingredients = await process_ingredients_with_llm(raw_ingredients)
        
        # TODO: Save to database
        # await update_recipe_shopping_ingredients(recipe_id, shopping_ingredients)
        
        print(f"✅ Background conversion completed for recipe {recipe_id}")
        
    except Exception as e:
        print(f"❌ Background conversion failed for recipe {recipe_id}: {e}")
        
        # TODO: Implement retry logic
        # if retry_count < MAX_RETRIES:
        #     await queue_ingredient_conversion_retry(recipe_id, raw_ingredients, retry_count + 1)
        # else:
        #     await log_conversion_failure(recipe_id, str(e))


# TODO: Implement batch processing for efficiency
async def batch_convert_ingredients(recipe_batches: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Process multiple recipes' ingredients in an efficient batch.
    
    Future optimization: Process similar ingredients across recipes
    to reduce LLM calls and improve efficiency.
    
    Args:
        recipe_batches: List of {recipe_id, raw_ingredients} dictionaries
        
    Returns:
        Dictionary mapping recipe_id to converted ingredients
    """
    results = {}
    
    for batch in recipe_batches:
        recipe_id = batch['recipe_id']
        raw_ingredients = batch['raw_ingredients']
        
        try:
            converted = await process_ingredients_with_llm(raw_ingredients)
            results[recipe_id] = converted
        except Exception as e:
            print(f"❌ Batch conversion failed for recipe {recipe_id}: {e}")
            results[recipe_id] = []
    
    return results


# TODO: Implement caching for common ingredients
class IngredientCache:
    """
    Cache common ingredient conversions to speed up background processing.
    
    Many recipes use similar ingredients (garlic, salt, pepper, etc.)
    Caching these conversions can dramatically reduce LLM API calls.
    """
    
    def __init__(self):
        self.cache = {}  # TODO: Replace with Redis or database cache
    
    async def get_cached_conversion(self, ingredient: str) -> Optional[Dict]:
        """Get cached conversion if available."""
        return self.cache.get(ingredient)
    
    async def cache_conversion(self, ingredient: str, conversion: Dict) -> None:
        """Cache ingredient conversion for future use."""
        self.cache[ingredient] = conversion
    
    async def batch_lookup(self, ingredients: List[str]) -> Dict[str, Dict]:
        """Look up multiple ingredients in cache."""
        cached = {}
        for ingredient in ingredients:
            conversion = await self.get_cached_conversion(ingredient)
            if conversion:
                cached[ingredient] = conversion
        return cached


# Example usage for testing
async def test_conversion():
    """Test the conversion system with sample ingredients."""
    test_ingredients = [
        "4 cloves garlic, minced",
        "1/2 cup olive oil", 
        "2 tablespoons fresh basil",
        "1 (14.5 oz) can diced tomatoes",
        "salt and pepper to taste"
    ]
    
    print("🧪 Testing background ingredient conversion...")
    converted = await process_ingredients_with_llm(test_ingredients)
    
    print(f"✅ Conversion test completed: {len(converted)} ingredients")
    for ingredient in converted:
        print(f"   - {ingredient['original']} → {ingredient['store_quantity']} {ingredient['store_unit']} {ingredient['ingredient']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_conversion())