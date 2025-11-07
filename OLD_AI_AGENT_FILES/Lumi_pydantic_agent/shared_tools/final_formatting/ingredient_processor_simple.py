"""
Ingredient Processor Simple - Ultra-lean ingredient parsing for recipe data
Converts raw ingredient strings to structured, app-ready format.

PURE REGEX PIPELINE (NO LLM CALLS):
1. Enhanced Regex Parsing: Robust pattern matching for all ingredients
2. Smart Fallback: Default to "1 count" for unmatched patterns
3. Categorization: Assign food categories using keyword matching

Performance optimized: NO API calls, fully parallel processing capable
Input: List of ingredient strings → Output: List of structured ingredient objects
"""

import re
from typing import Dict, List
import os


def _normalize_to_instacart_unit(unit: str) -> str:
    """
    Normalize unit variants to accepted primary units.
    Uses first variant from accepted list.
    """
    unit_lower = unit.lower()
    
    # Unit mappings (use first variant) + period variants
    unit_mappings = {
        # Volume
        'cups': 'cup', 'c': 'cup', 'c.': 'cup',
        'tablespoons': 'tablespoon', 'tbsp': 'tablespoon', 'tbsp.': 'tablespoon', 'tb': 'tablespoon', 'tbs': 'tablespoon',
        'teaspoons': 'teaspoon', 'tsp': 'teaspoon', 'tsp.': 'teaspoon', 'ts': 'teaspoon', 'tspn': 'teaspoon',
        'gallons': 'gallon', 'gal': 'gallon', 'gals': 'gallon',
        'pints': 'pint', 'pt': 'pint', 'pts': 'pint',
        'quarts': 'quart', 'qt': 'quart', 'qts': 'quart',
        'liters': 'liter', 'litres': 'liter', 'l': 'liter',
        'milliliters': 'milliliter', 'millilitres': 'milliliter', 'ml': 'milliliter', 'mls': 'milliliter',
        
        # Weight
        'ounces': 'ounce', 'oz': 'ounce', 'oz.': 'ounce',
        'pounds': 'pound', 'lbs': 'pound', 'lb': 'pound', 'lb.': 'pound',
        'grams': 'gram', 'g': 'gram', 'g.': 'gram', 'gs': 'gram',
        'kilograms': 'kilogram', 'kg': 'kilogram', 'kgs': 'kilogram',
        
        # Count
        'cans': 'can',
        'bunches': 'bunch',
        'heads': 'head',
        'cloves': 'clove',
        'slices': 'slice',
        'pieces': 'piece',
        'packages': 'package', 'pkgs': 'package', 'pkg': 'package',
        'jars': 'jar',
        'bottles': 'bottle',
        'bags': 'bag',
        
        # Descriptive
        'large': 'large',
        'medium': 'medium',
        'small': 'small'
    }
    
    return unit_mappings.get(unit_lower, unit)


