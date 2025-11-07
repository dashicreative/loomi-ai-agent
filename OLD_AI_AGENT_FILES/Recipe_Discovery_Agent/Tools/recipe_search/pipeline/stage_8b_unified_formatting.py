"""
Stage 8b: Unified Formatting and Ingredient Processing
Alternative approach combining Stage 9a and 9b functionality.

This module handles both ingredient parsing and final formatting in a unified approach,
allowing for easy A/B testing against the Stage 9a/9b pipeline.
"""

from typing import Dict, List
import re
import asyncio
import json
import httpx
import os

# Try to import ingredient-parser, fallback to basic parsing if not available
try:
    import ingredient_parser
    NLP_PARSER_AVAILABLE = True
    print("✅ ingredient-parser available")
except ImportError:
    NLP_PARSER_AVAILABLE = False
    print("⚠️  ingredient-parser not available, using basic parsing")

# Import the nutrition parser that works well
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list


def clean_nutrition_for_final_formatting(unified_nutrition: List[str]) -> Dict[str, float]:
    """
    Enhanced nutrition cleaning that handles messy data and returns clean numeric values.
    DUPLICATED from stage_6_requirements_verification.py because this parser actually works.
    
    Args:
        unified_nutrition: Raw nutrition strings from recipe parsing
        
    Returns:
        Dict with clean numeric values: {"protein": 30.0, "calories": 402.0, "carbs": 50.0, "fat": 13.0}
    """
    nutrition_clean = {}
    
    if not unified_nutrition:
        return nutrition_clean
    
    # Step 1: Combine and preprocess all nutrition text
    full_text = " ".join(unified_nutrition).lower()
    
    # Step 2: Split mashed-together strings using common delimiters
    # Handle cases like "Calories300Protein25gFat10g" or "calories: 300 protein: 25g fat: 10g"
    delimited_text = re.sub(r'([a-z])(\d)', r'\1 \2', full_text)  # Add space before numbers
    delimited_text = re.sub(r'(\d)([a-z])', r'\1 \2', delimited_text)  # Add space after numbers
    delimited_text = re.sub(r'(calories|protein|carbs|carbohydrates|fat)', r' \1', delimited_text)
    
    # Step 3: Remove interfering text
    clean_text = delimited_text.replace('per serving', '').replace('per portion', '')
    clean_text = clean_text.replace('amount per serving', '').replace('nutrition facts', '')
    
    # Step 4: Enhanced patterns with validation - FIXED ORDER
    nutrition_patterns = {
        "calories": [
            r'(\d{2,4})\s*calories\b',              # "334 calories" - PRIORITIZE NUMBER FIRST
            r'(\d{2,4})\s*kcal\b',                  # "334 kcal"  
            r'calories[:\s]*(\d{2,4})\b',           # "Calories: 334" - SECONDARY
            r'energy[:\s]*(\d{2,4})\b',             # "Energy: 334"
        ],
        "protein": [
            r'(\d+(?:\.\d+)?)\s*g\s*protein\b',         # "19g protein" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*grams?\s*protein\b',    # "19 grams protein"  
            r'protein[:\s]*(\d+(?:\.\d+)?)\s*g?\b',     # "Protein: 19g" - SECONDARY
        ],
        "carbs": [
            r'(\d+(?:\.\d+)?)\s*g\s*carbohydrates?\b',      # "26g carbohydrates" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*g\s*carbs\b',              # "26g carbs"
            r'carbohydrates?[:\s]*(\d+(?:\.\d+)?)\s*g?\b',  # "Carbohydrates: 26g" - SECONDARY
            r'carbs[:\s]*(\d+(?:\.\d+)?)\s*g?\b',
            r'total\s+carbohydrates?[:\s]*(\d+(?:\.\d+)?)\b',
        ],
        "fat": [
            r'(\d+(?:\.\d+)?)\s*g\s*fat\b',                 # "17g fat" - PRIORITIZE NUMBER FIRST
            r'(\d+(?:\.\d+)?)\s*g\s*total\s*fat\b',         # "17g total fat"
            r'(?:total\s+)?fat[:\s]*(\d+(?:\.\d+)?)\s*g?\b', # "Fat: 17g" - SECONDARY
        ]
    }
    
    # Step 5: Extract and validate values
    for nutrient, patterns in nutrition_patterns.items():
        found_value = None
        for pattern in patterns:
            match = re.search(pattern, clean_text)
            if match and found_value is None:  # Take first valid match
                try:
                    value = float(match.group(1))
                    
                    # Validation: reject obviously wrong values
                    if nutrient == "calories" and (value < 10 or value > 5000):
                        continue  # Skip invalid calorie values
                    elif nutrient in ["protein", "carbs", "fat"] and (value < 0 or value > 200):
                        continue  # Skip invalid macro values
                    
                    found_value = value
                    break
                except ValueError:
                    continue
        
        if found_value is not None:
            nutrition_clean[nutrient] = found_value
    
    return nutrition_clean


