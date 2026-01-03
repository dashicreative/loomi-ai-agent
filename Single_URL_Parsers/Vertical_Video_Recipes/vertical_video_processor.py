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

    def parse_recipe_parallel(self, combined_content: str) -> Tuple[str, str, str]:
        """
        Run ingredient, direction, and meal occasion extraction in parallel.

        Args:
            combined_content: Combined transcript and metadata

        Returns:
            Tuple of (ingredients_output, directions_output, meal_occasion_output)
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            print("   🍅 Starting ingredients extraction (GEMINI)...")
            print("   📝 Starting directions extraction (GEMINI)...")
            print("   🍽️  Starting meal occasion extraction (GEMINI)...")

            parallel_start = time.time()

            # Submit all three tasks
            ingredients_future = executor.submit(self.extract_ingredients, combined_content)
            directions_future = executor.submit(self.extract_title_and_directions, combined_content)
            meal_occasion_future = executor.submit(self.extract_meal_occasion, combined_content)

            # Wait for results
            ingredients_result = ingredients_future.result()
            directions_result = directions_future.result()
            meal_occasion_result = meal_occasion_future.result()

            parallel_total = time.time() - parallel_start
            print(f"   ✅ Parallel LLM calls completed in {parallel_total:.2f}s")

            return ingredients_result, directions_result, meal_occasion_result

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

        # Step 6: Run parallel recipe extraction
        print("🤖 Step 6: Running parallel LLM recipe extraction (GEMINI)...")
        step_start = time.time()
        ingredients_output, directions_output, meal_occasion_output = self.parse_recipe_parallel(combined_content)
        timings['llm_parsing'] = time.time() - step_start
        print(f"   ✅ LLM parsing complete ({timings['llm_parsing']:.2f}s)")

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

        # Step 9: SEQUENTIAL - Step-Ingredient Matching
        print("🔗 Step 9: Matching ingredients to steps (GEMINI)...")
        step_start = time.time()

        step_ingredient_result = self.step_ingredient_matcher.match_steps_with_ingredients(
            rescued_ingredients,
            paraphrased_directions
        )

        timings['step_matching'] = time.time() - step_start
        print(f"   ✅ Step-ingredient matching complete ({timings['step_matching']:.2f}s)")

        # Step 10: Structure into enhanced JSON format
        print("📦 Step 10: Structuring into enhanced JSON...")
        step_start = time.time()

        recipe_dict = create_enhanced_recipe_json(
            title=title,
            parser_method=parser_method,
            source_url=source_url,
            step_ingredient_result=step_ingredient_result,
            meta_step_result=meta_step_result,
            image=metadata.get("image_url", ""),  # Cover photo/thumbnail
            meal_occasion=meal_occasion_output,
            servings=0  # Vertical videos rarely specify servings
        )

        timings['json_structuring'] = time.time() - step_start
        print(f"   ✅ JSON structuring complete ({timings['json_structuring']:.2f}s)")

        # Convert to JSON string
        import json
        recipe_json = json.dumps(recipe_dict, ensure_ascii=False, indent=2)

        return recipe_json
