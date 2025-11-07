"""
Batch Ingredient Processor - Efficient batch processing for multiple recipes
Processes all ingredients from multiple recipes in optimized batches.

Performance: 1-2 LLM calls total instead of 4 calls per recipe
"""

import asyncio
import httpx
import json
import re
import time
from typing import Dict, List, Tuple, Optional
import os


class BatchIngredientProcessor:
    """
    Ultra-efficient batch processing for ingredients across multiple recipes.
    Processes all ingredients together, then reassembles by recipe ID.
    """
    
    def __init__(self, openai_key: str = None):
        """Initialize processor with OpenAI API key."""
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY')
    
    async def batch_process_all_recipes(self, recipe_memory: Dict[str, Dict], recipe_ids: List[str]) -> Dict[str, List[Dict]]:
        """
        Main entry point: Batch process ingredients for multiple recipes.
        
        Args:
            recipe_memory: Full recipe memory dict
            recipe_ids: List of recipe IDs to process
            
        Returns:
            Dict mapping recipe_id -> processed_ingredients_list
        """
        print(f"🚀 BATCH PROCESSING: {len(recipe_ids)} recipes")
        batch_start = time.time()
        
        if not self.openai_key:
            print("   ⚠️ No OpenAI API key - using basic processing")
            return self._batch_fallback_processing(recipe_memory, recipe_ids)
        
        # PHASE 1: Collect all ingredients with recipe associations
        ingredient_batch = self._collect_all_ingredients(recipe_memory, recipe_ids)
        print(f"   📦 Collected {len(ingredient_batch)} ingredients from {len(recipe_ids)} recipes")
        
        if not ingredient_batch:
            return {recipe_id: [] for recipe_id in recipe_ids}
        
        # PHASE 2: Call 1 - Spacing fixes only
        print(f"   🔧 Call 1: Spacing fixes...")
        call1_start = time.time()
        
        spaced_ingredients = await self._batch_spacing_fixes(ingredient_batch)
        
        call1_time = time.time() - call1_start
        print(f"   ✅ Call 1 completed: {call1_time:.2f}s")
        
        # PHASE 3: Call 2 - Labeling only
        print(f"   🔧 Call 2: Complexity labeling...")
        call2_start = time.time()
        
        labeled_ingredients = await self._batch_complexity_labeling(spaced_ingredients)
        
        call2_time = time.time() - call2_start
        print(f"   ✅ Call 2 completed: {call2_time:.2f}s")
        
        # PHASE 4: Call 3 - Parsing only
        print(f"   🔧 Call 3: Ingredient parsing...")
        call3_start = time.time()
        
        parsed_ingredients = await self._batch_ingredient_parsing(labeled_ingredients)
        
        call3_time = time.time() - call3_start
        print(f"   ✅ Call 3 completed: {call3_time:.2f}s")
        
        # PHASE 5: Call 4 - Categorization only
        print(f"   🔧 Call 4: Categorization...")
        call4_start = time.time()
        
        processed_ingredients = await self._batch_categorization(parsed_ingredients)
        
        call4_time = time.time() - call4_start
        print(f"   ✅ Call 4 completed: {call4_time:.2f}s")
        
        # PHASE 6: Reassemble by recipe ID
        recipe_ingredients_map = self._reassemble_by_recipe_id(processed_ingredients)
        
        total_time = time.time() - batch_start
        print(f"   🎉 Total batch processing: {total_time:.2f}s ({len(ingredient_batch)} ingredients)")
        
        return recipe_ingredients_map
    
    def _collect_all_ingredients(self, recipe_memory: Dict[str, Dict], recipe_ids: List[str]) -> List[Dict]:
        """
        Collect all ingredients from all recipes with recipe ID associations.
        
        Returns:
            List of dicts: [{"recipe_id": "...", "ingredient_index": 0, "ingredient_text": "2 cups flour"}, ...]
        """
        ingredient_batch = []
        
        for recipe_id in recipe_ids:
            if recipe_id not in recipe_memory:
                continue
                
            recipe = recipe_memory[recipe_id]
            ingredients = recipe.get('ingredients', [])
            
            for i, ingredient in enumerate(ingredients):
                # Handle both string and dict formats
                if isinstance(ingredient, dict):
                    ingredient_text = ingredient.get('ingredient', str(ingredient))
                else:
                    ingredient_text = str(ingredient)
                
                ingredient_batch.append({
                    'recipe_id': recipe_id,
                    'ingredient_index': i,
                    'ingredient_text': ingredient_text,
                    'original': ingredient_text
                })
        
        return ingredient_batch
    
    async def _batch_spacing_fixes(self, ingredient_batch: List[Dict]) -> List[Dict]:
        """
        CALL 1: Fix spacing issues only - focused and fast.
        """
        if not ingredient_batch:
            return []
        
        ingredients_text = "\n".join([
            f"{i+1}. {ing['ingredient_text']}" 
            for i, ing in enumerate(ingredient_batch)
        ])
        
        prompt = f"""Fix spacing issues in these {len(ingredient_batch)} ingredients.

INGREDIENTS:
{ingredients_text}

TASK: Fix spacing only
Examples: "2Tbsp" → "2 Tbsp", "1cupflour" → "1 cup flour", "½teaspoon" → "½ teaspoon"

Return JSON array with {len(ingredient_batch)} objects in same order:
[{{"ingredient_text": "fixed spacing text"}}, ...]"""

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",  # Upgraded model for better accuracy
                        "max_tokens": min(3000, len(ingredient_batch) * 20),
                        "temperature": 0.0,  # Deterministic for spacing fixes
                        "messages": [
                            {"role": "system", "content": "You fix ingredient spacing. Focus on decision making, not formatting. Return exactly the requested number of JSON objects in same order."},
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
                
                parsed_results = json.loads(llm_response)
                
                if isinstance(parsed_results, list) and len(parsed_results) == len(ingredient_batch):
                    spaced_ingredients = []
                    for i, (original, parsed) in enumerate(zip(ingredient_batch, parsed_results)):
                        spaced = original.copy()
                        spaced['ingredient_text'] = parsed.get('ingredient_text', original['ingredient_text'])
                        spaced_ingredients.append(spaced)
                    
                    return spaced_ingredients
            
            # Fallback: return original
            return ingredient_batch
            
        except Exception as e:
            print(f"   ⚠️ Spacing fixes failed: {e}")
            return ingredient_batch
    
    async def _batch_complexity_labeling(self, spaced_ingredients: List[Dict]) -> List[Dict]:
        """
        CALL 2: Label ingredients as simple vs complex only.
        """
        if not spaced_ingredients:
            return []
        
        ingredients_text = "\n".join([
            f"{i+1}. {ing['ingredient_text']}" 
            for i, ing in enumerate(spaced_ingredients)
        ])
        
        prompt = f"""Identify ONLY the complex ingredients that need special LLM parsing. Most ingredients are simple and don't need flagging.

INGREDIENTS:
{ingredients_text}

TASK: Flag ONLY complex cases that need special handling
ONLY mark "complex": true if ingredient has:
1. 30+ characters (usually indicates editorial text)
2. Missing standard units (cup, tbsp, tsp, oz, lb, g, ml, can, jar, pkg, bunch, head, clove, slice, piece, large, medium, small)
3. Editorial additions ("to taste", "if desired", "preferably", "but you can also use")
4. Cooking instructions mixed in ("softened", "at room temperature")
5. Multiple alternatives or complex parentheses

DEFAULT: All ingredients are simple unless flagged

EXAMPLES (ONLY the complex ones get flagged):
"2 cups flour" → {{"complex": false}}
"1 tbsp olive oil" → {{"complex": false}}
"salt to taste" → {{"complex": true}}
"2 (8-ounce) packages cream cheese, softened at room temperature" → {{"complex": true}}
"1 cup butter (or you can substitute margarine)" → {{"complex": true}}
"freshly ground black pepper" → {{"complex": true}}

Return JSON array with {len(spaced_ingredients)} objects in same order:
[{{"complex": false}}, {{"complex": true}}, ...]"""

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",  # Upgraded model
                        "max_tokens": min(2000, len(spaced_ingredients) * 15),
                        "temperature": 0.0,
                        "messages": [
                            {"role": "system", "content": "You label ingredient complexity. Focus on decision making. Return exactly the requested number of JSON objects in same order."},
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
                
                parsed_results = json.loads(llm_response)
                
                if isinstance(parsed_results, list) and len(parsed_results) == len(spaced_ingredients):
                    labeled_ingredients = []
                    for i, (original, parsed) in enumerate(zip(spaced_ingredients, parsed_results)):
                        labeled = original.copy()
                        labeled['complex'] = parsed.get('complex', False)  # Default to simple (false)
                        labeled_ingredients.append(labeled)
                    
                    return labeled_ingredients
            
            # Fallback: label all as complex
            return self._fallback_complexity_labeling(spaced_ingredients)
            
        except Exception as e:
            print(f"   ⚠️ Complexity labeling failed: {e}")
            return self._fallback_complexity_labeling(spaced_ingredients)
    
    def _fallback_complexity_labeling(self, spaced_ingredients: List[Dict]) -> List[Dict]:
        """Fallback when complexity labeling fails - use simple heuristics."""
        fallback_results = []
        for ingredient in spaced_ingredients:
            ingredient_text = ingredient.get('ingredient_text', '')
            # Simple heuristics for complexity
            is_complex = (
                len(ingredient_text) > 30 or  # Long text usually complex
                'to taste' in ingredient_text.lower() or
                'if desired' in ingredient_text.lower() or
                'preferably' in ingredient_text.lower() or
                'softened' in ingredient_text.lower()
            )
            fallback_results.append({
                **ingredient,
                'complex': is_complex
            })
        return fallback_results
    
    async def _batch_ingredient_parsing(self, labeled_ingredients: List[Dict]) -> List[Dict]:
        """
        CALL 3: Parse ingredients into quantity, unit, ingredient name only.
        """
        if not labeled_ingredients:
            return []
        
        # Split by complexity for different processing approaches
        simple_ingredients = [ing for ing in labeled_ingredients if not ing.get('complex', False)]
        complex_ingredients = [ing for ing in labeled_ingredients if ing.get('complex', False)]
        
        print(f"   📊 Parsing: {len(simple_ingredients)} simple (regex), {len(complex_ingredients)} complex (LLM)")
        
        parsed_ingredients = []
        
        # Process simple ingredients with regex (fast)
        for ingredient in simple_ingredients:
            parsed = self._regex_parse_simple_ingredient(ingredient)
            parsed_ingredients.append(parsed)
        
        # Process complex ingredients with LLM (if any)
        if complex_ingredients:
            llm_parsed = await self._llm_parse_complex_ingredients(complex_ingredients)
            parsed_ingredients.extend(llm_parsed)
        
        # Sort back to original order using ingredient_index
        parsed_ingredients.sort(key=lambda x: x.get('ingredient_index', 0))
        
        return parsed_ingredients
    
    async def _llm_parse_complex_ingredients(self, complex_ingredients: List[Dict]) -> List[Dict]:
        """LLM parsing for complex ingredients - quantity, unit, ingredient name only."""
        ingredients_text = "\n".join([
            f"{i+1}. {ing['ingredient_text']}" 
            for i, ing in enumerate(complex_ingredients)
        ])
        
        prompt = f"""Parse these {len(complex_ingredients)} complex ingredients - extract quantity, unit, and clean ingredient name only.

INGREDIENTS:
{ingredients_text}

TASK: Parse into structured format
1. Extract quantity, unit, clean ingredient name
2. For complex ingredients, default to quantity: "1", unit: "count" 
3. Move editorial text to additional_context (e.g., "preferably Philadelphia brand")
4. Clean ingredient names (remove prep instructions)

EXAMPLES:
"salt to taste" → {{"quantity": "1", "unit": "count", "ingredient": "salt", "additional_context": "to taste"}}
"2 (8-ounce) packages cream cheese (preferably Philadelphia)" → {{"quantity": "2", "unit": "package", "ingredient": "cream cheese", "additional_context": "8-ounce packages, preferably Philadelphia brand"}}

Return JSON array with {len(complex_ingredients)} objects:
[{{"quantity": "1", "unit": "count", "ingredient": "name", "additional_context": null}}, ...]"""
        
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",  # Upgraded model for complex parsing
                        "max_tokens": min(2500, len(complex_ingredients) * 60),
                        "temperature": 0.0,
                        "messages": [
                            {"role": "system", "content": "You parse complex ingredients into structured format. Focus on decision making, not formatting. Return exactly the requested number of JSON objects."},
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
                
                parsed_results = json.loads(llm_response)
                
                if isinstance(parsed_results, list) and len(parsed_results) == len(complex_ingredients):
                    processed_complex = []
                    for i, (original, parsed) in enumerate(zip(complex_ingredients, parsed_results)):
                        result = original.copy()
                        result.update({
                            'quantity': parsed.get('quantity', '1'),
                            'unit': self._normalize_unit(parsed.get('unit', 'count')),
                            'ingredient': parsed.get('ingredient', original['ingredient_text']),
                            'additional_context': parsed.get('additional_context', None)
                        })
                        processed_complex.append(result)
                    
                    return processed_complex
            
            # Fallback for complex ingredients
            return self._fallback_complex_parsing(complex_ingredients)
            
        except Exception as e:
            print(f"   ⚠️ Complex ingredient parsing failed: {e}")
            return self._fallback_complex_parsing(complex_ingredients)
    
    def _fallback_complex_parsing(self, complex_ingredients: List[Dict]) -> List[Dict]:
        """Fallback parsing for complex ingredients."""
        fallback_results = []
        for ingredient in complex_ingredients:
            result = ingredient.copy()
            result.update({
                'quantity': '1',
                'unit': 'count', 
                'ingredient': ingredient['ingredient_text'],
                'additional_context': None
            })
            fallback_results.append(result)
        return fallback_results
    
    async def _batch_categorization(self, parsed_ingredients: List[Dict]) -> List[Dict]:
        """
        CALL 4: Categorize all parsed ingredients using user's 10 categories only.
        """
        if not parsed_ingredients:
            return []
        
        ingredients_text = "\n".join([
            f"{i+1}. {ing['ingredient']}" 
            for i, ing in enumerate(parsed_ingredients)
        ])
        
        # User's 10 categories
        categories = """🥬 Produce, 🥩 Meat & Seafood, 🥛 Dairy, 🧊 Frozen, 🏺 Pantry & Dry Goods, 🧂 Spices & Seasonings, 🍯 Condiments & Sauces, 🧁 Baking, 🥤 Beverages, 🌟 Specialty Items"""
        
        prompt = f"""Categorize these {len(parsed_ingredients)} ingredients into the provided categories and mark pantry staples.

INGREDIENTS:
{ingredients_text}

TASK: Categorization and metadata only
1. Categorize into ONE of these categories: {categories}
2. Mark pantry staples (salt, pepper, butter, oil, sugar, flour, vanilla, spices)
3. Mark optional items (if original text contained "to taste", "if desired", "optional")

EXAMPLES:
"salt" → {{"category": "🧂 Spices & Seasonings", "pantry_staple": true, "optional": true}}
"cream cheese" → {{"category": "🥛 Dairy", "pantry_staple": false, "optional": false}}
"chicken breast" → {{"category": "🥩 Meat & Seafood", "pantry_staple": false, "optional": false}}

Return JSON array with {len(parsed_ingredients)} objects:
[{{"category": "🥬 Produce", "pantry_staple": false, "optional": false}}, ...]"""
        
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",  # Upgraded model for categorization
                        "max_tokens": min(2000, len(parsed_ingredients) * 30),
                        "temperature": 0.0,
                        "messages": [
                            {"role": "system", "content": "You categorize ingredients and mark metadata. Focus on decision making. Return exactly the requested number of JSON objects in same order."},
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
                
                parsed_results = json.loads(llm_response)
                
                if isinstance(parsed_results, list) and len(parsed_results) == len(parsed_ingredients):
                    categorized_ingredients = []
                    for i, (original, categorization) in enumerate(zip(parsed_ingredients, parsed_results)):
                        result = original.copy()
                        result.update({
                            'category': categorization.get('category', '🌟 Specialty Items'),
                            'pantry_staple': categorization.get('pantry_staple', False),
                            'optional': categorization.get('optional', False) or 'to taste' in original.get('ingredient_text', '').lower()
                        })
                        categorized_ingredients.append(result)
                    
                    return categorized_ingredients
            
            # Fallback categorization
            return self._fallback_categorization(parsed_ingredients)
            
        except Exception as e:
            print(f"   ⚠️ Categorization failed: {e}")
            return self._fallback_categorization(parsed_ingredients)
    
    def _fallback_categorization(self, parsed_ingredients: List[Dict]) -> List[Dict]:
        """Fallback categorization using basic keyword matching."""
        categorized_ingredients = []
        for ingredient in parsed_ingredients:
            result = ingredient.copy()
            
            # Basic categorization using _basic_categorize method
            category = self._basic_categorize(ingredient.get('ingredient', ''))
            
            # Basic pantry detection
            pantry_items = ['salt', 'pepper', 'butter', 'oil', 'sugar', 'flour', 'vanilla']
            is_pantry = any(item in ingredient.get('ingredient', '').lower() for item in pantry_items)
            
            result.update({
                'category': category,
                'pantry_staple': is_pantry,
                'optional': 'to taste' in ingredient.get('ingredient_text', '').lower()
            })
            categorized_ingredients.append(result)
        
        return categorized_ingredients
    
    def _basic_categorize(self, ingredient_name: str) -> str:
        """Basic categorization for simple ingredients using user's 10 categories."""
        name_lower = ingredient_name.lower()
        
        # User's 10 categories with keyword matching
        category_keywords = {
            "🥬 Produce": ['apple', 'banana', 'orange', 'lemon', 'lime', 'potato', 'onion', 'carrot', 'lettuce', 'broccoli', 'pepper', 'tomato', 'cucumber', 'celery', 'spinach', 'garlic', 'mushroom', 'avocado', 'cherry', 'blueberry', 'raspberry', 'mango', 'pineapple'],
            "🥩 Meat & Seafood": ['chicken', 'beef', 'pork', 'sausage', 'bacon', 'ham', 'turkey', 'ground beef', 'fish', 'salmon', 'shrimp', 'crab'],
            "🥛 Dairy": ['butter', 'cheese', 'egg', 'eggs', 'milk', 'yogurt', 'cream cheese', 'sour cream', 'heavy cream', 'mozzarella', 'cheddar', 'parmesan'],
            "🧊 Frozen": ['frozen'],
            "🏺 Pantry & Dry Goods": ['rice', 'pasta', 'beans', 'lentils', 'quinoa', 'oats', 'nuts', 'almonds', 'walnuts', 'canned'],
            "🧂 Spices & Seasonings": ['salt', 'pepper', 'oregano', 'cinnamon', 'garlic powder', 'paprika', 'cumin', 'thyme', 'basil', 'rosemary'],
            "🍯 Condiments & Sauces": ['olive oil', 'vegetable oil', 'vinegar', 'soy sauce', 'ketchup', 'mustard', 'mayo'],
            "🧁 Baking": ['flour', 'sugar', 'brown sugar', 'baking powder', 'baking soda', 'yeast', 'vanilla extract', 'cocoa powder', 'chocolate chips'],
            "🥤 Beverages": ['wine', 'beer', 'juice', 'broth', 'stock'],
            "🌟 Specialty Items": []  # Default category
        }
        
        # Find matching category
        for category, keywords in category_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                return category
        
        # Default to Specialty Items
        return "🌟 Specialty Items"
    
    def _regex_parse_simple_ingredient(self, ingredient: Dict) -> Dict:
        """Fast regex parsing for simple ingredients."""
        text = ingredient['ingredient_text']
        
        # Basic regex parsing (same as fallback)
        quantity = "1"
        unit = "count"
        name = text
        
        quantity_match = re.match(r'(\d+(?:\.\d+)?)\s+(\w+)\s+(.+)', text.strip())
        if quantity_match:
            quantity = quantity_match.group(1)
            potential_unit = quantity_match.group(2).lower()
            name = quantity_match.group(3)
            
            # Validate unit
            valid_units = ['cup', 'tablespoon', 'teaspoon', 'ounce', 'pound', 'gram', 'can', 'count']
            if potential_unit in valid_units or potential_unit + 's' in [u + 's' for u in valid_units]:
                unit = self._normalize_unit(potential_unit)
        
        # Basic pantry detection
        pantry_items = ['salt', 'pepper', 'butter', 'oil', 'sugar', 'flour', 'vanilla']
        is_pantry = any(item in text.lower() for item in pantry_items)
        
        # Basic categorization for simple ingredients
        category = self._basic_categorize(name)
        
        result = ingredient.copy()
        result.update({
            'quantity': quantity,
            'unit': unit,
            'ingredient': name,
            'pantry_staple': is_pantry,
            'optional': 'to taste' in text.lower(),
            'category': category,
            'additional_context': None
        })
        
        return result
    
    def _reassemble_by_recipe_id(self, processed_ingredients: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group processed ingredients back by recipe ID.
        """
        recipe_ingredients_map = {}
        
        for ingredient in processed_ingredients:
            recipe_id = ingredient['recipe_id']
            if recipe_id not in recipe_ingredients_map:
                recipe_ingredients_map[recipe_id] = []
            
            # Clean up processing metadata
            clean_ingredient = {
                'quantity': ingredient['quantity'],
                'unit': ingredient['unit'],
                'ingredient': ingredient['ingredient'],
                'size': None,
                'additional_context': None,
                'alternatives': [],
                'pantry_staple': ingredient['pantry_staple'],
                'optional': ingredient['optional'],
                'disqualified': False,
                'original': ingredient['original'],
                'category': ingredient['category']
            }
            
            recipe_ingredients_map[recipe_id].append(clean_ingredient)
        
        # Sort ingredients by original index to maintain order
        for recipe_id in recipe_ingredients_map:
            recipe_ingredients_map[recipe_id].sort(
                key=lambda x: next(
                    ing['ingredient_index'] 
                    for ing in processed_ingredients 
                    if ing['recipe_id'] == recipe_id and ing['original'] == x['original']
                )
            )
        
        return recipe_ingredients_map
    
    def _normalize_unit(self, unit: str) -> str:
        """Normalize unit variants to standard forms."""
        unit_mappings = {
            'cups': 'cup', 'c': 'cup',
            'tablespoons': 'tablespoon', 'tbsp': 'tablespoon', 'tb': 'tablespoon',
            'teaspoons': 'teaspoon', 'tsp': 'teaspoon', 'ts': 'teaspoon',
            'ounces': 'ounce', 'oz': 'ounce',
            'pounds': 'pound', 'lbs': 'pound', 'lb': 'pound',
            'grams': 'gram', 'g': 'gram',
            'cans': 'can', 'packages': 'package',
            'each': 'count'  # Legacy mapping
        }
        return unit_mappings.get(unit.lower(), unit.lower())
    
    def _fallback_batch_processing(self, ingredient_batch: List[Dict]) -> List[Dict]:
        """Fallback processing when LLM fails."""
        processed = []
        
        for ingredient in ingredient_batch:
            # Basic regex processing
            text = ingredient['ingredient_text']
            quantity = "1"
            unit = "count"
            name = text
            
            # Simple quantity extraction
            quantity_match = re.match(r'(\d+(?:\.\d+)?)\s+(\w+)\s+(.+)', text.strip())
            if quantity_match:
                quantity = quantity_match.group(1)
                potential_unit = quantity_match.group(2).lower()
                name = quantity_match.group(3)
                
                # Validate unit
                valid_units = ['cup', 'tablespoon', 'teaspoon', 'ounce', 'pound', 'gram', 'can', 'count']
                if potential_unit in valid_units or potential_unit + 's' in [u + 's' for u in valid_units]:
                    unit = self._normalize_unit(potential_unit)
            
            # Detect pantry staples
            pantry_items = ['salt', 'pepper', 'butter', 'oil', 'sugar', 'flour', 'vanilla']
            is_pantry = any(item in text.lower() for item in pantry_items)
            
            processed_ingredient = ingredient.copy()
            processed_ingredient.update({
                'quantity': quantity,
                'unit': unit,
                'ingredient': name,
                'pantry_staple': is_pantry,
                'optional': 'to taste' in text.lower(),
                'category': 'Condiments & Spices'  # Default
            })
            
            processed.append(processed_ingredient)
        
        return processed
    
    def _batch_fallback_processing(self, recipe_memory: Dict[str, Dict], recipe_ids: List[str]) -> Dict[str, List[Dict]]:
        """Complete fallback when no API key available."""
        recipe_ingredients_map = {}
        
        for recipe_id in recipe_ids:
            if recipe_id not in recipe_memory:
                recipe_ingredients_map[recipe_id] = []
                continue
                
            recipe = recipe_memory[recipe_id]
            ingredients = recipe.get('ingredients', [])
            
            processed_ingredients = []
            for ingredient in ingredients:
                ingredient_text = ingredient if isinstance(ingredient, str) else str(ingredient)
                
                processed_ingredients.append({
                    'quantity': '1',
                    'unit': 'count',
                    'ingredient': ingredient_text,
                    'size': None,
                    'additional_context': None,
                    'alternatives': [],
                    'pantry_staple': False,
                    'optional': False,
                    'disqualified': False,
                    'original': ingredient_text,
                    'category': 'Condiments & Spices'
                })
            
            recipe_ingredients_map[recipe_id] = processed_ingredients
        
        return recipe_ingredients_map


# Main function for external use
async def batch_process_recipe_ingredients(
    recipe_memory: Dict[str, Dict], 
    recipe_ids: List[str], 
    openai_key: str = None
) -> Dict[str, List[Dict]]:
    """
    Batch process ingredients for multiple recipes efficiently.
    
    Args:
        recipe_memory: Full recipe memory dict
        recipe_ids: List of recipe IDs to process
        openai_key: OpenAI API key (optional)
        
    Returns:
        Dict mapping recipe_id -> processed_ingredients_list
    """
    processor = BatchIngredientProcessor(openai_key)
    return await processor.batch_process_all_recipes(recipe_memory, recipe_ids)