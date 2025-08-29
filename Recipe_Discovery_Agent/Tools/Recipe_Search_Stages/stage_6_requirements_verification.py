"""
Stage 6: Requirements Verification
Handles recipe requirement verification using LLM reasoning.

This module verifies that recipes meet user-specified requirements.
"""

import httpx
import json
import re
from typing import Dict, List, Tuple, Optional, Set


# Dietary restriction ingredient mappings for deterministic checking
GLUTEN_INGREDIENTS = {
    'wheat', 'flour', 'bread', 'pasta', 'noodles', 'couscous', 'bulgur', 
    'semolina', 'spelt', 'barley', 'rye', 'malt', 'breaded', 'breadcrumbs',
    'crackers', 'croutons', 'tortilla', 'wrap', 'pita', 'nan', 'naan',
    'soy sauce', 'teriyaki', 'hoisin'
}

DAIRY_INGREDIENTS = {
    'milk', 'cheese', 'butter', 'cream', 'yogurt', 'yoghurt', 'whey',
    'casein', 'lactose', 'mozzarella', 'cheddar', 'parmesan', 'ricotta',
    'cottage cheese', 'sour cream', 'half and half', 'ice cream', 'ghee',
    'mascarpone', 'feta', 'gouda', 'brie', 'camembert'
}

MEAT_INGREDIENTS = {
    'chicken', 'beef', 'pork', 'lamb', 'turkey', 'duck', 'veal',
    'bacon', 'sausage', 'ham', 'prosciutto', 'salami', 'pepperoni',
    'ground beef', 'ground turkey', 'steak', 'ribs', 'brisket',
    'chorizo', 'pancetta', 'bresaola', 'mortadella'
}

DIETARY_MAPPINGS = {
    'gluten_free': GLUTEN_INGREDIENTS,
    'dairy_free': DAIRY_INGREDIENTS,
    'vegetarian': MEAT_INGREDIENTS,
    'vegan': MEAT_INGREDIENTS | DAIRY_INGREDIENTS | {'egg', 'eggs', 'honey', 'gelatin', 'mayo', 'mayonnaise'}
}


def normalize_ingredient(ingredient: str) -> Set[str]:
    """
    Normalize an ingredient string to a set of key terms for matching.
    """
    ingredient_lower = ingredient.lower()
    
    # Remove measurements and quantities
    measurements = r'\b\d+(?:/\d+)?\s*(?:cups?|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|lbs?|pounds?|g|grams?|kg|ml|liters?)\b'
    ingredient_lower = re.sub(measurements, '', ingredient_lower)
    ingredient_lower = re.sub(r'\d+(?:\.\d+)?', '', ingredient_lower)
    
    # Remove preparation descriptors
    descriptors = r'\b(?:fresh|dried|chopped|minced|sliced|diced|whole|ground|fine|coarse|large|small|medium|shredded|grated)\b'
    ingredient_lower = re.sub(descriptors, '', ingredient_lower)
    
    # Extract meaningful words
    words = re.findall(r'\b[a-z]+\b', ingredient_lower)
    stop_words = {'and', 'or', 'the', 'a', 'an', 'of', 'to', 'for', 'in', 'as', 'with'}
    
    return set(word for word in words if word not in stop_words and len(word) > 2)


