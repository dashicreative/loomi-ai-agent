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
            self.google_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            raise ValueError("Google Gemini API key is required. Please add GOOGLE_GEMINI_KEY to your .env file.")
        
        # Initialize shared ingredient parser
        self.ingredient_parser = IngredientParser()
        
        # Initialize enhanced analysis modules
        self.step_ingredient_matcher = StepIngredientMatcher(self.google_model)
        self.meta_step_extractor = MetaStepExtractor(self.google_model)
    
    def call_llm(self, prompt: str, max_tokens: int = 800) -> str:
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
            "total_time": total_time
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
        
        llm_response = self.call_llm(prompt, max_tokens=1000)
        
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
            
            llm_response = self.call_llm(prompt, max_tokens=50)
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
        
        # Run LLM calls in parallel (instructions formatting + meal occasion)
        print("   🤖 Running parallel LLM analysis...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both LLM tasks
            instructions_future = executor.submit(self.format_instructions_with_llm, key_fields["instructions"])
            meal_occasion_future = executor.submit(self.extract_meal_occasion, combined_content)
            
            # Get results
            formatted_directions = instructions_future.result()
            meal_occasion = meal_occasion_future.result()
        
        print(f"   📊 Parallel LLM analysis complete - meal occasion: {meal_occasion}")
        
        # Enhanced recipe analysis (step-ingredient matching + meta step extraction)
        print("   🔗 Running enhanced recipe analysis (GEMINI)...")
        start_time = time.time()
        
        # Run step-ingredient matching and meta step extraction in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both analysis tasks
            step_ingredient_future = executor.submit(
                self.step_ingredient_matcher.match_steps_with_ingredients,
                processed_ingredients,
                formatted_directions
            )
            meta_step_future = executor.submit(
                self.meta_step_extractor.extract_meta_steps,
                processed_ingredients,
                formatted_directions,
                key_fields["title"]
            )
            
            # Get results
            step_ingredient_result = step_ingredient_future.result()
            meta_step_result = meta_step_future.result()
        
        elapsed = time.time() - start_time
        print(f"   ✅ Enhanced recipe analysis complete in {elapsed:.2f}s")
        
        # Create enhanced recipe JSON with step-ingredient matching and meta steps
        recipe_dict = create_enhanced_recipe_json(
            title=key_fields["title"],
            parser_method="RecipeSite",
            source_url=key_fields["source_url"],
            step_ingredient_result=step_ingredient_result,
            meta_step_result=meta_step_result,
            nutrition=key_fields["nutrition"],
            meal_occasion=meal_occasion,
            total_time=key_fields["total_time"]
        )
        
        # Add image field (not in standard model yet)
        recipe_dict["image"] = key_fields["image"]
        
        print(f"   ✅ Final JSON: {len(processed_ingredients)} ingredients, {len(formatted_directions)} steps, image included")
        
        return format_standard_recipe_json(recipe_dict)