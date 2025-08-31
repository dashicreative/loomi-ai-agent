"""
Stage 7: Relevance Ranking
Handles ranking of qualified recipes by relevance to user query.

This module ranks pre-qualified recipes by relevance using LLM.
"""

import httpx
from typing import Dict, List


async def rank_qualified_recipes_by_relevance(qualified_recipes: List[Dict], query: str, openai_key: str) -> List[Dict]:
    """
    Phase 2: Relevance Ranking LLM - Ranks pre-qualified recipes by relevance only.
    Focused on quality and relevance ranking after requirements verification.
    
    Args:
        qualified_recipes: List of recipes that already passed requirement verification
        query: Original user query
        openai_key: OpenAI API key
        
    Returns:
        Recipes ranked by relevance to user query
    """
    if not qualified_recipes:
        return []
    
    if len(qualified_recipes) == 1:
        return qualified_recipes  # No need to rank single recipe
    
    # Build recipe summaries for relevance ranking
    detailed_recipes = []
    for i, recipe in enumerate(qualified_recipes):
        ingredients_list = recipe.get("ingredients", [])[:8]  # First 8 ingredients
        ingredients_text = ", ".join(ingredients_list) if ingredients_list else ""
        
        recipe_summary = f"""{i+1}. {recipe.get('title', 'Untitled Recipe')}
Ingredients: {ingredients_text}
Cook Time: {recipe.get('cook_time', 'Not specified')}
Servings: {recipe.get('servings', 'Not specified')}"""
        
        detailed_recipes.append(recipe_summary)
    
    recipes_text = "\n\n".join(detailed_recipes)
    
    prompt = f"""User is searching for: "{query}"

These recipes have already PASSED all requirement verification. Your job is to rank them by RELEVANCE to the user's query only.

🎯 RANKING FACTORS:
- How well the recipe matches the user's intent
- Quality and appeal of the recipe
- Cooking complexity appropriate to query
- Ingredient freshness and accessibility

🍳 PRE-QUALIFIED RECIPES TO RANK:
{recipes_text}

📋 RETURN FORMAT:
Return ONLY a comma-separated list of numbers in order of relevance (best first).
Example: "3,1,2" (if recipe 3 is most relevant, then 1, then 2)"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a recipe relevance ranker. Return only comma-separated numbers."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }
        )
        
        if response.status_code != 200:
            return qualified_recipes
        
        try:
            data = response.json()
            ranking_text = data['choices'][0]['message']['content'].strip()
            rankings = [int(x.strip()) - 1 for x in ranking_text.split(',')]
            
            reranked = []
            for idx in rankings:
                if 0 <= idx < len(qualified_recipes):
                    reranked.append(qualified_recipes[idx])
            
            # Add any missing recipes
            for recipe in qualified_recipes:
                if recipe not in reranked:
                    reranked.append(recipe)
            
            print(f"   ✅ Phase 2 Ranking: Ranked {len(qualified_recipes)} qualified recipes by relevance")
            return reranked
            
        except (ValueError, IndexError):
            return qualified_recipes