def extract_requirement_types(requirements: Dict, user_query: str) -> Dict:
    """
    Categorize requirements into numerical, ingredient, and subjective types.
    """
    categorized = {
        "numerical": {
            "nutrition": {},
            "time": {}
        },
        "ingredients": {
            "exclude": [],
            "include": [],
            "dietary_tags": []
        },
        "subjective": {}
    }
    
    # Extract nutrition requirements
    if 'nutrition' in requirements:
        categorized["numerical"]["nutrition"] = requirements['nutrition']
    
    # Extract time requirements
    if 'time_constraints' in requirements:
        time_str = requirements['time_constraints']
        match = re.search(r'under\s+(\d+)\s*min', time_str, re.I)
        if match:
            categorized["numerical"]["time"]["cook_time"] = {"max": int(match.group(1))}
    
    # Extract ingredient requirements
    if 'allergies' in requirements:
        categorized["ingredients"]["exclude"].extend(requirements['allergies'])
    
    if 'exclude_ingredients' in requirements:
        categorized["ingredients"]["exclude"].extend(requirements['exclude_ingredients'])
    
    if 'include_ingredients' in requirements:
        categorized["ingredients"]["include"].extend(requirements['include_ingredients'])
    
    # Extract dietary restrictions
    if 'dietary_restrictions' in requirements:
        dietary = requirements['dietary_restrictions']
        if isinstance(dietary, str):
            dietary = [dietary]
        for restriction in dietary:
            restriction_normalized = restriction.lower().replace('-', '_').replace(' ', '_')
            if restriction_normalized in DIETARY_MAPPINGS:
                categorized["ingredients"]["dietary_tags"].append(restriction_normalized)
            else:
                # Unknown dietary restriction - needs LLM
                categorized["subjective"]["dietary_restriction"] = restriction
    
    # Extract subjective requirements
    subjective_keys = {'meal_type', 'cuisine_type', 'cooking_method'}
    for key in subjective_keys:
        if key in requirements:
            categorized["subjective"][key] = requirements[key]
    
    return categorized


def layer1_nutrition_check(recipe: Dict, nutrition_reqs: Dict) -> Tuple[bool, Dict]:
    """
    Layer 1a: Deterministic nutrition verification.
    Returns (passes, details) tuple.
    """
    if not nutrition_reqs:
        return True, {"status": "No nutrition requirements"}
    
    # First extract and clean nutrition data
    unified_nutrition = recipe.get('unified_nutrition', [])
    clean_nutrition = clean_nutrition_for_verification(unified_nutrition)
    
    # If nutrition requirements exist but no nutrition data, auto-fail
    if not clean_nutrition:
        return False, {"status": "❌ FAIL - No nutrition data available"}
    
    verification_details = {}
    passes_all = True
    
    for nutrient, constraints in nutrition_reqs.items():
        if nutrient not in clean_nutrition:
            verification_details[nutrient] = f"Missing {nutrient} data ❌"
            passes_all = False
            continue
        
        actual_value = clean_nutrition[nutrient]
        
        # Check constraints
        if 'min' in constraints:
            required_min = constraints['min']
            if actual_value >= required_min:
                verification_details[nutrient] = f"{actual_value} >= {required_min} ✅"
            else:
                verification_details[nutrient] = f"{actual_value} < {required_min} ❌"
                passes_all = False
        
        if 'max' in constraints:
            required_max = constraints['max']
            if actual_value <= required_max:
                verification_details[nutrient] = f"{actual_value} <= {required_max} ✅"
            else:
                verification_details[nutrient] = f"{actual_value} > {required_max} ❌"
                passes_all = False
    
    return passes_all, verification_details


def layer1_time_check(recipe: Dict, time_reqs: Dict) -> Tuple[bool, Dict]:
    """
    Layer 1b: Deterministic time verification.
    """
    if not time_reqs or 'cook_time' not in time_reqs:
        return True, {"status": "No time requirements"}
    
    cook_time_str = recipe.get('cook_time', '')
    if not cook_time_str or cook_time_str == "Not specified":
        return True, {"status": "No time data - assuming OK"}
    
    # Parse various time formats
    total_minutes = 0
    
    # Handle ISO duration format (PT30M, PT1H30M)
    if cook_time_str.startswith('PT'):
        hours_match = re.search(r'(\d+)H', cook_time_str)
        minutes_match = re.search(r'(\d+)M', cook_time_str)
        
        if hours_match:
            total_minutes += int(hours_match.group(1)) * 60
        if minutes_match:
            total_minutes += int(minutes_match.group(1))
    else:
        # Handle "30 minutes", "1 hour", etc.
        hours_match = re.search(r'(\d+)\s*(?:hours?|hrs?)', cook_time_str, re.I)
        minutes_match = re.search(r'(\d+)\s*(?:minutes?|mins?)', cook_time_str, re.I)
        
        if hours_match:
            total_minutes += int(hours_match.group(1)) * 60
        if minutes_match:
            total_minutes += int(minutes_match.group(1))
    
    if total_minutes == 0:
        return True, {"status": f"Could not parse time '{cook_time_str}'"}
    
    max_minutes = time_reqs['cook_time'].get('max', float('inf'))
    
    if total_minutes <= max_minutes:
        return True, {"cook_time": f"{total_minutes} min <= {max_minutes} min ✅"}
    else:
        return False, {"cook_time": f"{total_minutes} min > {max_minutes} min ❌"}