class IngredientProcessorSimple:
    """
    Simplified ingredient processor - lean and focused.
    Only processes ingredients: strings in → structured objects out.
    """
    
    def __init__(self):
        """Initialize processor with category keywords."""
        
        # Grocery store category keywords - strict matching only
        # ORDER MATTERS: More specific terms first to avoid false matches
        self.category_keywords = {
            "Spices & Seasonings": [
                # Specific spice powders FIRST (before raw ingredients)
                "garlic powder", "onion powder", "chili powder", "cayenne pepper", "cumin powder",
                "salt", "pepper", "cinnamon", "paprika", "cumin", "turmeric", 
                "cayenne", "nutmeg", "allspice", "bay leaves",
                "dried oregano", "dried basil", "dried thyme", "kosher salt", "black pepper",
                "red pepper flakes", "pepper flakes", "msg", "coriander seeds", "peppercorns"
            ],
            "Produce": [
                # Vegetables (raw ingredients come after spice powders)
                "onion", "onions", "garlic", "tomato", "tomatoes", "carrot", "carrots", "celery",
                "bell pepper", "peppers", "mushroom", "mushrooms", "spinach", "lettuce", "cucumber",
                "broccoli", "cauliflower", "potato", "potatoes", "sweet potato", "zucchini",
                "eggplant", "cabbage", "corn kernels", "corn cob", "fresh corn", "peas", "beans", "green beans", "kale", "arugula",
                "tomatillos", "roma tomato", "white onion", "red onion", "capsicum", "chiles",
                "pasilla", "arbol",
                # Fruits  
                "apple", "apples", "banana", "bananas", "grape", "grapes", "orange", "oranges",
                "strawberry", "strawberries", "blueberry", "blueberries", "raspberry", "raspberries",
                "lemon", "lemons", "lime", "limes", "cherry", "cherries", "peach", "peaches",
                "pear", "pears", "pineapple", "mango", "kiwi", "avocado", "avocados", "raisins",
                # Fresh herbs
                "basil", "cilantro", "parsley", "thyme", "rosemary", "sage", "mint", "oregano",
                "fresh thyme", "fresh basil", "green onions", "scallions", "dill", "chives",
                "sprigs dill", "sprigs", "fresh herbs"
            ],
            "Meat & Seafood": [
                # Beef
                "beef", "steak", "ground beef", "chuck roast", "ribeye", "sirloin",
                # Poultry
                "chicken", "turkey", "duck", "chicken breast", "chicken thighs",
                # Pork
                "pork", "bacon", "ham", "sausage", "pork chops", "pork tenderloin",
                # Fish
                "salmon", "tuna", "cod", "tilapia", "trout", "halibut", "fish",
                # Shellfish
                "shrimp", "crab", "lobster", "scallops", "mussels", "clams",
                # Lamb
                "lamb", "lamb chops"
            ],
            "Dairy": [
                "milk", "cheese", "butter", "cream", "yogurt", "sour cream", "cream cheese",
                "mozzarella", "cheddar", "parmesan", "ricotta", "feta", "goat cheese", "cottage cheese",
                "egg", "eggs", "buttermilk", "monterey jack", "pepper jack", "american cheese",
                "mexican cheese", "cheese blend", "jack cheese", "cheddar cheese", "shredded cheese"
            ],
            "Frozen": [
                "frozen", "ice cream", "frozen vegetables", "frozen fruit", "frozen pizza",
                "frozen berries", "frozen peas", "frozen corn"
            ],
            "Pantry & Dry Goods": [
                # Grains (specific tortilla terms first)
                "corn tortillas", "flour tortillas", "white corn tortillas", "tortilla", "tortillas",
                "rice", "pasta", "bread", "flour", "oats", "quinoa", "barley", "wheat", "noodles",
                "crackers", "cereal", "bagel", "couscous", "buns", "burger buns", 
                "brioche rolls", "rolls", "breadcrumbs", "panko breadcrumbs", "graham cracker",
                "graham crackers", "graham cracker crumbs", "almond flour", "lupin flour",
                # Legumes
                "lentils", "chickpeas", "black beans", "kidney beans", "navy beans",
                # Nuts/Seeds
                "almonds", "walnuts", "pecans", "cashews", "peanuts", "sunflower seeds", "chia seeds",
                # Canned goods
                "canned tomatoes", "tomato paste", "coconut milk", "broth", "stock", "canned beans",
                "refried beans", "canned corn", "hominy"
            ],
            "Condiments & Sauces": [
                "ketchup", "mustard", "mayonnaise", "mayo", "soy sauce", "hot sauce", "bbq sauce",
                "worcestershire", "vinegar", "salad dressing", "ranch", "italian dressing",
                "dijon mustard", "anchovy paste", "pickles", "dill pickles", "gherkins",
                "burger sauce", "yellow mustard", "american mustard", "maple syrup",
                "enchilada sauce", "tomato passata", "puree", "crema", "buffalo wing sauce",
                "wing sauce", "salsa", "salsa verde", "pico de gallo", "guacamole",
                "jalapeño", "jalapenos", "pickled jalapenos", "olives", "black olives"
            ],
            "Baking": [
                "baking powder", "baking soda", "vanilla extract", "vanilla", "sugar", "brown sugar",
                "powdered sugar", "cocoa powder", "chocolate chips", "yeast", "cornstarch",
                "granulated sugar", "confectioners' sugar", "espresso powder", "caster sugar",
                "superfine sugar", "icing sugar", "gelatin", "sweetener", "keto sweetener",
                "monkfruit sweetener", "splenda"
            ],
            "Beverages": [
                "water", "juice", "coffee", "tea", "soda", "wine", "beer", "milk", "almond milk",
                "coconut milk", "orange juice", "apple juice"
            ],
            "Specialty Items": [
                # Oils
                "olive oil", "vegetable oil", "coconut oil", "sesame oil", "avocado oil",
                # Plant proteins
                "tofu", "tempeh", "seitan", "plant protein", "protein powder", "vanilla protein",
                "protein cookies", "scoops",
                # Specialty ingredients
                "truffle oil", "miso paste", "tahini", "nutritional yeast", "agave"
            ]
        }


    def process_ingredients(self, ingredients: List[str]) -> List[Dict]:
        """
        Main entry point: Process list of ingredient strings using pure regex.
        
        Args:
            ingredients: List of raw ingredient strings
            
        Returns:
            List of structured ingredient objects
        """
        if not ingredients:
            return []
        
        try:
            # STAGE 1: Enhanced regex parsing (handles all ingredients)
            parsed_ingredients = []
            all_alternatives = {}  # Store alternatives by index
            
            for i, ingredient in enumerate(ingredients):
                parsed = self._parse_single_ingredient_enhanced(ingredient)
                
                # Extract and store alternatives if present
                alternatives = parsed.pop('_alternatives', [])
                if alternatives:
                    all_alternatives[i] = alternatives
                
                parsed_ingredients.append(parsed)
            
            # STAGE 2: Categorization
            categorized_ingredients = self._categorize_ingredients(parsed_ingredients)
            
            # Store alternatives in a way that can be retrieved by the calling function
            if hasattr(self, '_last_alternatives'):
                self._last_alternatives = all_alternatives
            else:
                # Store alternatives as a class attribute for retrieval
                self._alternatives_map = all_alternatives
            
            return categorized_ingredients
            
        except Exception as e:
            print(f"   ❌ Ingredient processing failed: {e}")
            # Even on error, try to return basic parsing
            return [self._create_default_ingredient(ing) for ing in ingredients]


    def _create_default_ingredient(self, ingredient: str) -> Dict:
        """Create default ingredient structure with 1 count when parsing fails."""
        # Extract potential ingredient name (remove parentheses and extra context)
        ingredient_name = re.sub(r'\([^)]*\)', '', ingredient).strip()
        ingredient_name = re.sub(r'\s+', ' ', ingredient_name)  # Clean whitespace
        
        return {
            "ingredient": ingredient_name,
            "quantity": "1",
            "unit": "count", 
            "additional_context": "",
            "category": ""  # Blank until categorization
        }


    def _parse_single_ingredient_enhanced(self, ingredient: str) -> Dict:
        """
        Enhanced regex parsing for all ingredient patterns.
        Handles fractions, ranges, complex descriptions, special characters, and smart fallbacks.
        """
        # Clean ingredient string first
        ingredient = ingredient.strip()
        
        # Remove special characters from beginning (checkboxes, bullets, etc.)
        # Keep decimal points for ingredients like ".25 oz"
        ingredient = re.sub(r'^[^\w\d\s¼⅓½⅔¾/.,-]+\s*', '', ingredient)
        ingredient = ingredient.strip()
        
        # Define acceptable units (from normalize function + period variants)
        accepted_units = [
            # Volume
            'cup', 'cups', 'c', 'c.', 'tablespoon', 'tablespoons', 'tbsp', 'tbsp.', 'tb', 'tbs',
            'teaspoon', 'teaspoons', 'tsp', 'tsp.', 'ts', 'tspn', 'gallon', 'gallons', 'gal', 'gals',
            'pint', 'pints', 'pt', 'pts', 'quart', 'quarts', 'qt', 'qts',
            'liter', 'liters', 'litres', 'l', 'milliliter', 'milliliters', 'millilitres', 'ml', 'mls',
            # Weight  
            'ounce', 'ounces', 'oz', 'oz.', 'pound', 'pounds', 'lbs', 'lb', 'lb.',
            'gram', 'grams', 'g', 'g.', 'gs', 'kilogram', 'kilograms', 'kg', 'kgs',
            # Count
            'can', 'cans', 'bunch', 'bunches', 'head', 'heads', 'clove', 'cloves',
            'slice', 'slices', 'piece', 'pieces', 'package', 'packages', 'pkg', 'pkgs',
            'jar', 'jars', 'bottle', 'bottles', 'bag', 'bags', 'each',
            # Descriptive
            'large', 'medium', 'small'
        ]
        
        # Enhanced regex patterns (ordered by specificity - most specific first)
        patterns = [
            # Pattern 1: Complex fractions with "and" - "1 and 1/3 cup flour"
            r'^(\d+)\s+and\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 2: Range-fraction combo - "1-¼ cups", "2-½ tsp"
            r'^(\d+)[-–]([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 3: Decimals starting with period - ".25 oz", ".5 cup"  
            r'^(\.\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 4: NO-SPACE units (common issue) - "300g flour", "9g salt"
            r'^(\d+(?:\.\d+)?)(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 5: Unicode fractions WITH SPACE - "1 ½ teaspoons", "2 ¼ cups"
            r'^(\d+)\s+([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s*(.+)$',
            
            # Pattern 6: Mixed number with Unicode fractions NO SPACE - "1¼ cup", "2½ ounces"
            r'^(\d+)([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 7: Mixed number with text fractions - "1 1/2 cup", "2 3/4 ounces"
            r'^(\d+)\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 8: Pure Unicode fractions - "¼ cup", "⅓ cup", "½ teaspoon"
            r'^([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 9: Text fractions - "1/2 cup sugar", "3/4 cup flour"
            r'^(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 10: Range quantities with spaces - "2 - 3 tbsp" or "4 - 8 slices"
            r'^(\d+)\s*[-–]\s*(\d+)\s+(' + '|'.join(accepted_units) + r')\s*(.+)$',
            
            # Pattern 11: Decimal quantities - "2.5 teaspoon salt"
            r'^(\d+\.\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 12: Integer quantities - "16 ounce pizza dough"
            r'^(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 13: Quantities with no accepted unit - "15 graham crackers"
            r'^(\d+(?:\.\d+)?)\s+(.+)$',
            
            # Pattern 14: Descriptive only - "salt to taste"
            r'^(.+)$'
        ]
        
        # Parse ingredient normally (no unit prioritization)
        for i, pattern in enumerate(patterns):
            match = re.match(pattern, ingredient, re.IGNORECASE)
            if match:
                # Also detect alternative units during parsing
                alternatives = self._detect_alternative_units(ingredient)
                result = self._process_regex_match(match, i, ingredient)
                result['_alternatives'] = alternatives  # Store for metadata capture
                return result
        
        # Ultimate fallback (should never reach here)
        return self._create_default_ingredient(ingredient)
    
    
    def _detect_alternative_units(self, ingredient: str) -> List[Dict]:
        """
        Detect all alternative units present in ingredient for metadata capture.
        Example: '400g/14oz canned corn (sub frozen 1 3/4 cups)' 
        → [{"quantity": "14", "unit": "ounce"}, {"quantity": "1 3/4", "unit": "cup"}]
        """
        alternatives = []
        
        # All possible unit patterns to look for
        unit_patterns = [
            # Volume units
            r'(\d+(?:\.\d+)?(?:\s+\d+/\d+)?(?:\s*[-–]\s*\d+)?)\s*(cups?|c\.?)\b',
            r'(\d+(?:\.\d+)?(?:\s+\d+/\d+)?)\s*(tablespoons?|tbsp\.?|tb|tbs)\b', 
            r'(\d+(?:\.\d+)?(?:\s+\d+/\d+)?)\s*(teaspoons?|tsp\.?|ts)\b',
            # Weight units
            r'(\d+(?:\.\d+)?(?:\s+\d+/\d+)?)\s*(pounds?|lbs?\.?|lb\.?)\b',
            r'(\d+(?:\.\d+)?(?:\s+\d+/\d+)?)\s*(ounces?|oz\.?)\b',
            r'(\d+(?:\.\d+)?)([g]\.?)\b',  # Special case for no-space grams
            r'(\d+(?:\.\d+)?)\s*(grams?|g\.?)\b',
            r'(\d+(?:\.\d+)?)\s*(kilograms?|kg)\b',
            # Unicode fractions
            r'([¼⅓½⅔¾])\s*(cups?|tablespoons?|teaspoons?|ounces?|pounds?)\b',
            # Special slash format: "400g/14oz"
            r'(\d+(?:\.\d+)?)([g])\/(\d+(?:\.\d+)?)([a-z]+)\b'
        ]
        
        # Find all unit matches in the ingredient
        for pattern in unit_patterns:
            matches = re.finditer(pattern, ingredient, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                
                # Handle different match formats
                if len(groups) == 2:  # Standard format
                    quantity, unit = groups
                    alternatives.append({
                        "quantity": quantity.strip(),
                        "unit": _normalize_to_instacart_unit(unit.strip())
                    })
                elif len(groups) == 4:  # Slash format: "400g/14oz"
                    # First unit: groups[0] + groups[1]  
                    alternatives.append({
                        "quantity": groups[0].strip(),
                        "unit": _normalize_to_instacart_unit(groups[1].strip())
                    })
                    # Second unit: groups[2] + groups[3]
                    alternatives.append({
                        "quantity": groups[2].strip(),  
                        "unit": _normalize_to_instacart_unit(groups[3].strip())
                    })
        
        # Remove duplicates and return
        seen = set()
        unique_alternatives = []
        for alt in alternatives:
            key = f"{alt['quantity']}|{alt['unit']}"
            if key not in seen:
                seen.add(key)
                unique_alternatives.append(alt)
        
        return unique_alternatives
    
    
    def _process_regex_match(self, match, pattern_index: int, original: str) -> Dict:
        """Process regex match based on pattern type."""
        groups = match.groups()
        
        # Unicode to text fraction mapping (expanded)
        unicode_fractions = {'¼': '1/4', '⅓': '1/3', '½': '1/2', '⅔': '2/3', '¾': '3/4'}
        
        if pattern_index == 0:  # Complex fractions with "and"
            # "1 and 1/3 cup flour" → groups: ('1', '1', '3', 'cup', 'flour')
            whole = groups[0]
            numerator = groups[1]
            denominator = groups[2]
            unit = groups[3]
            name_and_context = groups[4]
            quantity = f"{whole} and {numerator}/{denominator}"
            
        elif pattern_index == 1:  # Range-fraction combo
            # "1-¼ cups" → groups: ('1', '¼', 'cups', 'flour')
            whole = groups[0]
            unicode_frac = groups[1]
            unit = groups[2]
            name_and_context = groups[3]
            text_frac = unicode_fractions.get(unicode_frac, unicode_frac)
            quantity = f"{whole} {text_frac}"
            
        elif pattern_index == 2:  # Decimals starting with period
            # ".25 oz gelatin" → groups: ('.25', 'oz', 'gelatin')
            quantity = "0" + groups[0]  # Convert .25 to 0.25
            unit = groups[1]
            name_and_context = groups[2]
            
        elif pattern_index == 3:  # NO-SPACE units
            # "300g flour" → groups: ('300', 'g', 'flour')
            quantity = groups[0]
            unit = groups[1]
            name_and_context = groups[2]
            
        elif pattern_index == 4:  # Unicode fractions WITH SPACE - "1 ½ teaspoons"
            # "1 ½ teaspoons" → groups: ('1', '½', 'teaspoons', 'ground cinnamon')
            whole = groups[0]
            unicode_frac = groups[1]
            unit = groups[2]
            name_and_context = groups[3]
            text_frac = unicode_fractions.get(unicode_frac, unicode_frac)
            quantity = f"{whole} {text_frac}"
            
        elif pattern_index == 5:  # Mixed number with Unicode fractions NO SPACE - "1¼ cup"
            # "1¼ cup" → groups: ('1', '¼', 'cup', 'flour')
            whole = groups[0]
            unicode_frac = groups[1]
            unit = groups[2]
            name_and_context = groups[3]
            text_frac = unicode_fractions.get(unicode_frac, unicode_frac)
            quantity = f"{whole} {text_frac}"
            
        elif pattern_index == 6:  # Mixed number with text fractions
            # "1 1/2 cup" → groups: ('1', '1', '2', 'cup', 'flour')
            whole = groups[0]
            numerator = groups[1]
            denominator = groups[2]
            unit = groups[3]
            name_and_context = groups[4]
            quantity = f"{whole} {numerator}/{denominator}"
            
        elif pattern_index == 7:  # Pure Unicode fractions
            # "¼ cup" → groups: ('¼', 'cup', 'flour')
            unicode_frac = groups[0]
            unit = groups[1]
            name_and_context = groups[2]
            quantity = unicode_fractions.get(unicode_frac, unicode_frac)
            
        elif pattern_index == 8:  # Text fractions
            # "1/2 cup sugar" → groups: ('1', '2', 'cup', 'sugar')
            numerator = groups[0]
            denominator = groups[1]
            unit = groups[2]
            name_and_context = groups[3]
            quantity = f"{numerator}/{denominator}"
            
        elif pattern_index == 9:  # Range quantities
            # "18-20 slice pepperoni" or "3–4 pounds" → groups: ('3', '4', 'pounds', 'clams')
            start = groups[0]
            end = groups[1]
            unit = groups[2]
            name_and_context = groups[3]
            quantity = f"{start}-{end}"
            
        elif pattern_index in [10, 11]:  # Decimal or integer with accepted unit
            # "2.5 teaspoon salt" or "16 ounce pizza dough"
            quantity = groups[0]
            unit = groups[1]
            name_and_context = groups[2]
            
        elif pattern_index == 12:  # Quantity without accepted unit
            # "15 graham crackers" - no accepted unit found
            quantity = groups[0]
            name_and_context = groups[1]
            unit = "count"  # Default fallback
            
        else:  # pattern_index == 13: Descriptive only
            # "salt to taste" - no quantity found
            name_and_context = groups[0]
            quantity = "1"
            unit = "count"
        
        # Extract ingredient name and additional context
        ingredient_name, additional_context = self._extract_name_and_context(name_and_context)
        
        # Normalize unit
        unit = _normalize_to_instacart_unit(unit)
        
        return {
            "ingredient": ingredient_name,
            "quantity": str(quantity),
            "unit": unit,
            "additional_context": additional_context,
            "category": ""  # Will be set in categorization step, blank if no match
        }
    
    
    def _extract_name_and_context(self, text: str) -> tuple:
        """Extract ingredient name and additional context from text."""
        text = text.strip()
        
        # Look for parentheses content as additional context
        paren_match = re.search(r'\(([^)]+)\)', text)
        if paren_match:
            additional_context = paren_match.group(1)
            # Remove parentheses content to get clean ingredient name
            ingredient_name = re.sub(r'\s*\([^)]*\)\s*', ' ', text).strip()
            ingredient_name = re.sub(r'\s+', ' ', ingredient_name)  # Clean whitespace
        else:
            ingredient_name = text
            additional_context = ""
        
        return ingredient_name, additional_context











    def _categorize_ingredients(self, ingredients: List[Dict]) -> List[Dict]:
        """Assign grocery store categories to ingredients using strict keyword matching."""
        categorized_ingredients = []
        
        for ingredient in ingredients:
            ingredient_name = ingredient.get("ingredient", "").lower()
            category = ""  # Default to empty string for no match
            
            # Strict keyword matching with word boundaries to avoid false matches
            # (e.g., "graham" shouldn't match "ham" from Meat & Seafood)
            for cat, keywords in self.category_keywords.items():
                for keyword in keywords:
                    # Use word boundary regex for better matching
                    if re.search(r'\b' + re.escape(keyword) + r'\b', ingredient_name, re.IGNORECASE):
                        category = cat
                        break
                if category:  # Break outer loop if category found
                    break
            
            # Create categorized ingredient
            categorized_ingredient = ingredient.copy()
            categorized_ingredient["category"] = category
            categorized_ingredients.append(categorized_ingredient)
        
        return categorized_ingredients


# Main function for external use
def process_ingredients_simple(ingredients: List[str]) -> tuple:
    """
    Process ingredients list into structured format using pure regex parsing.
    
    Args:
        ingredients: List of raw ingredient strings
        
    Returns:
        Tuple of (structured_ingredients, alternatives_map)
        - structured_ingredients: List of structured ingredient objects
        - alternatives_map: Dict of {index: [alternative_units]} for metadata
    """
    processor = IngredientProcessorSimple()
    processed_ingredients = processor.process_ingredients(ingredients)
    alternatives_map = getattr(processor, '_alternatives_map', {})
    return processed_ingredients, alternatives_map