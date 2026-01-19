"""
Macro Calculation Agent
A minimal Pydantic AI agent for calculating recipe macronutrients using USDA data.
"""

import os
import json
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from dependencies import MacroDeps, create_macro_deps
import tools

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Load system prompt from file
def load_system_prompt() -> str:
    """Load system prompt from external txt file"""
    prompt_path = Path(__file__).parent / "system_prompt.txt"
    with open(prompt_path, 'r') as f:
        return f.read().strip()

# Configure Gemini API - Set as GOOGLE_API_KEY for Pydantic AI
google_key = os.getenv('GOOGLE_GEMINI_KEY')
if not google_key:
    raise ValueError("GOOGLE_GEMINI_KEY not found in .env file")

# Pydantic AI expects GOOGLE_API_KEY, so set it from your GOOGLE_GEMINI_KEY
os.environ['GOOGLE_API_KEY'] = google_key

# Create the macro calculation agent using Google model
macro_agent = Agent(
    'google-gla:gemini-2.5-flash',  # Correct model format for Pydantic AI
    deps_type=MacroDeps,
    system_prompt=load_system_prompt(),
)


@macro_agent.tool
async def lookup_nutrition_data(ctx: RunContext[MacroDeps], ingredient_name: str) -> str:
    """
    Look up nutrition data for an ingredient with USDA primary and web fallback.
    Returns: "calories: X, protein: Y, fat: Z, carbs: W per 100g (source: USDA/WEB)"
    """
    # Try USDA first
    usda_result = await tools.usda_lookup(ctx, ingredient_name)
    
    if "error" not in usda_result:
        # USDA success
        source = usda_result.get('source', 'USDA')
        return f"calories: {usda_result.get('calories', 0)}, protein: {usda_result.get('protein', 0)}g, fat: {usda_result.get('fat', 0)}g, carbs: {usda_result.get('carbs', 0)}g per 100g (source: {source})"
    
    # USDA failed, try web search fallback
    web_result = await tools.web_nutrition_search(ctx, ingredient_name)
    
    if "error" not in web_result:
        # Web search success
        source = web_result.get('source', 'WEB')
        return f"calories: {web_result.get('calories', 0)}, protein: {web_result.get('protein', 0)}g, fat: {web_result.get('fat', 0)}g, carbs: {web_result.get('carbs', 0)}g per 100g (source: {source})"
    
    # Both failed
    return f"Error: Could not find nutrition data for {ingredient_name}. USDA: {usda_result.get('error', 'Unknown')}. Web: {web_result.get('error', 'Unknown')}"


@macro_agent.tool  
def convert_to_grams(ctx: RunContext[MacroDeps], quantity: str, unit: str, ingredient_name: str) -> str:
    """
    Convert ingredient quantity and unit to grams for macro calculation.
    Example: quantity="2", unit="cups", ingredient_name="flour" returns "240g"
    """
    grams = tools.convert_to_grams(ctx, quantity, unit, ingredient_name)
    return f"{grams:.1f}g"


@macro_agent.tool
def calculate_nutrition_for_amount(ctx: RunContext[MacroDeps], calories_per_100g: float, protein_per_100g: float, fat_per_100g: float, carbs_per_100g: float, total_grams: float) -> str:
    """
    Calculate nutrition for a specific amount of ingredient.
    Takes nutrition per 100g and total grams, returns scaled nutrition values.
    """
    scale = total_grams / 100.0
    
    scaled_calories = calories_per_100g * scale
    scaled_protein = protein_per_100g * scale
    scaled_fat = fat_per_100g * scale
    scaled_carbs = carbs_per_100g * scale
    
    return f"calories: {scaled_calories:.1f}, protein: {scaled_protein:.1f}g, fat: {scaled_fat:.1f}g, carbs: {scaled_carbs:.1f}g"


