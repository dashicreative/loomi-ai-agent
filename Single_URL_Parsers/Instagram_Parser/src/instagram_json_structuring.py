#!/usr/bin/env python3
"""
Recipe JSON Structuring Module

Converts LLM-generated ingredient and direction strings into structured JSON format.
Handles parsing of ingredient quantities/units and extracts recipe title from directions.
"""

import re
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Handle both relative and direct imports for flexibility
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from json_recipe_model import create_standard_recipe_json, format_standard_recipe_json
    from ingredient_parser import IngredientParser, ParsedIngredient
except ImportError:
    # Fallback for different import contexts
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from json_recipe_model import create_standard_recipe_json, format_standard_recipe_json
    from ingredient_parser import IngredientParser, ParsedIngredient


@dataclass  
class Recipe:
    """Represents a complete recipe with all components."""
    title: str
    ingredients: List[ParsedIngredient]
    directions: List[str]
    source_url: str


class RecipeStructurer:
    """
    Converts raw LLM outputs into structured recipe JSON.
    """
    
    def __init__(self):
        """Initialize the recipe structurer with shared ingredient parser."""
        # Use shared ingredient parser for robust parsing
        self.ingredient_parser = IngredientParser()
    
    def parse_ingredients(self, ingredients_output: str) -> List[ParsedIngredient]:
        """
        Parse ingredients string into structured ingredient objects using shared parser.
        
        Expected format: "quantity unit ingredient" or just "ingredient"
        
        Args:
            ingredients_output: Raw string output from ingredients LLM
            
        Returns:
            List of ParsedIngredient objects
        """
        # Use shared ingredient parser for robust, consistent parsing
        return self.ingredient_parser.parse_ingredients_list(ingredients_output)
    
    def parse_directions(self, directions_output: str) -> tuple[str, List[str]]:
        """
        Parse directions string to extract title and direction steps.
        
        Expected format:
        Title
        1. First step
        2. Second step
        etc.
        
        Args:
            directions_output: Raw string output from directions LLM
            
        Returns:
            Tuple of (title, list of direction steps)
        """
        if not directions_output or not directions_output.strip():
            return "Untitled Recipe", []
        
        lines = directions_output.strip().split('\n')
        clean_lines = [line.strip() for line in lines if line.strip()]
        
        if not clean_lines:
            return "Untitled Recipe", []
        
        # First line is the title
        title = clean_lines[0]
        
        # Remaining lines are directions (filter out numbered prefixes)
        directions = []
        for line in clean_lines[1:]:
            # Remove number prefixes like "1.", "2.", etc.
            cleaned_step = re.sub(r'^\d+\.\s*', '', line).strip()
            if cleaned_step:
                directions.append(cleaned_step)
        
        return title, directions
    
    def structure_recipe(self, ingredients_output: str, directions_output: str, source_url: str) -> Recipe:
        """
        Convert raw LLM outputs into a structured Recipe object.
        
        Args:
            ingredients_output: Raw ingredients string from LLM
            directions_output: Raw directions string from LLM (title + numbered steps)
            source_url: Original Instagram URL
            
        Returns:
            Structured Recipe object
        """
        # Parse ingredients
        ingredients = self.parse_ingredients(ingredients_output)
        
        # Parse directions and extract title
        title, directions = self.parse_directions(directions_output)
        
        # Create recipe object
        return Recipe(
            title=title,
            ingredients=ingredients,
            directions=directions,
            source_url=source_url
        )
    
    def recipe_to_json(self, recipe: Recipe, image_url: str = "", meal_occasion: str = "Other") -> str:
        """
        Convert Recipe object to standardized JSON string.
        
        Args:
            recipe: Recipe object
            image_url: Optional image URL for the recipe
            meal_occasion: Meal occasion category (Breakfast/Lunch/Dinner/Dessert/Snack/Other)
            
        Returns:
            JSON string representation using standard format
        """
        # Convert ingredients to standard format
        ingredients = [
            {
                "name": ingredient.name,
                "quantity": ingredient.quantity,
                "unit": ingredient.unit
            }
            for ingredient in recipe.ingredients
        ]
        
        # Create standardized recipe dictionary
        recipe_dict = create_standard_recipe_json(
            title=recipe.title,
            parser_method="Instagram",
            ingredients=ingredients,
            directions=recipe.directions,
            source_url=recipe.source_url,
            image=image_url,
            meal_occasion=meal_occasion,
            total_time=""  # Instagram doesn't provide total time data
            # nutrition defaults to empty strings in standard format
        )
        
        return format_standard_recipe_json(recipe_dict)
    
    def process_llm_outputs(self, ingredients_output: str, directions_output: str, source_url: str, image_url: str = "", meal_occasion: str = "Other") -> str:
        """
        Main method: Convert LLM outputs directly to JSON string.
        
        Args:
            ingredients_output: Raw ingredients string from LLM
            directions_output: Raw directions string from LLM
            source_url: Original Instagram URL
            image_url: Optional image URL for the recipe
            meal_occasion: Meal occasion category (Breakfast/Lunch/Dinner/Dessert/Snack/Other)
            
        Returns:
            Formatted JSON string
        """
        recipe = self.structure_recipe(ingredients_output, directions_output, source_url)
        return self.recipe_to_json(recipe, image_url, meal_occasion)


# Example usage and testing
if __name__ == "__main__":
    # Test with example LLM outputs
    structurer = RecipeStructurer()
    
    # Example ingredients output
    test_ingredients = """pizza dough
Italian sausage
2 cups mozzarella cheese
pepperoni
tomato sauce
Calabrian chili
ricotta cheese
heavy cream
salt
fresh basil
olive oil
fresh parmesan"""
    
    # Example directions output (title + numbered steps)
    test_directions = """Detroit Style Pizza with Sausage, Pepperoni & Whipped Ricotta
1. Proof pizza dough right in the pan
2. Crisp up Italian sausage in a pan
3. Blend simple tomato sauce
4. Grate mozzarella cheese
5. Put cheese on first for crispy crust
6. Add sausage and pepperoni when pizza is evenly coated
7. Add tomato sauce in empty spots along with Calabrian chili
8. Bake at 450°F for about 20 minutes
9. Blend ricotta cheese, heavy cream, and salt for whipped ricotta
10. Top with dollops of whipped ricotta
11. Finish with basil, olive oil, and fresh parmesan"""
    
    test_url = "https://www.instagram.com/p/DKR3zf4uYHy/"
    
    # Convert to JSON
    result_json = structurer.process_llm_outputs(test_ingredients, test_directions, test_url)
    
    print("🧪 Recipe JSON Structuring Test")
    print("=" * 50)
    print(result_json)