"""
Recipe Formatter - Final formatting for app consumption
Combines agent conversational response with fully processed recipe data.

Takes:
- Agent's conversational response ("Found 8 great recipes!")
- Recipe IDs from agent tool results 
- Raw recipe data from memory (deps.recipe_memory)

Returns:
- Complete app-ready structure with agent response + formatted recipes
"""

import time
import re
from typing import Dict, List, Optional
from .ingredient_processor import process_recipe_ingredients


def clean_nutrition_for_final_formatting(unified_nutrition: List[str]) -> Dict[str, float]:
    """
    Enhanced nutrition cleaning that handles messy data and returns clean numeric values.
    Copied from the old agent's final formatting stage.
    
    Args:
        unified_nutrition: Raw nutrition strings from recipe parsing
        
    Returns:
        Dict with clean numeric values: {"protein": 30.0, "calories": 402.0, "carbs": 50.0, "fat": 13.0}
    """
    nutrition_clean = {}
    
    if not unified_nutrition:
        return nutrition_clean
    
    # Step 1: Combine and preprocess all nutrition text
    full_text = " ".join(unified_nutrition).lower()
    
    # Step 2: Split mashed-together strings using common delimiters
    delimited_text = re.sub(r'([a-z])(\d)', r'\1 \2', full_text)  # Add space before numbers
    delimited_text = re.sub(r'(\d)([a-z])', r'\1 \2', delimited_text)  # Add space after numbers
    delimited_text = re.sub(r'(calories|protein|carbs|carbohydrates|fat)', r' \1', delimited_text)
    
    # Step 3: Remove interfering text
    clean_text = delimited_text.replace('per serving', '').replace('per portion', '')
    clean_text = clean_text.replace('amount per serving', '').replace('nutrition facts', '')
    
    # Step 4: Enhanced patterns with validation - FIXED ORDER
    nutrition_patterns = {
        "calories": [
            r'(\d{2,4})\s*calories\b',              # "334 calories" - PRIORITIZE NUMBER FIRST
            r'(\d{2,4})\s*kcal\b',                  # "334 kcal"  
            r'calories[:\s]*(\d{2,4})\b',           # "Calories: 334" - SECONDARY
            r'energy[:\s]*(\d{2,4})\b',             # "Energy: 334"
        ],
        "protein": [
            r'(\d{1,3}(?:\.\d+)?)\s*g?\s*protein\b',     # "25g protein" or "25 protein"
            r'protein[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b',  # "Protein: 25g"
        ],
        "carbs": [
            r'(\d{1,3}(?:\.\d+)?)\s*g?\s*carb(?:ohydrate)?s?\b',     # "45g carbs"
            r'carb(?:ohydrate)?s?[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b',  # "Carbs: 45g"
            r'total\s*carb(?:ohydrate)?s?[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b',  # "Total Carbs: 45g"
        ],
        "fat": [
            r'(\d{1,3}(?:\.\d+)?)\s*g?\s*fat\b',         # "12g fat"
            r'total\s*fat[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b',  # "Total Fat: 12g"
            r'fat[:\s]*(\d{1,3}(?:\.\d+)?)\s*g?\b',      # "Fat: 12g"
        ]
    }
    
    # Step 5: Extract values using patterns (prioritized order)
    for nutrient, patterns in nutrition_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, clean_text)
            if matches:
                try:
                    # Take first valid match
                    value = float(matches[0])
                    
                    # Validation ranges to catch obvious parsing errors
                    if nutrient == "calories" and 50 <= value <= 2000:
                        nutrition_clean[nutrient] = value
                        break
                    elif nutrient == "protein" and 0 <= value <= 200:
                        nutrition_clean[nutrient] = value
                        break
                    elif nutrient == "carbs" and 0 <= value <= 500:
                        nutrition_clean[nutrient] = value
                        break
                    elif nutrient == "fat" and 0 <= value <= 200:
                        nutrition_clean[nutrient] = value
                        break
                except (ValueError, IndexError):
                    continue
    
    return nutrition_clean


