"""
Meta Step Extraction System
Identifies section headers (meta steps) vs detailed implementation steps in recipe directions.
Preserves original step order while adding optional meta step organization.
"""

import time
from pathlib import Path
from typing import Dict, List, Any
import google.generativeai as genai


class MetaStepExtractor:
    """
    Extracts meta step organization from recipe directions using conservative LLM analysis.
    Only identifies explicitly mentioned section headers, preserves original step order.
    """
    
    def __init__(self, google_model):
        """Initialize with existing Gemini model instance."""
        self.google_model = google_model
    
    def format_prompt_content(self, ingredients: List[Dict], steps: List[str], recipe_title: str = "") -> Dict[str, str]:
        """
        Format ingredients, steps and recipe title for LLM prompt.
        
        Args:
            ingredients: List of ingredient dicts (for context)
            steps: List of cooking step strings
            recipe_title: Recipe title for additional context
            
        Returns:
            Dictionary with formatted ingredients, steps and title
        """
        # Format ingredients for context: "chicken breast, olive oil, garlic"
        ingredient_names = [ingredient["name"] for ingredient in ingredients]
        ingredients_formatted = ", ".join(ingredient_names)
        
        # Format steps: "1. Season chicken | 2. Heat oil in pan"
        numbered_steps = []
        for i, step in enumerate(steps, 1):
            numbered_steps.append(f"{i}. {step}")
        
        steps_formatted = " | ".join(numbered_steps)
        
        return {
            "recipe_title": recipe_title,
            "ingredients_list": ingredients_formatted,
            "numbered_steps": steps_formatted
        }
    
    def call_llm_for_extraction(self, recipe_title: str, ingredients_formatted: str, steps_formatted: str) -> str:
        """
        Call Gemini LLM to identify meta steps vs regular steps.
        
        Args:
            recipe_title: Recipe title for additional context
            ingredients_formatted: Formatted ingredients string (for context)
            steps_formatted: Formatted steps string
            
        Returns:
            LLM response with step classifications
        """
        # Load prompt template
        prompt_path = Path(__file__).parent / "Meta_Step_Extraction_Prompt.txt"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            prompt = prompt_template.format(
                recipe_title=recipe_title,
                ingredients_list=ingredients_formatted,
                numbered_steps=steps_formatted
            )
            
        except FileNotFoundError:
            raise Exception(f"Meta step extraction prompt file not found: {prompt_path}")
        
        # Call Gemini
        print(f"   📋 Extracting meta steps with GEMINI...")
        start_time = time.time()
        
        response = self.google_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=600
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        )
        
        elapsed = time.time() - start_time
        print(f"   ✅ Meta step extraction completed in {elapsed:.2f}s")
        
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
    
    def parse_llm_response(self, llm_response: str, original_steps: List[str]) -> List[Dict]:
        """
        Parse LLM response into structured step classifications.
        
        Args:
            llm_response: Raw LLM response like "Step1:META|Step2:REGULAR:Saute the veggies"
            original_steps: Original list of step strings
            
        Returns:
            List of step dictionaries with type and meta_step_section info
        """
        if "No Meta Steps Available" in llm_response:
            # Return all steps as regular steps
            return [
                {
                    "step_number": i + 1,
                    "text": step,
                    "type": "regular_step",
                    "meta_step_section": None
                }
                for i, step in enumerate(original_steps)
            ]
        
        try:
            structured_steps = []
            current_meta_step = None
            
            # Split by | to get each step classification
            step_classifications = llm_response.split('|')
            
            for i, step_classification in enumerate(step_classifications):
                step_classification = step_classification.strip()
                if not step_classification:
                    continue
                
                # Parse "Step1:META" or "Step2:REGULAR:Saute the veggies"
                if ':' not in step_classification:
                    continue
                
                parts = step_classification.split(':', 2)
                step_label = parts[0].strip()
                step_type = parts[1].strip()
                
                # Extract step number
                step_num = int(step_label.replace('Step', '').strip())
                
                # Ensure we don't go beyond available steps
                if step_num > len(original_steps):
                    continue
                
                step_text = original_steps[step_num - 1]
                
                if step_type == "META":
                    # This step is a meta step (section header)
                    current_meta_step = step_text
                    structured_steps.append({
                        "step_number": step_num,
                        "text": step_text,
                        "type": "meta_step",
                        "meta_step_section": None
                    })
                    
                elif step_type == "REGULAR":
                    # Regular step, may or may not belong to a meta step section
                    meta_section = None
                    if len(parts) > 2:
                        meta_section = parts[2].strip()
                    elif current_meta_step:
                        # If no explicit meta step mentioned, use current context
                        meta_section = current_meta_step
                    
                    structured_steps.append({
                        "step_number": step_num,
                        "text": step_text,
                        "type": "regular_step",
                        "meta_step_section": meta_section
                    })
                else:
                    # Fallback: treat as regular step
                    structured_steps.append({
                        "step_number": step_num,
                        "text": step_text,
                        "type": "regular_step",
                        "meta_step_section": None
                    })
            
            # Fill in any missing steps as regular steps
            for i, step in enumerate(original_steps, 1):
                if not any(s["step_number"] == i for s in structured_steps):
                    structured_steps.append({
                        "step_number": i,
                        "text": step,
                        "type": "regular_step",
                        "meta_step_section": None
                    })
            
            # Sort by step number to maintain order
            structured_steps.sort(key=lambda x: x["step_number"])
            
            return structured_steps
            
        except Exception as e:
            print(f"   ⚠️  Failed to parse LLM response: {str(e)}")
            # Fallback: return all steps as regular steps
            return [
                {
                    "step_number": i + 1,
                    "text": step,
                    "type": "regular_step", 
                    "meta_step_section": None
                }
                for i, step in enumerate(original_steps)
            ]
    
    def extract_meta_steps(self, ingredients: List[Dict], steps: List[str], recipe_title: str = "") -> List[Dict]:
        """
        Main method: Extract meta step organization from recipe directions.
        
        Args:
            ingredients: List of ingredient dicts (for context)
            steps: List of cooking step strings
            recipe_title: Recipe title for additional context (optional)
            
        Returns:
            List of step dictionaries with meta step organization
        """
        if not steps:
            return []
        
        print(f"📋 Analyzing {len(steps)} steps for meta step organization...")
        
        # Step 1: Format for LLM prompt
        formatted_content = self.format_prompt_content(ingredients, steps, recipe_title)
        
        # Step 2: Call LLM for meta step extraction
        try:
            llm_response = self.call_llm_for_extraction(
                formatted_content["recipe_title"],
                formatted_content["ingredients_list"],
                formatted_content["numbered_steps"]
            )
            
            # Step 3: Parse response into structured format
            structured_steps = self.parse_llm_response(llm_response, steps)
            
            meta_step_count = len([s for s in structured_steps if s["type"] == "meta_step"])
            print(f"   ✅ Identified {meta_step_count} meta steps with preserved step order")
            
            return structured_steps
            
        except Exception as e:
            print(f"   ⚠️  Meta step extraction failed: {str(e)}")
            # Fallback: return all steps as regular steps
            return [
                {
                    "step_number": i + 1,
                    "text": step,
                    "type": "regular_step",
                    "meta_step_section": None
                }
                for i, step in enumerate(steps)
            ]