async def calculate_recipe_macros_optimized(ingredients: List[Dict]) -> str:
    """
    Optimized parallel processing version - bypasses LLM tool-calling overhead.

    Processes all ingredients in parallel:
    1. Parallel USDA/web lookups for all ingredients simultaneously
    2. Parallel gram conversions
    3. Calculate and sum nutrition

    Args:
        ingredients: List of ingredient dictionaries with name, quantity, unit

    Returns:
        Comma-separated numbers: "calories,protein,fat,carbs" (e.g., "450,50,25,30")
    """
    import asyncio

    # Create dependencies instance
    deps = create_macro_deps()

    # Create a simple context-like object with just deps
    class SimpleContext:
        def __init__(self, deps):
            self.deps = deps

    ctx = SimpleContext(deps)

    try:
        # Step 1: Parallel nutrition lookups for ALL ingredients
        async def lookup_ingredient(ingredient: Dict):
            """Lookup nutrition data for a single ingredient"""
            name = ingredient['name']

            # Try USDA first
            usda_result = await tools.usda_lookup(ctx, name)

            if "error" not in usda_result:
                return {
                    'name': name,
                    'calories': usda_result.get('calories', 0),
                    'protein': usda_result.get('protein', 0),
                    'fat': usda_result.get('fat', 0),
                    'carbs': usda_result.get('carbs', 0),
                    'source': 'USDA'
                }

            # USDA failed, try web search
            web_result = await tools.web_nutrition_search(ctx, name)

            if "error" not in web_result:
                return {
                    'name': name,
                    'calories': web_result.get('calories', 0),
                    'protein': web_result.get('protein', 0),
                    'fat': web_result.get('fat', 0),
                    'carbs': web_result.get('carbs', 0),
                    'source': 'WEB'
                }

            # Both failed
            return {
                'name': name,
                'calories': 0,
                'protein': 0,
                'fat': 0,
                'carbs': 0,
                'source': 'ERROR'
            }

        # Parallel lookups for all ingredients
        print("\n🔍 Nutrition Data Sources:")
        print("-" * 50)
        nutrition_data = await asyncio.gather(*[lookup_ingredient(ing) for ing in ingredients])

        for data in nutrition_data:
            source_emoji = "✅" if data['source'] == 'USDA' else ("🌐" if data['source'] == 'WEB' else "❌")
            print(f"{source_emoji} {data['source']:5} - {data['name']}")
        print()

        # Step 2: Calculate scaled nutrition for each ingredient
        total_calories = 0.0
        total_protein = 0.0
        total_fat = 0.0
        total_carbs = 0.0

        print("\n📊 Ingredient Breakdown:")
        print("-" * 70)
        for i, ingredient in enumerate(ingredients):
            nutrition = nutrition_data[i]

            # Convert quantity to grams
            quantity = ingredient.get('quantity', '1')
            unit = ingredient.get('unit', 'count')
            name = ingredient.get('name', '')

            grams = tools.convert_to_grams(ctx, quantity, unit, name)

            # Scale nutrition from per-100g to actual amount
            scale = grams / 100.0

            cal_scaled = nutrition['calories'] * scale
            pro_scaled = nutrition['protein'] * scale
            fat_scaled = nutrition['fat'] * scale
            carb_scaled = nutrition['carbs'] * scale

            print(f"{name[:35]:35} | {grams:6.1f}g")
            print(f"  Per 100g: {nutrition['calories']:4.0f}cal {nutrition['protein']:4.1f}p {nutrition['fat']:4.1f}f {nutrition['carbs']:5.1f}c")
            print(f"  Scaled:   {cal_scaled:4.0f}cal {pro_scaled:4.1f}p {fat_scaled:4.1f}f {carb_scaled:5.1f}c")

            total_calories += cal_scaled
            total_protein += pro_scaled
            total_fat += fat_scaled
            total_carbs += carb_scaled
        print()

        # Step 3: Return comma-separated result
        return f"{total_calories:.0f},{total_protein:.0f},{total_fat:.0f},{total_carbs:.0f}"

    finally:
        # Clean up HTTP client
        await deps.http_client.aclose()


async def calculate_recipe_macros(ingredients: List[Dict]) -> str:
    """
    Main function to calculate macros for a complete recipe.

    Args:
        ingredients: List of ingredient dictionaries with name, quantity, unit

    Returns:
        Comma-separated numbers: "calories,protein,fat,carbs" (e.g., "450,50,25,30")
    """
    # Create dependencies instance
    deps = create_macro_deps()
    
    try:
        # Convert ingredients to JSON for agent processing
        ingredients_json = json.dumps(ingredients, indent=2)
        
        # Run the agent with ingredient list
        result = await macro_agent.run(
            f"Calculate total macros for these ingredients:\n{ingredients_json}",
            deps=deps
        )
        
        # Return the agent's response data (try different attributes)
        if hasattr(result, 'data'):
            return result.data
        elif hasattr(result, 'message'):
            return result.message
        else:
            # Debug: check what the result actually contains
            print(f"DEBUG: Available attributes: {dir(result)}")
            return str(result)
        
    finally:
        # Clean up HTTP client
        await deps.http_client.aclose()


# Sync wrapper for easier testing (uses optimized version)
def calculate_recipe_macros_sync(ingredients: List[Dict]) -> str:
    """
    Synchronous wrapper for optimized macro calculation.
    Uses parallel processing for maximum speed.
    """
    import asyncio
    return asyncio.run(calculate_recipe_macros_optimized(ingredients))