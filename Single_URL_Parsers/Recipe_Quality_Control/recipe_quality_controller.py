"""
Recipe Quality Control Module

Shared quality control operations for recipes from ANY source.
Used by Site Parser, Instagram Parser, and any future parsers.

All methods are source-agnostic and operate on standardized data formats.
"""

import re
import time
from pathlib import Path
from typing import Dict, List, Any
import google.generativeai as genai

# Import shared ingredient parser
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingredient_parser import IngredientParser


class RecipeQualityController:
    """
    Shared quality control operations for recipes from ANY source.

    Provides three core quality control operations:
    1. Ingredient cleanup - Remove editorial notes, split multi-ingredients
    2. Failed parse rescue - Fix ingredients that regex couldn't parse
    3. Directions paraphrasing - Copyright-safe rewriting

    All operations are source-agnostic and work on standardized data formats.
    """

    def __init__(self, google_model):
        """
        Initialize with Gemini model instance.

        Args:
            google_model: Configured Google Gemini model instance
        """
        self.google_model = google_model
        self.ingredient_parser = IngredientParser()  # For re-parsing rescued ingredients

    def call_llm(self, prompt: str, max_tokens: int = 1200) -> str:
        """
        Call Gemini LLM for quality control operations.

        Args:
            prompt: The prompt to send to Gemini
            max_tokens: Maximum tokens for the response

        Returns:
            Gemini response text
        """
        response = self.google_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=max_tokens
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        )

        if hasattr(response, 'text') and response.text:
            return response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                return candidate.content.parts[0].text.strip()
            else:
                raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
        else:
            raise Exception("Gemini returned empty response")

    def clean_ingredients_with_llm(self, processed_ingredients: List[Dict]) -> List[Dict]:
        """
        Use Gemini LLM to perform conservative quality control cleanup on ingredients.

        Operations:
        - Splits multi-ingredient entries ("1 tsp EACH: salt, pepper")
        - Removes editorial notes ("2 lbs chicken (I love organic)")
        - Removes parenthetical prep notes

        Source-agnostic: Works on any List[Dict] with {name, quantity, unit} format.

        Args:
            processed_ingredients: List of ingredient dictionaries from regex parser

        Returns:
            List of cleaned ingredient dictionaries (same structure, cleaned content)
        """
        if not processed_ingredients:
            return []

        # Convert ingredient objects to semicolon-delimited format for LLM reasoning
        ingredients_text_list = []
        for ingredient in processed_ingredients:
            # Format as "quantity unit name" or just "name" if no quantity/unit
            if ingredient.get("quantity") and ingredient.get("unit"):
                ingredient_text = f"{ingredient['quantity']} {ingredient['unit']} {ingredient['name']}"
            elif ingredient.get("quantity"):
                ingredient_text = f"{ingredient['quantity']} {ingredient['name']}"
            else:
                ingredient_text = ingredient['name']
            ingredients_text_list.append(ingredient_text)

        ingredients_input = ";".join(ingredients_text_list)

        # Load quality control prompt from shared location
        prompt_path = Path(__file__).parent / "llm_prompts" / "Ingredients_Quality_Control_Prompt.txt"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()

            prompt = prompt_template.format(ingredients_list=ingredients_input)

        except FileNotFoundError:
            raise Exception(f"Ingredients quality control prompt file not found: {prompt_path}")

        # Call Gemini for conservative ingredient cleanup
        print(f"   🧹 Performing ingredient quality control with GEMINI...")
        start_time = time.time()

        llm_response = self.call_llm(prompt, max_tokens=1200)

        elapsed = time.time() - start_time
        print(f"   ✅ Ingredient quality control completed in {elapsed:.2f}s")

        # Parse LLM response back to ingredient objects
        if not llm_response.strip():
            print(f"   ⚠️  LLM returned empty response - using original ingredients")
            return processed_ingredients

        # Split by semicolon delimiter and parse back to ingredient objects
        cleaned_ingredients = []
        raw_ingredients = llm_response.strip().split(';')

        for raw_ingredient in raw_ingredients:
            ingredient_text = raw_ingredient.strip()
            if not ingredient_text:
                continue

            # Parse back into quantity/unit/name using shared ingredient parser
            try:
                # Use single ingredient parsing
                parsed_ingredient = self.ingredient_parser.parse_ingredients_list(ingredient_text)
                if parsed_ingredient:
                    ingredient_obj = parsed_ingredient[0]  # Get first parsed ingredient
                    cleaned_ingredients.append({
                        "name": ingredient_obj.name,
                        "quantity": ingredient_obj.quantity,
                        "unit": ingredient_obj.unit
                    })
                else:
                    # Fallback: treat as name-only ingredient
                    cleaned_ingredients.append({
                        "name": ingredient_text,
                        "quantity": "",
                        "unit": ""
                    })
            except Exception:
                # Fallback: treat as name-only ingredient
                cleaned_ingredients.append({
                    "name": ingredient_text,
                    "quantity": "",
                    "unit": ""
                })

        print(f"   ✅ Quality control: {len(processed_ingredients)} → {len(cleaned_ingredients)} ingredients")
        return cleaned_ingredients

    def rescue_failed_ingredient_parses(self, ingredients: List[Dict]) -> List[Dict]:
        """
        Use Gemini LLM to rescue ingredients that failed regex parsing.

        Identifies ingredients with quantity="1" and unit="count" (likely failures),
        then extracts the real quantity/unit from the name field.

        Source-agnostic: Works on any List[Dict] with {name, quantity, unit} format.

        Args:
            ingredients: List of ingredient dicts (already editorial-cleaned)

        Returns:
            List of ingredient dictionaries with rescued quantity/unit/name
        """
        if not ingredients:
            return []

        # Identify failed parses (defaulted to "1 count")
        failed_ingredients = []
        failed_indices = []

        for i, ingredient in enumerate(ingredients):
            qty = ingredient.get("quantity", "")
            unit = ingredient.get("unit", "")

            # Heuristic: If quantity is "1" and unit is "count", likely a failed parse
            # (unless the name is something clearly countable like "egg" or "apple")
            if qty == "1" and unit == "count":
                name = ingredient.get("name", "")
                # Check if name still contains quantity/unit patterns (strong signal of failure)
                if any(char.isdigit() for char in name) or any(u in name.lower() for u in ["cup", "oz", "lb", "tsp", "tbsp", "tablespoon", "teaspoon"]):
                    failed_ingredients.append(name)
                    failed_indices.append(i)

        if not failed_ingredients:
            print(f"   ✅ No failed parses detected to rescue")
            return ingredients

        print(f"   🚨 Detected {len(failed_ingredients)} failed parses, attempting rescue...")

        # Format for LLM: semicolon-delimited list of ingredient names
        failed_input = ";".join(failed_ingredients)

        # Load rescue prompt from shared location
        prompt_path = Path(__file__).parent / "llm_prompts" / "Failed_Parse_Rescue_Prompt.txt"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()

            prompt = prompt_template.format(failed_ingredients=failed_input)

        except FileNotFoundError:
            raise Exception(f"Failed parse rescue prompt file not found: {prompt_path}")

        # Call Gemini for rescue
        print(f"   🔧 Rescuing failed parses with GEMINI...")
        start_time = time.time()

        llm_response = self.call_llm(prompt, max_tokens=1500)

        elapsed = time.time() - start_time
        print(f"   ✅ Failed parse rescue completed in {elapsed:.2f}s")

        # Parse LLM response: "quantity|unit|name;quantity|unit|name"
        rescued_ingredients = []
        raw_rescued = llm_response.strip().split(';')

        for raw_ingredient in raw_rescued:
            ingredient_text = raw_ingredient.strip()
            if not ingredient_text or '|' not in ingredient_text:
                continue

            parts = ingredient_text.split('|', 2)
            if len(parts) == 3:
                quantity, unit, name = parts
                rescued_ingredients.append({
                    "name": name.strip(),
                    "quantity": quantity.strip(),
                    "unit": unit.strip()
                })

        # Verify we got the expected number of rescues
        if len(rescued_ingredients) != len(failed_indices):
            print(f"   ⚠️  Expected {len(failed_indices)} rescues, got {len(rescued_ingredients)} - using partial results")

        # Merge rescued results back into original ingredient list
        result = ingredients.copy()
        rescue_count = 0

        for i, failed_idx in enumerate(failed_indices):
            if i < len(rescued_ingredients):
                original_name = ingredients[failed_idx]["name"]
                rescued = rescued_ingredients[i]
                result[failed_idx] = rescued
                rescue_count += 1
                print(f"   ✅ Rescued: '{original_name}' → {rescued['quantity']} {rescued['unit']} {rescued['name']}")

        print(f"   🎯 Successfully rescued {rescue_count}/{len(failed_indices)} failed parses")
        return result

    def paraphrase_directions_with_llm(self, formatted_directions: List[str]) -> List[str]:
        """
        Use Gemini LLM to paraphrase directions for copyright compliance.

        - Removes editorial flourishes ("lovingly combine" → "combine")
        - Removes personal voice ("I like to add" → "add")
        - Preserves all technical details (temperatures, times, techniques)

        Source-agnostic: Works on any List[str] of cooking steps.

        Args:
            formatted_directions: List of numbered cooking steps

        Returns:
            List of paraphrased cooking steps (same structure, different wording)
        """
        if not formatted_directions:
            return []

        # Convert list to pipe-delimited format for LLM reasoning
        steps_text = "|".join([f"{i+1}. {step}" for i, step in enumerate(formatted_directions)])

        # Load paraphrasing prompt from shared location
        prompt_path = Path(__file__).parent / "llm_prompts" / "Directions_Paraphrasing_Prompt.txt"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()

            prompt = prompt_template.format(formatted_steps=steps_text)

        except FileNotFoundError:
            raise Exception(f"Paraphrasing prompt file not found: {prompt_path}")

        # Call Gemini for conservative paraphrasing
        print(f"   ✏️  Paraphrasing directions with GEMINI...")
        start_time = time.time()

        llm_response = self.call_llm(prompt, max_tokens=1200)

        elapsed = time.time() - start_time
        print(f"   ✅ Directions paraphrased in {elapsed:.2f}s")

        # Parse LLM response back to list of steps
        if "No Paraphrasing Available" in llm_response:
            print(f"   ⚠️  LLM couldn't safely paraphrase - using original directions")
            return formatted_directions

        # Split by pipe delimiter and clean up numbering
        paraphrased_steps = []
        raw_steps = llm_response.strip().split('|')

        for raw_step in raw_steps:
            step = raw_step.strip()
            if not step:
                continue

            # Remove number prefixes and keep the step text
            step_text = re.sub(r'^\d+\.\s*', '', step).strip()
            if step_text:
                paraphrased_steps.append(step_text)

        # Ensure we have same number of steps
        if len(paraphrased_steps) != len(formatted_directions):
            print(f"   ⚠️  Paraphrasing changed step count ({len(formatted_directions)} → {len(paraphrased_steps)}) - using original")
            return formatted_directions

        print(f"   ✅ Successfully paraphrased {len(paraphrased_steps)} steps")
        return paraphrased_steps