class InstacartRecipeParser:
    """
    Advanced ingredient parser using NLP with Instacart validation and smart LLM fallback.
    """
    
    def __init__(self):
        # Check if ingredient_parser is available
        self.parser_available = NLP_PARSER_AVAILABLE
        if self.parser_available:
            print("✅ ingredient-parser ready for use")
        else:
            print("⚠️  ingredient-parser not available, using fallback")
        
        # Instacart's accepted units (from our research)
        self.INSTACART_UNITS = {
            # Volume
            'cup', 'cups', 'c',
            'tablespoon', 'tablespoons', 'tb', 'tbs', 'tbsp',
            'teaspoon', 'teaspoons', 'ts', 'tsp', 'tspn',
            'gallon', 'gallons', 'gal', 'gals',
            'milliliter', 'millilitre', 'milliliters', 'millilitres', 'ml', 'mls',
            'liter', 'litre', 'liters', 'litres', 'l',
            'pint', 'pints', 'pt', 'pts',
            'quart', 'quarts', 'qt', 'qts',
            
            # Weight
            'gram', 'grams', 'g', 'gs',
            'kilogram', 'kilograms', 'kg', 'kgs',
            'ounce', 'ounces', 'oz',
            'pound', 'pounds', 'lb', 'lbs',
            
            # Count
            'each', 'bunch', 'bunches', 'can', 'cans',
            'head', 'heads', 'large', 'medium', 'small',
            'package', 'packages', 'packet', 'packets'
        }
        
        # Normalize unit variants to primary units
        self.unit_mappings = {
            'cups': 'cup', 'c': 'cup',
            'tablespoons': 'tablespoon', 'tbsp': 'tablespoon', 'tb': 'tablespoon', 'tbs': 'tablespoon',
            'teaspoons': 'teaspoon', 'tsp': 'teaspoon', 'ts': 'teaspoon', 'tspn': 'teaspoon',
            'gallons': 'gallon', 'gal': 'gallon', 'gals': 'gallon',
            'pints': 'pint', 'pt': 'pint', 'pts': 'pint',
            'quarts': 'quart', 'qt': 'quart', 'qts': 'quart',
            'liters': 'liter', 'litres': 'liter', 'l': 'liter',
            'milliliters': 'milliliter', 'millilitres': 'milliliter', 'ml': 'milliliter', 'mls': 'milliliter',
            'ounces': 'ounce', 'oz': 'ounce',
            'pounds': 'pound', 'lbs': 'pound', 'lb': 'pound',
            'grams': 'gram', 'g': 'gram', 'gs': 'gram',
            'kilograms': 'kilogram', 'kg': 'kilogram', 'kgs': 'kilogram',
            'cans': 'can', 'bunches': 'bunch', 'heads': 'head',
            'packages': 'package', 'packets': 'packet'
        }
    
    def parse_single_ingredient(self, ingredient_str: str) -> Dict:
        """
        Parse a single ingredient using NLP and validate against Instacart units.
        """
        if not ingredient_str or not ingredient_str.strip():
            return self._create_fallback_result(ingredient_str)
        
        # Try NLP parsing first
        if self.parser_available:
            try:
                parsed = ingredient_parser.parse_ingredient(ingredient_str.strip())
                
                # Extract components from ParsedIngredient object
                quantity = 1  # Default
                unit = 'each'  # Default
                name = ingredient_str  # Default
                
                # Extract name
                if parsed.name:
                    name = ' '.join([part.text for part in parsed.name])
                
                # Extract quantity and unit from amount
                if parsed.amount and len(parsed.amount) > 0:
                    amount_obj = parsed.amount[0]  # Take first amount
                    if amount_obj.quantity:
                        quantity = float(amount_obj.quantity)
                    if amount_obj.unit:
                        unit = str(amount_obj.unit).lower()
                
                # Extract comment if available
                comment = str(parsed.comment) if parsed.comment else ''
                
                # Normalize unit to Instacart format
                normalized_unit = self.unit_mappings.get(unit, unit)
                
                # Check if unit is Instacart-compatible
                is_valid_unit = normalized_unit in self.INSTACART_UNITS
                
                # Check for subjective/optional items
                is_subjective = any(phrase in ingredient_str.lower() for phrase in 
                                  ["to taste", "as needed", "optional", "if desired", "pinch", "dash", "splash"])
                
                return {
                    'original': ingredient_str,
                    'quantity': str(quantity),
                    'unit': normalized_unit if is_valid_unit else unit,
                    'ingredient': name,
                    'disqualified': is_subjective,
                    'type': 'nlp-simple' if is_valid_unit and not is_subjective else 'nlp-complex',
                    'needs_conversion': not is_valid_unit or is_subjective,
                    'confidence': 0.9 if is_valid_unit and not is_subjective else 0.6,
                    'comment': comment
                }
                
            except Exception as e:
                print(f"⚠️  NLP parsing failed for '{ingredient_str}': {e}")
                return self._create_fallback_result(ingredient_str)
        
        # Fallback to basic parsing
        return self._create_fallback_result(ingredient_str)
    
    def _create_fallback_result(self, ingredient_str: str) -> Dict:
        """Create a safe fallback result when parsing fails."""
        return {
            'original': ingredient_str,
            'quantity': '1',
            'unit': 'each',
            'ingredient': ingredient_str,
            'disqualified': False,
            'type': 'fallback',
            'needs_conversion': False,
            'confidence': 0.3
        }
    
    async def batch_convert_complex_ingredients(self, complex_ingredients: List[Dict], api_key: str) -> List[Dict]:
        """
        Batch convert complex ingredients using LLM (similar to Stage 9b approach).
        """
        if not complex_ingredients:
            return []
        
        # Create batch prompt
        ingredients_text = []
        for i, ing in enumerate(complex_ingredients):
            ingredients_text.append(f"{i}: {ing['original']}")
        
        prompt = f"""Convert these ingredients to Instacart-compatible format.

INGREDIENTS TO PROCESS:
{chr(10).join(ingredients_text)}

CONVERSION RULES:
- Convert to accepted Instacart units: cup, tablespoon, teaspoon, ounce, pound, gram, can, each, bunch, head, package
- For subjective amounts ("to taste", "pinch", "dash"), set disqualified: true
- Use first variant only (cup not cups, ounce not ounces)

EXAMPLES:
- "1 stick butter" → quantity: "0.5", unit: "cup"
- "pinch of salt" → disqualified: true
- "2 cloves garlic" → quantity: "1", unit: "head", ingredient: "garlic"

JSON FORMAT (return array in same order):
[{{"quantity": "amount", "unit": "instacart_unit", "ingredient": "name", "disqualified": boolean}}]"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": 800,
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
            
            if response.status_code == 200:
                data = response.json()
                llm_response = data['choices'][0]['message']['content'].strip()
                
                # Extract JSON
                if '```json' in llm_response:
                    llm_response = llm_response.split('```json')[1].split('```')[0]
                elif '```' in llm_response:
                    llm_response = llm_response.split('```')[1]
                
                conversions = json.loads(llm_response)
                
                # Update complex ingredients with LLM results
                results = []
                for i, conversion in enumerate(conversions):
                    if i < len(complex_ingredients):
                        original = complex_ingredients[i]
                        results.append({
                            'original': original['original'],
                            'quantity': str(conversion.get('quantity', '1')),
                            'unit': conversion.get('unit', 'each'),
                            'ingredient': conversion.get('ingredient', original['ingredient']),
                            'disqualified': conversion.get('disqualified', False),
                            'type': 'llm-converted',
                            'confidence': 0.8
                        })
                
                return results
                
        except Exception as e:
            print(f"⚠️  LLM batch conversion failed: {e}")
        
        # Fallback: return safe defaults
        return [self._create_fallback_result(ing['original']) for ing in complex_ingredients]


# Global parser instance
_parser_instance = None

def get_parser_instance():
    """Get or create the global parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = InstacartRecipeParser()
    return _parser_instance


