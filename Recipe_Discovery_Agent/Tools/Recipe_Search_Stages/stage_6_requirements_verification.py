"""
Stage 6: Requirements Verification
Handles recipe requirement verification using LLM reasoning.

This module verifies that recipes meet user-specified requirements.
"""

import httpx
import json
from typing import Dict, List


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
        # Get nutrition data from unified format (normalized during parsing)
        unified_nutrition = recipe.get('unified_nutrition', [])
        if unified_nutrition:
            nutrition_text = ", ".join(unified_nutrition)
        else:
            nutrition_text = "NO NUTRITION DATA AVAILABLE"
        
        recipe_data.append({
            "index": i,
            "title": recipe.get("title", "No title"),
            "nutrition": nutrition_text,
            "ingredients": recipe.get("ingredients", [])[:10],  # First 10 ingredients
            "cook_time": recipe.get("cook_time", "Not specified")
        })
        
        # DEBUG: Print what data is being sent to verification LLM
        print(f"   🔍 DEBUG Recipe {i+1}: {recipe.get('title', 'No title')}")
        print(f"      URL: {recipe.get('source_url', 'No URL')}")
        print(f"      Unified Nutrition: {nutrition_text}")
        print(f"      Original Raw Field: {recipe.get('nutrition', 'MISSING')}")
        print(f"      Original Structured Field: {recipe.get('structured_nutrition', 'MISSING')}")
        print(f"      Normalized Unified Field: {recipe.get('unified_nutrition', 'MISSING')}")
    
    prompt = f"""User's Original Query: "{user_query}"

You are verifying if recipes meet the user's requirements using your reasoning abilities.

REQUIREMENTS EXTRACTED FROM USER'S QUERY:
{json.dumps(requirements, indent=2)}

YOUR TASK:
Use your reasoning to determine if each recipe meets the user's intent and all extracted requirements.

VERIFICATION LOGIC:
- If nutrition requirements specified: Check if recipe meets the numeric values
- If meal_type specified: Verify the recipe is appropriate for that meal type
- If dietary restrictions: Check ingredients don't contain excluded items
- If time constraints: Verify cooking time fits requirements
- If recipe has "NO NUTRITION DATA AVAILABLE" and nutrition requirements exist: AUTOMATIC FAIL
- When in doubt about meeting requirements: FAIL the recipe

RECIPES TO VERIFY:
{json.dumps(recipe_data, indent=2)}

Use your reasoning to evaluate each recipe against the user's requirements and return qualifying indices:
{{
  "qualifying_indices": [0, 2, 4]
}}"""

    # DEBUG: Print exact LLM input
    print(f"\n🔍 DEBUG PHASE 1 LLM INPUT:")
    print(f"   Requirements Dict: {requirements}")
    print(f"   User Query: {user_query}")
    print(f"   Number of recipes to verify: {len(recipe_data)}")
    print(f"   Full Prompt Length: {len(prompt)} characters")

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
            
            # DEBUG: Print exact LLM response
            print(f"\n🔍 DEBUG PHASE 1 LLM OUTPUT:")
            print(f"   Raw LLM Response: {llm_response}")
            
            # Parse JSON response
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            result = json.loads(llm_response.strip())
            qualifying_indices = result.get('qualifying_indices', [])
            
            # DEBUG: Print parsed results
            print(f"   Parsed Qualifying Indices: {qualifying_indices}")
            
            # Return only qualifying recipes
            qualifying_recipes = []
            for idx in qualifying_indices:
                if 0 <= idx < len(scraped_recipes):
                    qualifying_recipes.append(scraped_recipes[idx])
            
            print(f"   ✅ Phase 1 Verification: {len(qualifying_recipes)}/{len(scraped_recipes)} recipes passed requirements")
            
            # DEBUG: Show which recipes passed/failed
            passed_indices = set(qualifying_indices)
            for i, recipe in enumerate(scraped_recipes):
                status = "✅ PASSED" if i in passed_indices else "❌ FAILED"
                print(f"      {status}: {recipe.get('title', 'No title')}")
            
            return qualifying_recipes
            
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠️  Phase 1 verification failed: {e}")
            # If parsing fails, return all recipes (fail-safe)
            return scraped_recipes