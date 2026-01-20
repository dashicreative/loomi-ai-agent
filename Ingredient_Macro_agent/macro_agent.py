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
        # Step 1: Parallel nutrition lookups for ALL ingredients (USDA only first)
        async def lookup_ingredient_usda(ingredient: Dict):
            """Try USDA lookup for a single ingredient"""
            name = ingredient['name']
            usda_result = await tools.usda_lookup(ctx, name)

            if "error" not in usda_result:
                # Return USDA result with matched description for validation
                return {
                    'name': name,
                    'calories': usda_result.get('calories', 0),
                    'protein': usda_result.get('protein', 0),
                    'fat': usda_result.get('fat', 0),
                    'carbs': usda_result.get('carbs', 0),
                    'portions': usda_result.get('portions', []),
                    'source': 'USDA',
                    'usda_match': usda_result.get('description', name)  # For validation
                }

            # USDA failed
            return {
                'name': name,
                'calories': 0,
                'protein': 0,
                'fat': 0,
                'carbs': 0,
                'source': 'USDA_FAILED',
                'usda_match': None
            }

        # First pass: Try USDA for all ingredients
        print("\n🔍 Nutrition Data Sources:")
        print("-" * 50)
        initial_data = await asyncio.gather(*[lookup_ingredient_usda(ing) for ing in ingredients])

        # Step 1.5: BATCH VALIDATE USDA MATCHES
        usda_matches = []
        usda_indices = []

        for i, data in enumerate(initial_data):
            if data['source'] == 'USDA' and data['usda_match']:
                usda_matches.append((data['name'], data['usda_match']))
                usda_indices.append(i)

        if usda_matches:
            print(f"\n🔍 Validating {len(usda_matches)} USDA matches...")
            validation_results = await tools.batch_validate_usda_matches(usda_matches)

            # Mark invalid matches for re-processing
            invalid_indices = []
            for i, is_valid in enumerate(validation_results):
                if not is_valid:
                    idx = usda_indices[i]
                    invalid_indices.append(idx)
                    initial_data[idx]['source'] = 'USDA_INVALID'

            if invalid_indices:
                print(f"\n🔄 Re-processing {len(invalid_indices)} invalid USDA matches with web search...")

        # Step 1.6: Retry failed/invalid matches with web search
        async def retry_with_web(index: int, ingredient: Dict):
            """Retry with web search for failed/invalid USDA lookups"""
            name = ingredient['name']
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

            # Both USDA and web failed
            return {
                'name': name,
                'calories': 0,
                'protein': 0,
                'fat': 0,
                'carbs': 0,
                'source': 'ERROR'
            }

        # Re-process failed/invalid matches
        retry_tasks = []
        retry_indices = []
        for i, data in enumerate(initial_data):
            if data['source'] in ['USDA_FAILED', 'USDA_INVALID']:
                retry_tasks.append(retry_with_web(i, ingredients[i]))
                retry_indices.append(i)

        if retry_tasks:
            retry_results = await asyncio.gather(*retry_tasks)
            for i, result in zip(retry_indices, retry_results):
                initial_data[i] = result

        # Final nutrition data
        nutrition_data = initial_data

        # Print final sources
        print()
        for data in nutrition_data:
            source_emoji = "✅" if data['source'] == 'USDA' else ("🌐" if data['source'] == 'WEB' else "❌")
            print(f"{source_emoji} {data['source']:5} - {data['name']}")
        print()

        # Step 2: Calculate scaled nutrition for each ingredient
        total_calories = 0.0
        total_protein = 0.0
        total_fat = 0.0
        total_carbs = 0.0

        # Step 2: Calculate scaled nutrition for each ingredient
        print("\n📊 Ingredient Breakdown:")
        print("-" * 70)

        # Track ingredients that used WATER fallback for LLM estimation
        water_fallback_ingredients = []
        ingredient_results = []  # Store results for potential re-calculation

        for i, ingredient in enumerate(ingredients):
            nutrition = nutrition_data[i]

            # Convert quantity to grams (with source tracking)
            quantity = ingredient.get('quantity', '1')
            unit = ingredient.get('unit', 'count')
            name = ingredient.get('name', '')
            portions = nutrition.get('portions', [])  # Pass USDA portion data

            grams, source = tools.convert_to_grams(ctx, quantity, unit, name, portions)

            # Scale nutrition from per-100g to actual amount
            scale = grams / 100.0

            cal_scaled = nutrition['calories'] * scale
            pro_scaled = nutrition['protein'] * scale
            fat_scaled = nutrition['fat'] * scale
            carb_scaled = nutrition['carbs'] * scale

            print(f"{name[:35]:35} | {grams:6.1f}g [{source}]")
            print(f"  Per 100g: {nutrition['calories']:4.0f}cal {nutrition['protein']:4.1f}p {nutrition['fat']:4.1f}f {nutrition['carbs']:5.1f}c")
            print(f"  Scaled:   {cal_scaled:4.0f}cal {pro_scaled:4.1f}p {fat_scaled:4.1f}f {carb_scaled:5.1f}c")

            # Track water fallbacks for LLM estimation
            if source == "WATER":
                water_fallback_ingredients.append({
                    'index': i,
                    'name': name,
                    'quantity': quantity,
                    'unit': unit,
                    'grams_water': grams  # Current water-based estimate
                })

            # Store result for this ingredient
            ingredient_results.append({
                'name': name,
                'grams': grams,
                'source': source,
                'calories': cal_scaled,
                'protein': pro_scaled,
                'fat': fat_scaled,
                'carbs': carb_scaled
            })

            total_calories += cal_scaled
            total_protein += pro_scaled
            total_fat += fat_scaled
            total_carbs += carb_scaled
        print()

        # Step 3 (TIER 3): LLM Batch Density Estimation for WATER fallbacks
        if water_fallback_ingredients:
            print("\n🤖 Tier 3: LLM Density Estimation")
            print("-" * 70)
            print(f"Found {len(water_fallback_ingredients)} ingredient(s) using water density fallback")
            print("Requesting LLM density estimates...\n")

            # Build prompt for batch estimation
            ingredient_list = []
            for item in water_fallback_ingredients:
                ingredient_list.append(f"- {item['name']} (currently estimated: {item['grams_water']:.1f}g for {item['quantity']} {item['unit']})")

            prompt = f"""Estimate the weight in grams for these ingredients. Compare to water density baseline (240g/cup).

Ingredients needing estimation:
{chr(10).join(ingredient_list)}

For each ingredient, provide ONLY the estimated grams for the given quantity.
Return one number per line, in the same order as listed above.
If an ingredient is similar to water density, return the current estimate.
If heavier (like honey, nut butter), estimate higher.
If lighter (like flour, oats, cocoa powder), estimate lower.

Example format:
120
340
85

Your estimates:"""

            try:
                # Call Gemini for density estimation
                import google.generativeai as genai
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(prompt)
                llm_estimates = response.text.strip().split('\n')

                # Parse LLM estimates and recalculate
                for idx, item in enumerate(water_fallback_ingredients):
                    if idx < len(llm_estimates):
                        try:
                            llm_grams = float(llm_estimates[idx].strip())

                            # Sanity check (shouldn't be > 500g for 1 cup or < 10g)
                            if 10 <= llm_grams <= 500:
                                result_idx = item['index']
                                old_grams = ingredient_results[result_idx]['grams']
                                nutrition = nutrition_data[result_idx]

                                # Recalculate macros with LLM estimate
                                new_scale = llm_grams / 100.0
                                new_cal = nutrition['calories'] * new_scale
                                new_pro = nutrition['protein'] * new_scale
                                new_fat = nutrition['fat'] * new_scale
                                new_carb = nutrition['carbs'] * new_scale

                                # Update totals (subtract old, add new)
                                total_calories += (new_cal - ingredient_results[result_idx]['calories'])
                                total_protein += (new_pro - ingredient_results[result_idx]['protein'])
                                total_fat += (new_fat - ingredient_results[result_idx]['fat'])
                                total_carbs += (new_carb - ingredient_results[result_idx]['carbs'])

                                # Update stored result
                                ingredient_results[result_idx].update({
                                    'grams': llm_grams,
                                    'source': 'LLM',
                                    'calories': new_cal,
                                    'protein': new_pro,
                                    'fat': new_fat,
                                    'carbs': new_carb
                                })

                                change_pct = ((llm_grams - old_grams) / old_grams) * 100
                                print(f"  ✅ {item['name']}: {old_grams:.1f}g → {llm_grams:.1f}g ({change_pct:+.0f}%)")
                            else:
                                print(f"  ⚠️  {item['name']}: LLM estimate {llm_grams}g rejected (out of range)")
                        except ValueError:
                            print(f"  ⚠️  {item['name']}: Could not parse LLM estimate")

                print()

            except Exception as e:
                print(f"  ⚠️  LLM density estimation failed: {e}")
                print("     Continuing with water density defaults\n")

        # Step 4: Calculate metadata summary
        source_counts = {}
        for result in ingredient_results:
            source = result['source']
            source_counts[source] = source_counts.get(source, 0) + 1

        # Generate quality indicator
        total_ingredients = len(ingredient_results)
        quality_parts = []
        for source in ['USDA_PORTION', 'TABLE', 'LLM', 'WATER', 'ESTIMATE', 'DIRECT']:
            if source in source_counts:
                count = source_counts[source]
                pct = (count / total_ingredients) * 100
                quality_parts.append(f"{source}:{pct:.0f}%")

        quality_summary = ",".join(quality_parts) if quality_parts else "UNKNOWN"

        # Step 5: Return result with metadata and ingredient sources
        # Format: calories;quality,protein;quality,fat;quality,carbs;quality
        result_string = f"{total_calories:.0f};{quality_summary},{total_protein:.0f};{quality_summary},{total_fat:.0f};{quality_summary},{total_carbs:.0f};{quality_summary}"

        # Return both the formatted string and the detailed ingredient results
        return (result_string, ingredient_results)

    finally:
        # Clean up HTTP client
        await deps.http_client.aclose()


