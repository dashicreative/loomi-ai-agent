#!/usr/bin/env python3
"""
Shared Ingredient Parser Module

Provides robust regex pattern matching and parsing for recipe ingredients.
Used across all parsers (Instagram, Site Parser, etc.) to ensure consistent
ingredient parsing with [quantity] + [unit] + [name] format.

This is the single source of truth for ingredient parsing logic.
"""

import re
from typing import List, Optional, Set
from dataclasses import dataclass


@dataclass
class ParsedIngredient:
    """Represents a single parsed ingredient with quantity, unit, and name."""
    name: str
    quantity: str = "1"
    unit: str = "count"


class IngredientParser:
    """
    Robust ingredient parser that handles various quantity/unit/name formats.
    
    Supports patterns like:
    - "2 cups flour" -> quantity=2, unit=cups, name=flour
    - "1/2 tsp salt" -> quantity=1/2, unit=tsp, name=salt  
    - "1 1/2 lbs chicken" -> quantity=1 1/2, unit=lbs, name=chicken
    - "salt" -> quantity=1, unit=count, name=salt
    """
    
    def __init__(self):
        """Initialize parser with comprehensive set of acceptable cooking units."""
        self.acceptable_units: Set[str] = {
            # Volume measurements
            "cup", "cups", "tablespoon", "tablespoons", "tbsp", "teaspoon", "teaspoons", "tsp",
            "milliliter", "milliliters", "ml", "liter", "liters", "l",
            "pint", "pints", "quart", "quarts", "gallon", "gallons",
            
            # Weight measurements  
            "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs", 
            "gram", "grams", "g", "kilogram", "kilograms", "kg",
            
            # Count/piece measurements
            "piece", "pieces", "slice", "slices", "clove", "cloves", 
            "bunch", "bunches", "head", "heads", "can", "cans", "jar", "jars",
            "package", "packages", "bag", "bags", "count"
        }
        
        # Unicode fraction mapping
        self.unicode_fractions = {
            '½': '1/2', '¼': '1/4', '¾': '3/4', '⅓': '1/3', '⅔': '2/3',
            '⅛': '1/8', '⅜': '3/8', '⅝': '5/8', '⅞': '7/8', '⅕': '1/5',
            '⅖': '2/5', '⅗': '3/5', '⅘': '4/5', '⅙': '1/6', '⅚': '5/6'
        }
        
        # Comprehensive regex patterns for all quantity formats
        self.patterns = [
            # Unicode: Whole number + Unicode fraction + unit + name: "1 ½ teaspoons salt"
            r'^(\d+)\s+([½¼¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚])\s+(\w+)\s+(.+)$',
            
            # Unicode: Pure Unicode fraction + unit + name: "½ teaspoon salt"  
            r'^([½¼¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚])\s+(\w+)\s+(.+)$',
            
            # Text fractions: "1 1/2 cups flour"
            r'^(\d+)\s+(\d+/\d+)\s+(\w+)\s+(.+)$',
            
            # Simple fractions: "1/2 cup flour"  
            r'^(\d+/\d+)\s+(\w+)\s+(.+)$',
            
            # Decimals: "1.5 tsp" or "0.25 cup"
            r'^(\d*\.\d+)\s+(\w+)\s+(.+)$',
            
            # Whole numbers: "2 cups flour"
            r'^(\d+)\s+(\w+)\s+(.+)$',
            
            # Fallback: anything else gets "1 count"
            r'^(.+)$'
        ]
    
    def parse_ingredient_line(self, line: str) -> Optional[ParsedIngredient]:
        """
        Parse a single ingredient line into a ParsedIngredient object.
        Enhanced to handle Unicode fractions properly.
        
        Args:
            line: Single ingredient line (e.g., "1 ½ teaspoons salt" or "salt")
            
        Returns:
            ParsedIngredient object or None if parsing fails completely
        """
        line = line.strip()
        if not line:
            return None
        
        # Try each pattern in order (most specific first)
        for pattern_index, pattern in enumerate(self.patterns):
            match = re.match(pattern, line)
            if match:
                return self._process_enhanced_match(match, pattern_index, line)
        
        # Fallback (should never reach here with current patterns)
        return ParsedIngredient(name=line, quantity="1", unit="count")
    
    def _process_enhanced_match(self, match: re.Match, pattern_index: int, original_line: str) -> ParsedIngredient:
        """
        Process regex match based on pattern type, with Unicode fraction support.
        
        Args:
            match: Successful regex match object
            pattern_index: Which pattern matched (0-6)
            original_line: Original line for fallback
            
        Returns:
            ParsedIngredient object
        """
        groups = match.groups()
        
        if pattern_index == 0:  # Whole number + Unicode fraction: "1 ½ teaspoons salt"
            whole = groups[0]
            unicode_frac = groups[1] 
            unit = groups[2]
            name = groups[3]
            text_frac = self.unicode_fractions.get(unicode_frac, unicode_frac)
            quantity = f"{whole} {text_frac}"
            
        elif pattern_index == 1:  # Pure Unicode fraction: "½ teaspoon salt"
            unicode_frac = groups[0]
            unit = groups[1]
            name = groups[2]
            quantity = self.unicode_fractions.get(unicode_frac, unicode_frac)
            
        elif pattern_index == 2:  # Text fractions: "1 1/2 cups flour"
            whole = groups[0]
            frac = groups[1] 
            unit = groups[2]
            name = groups[3]
            quantity = f"{whole} {frac}"
            
        elif pattern_index == 3:  # Simple fractions: "1/2 cup flour"
            quantity = groups[0]
            unit = groups[1]
            name = groups[2]
            
        elif pattern_index == 4:  # Decimals: "1.5 tsp"
            quantity = groups[0]
            unit = groups[1] 
            name = groups[2]
            
        elif pattern_index == 5:  # Whole numbers: "2 cups flour"
            quantity = groups[0]
            unit = groups[1]
            name = groups[2]
            
        else:  # pattern_index == 6: Fallback - no quantity/unit
            return ParsedIngredient(name=groups[0], quantity="1", unit="count")
        
        # Validate unit is acceptable
        unit_lower = unit.lower().strip()
        if unit_lower in self.acceptable_units:
            return ParsedIngredient(
                name=name.strip(),
                quantity=quantity.strip(),
                unit=unit_lower
            )
        else:
            # Unit not recognized, treat whole thing as ingredient name
            return ParsedIngredient(
                name=original_line,
                quantity="1", 
                unit="count"
            )
    
    def parse_ingredients_list(self, ingredients_text: str) -> List[ParsedIngredient]:
        """
        Parse a multi-line string of ingredients into structured ingredient objects.
        
        Args:
            ingredients_text: Raw string with ingredients (one per line)
            
        Returns:
            List of ParsedIngredient objects
        """
        if not ingredients_text or not ingredients_text.strip():
            return []
        
        ingredients = []
        lines = ingredients_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            ingredient = self.parse_ingredient_line(line)
            if ingredient:
                ingredients.append(ingredient)
        
        return ingredients
    
    def add_custom_unit(self, unit: str) -> None:
        """
        Add a custom unit to the acceptable units set.
        
        Args:
            unit: Custom unit to add (will be converted to lowercase)
        """
        self.acceptable_units.add(unit.lower())
    
    def add_custom_units(self, units: List[str]) -> None:
        """
        Add multiple custom units to the acceptable units set.
        
        Args:
            units: List of custom units to add
        """
        for unit in units:
            self.add_custom_unit(unit)
    
    def is_valid_unit(self, unit: str) -> bool:
        """
        Check if a unit is in the acceptable units set.
        
        Args:
            unit: Unit to check
            
        Returns:
            True if unit is acceptable, False otherwise
        """
        return unit.lower() in self.acceptable_units
    
    def get_acceptable_units(self) -> Set[str]:
        """
        Get a copy of the acceptable units set.
        
        Returns:
            Set of acceptable unit strings
        """
        return self.acceptable_units.copy()