def layer2_ingredient_exclusion_check(recipe: Dict, exclude_list: List[str]) -> Tuple[bool, Dict]:
    """
    Layer 2a: Deterministic ingredient exclusion (allergies).
    """
    if not exclude_list:
        return True, {"status": "No exclusions"}
    
    ingredients = recipe.get('ingredients', [])
    if not ingredients:
        return True, {"status": "No ingredients data"}
    
    found_excluded = []
    
    for ingredient in ingredients:
        ingredient_words = normalize_ingredient(ingredient)
        
        for excluded in exclude_list:
            excluded_lower = excluded.lower()
            # Check both exact word match and substring
            if excluded_lower in ingredient_words or any(excluded_lower in word for word in ingredient_words):
                found_excluded.append(f"{excluded} in '{ingredient[:50]}...'")
                break  # One violation per ingredient is enough
    
    if found_excluded:
        return False, {"excluded_found": found_excluded[:3]}  # Limit output
    
    return True, {"status": f"None of {exclude_list} found ✅"}


def layer2_ingredient_inclusion_check(recipe: Dict, include_list: List[str]) -> Tuple[bool, Dict]:
    """
    Layer 2b: Deterministic ingredient inclusion.
    """
    if not include_list:
        return True, {"status": "No required ingredients"}
    
    ingredients = recipe.get('ingredients', [])
    if not ingredients:
        return False, {"status": "No ingredients data"}
    
    # Combine all ingredients for searching
    all_ingredient_words = set()
    for ing in ingredients:
        all_ingredient_words.update(normalize_ingredient(ing))
    
    found = []
    missing = []
    
    for required in include_list:
        required_lower = required.lower()
        if required_lower in all_ingredient_words or any(required_lower in word for word in all_ingredient_words):
            found.append(required)
        else:
            missing.append(required)
    
    if missing:
        return False, {"missing": missing, "found": found}
    
    return True, {"found_all": found}


def layer2_dietary_check(recipe: Dict, dietary_tags: List[str]) -> Tuple[bool, Dict]:
    """
    Layer 2c: Deterministic dietary restriction check using ingredient mappings.
    """
    if not dietary_tags:
        return True, {"status": "No dietary restrictions"}
    
    ingredients = recipe.get('ingredients', [])
    if not ingredients:
        return True, {"status": "No ingredients to check"}
    
    violations = []
    
    for dietary_tag in dietary_tags:
        if dietary_tag not in DIETARY_MAPPINGS:
            continue
        
        excluded_ingredients = DIETARY_MAPPINGS[dietary_tag]
        tag_violations = []
        
        for ingredient in ingredients:
            ingredient_words = normalize_ingredient(ingredient)
            
            for excluded in excluded_ingredients:
                if excluded in ingredient_words or any(excluded in word for word in ingredient_words):
                    tag_violations.append(f"{excluded} in '{ingredient[:30]}...'")
                    break
        
        if tag_violations:
            violations.append({
                "dietary_tag": dietary_tag,
                "violations": tag_violations[:2]  # Limit output
            })
    
    if violations:
        return False, {"dietary_violations": violations}
    
    return True, {"dietary_tags_passed": dietary_tags}


