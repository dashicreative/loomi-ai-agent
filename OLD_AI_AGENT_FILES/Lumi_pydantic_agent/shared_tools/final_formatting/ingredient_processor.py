"""
Ingredient Processor - Advanced ingredient parsing for recipe data
Converts raw ingredient strings to structured, app-ready format.

Based on the sophisticated 3-stage pipeline from the original agent:
1. LLM Spacing Fixes: "2Tbsp" → "2 Tbsp" 
2. Intelligent Labeling: "simple" vs "complex" ingredients
3. Hybrid Parsing: Simple→regex, Complex→focused LLM

Performance: ~3-4 seconds for 5 recipes processed in parallel
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
    Normalize unit variants to accepted primary units.
    Uses first variant from accepted list.
    """
    unit_lower = unit.lower()
    
    # Unit mappings (use first variant)
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


class IngredientProcessor:
    """
    Advanced ingredient processing using hybrid LLM + regex approach.
    Handles edge cases, unicode fractions, and complex patterns.
    """
    
    def __init__(self, openai_key: str = None):
        """Initialize processor with OpenAI API key."""
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY')
        
        # Priority sites for reordering (matches current list)
        self.priority_sites = [
            'allrecipes.com', 'simplyrecipes.com', 'seriouseats.com',
            'food52.com', 'budgetbytes.com', 'bonappetit.com',
            'cookinglight.com', 'eatingwell.com', 'thekitchn.com',
            'skinnytaste.com', 'minimalistbaker.com'
        ]
        
        # 17 Category keyword mappings
        self.category_keywords = {
            "Fruits": [
                "apple", "apples", "banana", "bananas", "grape", "grapes", "orange", "oranges", 
                "strawberry", "strawberries", "avocado", "avocados", "peach", "peaches", "berry", "berries",
                "lemon", "lemons", "lime", "limes", "pear", "pears", "cherry", "cherries", "mango", "mangos",
                "pineapple", "blueberry", "blueberries", "raspberry", "raspberries", "blackberry", "blackberries",
                "kiwi", "coconut", "watermelon", "cantaloupe", "honeydew"
            ],
            "Vegetables": [
                "potato", "potatoes", "onion", "onions", "carrot", "carrots", "lettuce", "salad", "broccoli",
                "pepper", "peppers", "bell pepper", "tomato", "tomatoes", "cucumber", "cucumbers", "celery",
                "spinach", "kale", "cabbage", "cauliflower", "zucchini", "squash", "eggplant", "mushroom", "mushrooms",
                "garlic", "ginger", "scallion", "scallions", "green onion", "radish", "beet", "beets"
            ],
            "Canned Goods": [
                "canned", "can", "soup", "tuna", "canned fruit", "beans", "canned vegetables", 
                "pasta sauce", "tomato sauce", "diced tomatoes", "crushed tomatoes", "tomato paste",
                "coconut milk", "broth", "stock", "canned corn", "canned beans"
            ],
            "Dairy": [
                "butter", "cheese", "egg", "eggs", "milk", "yogurt", "cream cheese", "sour cream",
                "heavy cream", "whipping cream", "mozzarella", "cheddar", "parmesan", "ricotta",
                "cottage cheese", "feta", "goat cheese", "cream", "half and half"
            ],
            "Meat": [
                "chicken", "beef", "pork", "sausage", "bacon", "ham", "turkey", "lamb", "veal",
                "ground beef", "ground turkey", "ground chicken", "steak", "ribs", "brisket", 
                "chicken breast", "chicken thigh", "pork chop", "ground pork"
            ],
            "Fish & Seafood": [
                "shrimp", "crab", "cod", "tuna", "salmon", "fish", "seafood", "scallops", "lobster",
                "halibut", "mahi mahi", "tilapia", "catfish", "sole", "flounder", "anchovy", "anchovies"
            ],
            "Deli": [
                "deli cheese", "salami", "ham", "turkey", "roast beef", "pastrami", "prosciutto",
                "deli meat", "lunch meat", "sliced cheese", "deli turkey", "deli ham"
            ],
            "Condiments & Spices": [
                "salt", "pepper", "black pepper", "oregano", "cinnamon", "sugar", "olive oil", "ketchup", 
                "mayonnaise", "mustard", "vinegar", "soy sauce", "hot sauce", "garlic powder", "onion powder",
                "paprika", "cumin", "thyme", "rosemary", "basil", "parsley", "cilantro", "dill", "sage",
                "nutmeg", "vanilla", "vanilla extract", "honey", "maple syrup", "barbecue sauce", "ranch"
            ],
            "Snacks": [
                "chips", "pretzels", "popcorn", "crackers", "nuts", "peanuts", "almonds", "cashews",
                "walnuts", "pecans", "trail mix", "granola bars", "cookies", "candy"
            ],
            "Bread & Bakery": [
                "bread", "tortillas", "pita", "bagels", "muffins", "croissant", "rolls", "buns",
                "pie crust", "pizza dough", "naan", "biscuits", "cake", "cookies", "pastry"
            ],
            "Beverages": [
                "coffee", "tea", "teabags", "juice", "soda", "beer", "wine", "water", "sparkling water",
                "energy drink", "sports drink", "lemonade", "iced tea"
            ],
            "Pasta, Rice & Cereal": [
                "pasta", "rice", "brown rice", "white rice", "macaroni", "noodles", "spaghetti", "penne",
                "fettuccine", "angel hair", "quinoa", "couscous", "barley", "cereal", "oats", "oatmeal"
            ],
            "Baking": [
                "flour", "sugar", "brown sugar", "baking powder", "baking soda", "yeast", "vanilla extract",
                "cocoa powder", "chocolate chips", "powdered sugar", "cornstarch", "cake mix"
            ],
            "Frozen Foods": [
                "frozen", "ice cream", "frozen vegetables", "frozen fruit", "frozen pizza", "frozen meals"
            ],
            "Personal Care": [
                "toothpaste", "shampoo", "soap", "deodorant", "lotion"
            ],
            "Health Care": [
                "vitamins", "supplements", "medicine", "first aid"
            ],
            "Household & Cleaning": [
                "paper towels", "toilet paper", "cleaning supplies", "laundry detergent"
            ],
            "Baby Items": [
                "baby food", "diapers", "baby formula"
            ],
            "Pet Care": [
                "dog food", "cat food", "pet treats"
            ]
        }
    
    async def process_recipe_ingredients(self, recipe: Dict) -> Dict:
        """
        Main entry point: Process all ingredients for a single recipe.
        
        Args:
            recipe: Recipe dict with raw ingredient strings in 'ingredients' field
            
        Returns:
            Recipe dict with structured ingredients in app-ready format
        """
        print(f"🔧 Processing ingredients for: {recipe.get('title', 'Unknown Recipe')}")
        
        ingredients = recipe.get('ingredients', [])
        if not ingredients:
            print("   ⚠️ No ingredients found, skipping processing")
            return recipe
        
        if not self.openai_key:
            print("   ⚠️ No OpenAI API key - using basic ingredient parsing")
            return self._fallback_basic_parsing(recipe)
        
        total_start = time.time()
        
        try:
            # STAGE 1: LLM spacing fixes
            print(f"   🔧 Stage 1: Fixing spacing issues...")
            spacing_start = time.time()
            spaced_recipe = await self._process_recipe_spacing_llm(recipe)
            spacing_time = time.time() - spacing_start
            print(f"   ✅ Spacing fixes completed: {spacing_time:.2f}s")
            
            # STAGE 2: Ingredient labeling (simple vs complex)
            print(f"   🏷️ Stage 2: Labeling ingredients...")
            labeling_start = time.time()
            labeled_recipe = await self._label_recipe_ingredients(spaced_recipe)
            labeling_time = time.time() - labeling_start
            print(f"   ✅ Labeling completed: {labeling_time:.2f}s")
            
            # STAGE 3: Hybrid parsing (regex + focused LLM)
            print(f"   🔧 Stage 3: Hybrid parsing...")
            parsing_start = time.time()
            parsed_recipe = await self._parse_single_recipe_ingredients(labeled_recipe)
            parsing_time = time.time() - parsing_start
            print(f"   ✅ Parsing completed: {parsing_time:.2f}s")
            
            # STAGE 4: Categorization
            print(f"   📂 Stage 4: Categorizing ingredients...")
            categorization_start = time.time()
            categorized_recipe = await self._categorize_recipe_ingredients(parsed_recipe)
            categorization_time = time.time() - categorization_start
            print(f"   ✅ Categorization completed: {categorization_time:.2f}s")
            
            total_time = time.time() - total_start
            print(f"   🎉 Total ingredient processing: {total_time:.2f}s")
            
            return categorized_recipe
            
        except Exception as e:
            total_time = time.time() - total_start
            print(f"   ❌ Ingredient processing failed after {total_time:.2f}s: {e}")
            return self._fallback_basic_parsing(recipe)
    
    async def _process_recipe_spacing_llm(self, recipe: Dict) -> Dict:
        """
        Process spacing for all ingredients in a recipe using LLM.
        Focus: fix spacing issues only.
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
        
        # Fix spacing using LLM
        spaced_ingredient_strings = await self._fix_ingredient_spacing_llm(ingredient_strings)
        
        # Rebuild ingredients with corrected spacing
        spaced_ingredients = []
        for i, original_ingredient in enumerate(ingredients):
            spaced_text = spaced_ingredient_strings[i] if i < len(spaced_ingredient_strings) else ingredient_strings[i]
            
            if isinstance(original_ingredient, dict):
                true_original = original_ingredient.get('ingredient', '')
            else:
                true_original = str(original_ingredient)
            
            spaced_ingredients.append({
                'original': true_original,  # Preserve the TRUE original
                'spaced_formatted': spaced_text,
                'ingredient': spaced_text  # Will be parsed later
            })
        
        recipe['ingredients'] = spaced_ingredients
        return recipe
    
    async def _fix_ingredient_spacing_llm(self, ingredients: List[str]) -> List[str]:
        """
        Fix spacing issues for a list of ingredients using LLM.
        Singular focus: correct spacing in ingredient strings from HTML parsing.
        """
        if not ingredients or not self.openai_key:
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
                        "Authorization": f"Bearer {self.openai_key}",
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
            print(f"   ⚠️ LLM spacing failed: {e}")
            return ingredients
    
    async def _label_recipe_ingredients(self, recipe: Dict) -> Dict:
        """
        Label ingredients for a single recipe as "simple" or "complex".
        Uses refined prompt with few-shot examples.
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
        
        # Create robust labeling prompt with few-shot examples
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
Reasoning: "count" accepted = simple, "pound" accepted = simple, "box" not accepted = complex

