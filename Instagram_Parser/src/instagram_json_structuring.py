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


@dataclass
class Ingredient:
    """Represents a single recipe ingredient with quantity, unit, and name."""
    name: str
    quantity: str = "1"
    unit: str = "count"


@dataclass  
class Recipe:
    """Represents a complete recipe with all components."""
    title: str
    ingredients: List[Ingredient]
    directions: List[str]
    source_url: str


class RecipeStructurer:
    """
    Converts raw LLM outputs into structured recipe JSON.
    """
    
    def __init__(self):
        """Initialize the recipe structurer with acceptable units."""
        # Define acceptable units (as mentioned in original requirements)
        self.acceptable_units = {
            "cup", "cups", "tablespoon", "tablespoons", "tbsp", "teaspoon", "teaspoons", "tsp",
            "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs", "gram", "grams", "g",
            "kilogram", "kilograms", "kg", "milliliter", "milliliters", "ml", "liter", "liters", "l",
            "pint", "pints", "quart", "quarts", "gallon", "gallons", "piece", "pieces", "slice", "slices",
            "clove", "cloves", "bunch", "bunches", "head", "heads", "can", "cans", "jar", "jars",
            "package", "packages", "bag", "bags", "c", "count"
        }
    
    def parse_ingredients(self, ingredients_output: str) -> List[Ingredient]:
        """
        Parse ingredients string into structured ingredient objects.
        
        Expected format: "quantity unit ingredient" or just "ingredient"
        
        Args:
            ingredients_output: Raw string output from ingredients LLM
            
        Returns:
            List of Ingredient objects
        """
        if not ingredients_output or not ingredients_output.strip():
            return []
        
        ingredients = []
        lines = ingredients_output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            ingredient = self._parse_single_ingredient(line)
            if ingredient:
                ingredients.append(ingredient)
        
        return ingredients
    
    def _parse_single_ingredient(self, line: str) -> Optional[Ingredient]:
        """
        Parse a single ingredient line into an Ingredient object.
        
        Args:
            line: Single ingredient line (e.g., "2 cups flour" or "salt")
            
        Returns:
            Ingredient object or None if parsing fails
        """
        line = line.strip()
        if not line:
            return None
        
        # Try to match pattern: "quantity unit ingredient"
        # Using regex to handle various quantity formats (numbers, fractions, etc.)
        pattern = r'^(\d+(?:\.\d+)?(?:/\d+)?)\s+(\w+)\s+(.+)$'
        match = re.match(pattern, line)
        
        if match:
            quantity_str = match.group(1)
            unit_str = match.group(2).lower()
            name_str = match.group(3).strip()
            
            # Validate unit is acceptable, otherwise default to count
            if unit_str in self.acceptable_units:
                return Ingredient(name=name_str, quantity=quantity_str, unit=unit_str)
            else:
                # Unit not recognized, treat whole thing as ingredient name
                return Ingredient(name=line, quantity="1", unit="count")
        
        # No quantity/unit found, treat as ingredient name only
        return Ingredient(name=line, quantity="1", unit="count")
    
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
    
    def recipe_to_json(self, recipe: Recipe) -> str:
        """
        Convert Recipe object to JSON string.
        
        Args:
            recipe: Recipe object
            
        Returns:
            JSON string representation
        """
        recipe_dict = {
            "title": recipe.title,
            "ingredients": [
                {
                    "name": ingredient.name,
                    "quantity": ingredient.quantity,
                    "unit": ingredient.unit
                }
                for ingredient in recipe.ingredients
            ],
            "directions": recipe.directions,
            "source_url": recipe.source_url
        }
        
        return json.dumps(recipe_dict, indent=2, ensure_ascii=False)
    
    def process_llm_outputs(self, ingredients_output: str, directions_output: str, source_url: str) -> str:
        """
        Main method: Convert LLM outputs directly to JSON string.
        
        Args:
            ingredients_output: Raw ingredients string from LLM
            directions_output: Raw directions string from LLM
            source_url: Original Instagram URL
            
        Returns:
            Formatted JSON string
        """
        recipe = self.structure_recipe(ingredients_output, directions_output, source_url)
        return self.recipe_to_json(recipe)


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