class RecipeFormatter:
    """
    Final recipe formatting for app consumption.
    Processes raw recipe data into app-ready format with structured ingredients.
    """
    
    def __init__(self, openai_key: str = None):
        """Initialize formatter with OpenAI API key for ingredient processing."""
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
        Format complete response for app consumption.
        
        Args:
            agent_response: Agent's conversational response
            recipe_ids: List of recipe IDs to format
            recipe_memory: Full recipe memory (deps.recipe_memory)
            include_full_ingredients: Whether to include structured ingredients
            include_full_instructions: Whether to include full instructions
            
        Returns:
            Complete app-ready response structure
        """
        print(f"🎨 Formatting {len(recipe_ids)} recipes for app consumption...")
        
        start_time = time.time()
        formatted_recipes = []
        
        for recipe_id in recipe_ids:
            if recipe_id not in recipe_memory:
                print(f"   ⚠️ Recipe {recipe_id} not found in memory, skipping")
                continue
            
            raw_recipe = recipe_memory[recipe_id]
            formatted_recipe = await self._format_single_recipe(
                raw_recipe, 
                include_full_ingredients, 
                include_full_instructions
            )
            formatted_recipes.append(formatted_recipe)
        
        total_time = time.time() - start_time
        print(f"   ✅ Formatted {len(formatted_recipes)} recipes in {total_time:.2f}s")
        
        # Create final app response structure
        app_response = {
            "agent_response": agent_response,
            "recipes": formatted_recipes,
            "total_results": len(formatted_recipes),
            "processing_time": round(total_time, 2),
            "timestamp": time.time()
        }
        
        return app_response
    
    async def _format_single_recipe(
        self, 
        raw_recipe: Dict, 
        include_full_ingredients: bool, 
        include_full_instructions: bool
    ) -> Dict:
        """
        Format a single recipe for app consumption.
        
        Args:
            raw_recipe: Raw recipe data from memory
            include_full_ingredients: Whether to process ingredients
            include_full_instructions: Whether to include instructions
            
        Returns:
            App-ready recipe structure
        """
        recipe_start = time.time()
        
        # Start with base recipe structure for iOS app
        formatted_recipe = {
            "id": raw_recipe.get("recipe_id"),
            "title": raw_recipe.get("title", ""),
            "image": raw_recipe.get("image_url", ""),
            "sourceUrl": raw_recipe.get("source_url", ""),
            "servings": raw_recipe.get("servings", ""),
            "readyInMinutes": self._extract_ready_time(raw_recipe),
            "ingredients": [],  # Will be filled with structured data
            "nutrition": None   # Will be filled with clean nutrition
        }
        
        # Process ingredients if requested
        if include_full_ingredients:
            processed_recipe = await process_recipe_ingredients(raw_recipe, self.openai_key)
            formatted_recipe["ingredients"] = processed_recipe.get("ingredients", [])
        else:
            # Basic ingredient structure without processing
            raw_ingredients = raw_recipe.get("ingredients", [])
            basic_ingredients = []
            for ing in raw_ingredients:
                if isinstance(ing, str):
                    basic_ingredients.append({
                        "quantity": "1",
                        "unit": "count", 
                        "ingredient": ing,
                        "original": ing,
                        "pantry_staple": False,
                        "category": None
                    })
                else:
                    basic_ingredients.append(ing)
            formatted_recipe["ingredients"] = basic_ingredients
        
        # Add instructions if requested
        if include_full_instructions:
            formatted_recipe["instructions"] = raw_recipe.get("instructions", [])
        
        # Process nutrition data
        raw_nutrition = raw_recipe.get("nutrition", [])
        if raw_nutrition:
            # Convert nutrition list to clean numeric values
            if isinstance(raw_nutrition, list) and raw_nutrition:
                # Handle list of nutrition strings
                nutrition_strings = []
                for item in raw_nutrition:
                    if isinstance(item, dict):
                        # Handle dict format: {"name": "calories", "amount": "300"}
                        name = item.get("name", "")
                        amount = item.get("amount", "")
                        nutrition_strings.append(f"{amount} {name}")
                    else:
                        # Handle string format
                        nutrition_strings.append(str(item))
                
                clean_nutrition = clean_nutrition_for_final_formatting(nutrition_strings)
                
                # Convert to iOS app format
                if clean_nutrition:
                    formatted_recipe["nutrition"] = {
                        "calories": clean_nutrition.get("calories", 0.0),
                        "protein": clean_nutrition.get("protein", 0.0),
                        "carbs": clean_nutrition.get("carbs", 0.0),
                        "fat": clean_nutrition.get("fat", 0.0)
                    }
        
        # Add metadata from original recipe
        formatted_recipe["metadata"] = {
            "search_mode": raw_recipe.get("search_mode", "unknown"),
            "user_position": raw_recipe.get("user_position", 0),
            "source_domain": self._extract_domain_from_url(raw_recipe.get("source_url", "")),
            "cook_time": raw_recipe.get("cook_time", ""),
            "prep_time": raw_recipe.get("prep_time", ""),
            "timestamp": raw_recipe.get("timestamp", time.time())
        }
        
        recipe_time = time.time() - recipe_start
        print(f"   📄 Formatted '{formatted_recipe['title'][:30]}...' in {recipe_time:.2f}s")
        
        return formatted_recipe
    
    def _extract_ready_time(self, recipe: Dict) -> str:
        """
        Extract total ready time from cook_time and prep_time.
        
        Args:
            recipe: Raw recipe data
            
        Returns:
            Ready time in minutes as string
        """
        cook_time = recipe.get("cook_time", "")
        prep_time = recipe.get("prep_time", "")
        
        # Try to extract minutes from time strings
        def extract_minutes(time_str: str) -> int:
            if not time_str:
                return 0
            
            # Look for patterns like "30 minutes", "1 hour", "1h 30m"
            time_lower = time_str.lower()
            minutes = 0
            
            # Extract hours
            hour_match = re.search(r'(\d+)\s*(?:hour|hr|h)\b', time_lower)
            if hour_match:
                minutes += int(hour_match.group(1)) * 60
            
            # Extract minutes  
            minute_match = re.search(r'(\d+)\s*(?:minute|min|m)\b', time_lower)
            if minute_match:
                minutes += int(minute_match.group(1))
            
            # If no units, assume minutes
            if minutes == 0:
                number_match = re.search(r'(\d+)', time_str)
                if number_match:
                    minutes = int(number_match.group(1))
            
            return minutes
        
        total_minutes = extract_minutes(cook_time) + extract_minutes(prep_time)
        
        # If no time found, return empty string
        if total_minutes == 0:
            return ""
        
        return str(total_minutes)
    
    def _extract_domain_from_url(self, url: str) -> str:
        """Extract clean domain from URL."""
        if not url:
            return ""
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url.lower())
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ""


# Main function for external use
async def format_recipes_for_app(
    agent_response: str,
    recipe_ids: List[str], 
    recipe_memory: Dict[str, Dict],
    openai_key: str = None,
    include_full_ingredients: bool = True,
    include_full_instructions: bool = True
) -> Dict:
    """
    Format complete response for app consumption.
    
    Args:
        agent_response: Agent's conversational response
        recipe_ids: List of recipe IDs to format
        recipe_memory: Full recipe memory (deps.recipe_memory)
        openai_key: OpenAI API key for ingredient processing
        include_full_ingredients: Whether to process ingredients (default True)
        include_full_instructions: Whether to include instructions (default True)
        
    Returns:
        Complete app-ready response:
        {
            "agent_response": "Found 8 great recipes!",
            "recipes": [formatted_recipe_objects],
            "total_results": 8,
            "processing_time": 2.5,
            "timestamp": 1234567890
        }
    """
    formatter = RecipeFormatter(openai_key)
    return await formatter.format_recipes_for_app(
        agent_response,
        recipe_ids,
        recipe_memory, 
        include_full_ingredients,
        include_full_instructions
    )