def layer3_metadata_check(recipe: Dict, requirements: Dict) -> Tuple[float, Dict]:
    """
    Layer 3: Metadata analysis for meal type and dietary indicators.
    Returns (confidence, details).
    """
    findings = {}
    confidence_scores = []
    
    # Gather metadata
    title = recipe.get('title', '').lower()
    description = recipe.get('description', '').lower()
    categories = ' '.join(recipe.get('categories', [])).lower() if recipe.get('categories') else ''
    metadata_text = f"{title} {description} {categories}"
    
    # Check meal type if required
    if 'meal_type' in requirements:
        meal_type = requirements['meal_type'].lower()
        
        meal_indicators = {
            'breakfast': ['breakfast', 'morning', 'brunch', 'oatmeal', 'pancake', 'waffle', 
                         'cereal', 'granola', 'smoothie', 'egg', 'toast', 'muffin', 'bagel'],
            'lunch': ['lunch', 'sandwich', 'salad', 'soup', 'wrap', 'midday'],
            'dinner': ['dinner', 'supper', 'evening', 'entree', 'main course', 'roast'],
            'dessert': ['dessert', 'sweet', 'cake', 'cookie', 'pie', 'ice cream', 'candy'],
            'snack': ['snack', 'bite', 'appetizer', 'starter']
        }
        
        if meal_type in meal_indicators:
            if any(indicator in metadata_text for indicator in meal_indicators[meal_type]):
                findings['meal_type'] = f"Detected as {meal_type} ✅"
                confidence_scores.append(0.9)
            else:
                findings['meal_type'] = f"Not clearly {meal_type}"
                confidence_scores.append(0.3)
    
    # Check dietary indicators in metadata
    if 'dietary_tags' in requirements:
        for tag in requirements['dietary_tags']:
            tag_variations = [tag.replace('_', ' '), tag.replace('_', '-'), tag]
            
            if any(variation in metadata_text for variation in tag_variations):
                findings[tag] = "Explicitly mentioned ✅"
                confidence_scores.append(0.95)
            else:
                findings[tag] = "Not mentioned in metadata"
                confidence_scores.append(0.4)
    
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
    
    return avg_confidence, findings


