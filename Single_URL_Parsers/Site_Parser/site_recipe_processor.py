"""
Site Recipe Processor - Convert Apify responses to standard JSON format
Uses LLM for instruction formatting and regex parsing for ingredients.
"""

import json
import re
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
from dotenv import load_dotenv

# Import shared modules
sys.path.append(str(Path(__file__).parent.parent))
from ingredient_parser import IngredientParser, ParsedIngredient

# Import from shared model
sys.path.append(str(Path(__file__).parent.parent))
from json_recipe_model import create_enhanced_recipe_json, format_standard_recipe_json

# Import enhanced analysis modules
sys.path.append(str(Path(__file__).parent.parent / "Step_Ingredient_Matching"))
sys.path.append(str(Path(__file__).parent.parent / "Meta_Step_Extraction"))
from step_ingredient_matcher import StepIngredientMatcher
from meta_step_extractor import MetaStepExtractor

# Load environment variables
load_dotenv()


class SiteRecipeProcessor:
    """
    Process Apify recipe responses into standardized JSON format.
    Uses LLM for instruction formatting and regex for ingredient parsing.
    """
    
    def __init__(self):
        """Initialize processor with Gemini client and ingredient parser."""
        
        # Initialize Google Gemini client only
        google_key = os.getenv('GOOGLE_GEMINI_KEY')
        if google_key:
            genai.configure(api_key=google_key)
            #self.google_model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.google_model = genai.GenerativeModel('gemini-2.5-flash-lite')
        else:
            raise ValueError("Google Gemini API key is required. Please add GOOGLE_GEMINI_KEY to your .env file.")
        
        # Initialize shared ingredient parser
        self.ingredient_parser = IngredientParser()
        
        # Initialize enhanced analysis modules
        self.step_ingredient_matcher = StepIngredientMatcher(self.google_model)
        self.meta_step_extractor = MetaStepExtractor(self.google_model)
    
    def call_llm(self, prompt: str, max_tokens: int = 1200) -> str:
        """
        Call Gemini LLM for instruction formatting.
        
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
    
    def extract_key_fields(self, apify_response: Dict) -> Dict:
        """
        Extract only the key fields we need from Apify response.
        
        Args:
            apify_response: Raw Apify actor response
            
        Returns:
            Dictionary with key fields for processing
        """
        # Extract core fields
        title = apify_response.get("title", "")
        ingredients_list = apify_response.get("ingredients", [])
        instructions = apify_response.get("instructions", "")
        image_url = apify_response.get("image", "")
        source_url = apify_response.get("url", "")
        total_time = apify_response.get("total_time", "")
        servings_raw = apify_response.get("servings", "")
        
        # Extract servings count (default to 0 if no valid int found)
        servings_numeric = self._extract_numeric_value(servings_raw)
        servings_count = int(float(servings_numeric)) if servings_numeric else 0
        
        # Extract nutrition data (convert to simple format)
        nutrition = {}
        nutrients = apify_response.get("nutrients", {})
        if nutrients:
            # Extract key nutrition values
            calories = self._extract_numeric_value(nutrients.get("calories", ""))
            protein = self._extract_numeric_value(nutrients.get("proteinContent", ""))
            fat = self._extract_numeric_value(nutrients.get("fatContent", ""))
            carbs = self._extract_numeric_value(nutrients.get("carbohydrateContent", ""))
            
            nutrition = {
                "calories": calories or "",
                "protein": protein or "", 
                "fat": fat or "",
                "carbs": carbs or ""
            }
        
        return {
            "title": title,
            "ingredients": ingredients_list,
            "instructions": instructions,
            "image": image_url,
            "nutrition": nutrition,
            "source_url": source_url,
            "total_time": total_time,
            "servings": servings_count
        }
    
    def _extract_numeric_value(self, value: str) -> Optional[str]:
        """Extract numeric value from nutrition string (e.g., '180 kcal' -> '180')."""
        if not value:
            return None
        import re
        match = re.search(r'(\d+(?:\.\d+)?)', str(value))
        return match.group(1) if match else None
    
    def format_instructions_with_llm(self, instructions: str) -> List[str]:
        """
        Use Gemini LLM to convert paragraph instructions into numbered steps.
        
        Args:
            instructions: Raw instruction text (could be paragraph format)
            
        Returns:
            List of numbered instruction steps
        """
        if not instructions.strip():
            return []
        
        # Load directions prompt
        prompt_path = Path(__file__).parent / "llm_prompts" / "Directions_LLM_Parsing_Prompt.txt"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            prompt = prompt_template.format(instructions=instructions)
            
        except FileNotFoundError:
            raise Exception(f"Directions prompt file not found: {prompt_path}")
        
        # Call Gemini to format instructions
        print(f"   📝 Formatting instructions with GEMINI...")
        start_time = time.time()
        
        llm_response = self.call_llm(prompt, max_tokens=1200)
        
        elapsed = time.time() - start_time
        print(f"   ✅ Instructions formatted in {elapsed:.2f}s")
        
        # Parse LLM response into list of steps
        if "No Directions Available" in llm_response:
            return []
        
        # Split by lines and extract numbered steps
        lines = llm_response.strip().split('\n')
        steps = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove number prefixes and keep the step
            step = re.sub(r'^\d+\.\s*', '', line).strip()
            if step:
                steps.append(step)
        
        return steps
    
    def paraphrase_directions_with_llm(self, formatted_directions: List[str]) -> List[str]:
        """
        Use Gemini LLM to paraphrase directions for copyright compliance.
        
        Args:
            formatted_directions: List of numbered cooking steps
            
        Returns:
            List of paraphrased cooking steps (same structure, different wording)
        """
        if not formatted_directions:
            return []
        
        # Convert list to pipe-delimited format for LLM reasoning
        steps_text = "|".join([f"{i+1}. {step}" for i, step in enumerate(formatted_directions)])
        
        # Load paraphrasing prompt
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
    
    def clean_ingredients_with_llm(self, processed_ingredients: List[Dict]) -> List[Dict]:
        """
        Use Gemini LLM to perform conservative quality control cleanup on ingredients.
        
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
        
        # Load quality control prompt
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
    
    def extract_meal_occasion(self, combined_content: str) -> str:
        """
        Extract meal occasion using Gemini LLM.
        
        Args:
            combined_content: Recipe content for meal occasion analysis
            
        Returns:
            Meal occasion (Breakfast/Lunch/Dinner/Dessert/Snack/Other)
        """
        # Load meal occasion prompt
        prompt_path = Path(__file__).parent / "llm_prompts" / "Meal_Occasion_LLM_Parsing_Prompt.txt"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            prompt = prompt_template.format(combined_content=combined_content)
            
        except FileNotFoundError:
            print(f"   ⚠️  Meal occasion prompt file not found: {prompt_path}")
            return "Other"
        
        try:
            # Call Gemini for meal occasion
            print(f"   🍽️  Analyzing meal occasion with GEMINI...")
            start_time = time.time()
            
            llm_response = self.call_llm(prompt, max_tokens=1200)
            result = llm_response.strip()
            
            elapsed = time.time() - start_time
            print(f"   ✅ Meal occasion analyzed in {elapsed:.2f}s")
            
            # Validate that the result is one of the expected categories
            valid_categories = ["Breakfast", "Lunch", "Dinner", "Dessert", "Snack", "Other"]
            if result in valid_categories:
                meal_occasion = result
            else:
                print(f"   ⚠️  Invalid meal occasion '{result}', defaulting to 'Other'")
                meal_occasion = "Other"
                
            return meal_occasion
            
        except Exception as e:
            print(f"   ⚠️  Meal occasion extraction failed: {str(e)}, defaulting to 'Other'")
            return "Other"

    def rescue_failed_ingredient_parses(self, ingredients: List[Dict]) -> List[Dict]:
        """
        Use Gemini LLM to rescue ingredients that failed regex parsing.
        Identifies ingredients with quantity="1" and unit="count" (likely failures),
        then extracts the real quantity/unit from the name field.

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

        # Load rescue prompt
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

    def process_ingredients_with_regex(self, ingredients_list: List[str]) -> List[Dict]:
        """
        Process ingredients using shared regex parser.
        
        Args:
            ingredients_list: List of ingredient strings from Apify
            
        Returns:
            List of ingredient dictionaries in standard format
        """
        if not ingredients_list:
            return []
        
        # Convert list to multi-line string for shared parser
        ingredients_text = '\n'.join(ingredients_list)
        
        # Use shared ingredient parser
        print(f"   🧄 Processing {len(ingredients_list)} ingredients with regex...")
        start_time = time.time()
        
        parsed_ingredients = self.ingredient_parser.parse_ingredients_list(ingredients_text)
        
        elapsed = time.time() - start_time
        print(f"   ✅ Ingredients processed in {elapsed:.3f}s")
        
        # Convert to standard dictionary format
        return [
            {
                "name": ingredient.name,
                "quantity": ingredient.quantity,
                "unit": ingredient.unit
            }
            for ingredient in parsed_ingredients
        ]
    
    def process_apify_response(self, apify_response: Dict) -> str:
        """
        Main processing method: Convert Apify response to standard JSON format.
        
        Args:
            apify_response: Raw response from Apify recipe scraper actor
            
        Returns:
            Formatted JSON string in standard recipe format
        """
        print("📦 Processing Apify response into standard JSON format...")
        
        # Extract key fields from raw response
        key_fields = self.extract_key_fields(apify_response)
        
        print(f"   📋 Extracted: title, {len(key_fields['ingredients'])} ingredients, instructions, image, nutrition")
        
        # Process ingredients with shared regex parser
        processed_ingredients = self.process_ingredients_with_regex(key_fields["ingredients"])
        
        # Prepare combined content for meal occasion analysis
        combined_content = f"Title: {key_fields['title']}\n\nIngredients: {', '.join(key_fields['ingredients'])}\n\nInstructions: {key_fields['instructions']}"
        
        # Run LLM calls in parallel (instructions formatting + meal occasion + ingredient quality control)
        print("   🤖 Running parallel LLM analysis...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all three LLM tasks
            instructions_future = executor.submit(self.format_instructions_with_llm, key_fields["instructions"])
            meal_occasion_future = executor.submit(self.extract_meal_occasion, combined_content)
            clean_ingredients_future = executor.submit(self.clean_ingredients_with_llm, processed_ingredients)
            
            # Get results
            formatted_directions = instructions_future.result()
            meal_occasion = meal_occasion_future.result()
            clean_ingredients = clean_ingredients_future.result()
        
        print(f"   📊 Parallel LLM analysis complete - meal occasion: {meal_occasion}, ingredients: {len(clean_ingredients)}")

        # Enhanced recipe analysis (failed parse rescue + meta step extraction)
        print("   🔗 Running enhanced recipe analysis (GEMINI)...")
        start_time = time.time()

        # Run failed parse rescue and meta step extraction in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both analysis tasks
            rescue_future = executor.submit(
                self.rescue_failed_ingredient_parses,
                clean_ingredients
            )
            meta_step_future = executor.submit(
                self.meta_step_extractor.extract_meta_steps,
                clean_ingredients,
                formatted_directions,
                key_fields["title"]
            )

            # Get results
            rescued_ingredients = rescue_future.result()
            meta_step_result = meta_step_future.result()

        elapsed = time.time() - start_time
        print(f"   ✅ Enhanced recipe analysis complete in {elapsed:.2f}s")

        # Step-ingredient matching (uses rescued ingredients)
        print("   🔗 Matching ingredients to steps (GEMINI)...")
        step_start = time.time()

        step_ingredient_result = self.step_ingredient_matcher.match_steps_with_ingredients(
            rescued_ingredients,
            formatted_directions
        )

        step_elapsed = time.time() - step_start
        print(f"   ✅ Step-ingredient matching complete in {step_elapsed:.2f}s")
        
        # Step 5: Paraphrase directions for copyright compliance (final LLM call)
        print("   ✏️  Running directions paraphrasing (GEMINI)...")
        paraphrase_start = time.time()
        
        paraphrased_directions = self.paraphrase_directions_with_llm(formatted_directions)
        
        # Update meta step result with paraphrased text
        updated_meta_step_result = []
        for i, step_info in enumerate(meta_step_result):
            updated_step = step_info.copy()
            # Replace original text with paraphrased text (if available)
            if i < len(paraphrased_directions):
                updated_step["text"] = paraphrased_directions[i]
            updated_meta_step_result.append(updated_step)
        
        paraphrase_elapsed = time.time() - paraphrase_start
        print(f"   ✅ Directions paraphrasing complete in {paraphrase_elapsed:.2f}s")
        
        # Create enhanced recipe JSON with step-ingredient matching and meta steps
        recipe_dict = create_enhanced_recipe_json(
            title=key_fields["title"],
            parser_method="RecipeSite",
            source_url=key_fields["source_url"],
            step_ingredient_result=step_ingredient_result,
            meta_step_result=updated_meta_step_result,
            nutrition=key_fields["nutrition"],
            meal_occasion=meal_occasion,
            servings=key_fields["servings"],
            total_time=key_fields["total_time"]
        )
        
        # Add image field (not in standard model yet)
        recipe_dict["image"] = key_fields["image"]

        print(f"   ✅ Final JSON: {len(rescued_ingredients)} ingredients (rescued & cleaned), {len(paraphrased_directions)} steps (paraphrased), image included")

        return format_standard_recipe_json(recipe_dict)