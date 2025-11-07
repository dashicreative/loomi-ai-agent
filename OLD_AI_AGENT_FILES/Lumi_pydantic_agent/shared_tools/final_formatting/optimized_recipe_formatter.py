"""
Optimized Recipe Formatter - Ultra-efficient final formatting
Uses batch processing and eliminates redundancies for maximum performance.

Performance: 1-2 LLM calls total instead of 4 calls per recipe
"""

import time
import re
import asyncio
from typing import Dict, List, Optional
from .batch_ingredient_processor import batch_process_recipe_ingredients


def clean_nutrition_data(nutrition_list: List[str]) -> Dict[str, float]:
    """
    Fast nutrition cleaning using optimized regex patterns.
    
    Args:
        nutrition_list: Raw nutrition strings like ["300 calories", "25g protein"]
        
    Returns:
        Clean numeric dict: {"calories": 300.0, "protein": 25.0, "carbs": 45.0, "fat": 12.0}
    """
    if not nutrition_list:
        return {}
    
    # Combine all nutrition text
    full_text = " ".join(nutrition_list).lower()
    
    # Clean up text
    clean_text = re.sub(r'([a-z])(\d)', r'\1 \2', full_text)
    clean_text = re.sub(r'(\d)([a-z])', r'\1 \2', clean_text)
    clean_text = clean_text.replace('per serving', '').replace('nutrition facts', '')
    
    # Fast extraction patterns
    nutrition_data = {}
    
    # Calories (prioritize number-first patterns)
    calories_match = re.search(r'(\d{2,4})\s*(?:calories|kcal)\b', clean_text)
    if not calories_match:
        calories_match = re.search(r'calories[:\s]*(\d{2,4})\b', clean_text)
    if calories_match:
        nutrition_data['calories'] = float(calories_match.group(1))
    
    # Protein
    protein_match = re.search(r'(\d{1,3}(?:\.\d+)?)\s*g?\s*protein\b', clean_text)
    if not protein_match:
        protein_match = re.search(r'protein[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b', clean_text)
    if protein_match:
        nutrition_data['protein'] = float(protein_match.group(1))
    
    # Carbs
    carbs_match = re.search(r'(\d{1,3}(?:\.\d+)?)\s*g?\s*carb(?:ohydrate)?s?\b', clean_text)
    if not carbs_match:
        carbs_match = re.search(r'carb(?:ohydrate)?s?[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b', clean_text)
    if carbs_match:
        nutrition_data['carbs'] = float(carbs_match.group(1))
    
    # Fat
    fat_match = re.search(r'(\d{1,3}(?:\.\d+)?)\s*g?\s*fat\b', clean_text)
    if not fat_match:
        fat_match = re.search(r'total\s*fat[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b', clean_text)
    if fat_match:
        nutrition_data['fat'] = float(fat_match.group(1))
    
    return nutrition_data


def extract_ready_time(recipe: Dict) -> str:
    """
    Fast time extraction from cook_time and prep_time.
    """
    cook_time = recipe.get("cook_time", "")
    prep_time = recipe.get("prep_time", "")
    
    def extract_minutes(time_str: str) -> int:
        if not time_str:
            return 0
        
        time_lower = time_str.lower()
        minutes = 0
        
        # Extract hours and minutes
        hour_match = re.search(r'(\d+)\s*(?:hour|hr|h)\b', time_lower)
        if hour_match:
            minutes += int(hour_match.group(1)) * 60
        
        minute_match = re.search(r'(\d+)\s*(?:minute|min|m)\b', time_lower)
        if minute_match:
            minutes += int(minute_match.group(1))
        
        # If no units found, assume minutes
        if minutes == 0:
            number_match = re.search(r'(\d+)', time_str)
            if number_match:
                minutes = int(number_match.group(1))
        
        return minutes
    
    total_minutes = extract_minutes(cook_time) + extract_minutes(prep_time)
    return str(total_minutes) if total_minutes > 0 else ""


def extract_domain_from_url(url: str) -> str:
    """Fast domain extraction."""
    if not url:
        return ""
    
    try:
        from urllib.parse import urlparse
        domain = urlparse(url.lower()).netloc
        return domain[4:] if domain.startswith('www.') else domain
    except:
        return ""


