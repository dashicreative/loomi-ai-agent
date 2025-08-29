"""
Stage 6: Requirements Verification
Handles recipe requirement verification using LLM reasoning.

This module verifies that recipes meet user-specified requirements.
"""

import httpx
import json
import re
from typing import Dict, List


def nutrition_verification_tool(recipes_data: List[Dict], nutrition_requirements: Dict) -> Dict:
    """
    Deterministic nutrition verification tool for LLM to use.
    Performs precise numerical comparisons on nutrition requirements.
    
    Args:
        recipes_data: List of recipe data dicts with clean_nutrition field
        nutrition_requirements: {"protein": {"min": 30}, "calories": {"max": 400}}
        
    Returns:
        {
            "passing_recipe_indices": [0, 2, 4],
            "verification_details": [
                {"index": 0, "passes": True, "protein": "35g >= 30g ✅"},
                {"index": 1, "passes": False, "protein": "12g < 30g ❌"}
            ]
        }
    """
    passing_indices = []
    verification_details = []
    
    for i, recipe_data in enumerate(recipes_data):
        clean_nutrition = recipe_data.get('clean_nutrition', {})
        passes_all = True
        details = {"index": i, "title": recipe_data.get('title', 'Unknown')}
        
        # Check each nutrition requirement
        for nutrient, constraints in nutrition_requirements.items():
            if nutrient not in clean_nutrition:
                details[nutrient] = f"No {nutrient} data - FAIL"
                passes_all = False
                continue
                
            # Extract numeric value from clean nutrition (e.g., "30g" -> 30)
            nutrition_str = clean_nutrition[nutrient]
            try:
                # Extract number from strings like "30g", "400", "25.5g"
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', nutrition_str)
                if not match:
                    details[nutrient] = f"Could not parse '{nutrition_str}' - FAIL"
                    passes_all = False
                    continue
                    
                actual_value = float(match.group(1))
                
                # Check min constraint
                if 'min' in constraints:
                    required_min = constraints['min']
                    if actual_value >= required_min:
                        details[nutrient] = f"{nutrition_str} >= {required_min} ✅"
                    else:
                        details[nutrient] = f"{nutrition_str} < {required_min} ❌"
                        passes_all = False
                        
                # Check max constraint  
                if 'max' in constraints:
                    required_max = constraints['max']
                    if actual_value <= required_max:
                        details[nutrient] = f"{nutrition_str} <= {required_max} ✅"
                    else:
                        details[nutrient] = f"{nutrition_str} > {required_max} ❌"
                        passes_all = False
                        
            except (ValueError, AttributeError) as e:
                details[nutrient] = f"Parse error for '{nutrition_str}': {e} - FAIL"
                passes_all = False
        
        details["passes"] = passes_all
        verification_details.append(details)
        
        if passes_all:
            passing_indices.append(i)
    
    return {
        "passing_recipe_indices": passing_indices,
        "verification_details": verification_details
    }


def clean_nutrition_for_verification(unified_nutrition: List[str]) -> Dict[str, str]:
    """
    Clean and extract the 4 required nutrition values from messy unified_nutrition data.
    
    Args:
        unified_nutrition: Raw nutrition strings from recipe parsing
        
    Returns:
        Dict with clean nutrition values: {"protein": "30g", "calories": "402", "carbs": "50g", "fat": "13g"}
    """
    nutrition_clean = {}
    
    if not unified_nutrition:
        return nutrition_clean
    
    # Join all nutrition strings and clean them
    full_text = " ".join(unified_nutrition).lower()
    
    # More specific patterns to avoid mixing up values
    # Look for explicit nutrition labels with values
    nutrition_patterns = {
        "calories": [
            r'\b(\d{2,4})\s*calories\b',  # 2-4 digits followed by calories
            r'\bcalories[:\s]*(\d{2,4})\b',  # calories: followed by 2-4 digits
            r'\b(\d{2,4})\s*kcal\b',
            r'\bkcal[:\s]*(\d{2,4})\b'
        ],
        "protein": [
            r'\bprotein[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)\b',
            r'\b(\d+(?:\.\d+)?)\s*([a-z]*)\s+protein\b'
        ],
        "carbs": [
            r'\bcarbohydrates?[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)\b',
            r'\bcarbs[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)\b',
            r'\b(\d+(?:\.\d+)?)\s*([a-z]*)\s+carbs\b',
            r'\b(\d+(?:\.\d+)?)\s*([a-z]*)\s+carbohydrates?\b'
        ],
        "fat": [
            r'\b(?:total\s+)?fat[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)\b',
            r'\b(\d+(?:\.\d+)?)\s*([a-z]*)\s+fat\b'
        ]
    }
    
    # Debug: Show what we're parsing
    print(f"      🔍 Parsing nutrition from: {full_text[:500]}...")
    
    for nutrient, patterns in nutrition_patterns.items():
        found = False
        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match and not found:  # Take first match to avoid duplicates
                amount = match.group(1)
                unit = match.group(2) if len(match.groups()) > 1 else ""
                
                # Handle missing units - assume grams for protein/carbs/fat, no unit for calories
                if not unit or unit == "":
                    if nutrient == "calories":
                        nutrition_clean[nutrient] = f"{amount}"
                    else:
                        nutrition_clean[nutrient] = f"{amount}g"  # Default to grams
                else:
                    nutrition_clean[nutrient] = f"{amount}{unit}"
                
                print(f"         Found {nutrient}: {nutrition_clean[nutrient]} (pattern: {pattern})")
                found = True
                break
    
    print(f"      ✅ Clean nutrition result: {nutrition_clean}")
    return nutrition_clean