async def parse_ingredients_nlp_async(ingredients: List[str], api_key: str = None) -> List[Dict]:
    """
    Parse ingredients using NLP + Instacart validation + smart LLM batching.
    """
    parser = get_parser_instance()
    
    # Step 1: Parse all ingredients with NLP
    parsed_ingredients = []
    complex_ingredients = []
    
    for ingredient_text in ingredients:
        if isinstance(ingredient_text, dict):
            ingredient_text = ingredient_text.get('ingredient', '')
        
        parsed = parser.parse_single_ingredient(ingredient_text)
        
        if parsed.get('needs_conversion', False):
            complex_ingredients.append(parsed)
        else:
            parsed_ingredients.append(parsed)
    
    # Step 2: Batch process complex ingredients with LLM if API key available
    if complex_ingredients and api_key:
        print(f"🔧 Processing {len(complex_ingredients)} complex ingredients with LLM...")
        llm_results = await parser.batch_convert_complex_ingredients(complex_ingredients, api_key)
        parsed_ingredients.extend(llm_results)
    else:
        # No API key or no complex ingredients - use as-is
        parsed_ingredients.extend(complex_ingredients)
    
    print(f"✅ NLP parsing: {len(ingredients) - len(complex_ingredients)} simple, {len(complex_ingredients)} complex")
    return parsed_ingredients