NOW LABEL THESE {len(ingredient_strings)} INGREDIENTS (return exactly {len(ingredient_strings)} labels):
{ingredients_text}

ACCEPTED UNITS ONLY:
cup, tablespoon, teaspoon, ounce, pound, gram, kilogram, gallon, liter, pint, quart, can, each, bunch, head, large, medium, small, package

SIMPLE PATTERN: [number] [accepted_unit] [ingredient_name]
✓ "2 cups flour" ✓ "3 each eggs" ✓ "1 pound chicken" ✓ "1 tablespoon salt" ✓ "2 cans tomatoes"

COMPLEX PATTERNS (mark as complex):
✗ "4 whole eggs" → has "whole" descriptor, needs "count"
✗ "1 box graham crackers" → "box" not in accepted units  
✗ "15 graham crackers" → no unit specified
✗ "salt to taste" → subjective amount
✗ "juice from 1 lemon" → descriptive quantity

Return JSON object with labels array: {{"labels": ["simple", "complex", "simple", ...]}}
Order must match ingredient list exactly."""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",  # Fast model for labeling
                        "max_tokens": 1000,
                        "temperature": 0.3,
                        "response_format": {"type": "json_object"},  # Force JSON output
                        "messages": [
                            {"role": "system", "content": "You are a precise ingredient labeling system. Follow the rules EXACTLY as specified. Return only valid JSON with exactly the requested number of labels."},
                            {"role": "user", "content": prompt}
                        ]
                    }
                )
            
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
                                 'stick' in ingredient_lower or
                                 'clove' in ingredient_lower or
                                 'one' in ingredient_lower or
                                 'two' in ingredient_lower or
                                 'dash' in ingredient_lower or
                                 'pinch' in ingredient_lower or
                                 'splash' in ingredient_lower or
                                 'to taste' in ingredient_lower or
                                 'as needed' in ingredient_lower) and label == "simple"):
                                
                                corrected_label = "complex"
                                corrections_made += 1
                            
                            # Force complex for single words without quantities
                            if (re.match(r'^[A-Za-z]+$', ingredient.strip()) and label == "simple"):
                                corrected_label = "complex" 
                                corrections_made += 1
                            
                            # Force complex for parenthetical measurements
                            if ('(' in ingredient_lower and ')' in ingredient_lower and label == "simple"):
                                corrected_label = "complex"
                                corrections_made += 1
                            
                            validated_labels.append(corrected_label)
                        
                        if corrections_made > 0:
                            print(f"   ✅ Validation fixed {corrections_made} mislabels")
                        
                        # Add validated labels to recipe
                        recipe['ingredient_labels'] = validated_labels
                        return recipe
                        
                except json.JSONDecodeError:
                    pass
            
            # Fallback if labeling fails
            return self._fallback_ingredient_labeling(recipe)
            
        except Exception as e:
            print(f"   ⚠️ Ingredient labeling failed: {e}")
            return self._fallback_ingredient_labeling(recipe)
    
    async def _parse_single_recipe_ingredients(self, recipe: Dict) -> Dict:
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
            tasks.append(self._parse_simple_ingredients(simple_ingredients))
        else:
            tasks.append(empty_result())
            
        if complex_ingredients:
            tasks.append(self._parse_complex_ingredients(complex_ingredients))
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
                parsed["type"] = "simple"
                parsed_ingredients[original_index] = parsed
        
        # Place complex results  
        for i, parsed in enumerate(complex_results):
            map_key = f"complex_{i}"
            if map_key in ingredient_map:
                original_index = ingredient_map[map_key]
                parsed["type"] = "complex"
                parsed_ingredients[original_index] = parsed
        
        # Update recipe with parsed ingredients
        recipe['ingredients'] = [ing for ing in parsed_ingredients if ing is not None]
        
        # Clean up temporary fields
        if 'ingredient_labels' in recipe:
            del recipe['ingredient_labels']
        
        return recipe
    
    async def _parse_simple_ingredients(self, ingredients: List[str]) -> List[Dict]:
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
            # Extract ingredient text
            if isinstance(ingredient, dict):
                original_text = ingredient.get('original', '')
                processed = ingredient.get('ingredient', '').strip()
            else:
                original_text = str(ingredient)
                processed = ingredient.strip()
            
            # Detect pantry staples
            pantry_staples = ['salt', 'pepper', 'butter', 'oil', 'olive oil', 'sugar', 'flour', 'vanilla', 'baking powder', 'baking soda']
            is_pantry_staple = any(staple in processed.lower() for staple in pantry_staples)
            
            # Initialize with app-compatible structure (removed store units)
            result = {
                "quantity": None,
                "unit": None, 
                "ingredient": processed,  # Will be updated with clean ingredient name
                "size": None,
                "additional_context": None,
                "alternatives": [],
                "pantry_staple": is_pantry_staple,
                "optional": False,
                "disqualified": False,
                "original": original_text,
                "category": None  # Will be filled by categorization
            }
            
            # Convert unicode fractions
            for unicode_frac, decimal in fraction_map.items():
                processed = processed.replace(unicode_frac, decimal)
            
            # Convert mixed numbers written as improper fractions
            def convert_mixed_fraction(match):
                numerator = int(match.group(1))
                denominator = int(match.group(2))
                
                if numerator > denominator and denominator in [2, 3, 4, 8]:
                    whole_part = numerator // denominator
                    fraction_part = numerator % denominator
                    decimal_value = whole_part + (fraction_part / denominator)
                    return str(decimal_value)
                else:
                    return f"{numerator}/{denominator}"
            
            processed = re.sub(r'(\d+)/(\d+)', convert_mixed_fraction, processed)
            
            # Remove dots after unit abbreviations
            unit_abbreviations = ['tsp', 'tbsp', 'oz', 'lb', 'lbs', 'pt', 'qt', 'gal', 'ml', 'kg', 'g']
            for abbrev in unit_abbreviations:
                processed = re.sub(f'({abbrev})\\.', r'\1', processed, flags=re.IGNORECASE)
            
            # Extract quantity and unit
            quantity_match = re.match(r'(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s+(.+)', processed)
            if quantity_match:
                quantity_str, remainder = quantity_match.groups()
                
                # Convert mixed numbers to decimals
                def convert_mixed_to_decimal(qty_str):
                    if ' ' in qty_str and '/' in qty_str:
                        parts = qty_str.split(' ')
                        whole = int(parts[0])
                        frac_parts = parts[1].split('/')
                        numerator = int(frac_parts[0])
                        denominator = int(frac_parts[1])
                        return str(whole + (numerator / denominator))
                    elif '/' in qty_str:
                        frac_parts = qty_str.split('/')
                        numerator = int(frac_parts[0])
                        denominator = int(frac_parts[1])
                        return str(numerator / denominator)
                    else:
                        return qty_str
                
                converted_quantity = convert_mixed_to_decimal(quantity_str)
                
                # Extract valid unit from remainder
                valid_units = [
                    'cup', 'cups', 'c', 'tablespoon', 'tablespoons', 'tbsp', 'tb', 'tbs', 
                    'teaspoon', 'teaspoons', 'tsp', 'ts', 'tspn', 'gallon', 'gallons', 'gal', 'gals',
                    'pint', 'pints', 'pt', 'pts', 'quart', 'quarts', 'qt', 'qts', 
                    'liter', 'liters', 'litres', 'l', 'milliliter', 'milliliters', 'millilitres', 'ml', 'mls',
                    'ounce', 'ounces', 'oz', 'pound', 'pounds', 'lb', 'lbs',
                    'gram', 'grams', 'g', 'gs', 'kilogram', 'kilograms', 'kg', 'kgs',
                    'can', 'cans', 'bunch', 'bunches', 'head', 'heads',
                    'large', 'medium', 'small', 'count', 'package', 'packages', 'packet', 'packets'
                ]
                
                words = remainder.split()
                unit = None
                remaining_ingredient = remainder
                
                if words:
                    first_word = words[0].lower()
                    if first_word in valid_units:
                        unit = first_word
                        remaining_ingredient = ' '.join(words[1:])
                
                if unit:
                    normalized_unit = _normalize_to_instacart_unit(unit)
                    
                    result.update({
                        "quantity": converted_quantity,
                        "unit": normalized_unit,
                        "ingredient": remaining_ingredient.strip()
                    })
            
            # Check for optional indicators
            if any(phrase in processed.lower() for phrase in ['to taste', 'if desired', 'optional']):
                result["optional"] = True
            
            parsed.append(result)
        
        return parsed
    
    async def _parse_complex_ingredients(self, ingredients: List[str]) -> List[Dict]:
        """
        Focused LLM parsing for complex ingredients only.
        """
        if not ingredients:
            return []
        
        ingredients_text = "\n".join([f"- {ing}" for ing in ingredients])
        
        # Focused prompt for complex ingredients
        prompt = f"""Convert complex ingredients to app-compatible format.