class OptimizedRecipeFormatter:
    """
    Ultra-efficient recipe formatter using batch processing.
    Eliminates redundancies and maximizes performance.
    """
    
    def __init__(self, openai_key: str = None):
        """Initialize formatter with OpenAI API key."""
        self.openai_key = openai_key
    
    async def format_recipes_for_app(
        self, 
        agent_response: str,
        recipe_ids: List[str],
        recipe_memory: Dict[str, Dict],
        include_full_ingredients: bool = True,
        include_full_instructions: bool = True
    ) -> Dict:
        """
        Ultra-efficient app formatting using batch processing.
        
        Performance: 1-2 LLM calls total instead of 4 calls per recipe
        """
        print(f"⚡ OPTIMIZED FORMATTING: {len(recipe_ids)} recipes")
        start_time = time.time()
        
        if not recipe_ids:
            return {
                "agent_response": agent_response,
                "recipes": [],
                "total_results": 0,
                "processing_time": 0.0,
                "timestamp": time.time()
            }
        
        # PHASE 1: Batch ingredient processing (if needed)
        recipe_ingredients_map = {}
        if include_full_ingredients:
            print(f"   🚀 Batch processing all ingredients...")
            ingredients_start = time.time()
            
            recipe_ingredients_map = await batch_process_recipe_ingredients(
                recipe_memory, recipe_ids, self.openai_key
            )
            
            ingredients_time = time.time() - ingredients_start
            print(f"   ✅ All ingredients processed: {ingredients_time:.2f}s")
        
        # PHASE 2: Fast parallel recipe assembly
        print(f"   📦 Assembling recipes...")
        assembly_start = time.time()
        
        # Process all recipes in parallel (no LLM calls needed here)
        assembly_tasks = []
        for recipe_id in recipe_ids:
            if recipe_id in recipe_memory:
                task = self._fast_assemble_recipe(
                    recipe_memory[recipe_id],
                    recipe_ingredients_map.get(recipe_id, []),
                    include_full_instructions
                )
                assembly_tasks.append(task)
        
        formatted_recipes = await asyncio.gather(*assembly_tasks)
        
        assembly_time = time.time() - assembly_start
        total_time = time.time() - start_time
        
        print(f"   ✅ Assembly completed: {assembly_time:.2f}s")
        print(f"   🎉 Total optimized formatting: {total_time:.2f}s")
        
        return {
            "agent_response": agent_response,
            "recipes": [r for r in formatted_recipes if r],  # Filter out None results
            "total_results": len([r for r in formatted_recipes if r]),
            "processing_time": round(total_time, 2),
            "timestamp": time.time()
        }
    
    async def _fast_assemble_recipe(
        self, 
        raw_recipe: Dict, 
        processed_ingredients: List[Dict],
        include_instructions: bool
    ) -> Optional[Dict]:
        """
        Fast recipe assembly without LLM calls.
        Just combines existing data efficiently.
        """
        try:
            # Base structure
            formatted_recipe = {
                "id": raw_recipe.get("recipe_id"),
                "title": raw_recipe.get("title", ""),
                "image": raw_recipe.get("image_url", ""),
                "sourceUrl": raw_recipe.get("source_url", ""),
                "servings": raw_recipe.get("servings", ""),
                "readyInMinutes": extract_ready_time(raw_recipe),
                "ingredients": processed_ingredients,  # Already processed
                "nutrition": None
            }
            
            # Add instructions if requested
            if include_instructions:
                formatted_recipe["instructions"] = raw_recipe.get("instructions", [])
            
            # Fast nutrition processing
            raw_nutrition = raw_recipe.get("nutrition", [])
            if raw_nutrition:
                # Handle different nutrition formats
                nutrition_strings = []
                for item in raw_nutrition:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        amount = item.get("amount", "")
                        nutrition_strings.append(f"{amount} {name}")
                    else:
                        nutrition_strings.append(str(item))
                
                # Fast nutrition cleaning
                clean_nutrition = clean_nutrition_data(nutrition_strings)
                if clean_nutrition:
                    formatted_recipe["nutrition"] = {
                        "calories": clean_nutrition.get("calories", 0.0),
                        "protein": clean_nutrition.get("protein", 0.0),
                        "carbs": clean_nutrition.get("carbs", 0.0),
                        "fat": clean_nutrition.get("fat", 0.0)
                    }
            
            # Add metadata
            formatted_recipe["metadata"] = {
                "search_mode": raw_recipe.get("search_mode", "unknown"),
                "user_position": raw_recipe.get("user_position", 0),
                "source_domain": extract_domain_from_url(raw_recipe.get("source_url", "")),
                "cook_time": raw_recipe.get("cook_time", ""),
                "prep_time": raw_recipe.get("prep_time", ""),
                "timestamp": raw_recipe.get("timestamp", time.time())
            }
            
            return formatted_recipe
            
        except Exception as e:
            print(f"   ⚠️ Failed to assemble recipe: {e}")
            return None


# Main optimized function for external use
async def format_recipes_for_app_optimized(
    agent_response: str,
    recipe_ids: List[str], 
    recipe_memory: Dict[str, Dict],
    openai_key: str = None,
    include_full_ingredients: bool = True,
    include_full_instructions: bool = True
) -> Dict:
    """
    Ultra-efficient app formatting using batch processing.
    
    Performance Improvement:
    - OLD: 4 LLM calls per recipe (32 calls for 8 recipes)
    - NEW: 1-2 LLM calls total regardless of recipe count
    
    Args:
        agent_response: Agent's conversational response
        recipe_ids: List of recipe IDs to format
        recipe_memory: Full recipe memory dict
        openai_key: OpenAI API key for ingredient processing
        include_full_ingredients: Whether to process ingredients (default True)
        include_full_instructions: Whether to include instructions (default True)
        
    Returns:
        Complete app-ready response with optimized processing
    """
    formatter = OptimizedRecipeFormatter(openai_key)
    return await formatter.format_recipes_for_app(
        agent_response,
        recipe_ids,
        recipe_memory, 
        include_full_ingredients,
        include_full_instructions
    )