def parse_ingredients_nlp_sync(ingredients: List[str]) -> List[Dict]:
    """
    Sync version - only uses NLP parsing, no LLM conversion.
    """
    parser = get_parser_instance()
    
    parsed_ingredients = []
    for ingredient_text in ingredients:
        if isinstance(ingredient_text, dict):
            ingredient_text = ingredient_text.get('ingredient', '')
        
        parsed = parser.parse_single_ingredient(ingredient_text)
        parsed_ingredients.append(parsed)
    
    return parsed_ingredients


async def format_recipes_unified_async(recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Async version with unified NLP ingredient processing and formatting.
    """
    limited_recipes = recipes[:max_recipes]
    
    # Get API key for LLM processing
    api_key = os.getenv('OPENAI_API_KEY')
    
    # Process ingredients with NLP + Instacart validation + smart LLM batching
    for recipe in limited_recipes:
        ingredients = recipe.get('ingredients', [])
        print(f"🔧 Processing {len(ingredients)} ingredients for: {recipe.get('title', 'Unknown')}")
        recipe['ingredients'] = await parse_ingredients_nlp_async(ingredients, api_key)
    
    return _format_recipes_final(limited_recipes, max_recipes, fallback_used, exact_match_count)


def format_recipes_unified(recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Sync version with NLP ingredient processing (no LLM conversion).
    """
    limited_recipes = recipes[:max_recipes]
    
    # Process ingredients with NLP only (no LLM calls in sync version)
    for recipe in limited_recipes:
        ingredients = recipe.get('ingredients', [])
        print(f"🔧 Processing {len(ingredients)} ingredients for: {recipe.get('title', 'Unknown')} (sync - no LLM)")
        recipe['ingredients'] = parse_ingredients_nlp_sync(ingredients)
    
    return _format_recipes_final(limited_recipes, max_recipes, fallback_used, exact_match_count)


def _format_recipes_final(processed_recipes: List[Dict], max_recipes: int = 5, fallback_used: bool = False, exact_match_count: int = 0) -> List[Dict]:
    """
    Final formatting logic (shared by both async and sync versions).
    Maintains all the nutrition parsing and iOS formatting from Stage 9a.
    """
    formatted_recipes = []
    
    for recipe in processed_recipes:
        # Use processed ingredients
        processed_ingredients = recipe.get("ingredients", [])
        
        # Ensure ingredients are structured
        if processed_ingredients and len(processed_ingredients) > 0 and isinstance(processed_ingredients[0], dict):
            structured_ingredients = processed_ingredients
        else:
            # Fallback: Convert to simple display format for iOS app
            structured_ingredients = [{
                "ingredient": ing if isinstance(ing, str) else ing.get("ingredient", "")
            } for ing in processed_ingredients] if processed_ingredients else []
        
        # Parse nutrition using the working parser from Stage 6 (applied to ALL final recipes)
        raw_nutrition = recipe.get("nutrition", [])
        parsed_nutrition = clean_nutrition_for_final_formatting(raw_nutrition)
        
        # Convert parsed nutrition to structured format for iOS
        structured_nutrition = []
        for nutrient, value in parsed_nutrition.items():
            structured_nutrition.append({
                "name": nutrient,
                "amount": str(value),
                "unit": "g" if nutrient in ["protein", "fat", "carbs"] else "kcal" if nutrient == "calories" else "",
                "original": f"{value}{('g' if nutrient in ['protein', 'fat', 'carbs'] else 'kcal' if nutrient == 'calories' else '')} {nutrient}"
            })
        
        # Determine if this is an exact match or closest match
        is_exact_match = (len(formatted_recipes) + 1) <= exact_match_count
        nutrition_percentage = recipe.get('nutrition_match_percentage')
        
        formatted_recipe = {
            "id": len(formatted_recipes) + 1,
            "title": recipe.get("title", recipe.get("search_title", "")),
            "image": recipe.get("image_url", ""),
            "sourceUrl": recipe.get("source_url", ""),
            "servings": recipe.get("servings", ""),
            "readyInMinutes": recipe.get("cook_time", ""),
            "ingredients": structured_ingredients,
            "nutrition": structured_nutrition,
            "_instructions_for_analysis": recipe.get("instructions", [])
        }
        
        # Add metadata for agent context
        if fallback_used and not is_exact_match and nutrition_percentage is not None:
            formatted_recipe["_closest_match"] = True
            formatted_recipe["_nutrition_match_percentage"] = nutrition_percentage
        
        formatted_recipes.append(formatted_recipe)
    
    return formatted_recipes


def create_minimal_recipes_for_agent(formatted_recipes: List[Dict]) -> Dict:
    """
    Create minimal context for agent with fallback metadata.
    (Same as Stage 9a implementation)
    """
    minimal_recipes = []
    closest_match_count = 0
    exact_match_count = 0
    
    for recipe in formatted_recipes:
        is_closest_match = recipe.get("_closest_match", False)
        if is_closest_match:
            closest_match_count += 1
        else:
            exact_match_count += 1
            
        minimal_recipe = {
            "id": recipe["id"],
            "title": recipe["title"],
            "servings": recipe["servings"],
            "readyInMinutes": recipe["readyInMinutes"],
            "ingredients": [ing["ingredient"] for ing in recipe["ingredients"][:8]],
            "nutrition": recipe.get("nutrition", [])
        }
        
        # Include percentage for closest matches
        if is_closest_match:
            minimal_recipe["nutrition_match_percentage"] = recipe.get("_nutrition_match_percentage")
        
        minimal_recipes.append(minimal_recipe)
    
    return {
        "recipes": minimal_recipes,
        "exact_matches": exact_match_count,
        "closest_matches": closest_match_count,
        "fallback_used": closest_match_count > 0
    }


def create_failed_parse_report(fp1_failures: List[Dict], failed_parses: List[Dict]) -> Dict:
    """
    Create failure report for business analytics.
    (Same as Stage 9a implementation)
    """
    all_failures = fp1_failures + failed_parses
    
    return {
        "total_failed": len(all_failures),
        "content_scraping_failures": len(fp1_failures),
        "recipe_parsing_failures": len(failed_parses),
        "failed_urls": [
            {
                "url": fp.get("url") or fp.get("result", {}).get("url", ""),
                "failure_point": fp.get("failure_point", "Unknown"),
                "error": fp.get("error", "Unknown error")
            }
            for fp in all_failures
        ]
    }