async def verify_recipes_meet_requirements(scraped_recipes: List[Dict], requirements: Dict, openai_key: str, user_query: str = "") -> List[Dict]:
    """
    Phase 1: Strict verification LLM - Binary PASS/FAIL verification only.
    Fast and focused on requirement checking.
    
    Args:
        scraped_recipes: List of recipes with full parsed data
        requirements: Strict requirements that must be met
        openai_key: OpenAI API key
        
    Returns:
        List of recipes that pass ALL requirements
    """
    if not scraped_recipes or not requirements:
        return scraped_recipes
    
    if not requirements:
        return scraped_recipes  # No requirements to verify
    
    # Prepare recipe data for verification
    recipe_data = []
    for i, recipe in enumerate(scraped_recipes):
        # Clean nutrition data from unified format
        unified_nutrition = recipe.get('unified_nutrition', [])
        clean_nutrition = clean_nutrition_for_verification(unified_nutrition)
        
        if clean_nutrition:
            # Format clean nutrition as readable string
            nutrition_parts = []
            for nutrient in ["calories", "protein", "carbs", "fat"]:
                if nutrient in clean_nutrition:
                    nutrition_parts.append(f"{nutrient}: {clean_nutrition[nutrient]}")
            nutrition_text = ", ".join(nutrition_parts)
        else:
            nutrition_text = "NO NUTRITION DATA AVAILABLE"
        
        recipe_data.append({
            "index": i,
            "title": recipe.get("title", "No title"),
            "nutrition": nutrition_text,
            "clean_nutrition": clean_nutrition,  # Also include structured format for LLM
            "ingredients": recipe.get("ingredients", [])[:10],  # First 10 ingredients
            "cook_time": recipe.get("cook_time", "Not specified")
        })
        
    
    # Check if we have nutrition requirements
    has_nutrition_requirements = bool(requirements.get('nutrition'))
    
    # Auto-disqualify recipes with no nutrition data if nutrition requirements exist
    pre_qualified_indices = []
    for i, recipe in enumerate(recipe_data):
        if has_nutrition_requirements and recipe['nutrition'] == "NO NUTRITION DATA AVAILABLE":
            print(f"      ❌ Auto-FAIL Recipe {i} ({recipe['title']}): No nutrition data but nutrition requirements exist")
            continue  # Skip this recipe - don't send to LLM
        pre_qualified_indices.append(i)
    
    if not pre_qualified_indices:
        print(f"   ❌ All recipes auto-failed due to missing nutrition data")
        return []
    
    # Filter recipe_data to only include pre-qualified recipes
    qualified_recipe_data = [recipe_data[i] for i in pre_qualified_indices]
    
    print(f"   📊 Sending {len(qualified_recipe_data)}/{len(recipe_data)} recipes to LLM (others auto-failed)")

    # Check if we have nutrition requirements to use the deterministic tool
    has_nutrition_requirements = bool(requirements.get('nutrition'))
    
    if has_nutrition_requirements:
        # Use deterministic nutrition verification tool first
        print(f"   🔧 Using deterministic nutrition verification tool...")
        nutrition_results = nutrition_verification_tool(qualified_recipe_data, requirements['nutrition'])
        
        # Show results from deterministic tool
        print(f"\n📊 DETERMINISTIC NUTRITION VERIFICATION:")
        for detail in nutrition_results['verification_details']:
            status = "✅ PASS" if detail['passes'] else "❌ FAIL"
            print(f"   {status}: {detail['title']}")
            for nutrient in ['protein', 'calories', 'carbs', 'fat']:
                if nutrient in detail:
                    print(f"      {nutrient}: {detail[nutrient]}")
        
        nutrition_passing_indices = nutrition_results['passing_recipe_indices']
        print(f"   🎯 Nutrition tool result: {len(nutrition_passing_indices)}/{len(qualified_recipe_data)} recipes passed nutrition requirements")
        
        # Filter recipes that passed nutrition check for LLM to handle other requirements
        nutrition_qualified_recipes = [qualified_recipe_data[i] for i in nutrition_passing_indices]
        
        if not nutrition_qualified_recipes:
            print(f"   ❌ No recipes passed nutrition verification")
            return []
        
        llm_recipes_data = nutrition_qualified_recipes
        llm_instruction = f"""You have been given {len(nutrition_qualified_recipes)} recipes that have ALREADY PASSED nutrition verification using a deterministic tool.

Your job is to verify the remaining non-nutrition requirements."""
    else:
        # No nutrition requirements, send all recipes to LLM
        llm_recipes_data = qualified_recipe_data  
        nutrition_passing_indices = list(range(len(qualified_recipe_data)))
        llm_instruction = "You need to verify all requirements for these recipes."

    prompt = f"""You are a recipe requirements checker. {llm_instruction}

USER QUERY: "{user_query}"
EXTRACTED REQUIREMENTS: {json.dumps(requirements, indent=2)}

VERIFICATION RULES:
1. For meal_type requirements: Check if recipe fits the meal category (breakfast, lunch, dinner, dessert, snack)
2. For dietary restrictions: Check ingredients for excluded items (gluten-free, vegan, keto, etc.)
3. For time constraints: Check if cook time meets limits (under 30 minutes, etc.)
4. For cooking method restrictions: Check preparation methods (no-bake, slow cooker, etc.)

{f"NOTE: Nutrition requirements have been handled by a deterministic tool. These {len(llm_recipes_data)} recipes already passed nutrition verification." if has_nutrition_requirements else ""}

RECIPES TO VERIFY:
{json.dumps(llm_recipes_data, indent=2)}

Verify each recipe against the remaining requirements and return the indices of qualifying recipes.

Return ONLY valid JSON:
{{
  "qualifying_indices": [list_of_passing_recipe_indices]
}}"""

    # DEBUG: Show exactly what data is being sent to verification LLM
    print(f"\n🔍 REQUIREMENTS VERIFICATION DEBUG:")
    print(f"   User Query: '{user_query}'")
    print(f"   Requirements: {json.dumps(requirements, indent=4)}")
    print(f"   Number of recipes to verify: {len(recipe_data)}")
    
    print(f"\n📋 RECIPE DATA SENT TO LLM:")
    for i, recipe in enumerate(recipe_data):
        print(f"   Recipe {i}: {recipe['title']}")
        print(f"      Clean Nutrition: {recipe['nutrition']}")
        print(f"      Raw Unified Nutrition: {', '.join(scraped_recipes[i].get('unified_nutrition', []))[:200]}...")
        print(f"      Cook Time: {recipe['cook_time']}")
        print(f"      Source URL: {scraped_recipes[i].get('source_url', 'No URL')}")
        print(f"      Ingredients (first 5): {recipe['ingredients'][:5]}")
        print()


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
                    {"role": "system", "content": "You are a strict recipe requirement verifier. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 500
            }
        )
        
        if response.status_code != 200:
            # If verification fails, return all recipes (fail-safe)
            return scraped_recipes
        
        try:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # DEBUG: Show the raw LLM response
            print(f"\n🤖 RAW LLM RESPONSE:")
            print(f"{llm_response}")
            print()
            
            # Parse JSON response
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            result = json.loads(llm_response.strip())
            llm_qualifying_indices = result.get('qualifying_indices', [])
            
            # Map LLM indices back through the nutrition filtering to original indices
            final_qualifying_indices = []
            if has_nutrition_requirements:
                # LLM worked on nutrition-qualified recipes, map back through both filters
                for llm_idx in llm_qualifying_indices:
                    if 0 <= llm_idx < len(nutrition_passing_indices):
                        nutrition_idx = nutrition_passing_indices[llm_idx]  # Map to nutrition-qualified index
                        original_idx = pre_qualified_indices[nutrition_idx]  # Map to original index
                        final_qualifying_indices.append(original_idx)
            else:
                # No nutrition filtering, map directly through pre-qualified
                for llm_idx in llm_qualifying_indices:
                    if 0 <= llm_idx < len(pre_qualified_indices):
                        original_idx = pre_qualified_indices[llm_idx]
                        final_qualifying_indices.append(original_idx)
            
            # Return only qualifying recipes
            qualifying_recipes = []
            for idx in final_qualifying_indices:
                if 0 <= idx < len(scraped_recipes):
                    qualifying_recipes.append(scraped_recipes[idx])
            
            print(f"   ✅ Final Verification: {len(qualifying_recipes)}/{len(scraped_recipes)} recipes passed ALL requirements")
            
            # DEBUG: Show which recipes passed/failed with detailed reasoning
            print(f"\n📊 FINAL VERIFICATION RESULTS:")
            passed_indices = set(final_qualifying_indices)
            for i, recipe in enumerate(scraped_recipes):
                if has_nutrition_requirements and recipe_data[i]['nutrition'] == "NO NUTRITION DATA AVAILABLE":
                    status = "❌ AUTO-FAILED (No nutrition data)"
                elif has_nutrition_requirements and i not in [pre_qualified_indices[ni] for ni in nutrition_passing_indices]:
                    status = "❌ FAILED (Nutrition requirements)"
                elif i in passed_indices:
                    status = "✅ PASSED (All requirements)"
                else:
                    status = "❌ FAILED (Other requirements)"
                    
                print(f"   {status}: {recipe.get('title', 'No title')}")
                print(f"      URL: {recipe.get('source_url', 'No URL')}")
                print(f"      Nutrition: {recipe_data[i]['nutrition']}")
                print()
            
            return qualifying_recipes
            
        except (json.JSONDecodeError, KeyError) as e:
            pass
            # If parsing fails, return all recipes (fail-safe)
            return scraped_recipes