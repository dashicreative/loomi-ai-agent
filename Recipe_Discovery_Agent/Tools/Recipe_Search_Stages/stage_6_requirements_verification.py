"""
Stage 6: Requirements Verification
Handles recipe requirement verification using LLM reasoning.

This module verifies that recipes meet user-specified requirements.
"""

import httpx
import json
import re
from typing import Dict, List


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
    
    # Define patterns for the 4 required nutrition fields
    nutrition_patterns = {
        "protein": r'protein[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)',
        "calories": r'(?:calories|kcal|cal)[:\s]*(\d+(?:\.\d+)?)',
        "carbs": r'(?:carbs|carbohydrates?)[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)',
        "fat": r'fat[:\s]*(\d+(?:\.\d+)?)\s*([a-z]*)'
    }
    
    for nutrient, pattern in nutrition_patterns.items():
        match = re.search(pattern, full_text)
        if match:
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
        
    
    prompt = f"""User's Original Query: "{user_query}"

You are verifying if recipes meet the user's requirements using your reasoning abilities.

REQUIREMENTS EXTRACTED FROM USER'S QUERY:
{json.dumps(requirements, indent=2)}

YOUR TASK:
Use your reasoning to determine if each recipe meets the user's intent and all extracted requirements.

VERIFICATION LOGIC:
- If nutrition requirements specified: Check if recipe meets the numeric values (e.g., "protein >= 30g")
- If meal_type specified: Verify the recipe is appropriate for that meal type
- If dietary restrictions: Check ingredients don't contain excluded items
- If time constraints: Verify cooking time fits requirements
- If recipe has "NO NUTRITION DATA AVAILABLE" and nutrition requirements exist: AUTOMATIC FAIL
- When in doubt about meeting requirements: FAIL the recipe

EXAMPLE PROTEIN VERIFICATION:
- Requirement: protein >= 30g
- Recipe has "protein: 24g" → FAIL (24 < 30)
- Recipe has "protein: 30g" → PASS (30 >= 30)  
- Recipe has "protein: 35g" → PASS (35 > 30)

RECIPES TO VERIFY (with clean nutrition data):
{json.dumps(recipe_data, indent=2)}

IMPORTANT: Use the "nutrition" field which contains clean, parsed nutrition data in the format "calories: X, protein: Xg, carbs: Xg, fat: Xg".

Use your reasoning to evaluate each recipe against the user's requirements and return qualifying indices:
{{
  "qualifying_indices": [0, 2, 4]
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
            qualifying_indices = result.get('qualifying_indices', [])
            
            
            # Return only qualifying recipes
            qualifying_recipes = []
            for idx in qualifying_indices:
                if 0 <= idx < len(scraped_recipes):
                    qualifying_recipes.append(scraped_recipes[idx])
            
            print(f"   ✅ Phase 1 Verification: {len(qualifying_recipes)}/{len(scraped_recipes)} recipes passed requirements")
            
            # DEBUG: Show which recipes passed/failed
            print(f"\n📊 VERIFICATION RESULTS:")
            passed_indices = set(qualifying_indices)
            for i, recipe in enumerate(scraped_recipes):
                status = "✅ PASSED" if i in passed_indices else "❌ FAILED"
                print(f"   {status}: {recipe.get('title', 'No title')}")
                print(f"      URL: {recipe.get('source_url', 'No URL')}")
                print(f"      Nutrition: {recipe_data[i]['nutrition']}")
                print()
            
            return qualifying_recipes
            
        except (json.JSONDecodeError, KeyError) as e:
            pass
            # If parsing fails, return all recipes (fail-safe)
            return scraped_recipes