INGREDIENTS TO PROCESS:
{ingredients_text}

CONVERSION RULES:
- Convert to accepted units: cup, tablespoon, teaspoon, ounce, pound, gram, can, each, bunch, head, package
- For multiple measurements, choose the most practical unit (tablespoon for butter, ounce for most others)
- For subjective amounts ("to taste", "half a lime"), use default quantity: "1", unit: "count" 
- Use first variant only (cup not cups, ounce not ounces)
- Add pantry_staple: true for common items (salt, butter, olive oil, pepper, sugar, flour, etc.)
- Set optional: true for "to taste", "if desired", "garnish" items
- Never set disqualified: true - all items should be orderable

CONVERSION EXAMPLES:
- "Crust" → quantity: "1", unit: "count", ingredient: "pie crust", pantry_staple: false
- "2 1/2 ounces unsalted butter (about 5 tablespoons; 70 g)" → quantity: "5", unit: "tablespoon", ingredient: "unsalted butter", pantry_staple: true
- "Kosher salt, to taste" → quantity: "1", unit: "count", ingredient: "kosher salt", pantry_staple: true, optional: true
- "juice from 1 lemon" → quantity: "1", unit: "count", ingredient: "lemon", pantry_staple: false
- "4 whole eggs" → quantity: "4", unit: "count", ingredient: "eggs", pantry_staple: false