async def layer4_llm_verification(
    recipe: Dict,
    subjective_reqs: Dict,
    layer3_confidence: float,
    openai_key: str
) -> Tuple[bool, float, Dict]:
    """
    Layer 4: LLM verification for subjective requirements only.
    Used when previous layers are inconclusive or for subjective criteria.
    """
    if not subjective_reqs and layer3_confidence > 0.7:
        return True, layer3_confidence, {"status": "No LLM verification needed"}
    
    # Prepare minimal context
    context = {
        "title": recipe.get("title", "Unknown"),
        "ingredients": recipe.get("ingredients", []),  # Send ALL ingredients
        "description": recipe.get("description", "")[:300]
    }
    
    prompt = f"""Evaluate if this recipe meets these subjective requirements:

REQUIREMENTS: {json.dumps(subjective_reqs, indent=2)}

RECIPE:
Title: {context['title']}
Description: {context['description']}
Ingredients: {json.dumps(context['ingredients'], indent=2)}

Evaluate ONLY subjective aspects like meal type suitability, cuisine matching, or complex dietary compliance.
DO NOT evaluate numerical requirements (those are handled separately).

Return JSON:
{{
  "passes": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You evaluate subjective recipe requirements. Be strict and accurate."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                llm_response = data['choices'][0]['message']['content'].strip()
                
                if '```json' in llm_response:
                    llm_response = llm_response.split('```json')[1].split('```')[0]
                
                result = json.loads(llm_response)
                return (
                    result.get('passes', True),
                    result.get('confidence', 0.5),
                    {"reasoning": result.get('reasoning', '')}
                )
    except Exception as e:
        print(f"      ⚠️ LLM evaluation error: {e}")
        return False, 0.3, {"error": str(e)}
    
    return False, 0.5, {"status": "LLM check failed"}


def clean_nutrition_for_verification(unified_nutrition: List[str]) -> Dict[str, float]:
    """
    Enhanced nutrition cleaning that handles messy data and returns clean numeric values.
    
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
    
    # Step 4: Enhanced patterns with validation
    nutrition_patterns = {
        "calories": [
            r'calories[:\s]*(\d{2,4})\b',           # "Calories: 400"
            r'(\d{2,4})\s*calories\b',              # "400 calories"
            r'(\d{2,4})\s*kcal\b',                  # "400 kcal"
            r'energy[:\s]*(\d{2,4})\b',             # "Energy: 400"
        ],
        "protein": [
            r'protein[:\s]*(\d+(?:\.\d+)?)\s*g?\b',     # "Protein: 30g" or "Protein: 30"
            r'(\d+(?:\.\d+)?)\s*g?\s*protein\b',        # "30g protein" or "30 protein"
            r'(\d+(?:\.\d+)?)\s*grams?\s+protein\b',    # "30 grams protein"
        ],
        "carbs": [
            r'carbohydrates?[:\s]*(\d+(?:\.\d+)?)\s*g?\b',
            r'carbs[:\s]*(\d+(?:\.\d+)?)\s*g?\b',
            r'(\d+(?:\.\d+)?)\s*g?\s*carbs?\b',
            r'(\d+(?:\.\d+)?)\s*g?\s*carbohydrates?\b',
            r'total\s+carbohydrates?[:\s]*(\d+(?:\.\d+)?)\b',
        ],
        "fat": [
            r'(?:total\s+)?fat[:\s]*(\d+(?:\.\d+)?)\s*g?\b',
            r'(\d+(?:\.\d+)?)\s*g?\s*(?:total\s+)?fat\b',
        ]
    }
    
    # Debug: Show what we're parsing
    print(f"      🔍 Parsing nutrition from: {clean_text[:500]}...")
    
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
                    print(f"         Found {nutrient}: {value} (pattern: {pattern})")
                    break
                except ValueError:
                    continue
        
        if found_value is not None:
            nutrition_clean[nutrient] = found_value
    
    print(f"      ✅ Clean nutrition result: {nutrition_clean}")
    return nutrition_clean


