"""
Step-Ingredient Matching System
Matches cooking steps with their required ingredients using LLM pattern recognition.
"""

import random
import time
from pathlib import Path
from typing import Dict, List, Any
import google.generativeai as genai


class StepIngredientMatcher:
    """
    Matches recipe steps with their required ingredients using context-aware LLM analysis.
    Generates ingredient IDs and returns structured step-ingredient mappings.
    """
    
    def __init__(self, google_model):
        """Initialize with existing Gemini model instance."""
        self.google_model = google_model
    
    def generate_ingredient_id(self) -> str:
        """Generate unique ingredient ID like I79847637846"""
        timestamp_part = str(int(time.time() * 1000))[-8:]  # Last 8 digits of timestamp
        random_part = str(random.randint(1000, 9999))
        return f"I{timestamp_part}{random_part}"
    
    def prepare_ingredients_with_ids(self, ingredients: List[Dict]) -> Dict[str, Dict]:
        """
        Add unique IDs to ingredients and return mapping.
        
        Args:
            ingredients: List of ingredient dicts with name, quantity, unit
            
        Returns:
            Dictionary mapping ingredient ID to ingredient data
        """
        ingredients_with_ids = {}
        
        for ingredient in ingredients:
            ingredient_id = self.generate_ingredient_id()
            ingredients_with_ids[ingredient_id] = {
                "id": ingredient_id,
                "name": ingredient["name"],
                "quantity": ingredient["quantity"], 
                "unit": ingredient["unit"]
            }
            
        return ingredients_with_ids
    
    def format_prompt_content(self, ingredients_with_ids: Dict, steps: List[str]) -> Dict[str, str]:
        """
        Format ingredients and steps for LLM prompt.
        
        Args:
            ingredients_with_ids: Dictionary of ingredient ID -> ingredient data
            steps: List of cooking step strings
            
        Returns:
            Dictionary with formatted ingredients and steps
        """
        # Format ingredients: "I12345: chicken breast | I67890: olive oil"
        ingredient_list = []
        for ingredient_id, data in ingredients_with_ids.items():
            name = data["name"]
            ingredient_list.append(f"{ingredient_id}: {name}")
        
        ingredients_formatted = " | ".join(ingredient_list)
        
        # Format steps: "1. Season chicken | 2. Heat oil in pan"
        numbered_steps = []
        for i, step in enumerate(steps, 1):
            numbered_steps.append(f"{i}. {step}")
        
        steps_formatted = " | ".join(numbered_steps)
        
        return {
            "ingredients_with_ids": ingredients_formatted,
            "numbered_steps": steps_formatted
        }
    
    def call_llm_for_matching(self, ingredients_formatted: str, steps_formatted: str) -> str:
        """
        Call Gemini LLM to match ingredients with steps.
        
        Args:
            ingredients_formatted: Formatted ingredients string
            steps_formatted: Formatted steps string
            
        Returns:
            LLM response with step-ingredient mappings
        """
        # Load prompt template
        prompt_path = Path(__file__).parent / "Step_Ingredient_Matching_Prompt.txt"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            prompt = prompt_template.format(
                ingredients_with_ids=ingredients_formatted,
                numbered_steps=steps_formatted
            )
            
        except FileNotFoundError:
            raise Exception(f"Ingredient matching prompt file not found: {prompt_path}")
        
        # Call Gemini
        print(f"   🔗 Matching ingredients to steps with GEMINI...")
        start_time = time.time()
        
        response = self.google_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2000
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        )
        
        elapsed = time.time() - start_time
        print(f"   ✅ Step-ingredient matching completed in {elapsed:.2f}s")
        
        
        # Extract response text
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
    
    def parse_llm_response(self, llm_response: str, ingredients_with_ids: Dict) -> List[Dict]:
        """
        Parse LLM response into structured step-ingredient mappings.
        
        Args:
            llm_response: Raw LLM response like "Step1:I101,I102|Step2:I103"
            ingredients_with_ids: Dictionary of ingredient ID -> ingredient data
            
        Returns:
            List of step dictionaries with assigned ingredient IDs
        """
        if "No Matches Available" in llm_response:
            return []
        
        try:
            step_mappings = []
            
            # Split by | to get each step
            step_parts = llm_response.split('|')
            
            for step_part in step_parts:
                step_part = step_part.strip()
                if not step_part:
                    continue
                
                # Parse "Step1:I101,I102"
                if ':' not in step_part:
                    continue
                    
                step_label, ingredient_ids_str = step_part.split(':', 1)
                
                # Extract step number
                step_num = step_label.replace('Step', '').strip()
                
                # Extract ingredient IDs
                ingredient_ids = []
                if ingredient_ids_str.strip():
                    raw_ids = ingredient_ids_str.split(',')
                    for raw_id in raw_ids:
                        ingredient_id = raw_id.strip()
                        if ingredient_id in ingredients_with_ids:
                            ingredient_ids.append(ingredient_id)
                
                step_mappings.append({
                    "step_number": int(step_num),
                    "ingredient_ids": ingredient_ids
                })
            
            return step_mappings
            
        except Exception as e:
            print(f"   ⚠️  Failed to parse LLM response: {str(e)}")
            return []
    
    def match_steps_with_ingredients(self, ingredients: List[Dict], steps: List[str]) -> Dict[str, Any]:
        """
        Main method: Match cooking steps with ingredients using LLM analysis.
        
        Args:
            ingredients: List of ingredient dicts (name, quantity, unit)
            steps: List of cooking step strings
            
        Returns:
            Dictionary with ingredients_with_ids and step_mappings
        """
        if not ingredients or not steps:
            return {
                "ingredients_with_ids": {},
                "step_mappings": []
            }
        
        print(f"🔗 Matching {len(ingredients)} ingredients with {len(steps)} steps...")
        
        # Step 1: Add IDs to ingredients
        ingredients_with_ids = self.prepare_ingredients_with_ids(ingredients)
        
        # Step 2: Format for LLM prompt
        formatted_content = self.format_prompt_content(ingredients_with_ids, steps)
        
        # Step 3: Call LLM for matching
        try:
            # DEBUG: Show input to LLM
            print(f"\n{'='*60}")
            print(f"🐛 DEBUG: STEP-INGREDIENT MATCHING INPUT")
            print(f"{'='*60}")
            print(f"🥕 INGREDIENTS: {formatted_content['ingredients_with_ids'][:300]}...")
            print(f"📝 STEPS: {formatted_content['numbered_steps'][:300]}...")
            print(f"{'='*60}\n")

            llm_response = self.call_llm_for_matching(
                formatted_content["ingredients_with_ids"],
                formatted_content["numbered_steps"]
            )

            # DEBUG: Show raw LLM response
            print(f"\n{'='*60}")
            print(f"🐛 DEBUG: RAW LLM MATCHING RESPONSE")
            print(f"{'='*60}")
            print(f"🤖 RESPONSE: {llm_response}")
            print(f"{'='*60}\n")

            # Step 4: Parse response into structured format
            step_mappings = self.parse_llm_response(llm_response, ingredients_with_ids)

            # DEBUG: Show parsed mappings
            print(f"\n{'='*60}")
            print(f"🐛 DEBUG: PARSED STEP MAPPINGS")
            print(f"{'='*60}")
            for mapping in step_mappings:
                step_num = mapping["step_number"]
                ing_ids = mapping["ingredient_ids"]
                print(f"   Step {step_num}: {len(ing_ids)} ingredients → {ing_ids[:5]}")
            print(f"{'='*60}\n")

            print(f"   ✅ Successfully matched ingredients to {len(step_mappings)} steps")
            
            return {
                "ingredients_with_ids": ingredients_with_ids,
                "step_mappings": step_mappings
            }
            
        except Exception as e:
            print(f"   ⚠️  Step-ingredient matching failed: {str(e)}")
            return {
                "ingredients_with_ids": ingredients_with_ids,
                "step_mappings": []
            }