# Convenience function for quick parsing
def parse_ingredient(line: str) -> Optional[ParsedIngredient]:
    """
    Quick function to parse a single ingredient line.
    
    Args:
        line: Ingredient line to parse
        
    Returns:
        ParsedIngredient object or None
    """
    parser = IngredientParser()
    return parser.parse_ingredient_line(line)


def parse_ingredients(ingredients_text: str) -> List[ParsedIngredient]:
    """
    Quick function to parse multiple ingredients.
    
    Args:
        ingredients_text: Multi-line ingredient text
        
    Returns:
        List of ParsedIngredient objects
    """
    parser = IngredientParser()
    return parser.parse_ingredients_list(ingredients_text)


# Example usage and testing
if __name__ == "__main__":
    # Test the ingredient parser
    parser = IngredientParser()
    
    test_ingredients = """2 cups all-purpose flour
1/2 tsp salt
1 1/2 lbs chicken breast  
1 ½ teaspoons ground turmeric
½ teaspoon ground cumin
¼ teaspoon ground coriander
3 tbsp olive oil
1 can diced tomatoes
fresh basil
garlic cloves
0.5 cup water"""

    print("🧪 Ingredient Parser Test")
    print("=" * 50)
    print("Input:")
    print(test_ingredients)
    print("\nParsed Results:")
    print("-" * 30)
    
    results = parser.parse_ingredients_list(test_ingredients)
    for ingredient in results:
        print(f"'{ingredient.quantity}' {ingredient.unit} | {ingredient.name}")
    
    print(f"\n✅ Parsed {len(results)} ingredients successfully")