JSON FORMAT:
[{{"quantity": "amount", "unit": "unit", "ingredient": "name", "pantry_staple": boolean, "optional": boolean, "original": "text"}}]"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": 800,
                        "temperature": 0.1,
                        "messages": [
                            {"role": "system", "content": "You convert complex ingredients to app-compatible format. For single items without quantities (like 'Crust'), always add quantity: '1' and unit: 'count' or 'package'. For subjective amounts ('to taste'), use quantity: '1' and unit: 'count'. Mark common pantry items as pantry_staple: true. Set optional: true for 'to taste' items."},
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
                
                # Validate and normalize structure
                if isinstance(parsed_ingredients, list):
                    normalized = []
                    for ing in parsed_ingredients:
                        normalized_ing = {
                            "quantity": ing.get("quantity", "1"),
                            "unit": ing.get("unit", "count"),
                            "ingredient": ing.get("ingredient", ""),
                            "size": ing.get("size"),
                            "additional_context": ing.get("additional_context"),
                            "alternatives": ing.get("alternatives", []),
                            "pantry_staple": ing.get("pantry_staple", False),
                            "optional": ing.get("optional", False),
                            "disqualified": ing.get("disqualified", False),
                            "original": ing.get("original", ""),
                            "category": None  # Will be filled by categorization
                        }
                        normalized.append(normalized_ing)
                    return normalized
                    
            # Fallback for complex ingredients
            return self._fallback_complex_parsing(ingredients)
            
        except Exception as e:
            print(f"   ⚠️ Complex ingredient parsing failed: {e}")
            return self._fallback_complex_parsing(ingredients)
    
    async def _categorize_recipe_ingredients(self, recipe: Dict) -> Dict:
        """
        Categorize ingredients using keyword matching + LLM fallback.
        """
        ingredients = recipe.get('ingredients', [])
        if not ingredients:
            return recipe
        
        categorized_ingredients = []
        uncategorized_ingredients = []
        
        # First pass: keyword matching
        for ingredient in ingredients:
            ingredient_name = ingredient.get('ingredient', '').lower()
            category = None
            
            # Check each category for keyword matches
            for cat_name, keywords in self.category_keywords.items():
                if any(keyword in ingredient_name for keyword in keywords):
                    category = cat_name
                    break
            
            if category:
                ingredient['category'] = category
                categorized_ingredients.append(ingredient)
            else:
                uncategorized_ingredients.append(ingredient)
        
        # Second pass: LLM categorization for uncategorized items
        if uncategorized_ingredients and self.openai_key:
            llm_categorized = await self._categorize_ingredients_with_llm(uncategorized_ingredients)
            categorized_ingredients.extend(llm_categorized)
        else:
            # Fallback: assign default category
            for ingredient in uncategorized_ingredients:
                ingredient['category'] = "Condiments & Spices"  # Default category
                categorized_ingredients.append(ingredient)
        
        recipe['ingredients'] = categorized_ingredients
        return recipe
    
    async def _categorize_ingredients_with_llm(self, ingredients: List[Dict]) -> List[Dict]:
        """
        Use LLM to categorize ingredients that didn't match keywords.
        """
        if not ingredients:
            return []
        
        ingredient_names = [ing.get('ingredient', '') for ing in ingredients]
        ingredients_text = "\n".join([f"- {name}" for name in ingredient_names])
        
        categories = list(self.category_keywords.keys())
        categories_text = ", ".join(categories)
        
        prompt = f"""Categorize these ingredients into grocery store categories.

INGREDIENTS:
{ingredients_text}

AVAILABLE CATEGORIES:
{categories_text}

Return JSON array with categories in the same order:
["category1", "category2", "category3", ...]"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": 500,
                        "temperature": 0.1,
                        "messages": [
                            {"role": "system", "content": "You categorize grocery ingredients into store categories. Return only a JSON array of category names."},
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
                
                categories = json.loads(llm_response)
                
                # Apply categories to ingredients
                for i, ingredient in enumerate(ingredients):
                    if i < len(categories):
                        ingredient['category'] = categories[i]
                    else:
                        ingredient['category'] = "Condiments & Spices"  # Default
                
                return ingredients
        
        except Exception as e:
            print(f"   ⚠️ LLM categorization failed: {e}")
        
        # Fallback: assign default category
        for ingredient in ingredients:
            ingredient['category'] = "Condiments & Spices"
        
        return ingredients
    
    def _fallback_ingredient_labeling(self, recipe: Dict) -> Dict:
        """Fallback: Label all ingredients as complex (safer than simple)."""
        ingredients = recipe.get('ingredients', [])
        recipe['ingredient_labels'] = ["complex"] * len(ingredients)
        return recipe
    
    def _fallback_basic_parsing(self, recipe: Dict) -> Dict:
        """Fallback: Basic parsing when no API key available."""
        ingredients = recipe.get('ingredients', [])
        parsed_ingredients = []
        
        for ingredient in ingredients:
            ingredient_text = ingredient if isinstance(ingredient, str) else str(ingredient)
            
            # Detect pantry staples for fallback
            pantry_staples = ['salt', 'pepper', 'butter', 'oil', 'olive oil', 'sugar', 'flour', 'vanilla', 'baking powder', 'baking soda']
            is_pantry_staple = any(staple in ingredient_text.lower() for staple in pantry_staples)
            
            parsed_ingredients.append({
                "quantity": "1",
                "unit": "count",
                "ingredient": ingredient_text,
                "size": None,
                "additional_context": None,
                "alternatives": [],
                "pantry_staple": is_pantry_staple,
                "optional": False,
                "disqualified": False,
                "original": ingredient_text,
                "category": "Condiments & Spices",  # Default category
                "type": "fallback"
            })
        
        recipe['ingredients'] = parsed_ingredients
        return recipe
    
    def _fallback_complex_parsing(self, ingredients: List[str]) -> List[Dict]:
        """
        Improved fallback: Consistent structure with basic measurement extraction.
        """
        parsed = []
        
        for ingredient in ingredients:
            # Try basic measurement extraction
            quantity = None
            unit = None
            clean_ingredient = ingredient
            
            # Simple regex for basic quantity extraction
            quantity_match = re.match(r'(\d+(?:\.\d+)?(?:/\d+)?)\s*(\w+)?\s+(.+)', ingredient.strip())
            if quantity_match:
                quantity = quantity_match.group(1)
                unit = quantity_match.group(2) or ""
                clean_ingredient = quantity_match.group(3).strip()
            
            # Determine pantry staple status
            pantry_items = ["salt", "pepper", "oil", "flour", "sugar", "vanilla", "butter"]
            is_pantry = any(item in ingredient.lower() for item in pantry_items)
            
            # Normalize unit
            normalized_unit = _normalize_to_instacart_unit(unit) if unit else "count"
            
            parsed.append({
                "quantity": quantity or "1",
                "unit": normalized_unit,
                "ingredient": clean_ingredient,
                "size": None,
                "additional_context": None,
                "alternatives": [],
                "pantry_staple": is_pantry,
                "optional": False,
                "disqualified": False,
                "original": ingredient,
                "category": "Condiments & Spices",  # Default category
                "type": "complex-fallback"
            })
        
        return parsed


# Main function for external use
async def process_recipe_ingredients(recipe: Dict, openai_key: str = None) -> Dict:
    """
    Process ingredients for a single recipe.
    
    Args:
        recipe: Recipe dict with raw ingredient strings
        openai_key: OpenAI API key (optional, uses env var if not provided)
        
    Returns:
        Recipe dict with structured ingredients
    """
    processor = IngredientProcessor(openai_key)
    return await processor.process_recipe_ingredients(recipe)