async def verify_recipes_meet_requirements(
    scraped_recipes: List[Dict], 
    requirements: Dict, 
    openai_key: str, 
    user_query: str = ""
) -> List[Dict]:
    """
    Layered verification system with deterministic filters and minimal LLM usage.
    
    Processing order:
    1. Layer 1: Deterministic numerical checks (nutrition, time) - 100% reliable
    2. Layer 2: Deterministic ingredient checks (allergies, dietary) - 100% reliable
    3. Layer 3: Metadata analysis (meal type, dietary tags) - confidence scored
    4. Layer 4: LLM verification (only for subjective/uncertain cases)
    
    Returns only recipes that pass ALL requirements.
    """
    if not scraped_recipes or not requirements:
        return scraped_recipes
    
    # Categorize requirements
    categorized_reqs = extract_requirement_types(requirements, user_query)
    
    print(f"\n🔄 LAYERED VERIFICATION SYSTEM")
    print(f"   Total recipes: {len(scraped_recipes)}")
    print(f"   Numerical requirements: {categorized_reqs['numerical']}")
    print(f"   Ingredient requirements: {categorized_reqs['ingredients']}")
    print(f"   Subjective requirements: {categorized_reqs['subjective']}")
    
    qualifying_recipes = []
    
    for i, recipe in enumerate(scraped_recipes):
        print(f"\n📋 Recipe {i}: {recipe.get('title', 'Unknown')}")
        print(f"   URL: {recipe.get('source_url', 'No URL')}")
        
        # LAYER 1a: Nutrition Check (Deterministic)
        if categorized_reqs['numerical']['nutrition']:
            passes, details = layer1_nutrition_check(
                recipe, 
                categorized_reqs['numerical']['nutrition']
            )
            print(f"   Layer 1a (Nutrition): {'✅ PASS' if passes else '❌ FAIL'}")
            for nutrient, result in details.items():
                print(f"      {nutrient}: {result}")
            
            if not passes:
                continue  # Skip to next recipe
        
        # LAYER 1b: Time Check (Deterministic)
        if categorized_reqs['numerical']['time']:
            passes, details = layer1_time_check(
                recipe,
                categorized_reqs['numerical']['time']
            )
            print(f"   Layer 1b (Time): {'✅ PASS' if passes else '❌ FAIL'}")
            for key, result in details.items():
                print(f"      {result}")
            
            if not passes:
                continue
        
        # LAYER 2a: Ingredient Exclusion (Deterministic)
        if categorized_reqs['ingredients']['exclude']:
            passes, details = layer2_ingredient_exclusion_check(
                recipe,
                categorized_reqs['ingredients']['exclude']
            )
            print(f"   Layer 2a (Exclusions): {'✅ PASS' if passes else '❌ FAIL'}")
            if not passes:
                print(f"      Found: {details.get('excluded_found', [])}")
                continue
        
        # LAYER 2b: Ingredient Inclusion (Deterministic)
        if categorized_reqs['ingredients']['include']:
            passes, details = layer2_ingredient_inclusion_check(
                recipe,
                categorized_reqs['ingredients']['include']
            )
            print(f"   Layer 2b (Required): {'✅ PASS' if passes else '❌ FAIL'}")
            if not passes:
                print(f"      Missing: {details.get('missing', [])}")
                continue
        
        # LAYER 2c: Dietary Restrictions (Deterministic)
        if categorized_reqs['ingredients']['dietary_tags']:
            passes, details = layer2_dietary_check(
                recipe,
                categorized_reqs['ingredients']['dietary_tags']
            )
            print(f"   Layer 2c (Dietary): {'✅ PASS' if passes else '❌ FAIL'}")
            if not passes:
                for violation in details.get('dietary_violations', []):
                    print(f"      {violation['dietary_tag']}: {violation['violations']}")
                continue
        
        # LAYER 3: Metadata Analysis
        layer3_confidence = 1.0
        if categorized_reqs['subjective']:
            layer3_confidence, findings = layer3_metadata_check(recipe, categorized_reqs['subjective'])
            print(f"   Layer 3 (Metadata): Confidence {layer3_confidence:.2f}")
            for key, finding in findings.items():
                print(f"      {key}: {finding}")
        
        # LAYER 4: LLM Verification (only if needed)
        if categorized_reqs['subjective'] and layer3_confidence < 0.7:
            passes, confidence, details = await layer4_llm_verification(
                recipe,
                categorized_reqs['subjective'],
                layer3_confidence,
                openai_key
            )
            print(f"   Layer 4 (LLM): {'✅ PASS' if passes else '❌ FAIL'} (confidence: {confidence:.2f})")
            if 'reasoning' in details:
                print(f"      {details['reasoning']}")
            
            if not passes or confidence < 0.6:
                continue
        
        # Recipe passed all layers!
        print(f"   🎉 QUALIFIED")
        qualifying_recipes.append(recipe)
    
    print(f"\n✅ Final Results: {len(qualifying_recipes)}/{len(scraped_recipes)} recipes qualified")
    
    # Final summary
    if not qualifying_recipes and scraped_recipes:
        print("\n⚠️  No recipes met all requirements. Common failures:")
        if categorized_reqs['numerical']['nutrition']:
            print("   - Nutrition requirements not met or data missing")
        if categorized_reqs['ingredients']['exclude']:
            print("   - Contained excluded ingredients/allergens")
    
    return qualifying_recipes