async def validate_macro_results(
    recipe_title: str,
    directions: List[str],
    ingredient_results: List[Dict],
    total_calories: int,
    total_protein: int,
    total_fat: int,
    total_carbs: int
) -> Dict:
    """
    Validate calculated macro results using LLM reasoning.

    This is a TOOL that the agent can use to sanity-check its calculations.
    It provides contextual validation using recipe semantics and common sense.

    Args:
        recipe_title: Recipe name (e.g., "Loaded Greek Chicken Salad Bowl")
        directions: List of cooking directions
        ingredient_results: Per-ingredient breakdown with source tracking
        total_calories: Total calculated calories
        total_protein: Total calculated protein (g)
        total_fat: Total calculated fat (g)
        total_carbs: Total calculated carbs (g)

    Returns:
        {
            "confidence": 0-100,
            "flagged_ingredients": [...],
            "overall_reasoning": "..."
        }
    """
    import google.generativeai as genai

    # Load validation prompt template
    prompt_path = Path(__file__).parent / "validation_prompt.txt"
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()

    # Format ingredient breakdown for LLM
    ingredient_breakdown_lines = []
    for result in ingredient_results:
        name = result['name']
        grams = result['grams']
        source = result['source']
        cal = result['calories']
        pro = result['protein']
        fat = result['fat']
        carb = result['carbs']

        ingredient_breakdown_lines.append(
            f"• {name}: {grams:.1f}g | {cal:.0f} cal, {pro:.1f}p, {fat:.1f}f, {carb:.1f}c | SOURCE={source}"
        )

    ingredient_breakdown = "\n".join(ingredient_breakdown_lines)

    # Format directions
    directions_text = "\n".join([f"{i+1}. {d}" for i, d in enumerate(directions)])

    # Fill in the prompt
    prompt = prompt_template.format(
        recipe_title=recipe_title,
        directions=directions_text,
        ingredient_breakdown=ingredient_breakdown,
        total_calories=total_calories,
        total_protein=total_protein,
        total_fat=total_fat,
        total_carbs=total_carbs
    )

    try:
        # Call Gemini for validation
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.3,  # Lower temperature for more consistent validation
                "max_output_tokens": 2000
            }
        )

        # Parse JSON response
        response_text = response.text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
        if response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # Remove trailing ```

        response_text = response_text.strip()

        # Parse JSON
        validation_result = json.loads(response_text)

        return validation_result

    except json.JSONDecodeError as e:
        print(f"⚠️  Failed to parse validation JSON: {e}")
        print(f"   Response: {response_text[:200]}...")
        return {
            "confidence": 50,
            "flagged_ingredients": [],
            "overall_reasoning": f"Validation parsing failed: {str(e)}"
        }
    except Exception as e:
        print(f"⚠️  Validation failed: {e}")
        return {
            "confidence": 50,
            "flagged_ingredients": [],
            "overall_reasoning": f"Validation error: {str(e)}"
        }


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
def calculate_recipe_macros_sync(ingredients: List[Dict]) -> tuple:
    """
    Synchronous wrapper for optimized macro calculation.
    Uses parallel processing for maximum speed.

    Returns:
        Tuple of (result_string, ingredient_results)
    """
    import asyncio
    return asyncio.run(calculate_recipe_macros_optimized(ingredients))