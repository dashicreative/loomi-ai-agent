"""
Vertical Video Recipe Processor

Shared processing module for ALL vertical video recipe parsers (Instagram, TikTok, Facebook, YouTube).
Handles steps 5+ of the parsing pipeline - everything AFTER transcript extraction.

Source-agnostic: Works on any video recipe content with caption + transcript.
"""

import time
import sys
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Import shared quality control module
sys.path.insert(0, str(Path(__file__).parent.parent / "Recipe_Quality_Control"))
from recipe_quality_controller import RecipeQualityController

# Import Instagram modules temporarily (will be moved to shared later)
sys.path.insert(0, str(Path(__file__).parent.parent / "Instagram_Parser" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "Meta_Step_Extraction"))
sys.path.insert(0, str(Path(__file__).parent.parent / "Step_Ingredient_Matching"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from instagram_json_structuring import RecipeStructurer
from meta_step_extractor import MetaStepExtractor
from step_ingredient_matcher import StepIngredientMatcher
from json_recipe_model import create_enhanced_recipe_json


class VerticalVideoProcessor:
    """
    Shared processor for vertical video recipes (Instagram, TikTok, Facebook, YouTube).

    Handles Steps 5+:
    - Combine content for LLM parsing
    - Parallel LLM extraction (ingredients, directions, meal occasion)
    - Quality control (clean, rescue, paraphrase)
    - Meta step extraction
    - Step-ingredient matching
    - JSON structuring

    Source-agnostic: Operates on standardized (caption + transcript) format.
    """

    def __init__(self, google_model):
        """
        Initialize processor with Google Gemini model.

        Args:
            google_model: Configured Google Gemini model instance
        """
        self.google_model = google_model

        # Initialize shared modules
        self.quality_controller = RecipeQualityController(google_model)
        self.recipe_structurer = RecipeStructurer()
        self.meta_step_extractor = MetaStepExtractor(google_model)
        self.step_ingredient_matcher = StepIngredientMatcher(google_model)

        # Load LLM prompts from shared location
        self.prompts_dir = Path(__file__).parent / "llm_prompts"

    def combine_content_for_parsing(self, transcript: str, metadata: Dict[str, Any]) -> str:
        """
        Combine transcript and metadata into clean text for LLM parsing.

        Args:
            transcript: Video transcript text
            metadata: Dictionary with caption, creator info, etc.

        Returns:
            Combined content string for LLM parsing
        """
        parts = []

        # Add caption if available
        if metadata.get('caption'):
            parts.append(f"POST DESCRIPTION:\n{metadata['caption']}\n")

        # Add transcript
        if transcript:
            parts.append(f"VIDEO TRANSCRIPT:\n{transcript}\n")

        # Add creator context if available
        if metadata.get('creator_username'):
            parts.append(f"CREATOR: @{metadata['creator_username']}\n")

        return "\n".join(parts)

    def extract_ingredients(self, combined_content: str) -> str:
        """
        Extract ingredients from combined content using LLM.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Raw ingredients output from LLM
        """
        prompt_path = self.prompts_dir / "Ingredients_LLM_Parsing_Prompt.txt"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(combined_content=combined_content)

        start_time = time.time()
        response = self.google_model.generate_content(prompt)

        if hasattr(response, 'text') and response.text:
            result = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                result = candidate.content.parts[0].text.strip()
            else:
                raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
        else:
            raise Exception("Gemini returned empty response")

        elapsed = time.time() - start_time
        print(f"      🥕 Ingredients LLM (GEMINI): {elapsed:.2f}s")

        return result

    def extract_title_and_directions(self, combined_content: str) -> str:
        """
        Extract title and directions from combined content using LLM.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Raw directions output from LLM (includes title as first line)
        """
        prompt_path = self.prompts_dir / "Directions_LLM_Parsing_Prompt.txt"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(combined_content=combined_content)

        start_time = time.time()
        response = self.google_model.generate_content(prompt)

        if hasattr(response, 'text') and response.text:
            result = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                result = candidate.content.parts[0].text.strip()
            else:
                raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
        else:
            raise Exception("Gemini returned empty response")

        elapsed = time.time() - start_time
        print(f"      📝 Directions LLM (GEMINI): {elapsed:.2f}s")

        return result

    def extract_meal_occasion(self, combined_content: str) -> str:
        """
        Extract meal occasion from combined content using LLM.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Meal occasion category
        """
        prompt_path = self.prompts_dir / "Meal_Occasion_LLM_Parsing_Prompt.txt"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(combined_content=combined_content)

        start_time = time.time()
        response = self.google_model.generate_content(prompt)

        if hasattr(response, 'text') and response.text:
            result = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                result = candidate.content.parts[0].text.strip()
            else:
                raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
        else:
            raise Exception("Gemini returned empty response")

        # Validate category
        valid_categories = ["Breakfast", "Lunch", "Dinner", "Dessert", "Snack", "Other"]
        if result not in valid_categories:
            result = "Other"

        elapsed = time.time() - start_time
        print(f"      🍽️  Meal Occasion LLM (GEMINI): {elapsed:.2f}s")

        return result

    def extract_nutrition(self, combined_content: str) -> Dict[str, Any]:
        """
        Extract macro nutrition values from combined content using LLM.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Dictionary with calories, protein, fat, carbs, servings
            All values are integers. Returns all zeros if no nutrition found.
        """
        prompt_path = self.prompts_dir / "Nutrition_LLM_Parsing_Prompt.txt"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(combined_content=combined_content)

        start_time = time.time()
        response = self.google_model.generate_content(prompt)

        if hasattr(response, 'text') and response.text:
            result = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                result = candidate.content.parts[0].text.strip()
            else:
                raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
        else:
            raise Exception("Gemini returned empty response")

        elapsed = time.time() - start_time
        print(f"      🔢 Nutrition LLM (GEMINI): {elapsed:.2f}s")

        # Parse the comma-separated response: "calories,protein,fat,carbs,servings"
        try:
            # Extract numbers from response (handles any extra text)
            import re
            numbers = re.findall(r'\d+', result)

            if len(numbers) >= 5:
                return {
                    "calories": int(numbers[0]),
                    "protein": int(numbers[1]),
                    "fat": int(numbers[2]),
                    "carbs": int(numbers[3]),
                    "servings": int(numbers[4])
                }
            else:
                print(f"      ⚠️  Nutrition extraction returned unexpected format: {result}")
                return {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "servings": 0}
        except Exception as e:
            print(f"      ⚠️  Failed to parse nutrition response: {e}")
            return {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "servings": 0}

    def validate_single_macro(
        self,
        macro_name: str,
        stated_value: int,
        servings: int,
        recipe_title: str,
        ingredient_list: str
    ) -> bool:
        """
        Validate if a single macro value has already been multiplied by servings.

        Args:
            macro_name: Name of the macro (calories, protein, fat, carbs)
            stated_value: The extracted macro value
            servings: Number of servings
            recipe_title: Title of the recipe
            ingredient_list: Formatted ingredient list string

        Returns:
            True if value is already total (don't multiply), False if per-serving (needs multiply)
        """
        prompt_path = self.prompts_dir / "Nutrition_Validation_Prompt.txt"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        # Determine unit based on macro type
        unit = "" if macro_name == "calories" else "g"

        prompt = prompt_template.format(
            macro_name=macro_name,
            macro_name_upper=macro_name.upper(),
            stated_value=stated_value,
            unit=unit,
            servings=servings,
            recipe_title=recipe_title,
            ingredient_list=ingredient_list
        )

        start_time = time.time()
        response = self.google_model.generate_content(prompt)

        if hasattr(response, 'text') and response.text:
            result = response.text.strip().upper()
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                result = candidate.content.parts[0].text.strip().upper()
            else:
                # Default to TRUE (already multiplied) on error - safer
                result = "TRUE"
        else:
            result = "TRUE"

        elapsed = time.time() - start_time
        print(f"         🔍 {macro_name.capitalize()} validation: {result} ({elapsed:.2f}s)")

        # Parse response - TRUE means already multiplied, FALSE means needs multiply
        return "TRUE" in result

    def validate_nutrition_multiplier(
        self,
        nutrition: Dict[str, Any],
        recipe_title: str,
        ingredients: List[Dict[str, str]]
    ) -> bool:
        """
        Validate if nutrition values need to be multiplied by servings.

        Runs 4 parallel LLM calls (one per macro) and uses weighted voting.
        Calories and protein are weighted more heavily.

        Args:
            nutrition: Dict with calories, protein, fat, carbs, servings
            recipe_title: Title of the recipe
            ingredients: List of ingredient dicts with name, quantity, unit

        Returns:
            True if values are already total (don't multiply), False if per-serving (needs multiply)
        """
        servings = nutrition.get("servings", 1)
        if servings <= 1:
            return True  # No multiplication needed

        # Format ingredient list for the prompt
        ingredient_lines = []
        for ing in ingredients:
            qty = ing.get("quantity", "")
            unit = ing.get("unit", "")
            name = ing.get("name", "")
            ingredient_lines.append(f"- {qty} {unit} {name}".strip())
        ingredient_list = "\n".join(ingredient_lines)

        print(f"   🔍 Validating nutrition multiplier (servings={servings})...")
        validation_start = time.time()

        # Run 4 parallel validation calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            calories_future = executor.submit(
                self.validate_single_macro,
                "calories", nutrition["calories"], servings, recipe_title, ingredient_list
            )
            protein_future = executor.submit(
                self.validate_single_macro,
                "protein", nutrition["protein"], servings, recipe_title, ingredient_list
            )
            fat_future = executor.submit(
                self.validate_single_macro,
                "fat", nutrition["fat"], servings, recipe_title, ingredient_list
            )
            carbs_future = executor.submit(
                self.validate_single_macro,
                "carbs", nutrition["carbs"], servings, recipe_title, ingredient_list
            )

            # Get results
            calories_is_total = calories_future.result()
            protein_is_total = protein_future.result()
            fat_is_total = fat_future.result()
            carbs_is_total = carbs_future.result()

        validation_elapsed = time.time() - validation_start

        # Weighted voting: calories and protein count more
        # Calories: 2 votes, Protein: 2 votes, Fat: 1 vote, Carbs: 1 vote
        votes_for_total = 0
        if calories_is_total:
            votes_for_total += 2
        if protein_is_total:
            votes_for_total += 2
        if fat_is_total:
            votes_for_total += 1
        if carbs_is_total:
            votes_for_total += 1

        # Need 3+ votes (out of 6) to conclude it's already total
        is_already_total = votes_for_total >= 3

        print(f"      📊 Validation votes: cal={calories_is_total}, pro={protein_is_total}, fat={fat_is_total}, carbs={carbs_is_total}")
        print(f"      📊 Weighted score: {votes_for_total}/6 → {'ALREADY TOTAL' if is_already_total else 'NEEDS MULTIPLY'}")
        print(f"   ✅ Nutrition validation complete ({validation_elapsed:.2f}s)")

        return is_already_total

    def parse_recipe_parallel(self, combined_content: str) -> Tuple[str, str, str, Dict[str, Any]]:
        """
        Run ingredient, direction, meal occasion, and nutrition extraction in parallel.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Tuple of (ingredients_output, directions_output, meal_occasion_output, nutrition_output)
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            print("   🍅 Starting ingredients extraction (GEMINI)...")
            print("   📝 Starting directions extraction (GEMINI)...")
            print("   🍽️  Starting meal occasion extraction (GEMINI)...")
            print("   🔢 Starting nutrition extraction (GEMINI)...")

            parallel_start = time.time()

            # Submit all four tasks
            ingredients_future = executor.submit(self.extract_ingredients, combined_content)
            directions_future = executor.submit(self.extract_title_and_directions, combined_content)
            meal_occasion_future = executor.submit(self.extract_meal_occasion, combined_content)
            nutrition_future = executor.submit(self.extract_nutrition, combined_content)

            # Wait for results
            ingredients_result = ingredients_future.result()
            directions_result = directions_future.result()
            meal_occasion_result = meal_occasion_future.result()
            nutrition_result = nutrition_future.result()

            parallel_total = time.time() - parallel_start
            print(f"   ✅ Parallel LLM calls completed in {parallel_total:.2f}s")

            return ingredients_result, directions_result, meal_occasion_result, nutrition_result

    def parse_meta_ingredient_response(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Parse delimited LLM response into structured meta-ingredients.

        Expected format: META_1:I101,I102|baby cucumber

        Args:
            llm_response: Raw LLM response with pipe-delimited format

        Returns:
            List of meta-ingredient dictionaries with id, name, and linked_raw_ids
        """
        meta_ingredients = []

        try:
            lines = llm_response.strip().split('\n')

            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Split by pipe: "META_1:I101,I102" | "baby cucumber"
                if '|' not in line:
                    continue

                id_part, name = line.split('|', 1)
                name = name.strip()

                # Split by colon: "META_1" : "I101,I102"
                if ':' not in id_part:
                    continue

                meta_id, raw_ids_str = id_part.split(':', 1)
                meta_id = meta_id.strip()

                # Split by comma: ["I101", "I102"]
                raw_ids = [rid.strip() for rid in raw_ids_str.split(',') if rid.strip()]

                meta_ingredients.append({
                    "id": meta_id,
                    "name": name,
                    "linked_raw_ids": raw_ids
                })

            return meta_ingredients

        except Exception as e:
            print(f"   ⚠️  Failed to parse meta-ingredient response: {str(e)}")
            return []

    def generate_meta_ingredients(self, ingredients_with_ids: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Generate meta-ingredients by identifying and grouping duplicate ingredients using LLM.

        This creates a deduplicated shopping-friendly ingredient list while preserving
        product-defining descriptors and stripping only preparation notes.

        Args:
            ingredients_with_ids: Dictionary mapping ingredient ID to ingredient data
                                 (output from step_ingredient_matcher)

        Returns:
            List of meta-ingredient dictionaries:
            [
                {
                    "id": "META_1",
                    "name": "baby cucumber",
                    "linked_raw_ids": ["I101", "I102"]
                },
                ...
            ]
        """
        if not ingredients_with_ids:
            return []

        print(f"   🔍 Generating meta-ingredients (deduplication)...")
        step_start = time.time()

        # Format ingredients for LLM prompt: "I101: 1 count baby cucumber | I102: 2 count cucumber"
        ingredient_list = []
        for ingredient_id, data in ingredients_with_ids.items():
            name = data["name"]
            quantity = data.get("quantity", "")
            unit = data.get("unit", "")
            # Include quantity and unit for LLM context
            display = f"{ingredient_id}: {quantity} {unit} {name}".strip()
            ingredient_list.append(display)

        ingredients_formatted = " | ".join(ingredient_list)

        # Load prompt template
        prompt_path = self.prompts_dir / "Ingredient_Deduplication_Prompt.txt"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()

            prompt = prompt_template.format(ingredients_with_ids=ingredients_formatted)

            # Call Gemini for deduplication
            llm_start = time.time()

            response = self.google_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2000
                }
            )

            # Extract response text
            if hasattr(response, 'text') and response.text:
                llm_response = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content.parts:
                    llm_response = candidate.content.parts[0].text.strip()
                else:
                    raise Exception(f"Gemini response blocked: {candidate.finish_reason}")
            else:
                raise Exception("Gemini returned empty response")

            llm_elapsed = time.time() - llm_start
            print(f"      ✅ Deduplication LLM completed in {llm_elapsed:.2f}s")

            # Parse response into structured meta-ingredients
            meta_ingredients = self.parse_meta_ingredient_response(llm_response)

            # TODO: Quantity aggregation commented out for testing (iOS app may handle this)
            # # Aggregate quantities for each meta ingredient
            # for meta in meta_ingredients:
            #     linked_ids = meta.get("linked_raw_ids", [])
            #     if not linked_ids:
            #         meta["quantity"] = ""
            #         meta["unit"] = ""
            #         continue
            #
            #     # Collect all quantities and units from linked raw ingredients
            #     quantities = []
            #     units = []
            #     for raw_id in linked_ids:
            #         if raw_id in ingredients_with_ids:
            #             raw_ing = ingredients_with_ids[raw_id]
            #             qty = raw_ing.get("quantity", "")
            #             unit = raw_ing.get("unit", "")
            #             if qty and unit:
            #                 quantities.append(qty)
            #                 units.append(unit)
            #
            #     # Aggregate quantities if all have the same unit
            #     if quantities and units:
            #         unique_units = set(units)
            #         if len(unique_units) == 1:
            #             # Same unit - sum the quantities
            #             try:
            #                 total = sum(float(q) for q in quantities)
            #                 # Return as int if whole number
            #                 meta["quantity"] = str(int(total)) if total.is_integer() else str(total)
            #                 meta["unit"] = units[0]
            #             except (ValueError, TypeError):
            #                 # If conversion fails, leave empty
            #                 meta["quantity"] = ""
            #                 meta["unit"] = ""
            #         else:
            #             # Different units - can't aggregate, leave empty
            #             meta["quantity"] = ""
            #             meta["unit"] = ""
            #     else:
            #         meta["quantity"] = ""
            #         meta["unit"] = ""

            elapsed = time.time() - step_start
            print(f"   ✅ Generated {len(meta_ingredients)} meta-ingredients ({elapsed:.2f}s)")

            return meta_ingredients

        except Exception as e:
            print(f"   ⚠️  Meta-ingredient generation failed: {str(e)}")
            # Fallback: Create 1-to-1 mapping (no deduplication)
            fallback_meta = []
            for i, (ingredient_id, data) in enumerate(ingredients_with_ids.items(), 1):
                fallback_meta.append({
                    "id": f"META_{i}",
                    "name": data["name"],
                    "linked_raw_ids": [ingredient_id]
                    # TODO: Quantity/unit fields commented out for testing
                    # "quantity": data.get("quantity", ""),
                    # "unit": data.get("unit", "")
                })
            print(f"   ℹ️  Using fallback: {len(fallback_meta)} meta-ingredients (1-to-1 mapping)")
            return fallback_meta

    def process_recipe(
        self,
        transcript: str,
        metadata: Dict[str, Any],
        source_url: str,
        parser_method: str
    ) -> str:
        """
        Process vertical video recipe from transcript to structured JSON.

        This is the main entry point for ALL vertical video parsers.
        Steps 5-10 of the recipe parsing pipeline.

        Args:
            transcript: Video transcript text
            metadata: Dict with caption, creator info, etc.
            source_url: Original video URL
            parser_method: Parser name ("Instagram", "TikTok", "Facebook", "YouTube")

        Returns:
            Structured recipe JSON string
        """
        timings = {}

        # Step 5: Combine content for LLM parsing
        print("🔗 Step 5: Combining content...")
        step_start = time.time()
        combined_content = self.combine_content_for_parsing(transcript, metadata)
        timings['content_combination'] = time.time() - step_start
        print(f"   ✅ Content combined ({timings['content_combination']:.2f}s)")

        # Step 6: Run parallel recipe extraction (ingredients, directions, meal occasion, nutrition)
        print("🤖 Step 6: Running parallel LLM recipe extraction (GEMINI)...")
        step_start = time.time()
        ingredients_output, directions_output, meal_occasion_output, nutrition_output = self.parse_recipe_parallel(combined_content)
        timings['llm_parsing'] = time.time() - step_start
        print(f"   ✅ LLM parsing complete ({timings['llm_parsing']:.2f}s)")

        # DEBUG: Show raw LLM outputs
        print("\n" + "="*60)
        print("🐛 DEBUG: RAW LLM OUTPUTS FROM STEP 6")
        print("="*60)
        print(f"🥕 INGREDIENTS (first 400 chars):\n{ingredients_output[:400]}")
        print(f"\n📝 DIRECTIONS (first 400 chars):\n{directions_output[:400]}")
        print(f"\n🍽️  MEAL OCCASION: {meal_occasion_output}")
        print(f"\n🔢 NUTRITION: {nutrition_output['calories']} cal, {nutrition_output['protein']}g pro, {nutrition_output['fat']}g fat, {nutrition_output['carbs']}g carbs (servings: {nutrition_output['servings']})")
        print("="*60 + "\n")

        # Step 6.5: Parse LLM outputs into structured format
        print("📋 Step 6.5: Parsing LLM outputs...")
        step_start = time.time()

        parsed_ingredients = self.recipe_structurer.parse_ingredients(ingredients_output)
        title, parsed_directions = self.recipe_structurer.parse_directions(directions_output)

        # Convert ParsedIngredient objects to dict format for quality control
        ingredients_for_quality_control = [
            {
                "name": ing.name,
                "quantity": ing.quantity,
                "unit": ing.unit
            }
            for ing in parsed_ingredients
        ]

        timings['parsing'] = time.time() - step_start
        print(f"   ✅ Parsing complete ({timings['parsing']:.2f}s)")

        # Step 7: PARALLEL BATCH 2 - Quality Control (clean + paraphrase)
        print("🧹 Step 7: Running quality control (GEMINI)...")
        step_start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            clean_ingredients_future = executor.submit(
                self.quality_controller.clean_ingredients_with_llm,
                ingredients_for_quality_control
            )
            paraphrase_directions_future = executor.submit(
                self.quality_controller.paraphrase_directions_with_llm,
                parsed_directions
            )

            cleaned_ingredients = clean_ingredients_future.result()
            paraphrased_directions = paraphrase_directions_future.result()

        timings['quality_control'] = time.time() - step_start
        print(f"   ✅ Quality control complete ({timings['quality_control']:.2f}s)")

        # DEBUG: Show cleaned data after quality control
        print("\n" + "="*60)
        print("🐛 DEBUG: AFTER QUALITY CONTROL (STEP 7)")
        print("="*60)
        print(f"🥕 CLEANED INGREDIENTS ({len(cleaned_ingredients)} items):")
        for i, ing in enumerate(cleaned_ingredients[:5], 1):  # Show first 5
            print(f"   {i}. {ing.get('quantity', '')} {ing.get('unit', '')} {ing.get('name', '')}")
        if len(cleaned_ingredients) > 5:
            print(f"   ... and {len(cleaned_ingredients) - 5} more")
        print(f"\n📝 PARAPHRASED DIRECTIONS ({len(paraphrased_directions)} steps):")
        for i, step in enumerate(paraphrased_directions[:3], 1):  # Show first 3
            print(f"   {i}. {step[:80]}...")
        if len(paraphrased_directions) > 3:
            print(f"   ... and {len(paraphrased_directions) - 3} more")
        print("="*60 + "\n")

        # Step 8: PARALLEL BATCH 3 - Rescue + Meta Steps
        print("🔧 Step 8: Running rescue + meta step analysis (GEMINI)...")
        step_start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            rescue_future = executor.submit(
                self.quality_controller.rescue_failed_ingredient_parses,
                cleaned_ingredients
            )
            meta_step_future = executor.submit(
                self.meta_step_extractor.extract_meta_steps,
                cleaned_ingredients,
                paraphrased_directions,
                title
            )

            rescued_ingredients = rescue_future.result()
            meta_step_result = meta_step_future.result()

        timings['rescue_and_meta'] = time.time() - step_start
        print(f"   ✅ Rescue + meta step analysis complete ({timings['rescue_and_meta']:.2f}s)")

        # DEBUG: Show rescued ingredients before matching
        print("\n" + "="*60)
        print("🐛 DEBUG: AFTER RESCUE (STEP 8)")
        print("="*60)
        print(f"🥕 RESCUED INGREDIENTS ({len(rescued_ingredients)} items):")
        for i, ing in enumerate(rescued_ingredients[:8], 1):  # Show first 8
            ing_id = ing.get('id', 'NO_ID')
            print(f"   {i}. [{ing_id}] {ing.get('quantity', '')} {ing.get('unit', '')} {ing.get('name', '')}")
        if len(rescued_ingredients) > 8:
            print(f"   ... and {len(rescued_ingredients) - 8} more")
        print("="*60 + "\n")

        # Step 8.5: CONDITIONAL - Nutrition validation (only if servings > 1 and macros found)
        final_nutrition = {
            "calories": str(nutrition_output["calories"]) if nutrition_output["calories"] > 0 else "",
            "protein": str(nutrition_output["protein"]) if nutrition_output["protein"] > 0 else "",
            "fat": str(nutrition_output["fat"]) if nutrition_output["fat"] > 0 else "",
            "carbs": str(nutrition_output["carbs"]) if nutrition_output["carbs"] > 0 else ""
        }
        final_servings = nutrition_output["servings"] if nutrition_output["servings"] > 0 else 0

        # Only validate and potentially multiply if servings > 1 AND macros were found
        if nutrition_output["servings"] > 1 and nutrition_output["calories"] > 0:
            print("🔢 Step 8.5: Validating nutrition multiplier (GEMINI)...")
            step_start = time.time()

            is_already_total = self.validate_nutrition_multiplier(
                nutrition_output,
                title,
                rescued_ingredients
            )

            timings['nutrition_validation'] = time.time() - step_start

            if not is_already_total:
                # Multiply macros by servings
                multiplier = nutrition_output["servings"]
                final_nutrition = {
                    "calories": str(nutrition_output["calories"] * multiplier),
                    "protein": str(nutrition_output["protein"] * multiplier),
                    "fat": str(nutrition_output["fat"] * multiplier),
                    "carbs": str(nutrition_output["carbs"] * multiplier)
                }
                print(f"   📊 Multiplied macros by {multiplier}: {final_nutrition['calories']} cal, {final_nutrition['protein']}g pro, {final_nutrition['fat']}g fat, {final_nutrition['carbs']}g carbs")
            else:
                print(f"   📊 Using macros as-is (already total): {final_nutrition['calories']} cal, {final_nutrition['protein']}g pro, {final_nutrition['fat']}g fat, {final_nutrition['carbs']}g carbs")
        elif nutrition_output["calories"] > 0:
            print(f"   📊 Nutrition found (servings=1, no validation needed): {final_nutrition['calories']} cal, {final_nutrition['protein']}g pro, {final_nutrition['fat']}g fat, {final_nutrition['carbs']}g carbs")
        else:
            print("   ℹ️  No nutrition data found in content")

        # Step 9: SEQUENTIAL - Step-Ingredient Matching
        print("🔗 Step 9: Matching ingredients to steps (GEMINI)...")
        step_start = time.time()

        step_ingredient_result = self.step_ingredient_matcher.match_steps_with_ingredients(
            rescued_ingredients,
            paraphrased_directions
        )

        timings['step_matching'] = time.time() - step_start
        print(f"   ✅ Step-ingredient matching complete ({timings['step_matching']:.2f}s)")

        # Step 9.5: Generate meta-ingredients (deduplication for shopping)
        print("🔍 Step 9.5: Generating meta-ingredients...")
        step_start = time.time()

        meta_ingredients = self.generate_meta_ingredients(
            step_ingredient_result.get("ingredients_with_ids", {})
        )

        timings['meta_ingredients'] = time.time() - step_start

        # Step 10: Structure into enhanced JSON format
        print("📦 Step 10: Structuring into enhanced JSON...")
        step_start = time.time()

        # DEBUG: Show what's going into final JSON
        print("\n" + "="*60)
        print("🐛 DEBUG: BEFORE FINAL JSON STRUCTURING (STEP 10)")
        print("="*60)
        print(f"📝 TITLE: {title}")
        print(f"🥕 RAW INGREDIENT COUNT: {len(step_ingredient_result.get('ingredients_with_ids', {}))}")
        print(f"🔍 META-INGREDIENT COUNT: {len(meta_ingredients)} (deduplicated for shopping)")
        print(f"📋 DIRECTION COUNT: {len(meta_step_result)}")
        print(f"🔗 STEP MAPPINGS: {len(step_ingredient_result.get('step_mappings', []))} steps with ingredient assignments")
        print(f"🍽️  MEAL OCCASION: {meal_occasion_output}")
        print(f"🔢 FINAL NUTRITION: {final_nutrition['calories'] or '0'} cal, {final_nutrition['protein'] or '0'}g pro, {final_nutrition['fat'] or '0'}g fat, {final_nutrition['carbs'] or '0'}g carbs")
        print(f"🍴 SERVINGS: {final_servings}")
        print("="*60 + "\n")

        recipe_dict = create_enhanced_recipe_json(
            title=title,
            parser_method=parser_method,
            source_url=source_url,
            step_ingredient_result=step_ingredient_result,
            meta_step_result=meta_step_result,
            meta_ingredients=meta_ingredients,  # Deduplicated ingredient list
            nutrition=final_nutrition,  # Extracted macro nutrition
            image=metadata.get("image_url", ""),  # Cover photo/thumbnail
            meal_occasion=meal_occasion_output,
            servings=final_servings  # Extracted servings count
        )

        timings['json_structuring'] = time.time() - step_start
        print(f"   ✅ JSON structuring complete ({timings['json_structuring']:.2f}s)")

        # Convert to JSON string
        import json
        recipe_json = json.dumps(recipe_dict, ensure_ascii=False, indent=2)

        return recipe_json
