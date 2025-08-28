"""
Query Pattern Matching for Recipe Search Requirements

This file contains all the patterns used to extract hard requirements from user queries.
Easily customizable for adding new patterns or adjusting thresholds.

Pattern Structure:
{
    "nutrition": {"protein": {"min": 30}, "calories": {"max": 400}},
    "exclude_ingredients": ["wheat", "dairy"],
    "cooking_constraints": {"cook_time": {"max": 30}},
    "meal_type": "breakfast",
    "dietary_restrictions": ["gluten-free", "dairy-free"]
}
"""

# =============================================================================
# NUTRITION THRESHOLDS
# =============================================================================

NUTRITION_PATTERNS = {
    # Protein requirements
    r"(\d+)g protein": lambda match: {"protein": {"min": int(match.group(1))}},
    r"at least (\d+)g protein": lambda match: {"protein": {"min": int(match.group(1))}},
    r"(\d+)\+ ?g protein": lambda match: {"protein": {"min": int(match.group(1))}},
    r"high protein": {"protein": {"min": 25}},
    r"protein-rich": {"protein": {"min": 20}},
    
    # Calorie requirements
    r"under (\d+) calories": lambda match: {"calories": {"max": int(match.group(1))}},
    r"(\d+) calories or less": lambda match: {"calories": {"max": int(match.group(1))}},
    r"less than (\d+) calories": lambda match: {"calories": {"max": int(match.group(1))}},
    r"low calorie": {"calories": {"max": 300}},
    r"between (\d+)-(\d+) calories": lambda match: {"calories": {"min": int(match.group(1)), "max": int(match.group(2))}},
    
    # Carb requirements
    r"(\d+)g carbs or less": lambda match: {"carbs": {"max": int(match.group(1))}},
    r"under (\d+)g carbs": lambda match: {"carbs": {"max": int(match.group(1))}},
    r"low carb": {"carbs": {"max": 50}},
    r"keto": {"carbs": {"max": 20}},
    r"high carb": {"carbs": {"min": 100}},
    
    # Fat requirements
    r"(\d+)g fat or less": lambda match: {"fat": {"max": int(match.group(1))}},
    r"under (\d+)g fat": lambda match: {"fat": {"max": int(match.group(1))}},
    r"low fat": {"fat": {"max": 10}},
    r"high fat": {"fat": {"min": 20}},
}

# =============================================================================
# MAJOR ALLERGIES
# =============================================================================

ALLERGY_PATTERNS = {
    # Nut allergies
    r"nut-?free": ["peanuts", "almonds", "walnuts", "pecans", "cashews", "pistachios", "hazelnuts", "brazil nuts", "pine nuts", "macadamia"],
    r"peanut-?free": ["peanuts", "peanut butter", "peanut oil"],
    r"tree nut free": ["almonds", "walnuts", "cashews", "pistachios", "hazelnuts", "pecans", "brazil nuts", "macadamia"],
    
    # Shellfish & seafood allergies
    r"shellfish-?free": ["shrimp", "crab", "lobster", "mussels", "clams", "oysters", "scallops", "crawfish"],
    r"seafood-?free": ["fish", "salmon", "tuna", "cod", "shrimp", "crab", "lobster", "anchovy", "sardines"],
    
    # Other major allergies
    r"egg-?free": ["eggs", "egg whites", "egg yolks", "mayonnaise"],
    r"soy-?free": ["soy sauce", "tofu", "tempeh", "edamame", "soy milk", "miso", "soy protein"],
}

# =============================================================================
# DIETARY RESTRICTIONS
# =============================================================================

DIETARY_PATTERNS = {
    # Gluten restrictions
    r"gluten-?free": ["wheat", "flour", "bread", "pasta", "barley", "rye", "oats", "soy sauce", "beer", "malt"],
    r"celiac-?friendly": ["wheat", "flour", "bread", "pasta", "barley", "rye", "malt"],
    
    # Dairy restrictions
    r"dairy-?free": ["milk", "cheese", "butter", "cream", "yogurt", "sour cream", "ice cream", "whey", "casein"],
    r"lactose-?free": ["milk", "cheese", "butter", "cream", "yogurt", "ice cream", "lactose"],
    
    # Plant-based diets
    r"vegan": ["milk", "cheese", "butter", "eggs", "meat", "chicken", "beef", "pork", "fish", "honey", "gelatin"],
    r"plant-?based": ["meat", "chicken", "beef", "pork", "fish", "dairy", "eggs", "honey"],
    r"vegetarian": ["meat", "chicken", "beef", "pork", "fish", "seafood"],
    
    # Sugar restrictions
    r"sugar-?free": ["sugar", "honey", "maple syrup", "corn syrup", "brown sugar", "cane sugar", "agave"],
    r"no added sugar": ["sugar", "honey", "maple syrup", "corn syrup", "artificial sweetener"],
    r"diabetic-?friendly": ["sugar", "honey", "maple syrup", "corn syrup"],  # Also adds carb limit
}

# =============================================================================
# RELIGIOUS/CULTURAL DIETARY LAWS
# =============================================================================

RELIGIOUS_DIETARY_PATTERNS = {
    r"halal": ["pork", "bacon", "ham", "alcohol", "wine", "beer", "gelatin"],
    r"kosher": ["pork", "shellfish", "bacon", "ham"],  # Note: kosher has complex mixing rules
    r"no beef": ["beef", "steak", "ground beef", "beef broth", "ribeye", "sirloin"],
    r"no pork": ["pork", "bacon", "ham", "sausage", "pepperoni"],
}

# =============================================================================
# TIME CONSTRAINTS
# =============================================================================

TIME_PATTERNS = {
    r"under (\d+) minutes": lambda match: {"cook_time": {"max": int(match.group(1))}},
    r"(\d+) minutes or less": lambda match: {"cook_time": {"max": int(match.group(1))}},
    r"(\d+)-?minute meals": lambda match: {"cook_time": {"max": int(match.group(1))}},
    r"quick": {"cook_time": {"max": 20}},
    r"fast": {"cook_time": {"max": 15}},
    r"one hour or less": {"cook_time": {"max": 60}},
    r"slow cooking": {"cook_time": {"min": 120}},
    r"all day": {"cook_time": {"min": 240}},
}

# =============================================================================
# COOKING METHODS & EQUIPMENT
# =============================================================================

COOKING_METHOD_PATTERNS = {
    # Exclusion methods
    r"no-?bake": {"exclude_cooking_methods": ["baking", "oven"]},
    r"stovetop only": {"exclude_equipment": ["oven", "microwave"]},
    r"no oven": {"exclude_equipment": ["oven"]},
    
    # Required equipment
    r"slow cooker": {"required_equipment": ["slow cooker", "crockpot"]},
    r"crockpot": {"required_equipment": ["slow cooker", "crockpot"]},
    r"air fryer": {"required_equipment": ["air fryer"]},
    r"instant pot": {"required_equipment": ["instant pot", "pressure cooker"]},
    r"pressure cooker": {"required_equipment": ["pressure cooker", "instant pot"]},
    
    # Cooking styles
    r"one-?pot": {"cooking_style": "one-pot"},
    r"sheet pan": {"cooking_style": "sheet-pan"},
    r"grilled": {"required_cooking_methods": ["grilling"]},
    r"baked": {"required_cooking_methods": ["baking"]},
    r"fried": {"required_cooking_methods": ["frying"]},
}

# =============================================================================
# MEAL TYPES & TIMING
# =============================================================================

MEAL_TYPE_PATTERNS = {
    r"breakfast": "breakfast",
    r"lunch": "lunch", 
    r"dinner": "dinner",
    r"supper": "dinner",
    r"snack": "snack",
    r"dessert": "dessert",
    r"appetizer": "appetizer",
    r"starter": "appetizer",
    r"side dish": "side",
    r"main course": "main",
}

# =============================================================================
# SERVING & PORTION REQUIREMENTS
# =============================================================================

SERVING_PATTERNS = {
    r"serves (\d+)": lambda match: {"servings": {"target": int(match.group(1))}},
    r"for (\d+) people": lambda match: {"servings": {"target": int(match.group(1))}},
    r"family-?sized": {"servings": {"min": 6}},
    r"single serving": {"servings": {"max": 1}},
    r"individual": {"servings": {"max": 1}},
    r"meal prep": {"servings": {"min": 4}, "storage_friendly": True},
    r"batch cooking": {"servings": {"min": 8}, "storage_friendly": True},
}

# =============================================================================
# SPECIAL DIETARY COMBINATIONS
# =============================================================================

# These handle special cases that need multiple constraints
SPECIAL_DIETARY_COMBINATIONS = {
    r"diabetic-?friendly": {
        "exclude_ingredients": ["sugar", "honey", "maple syrup", "corn syrup"],
        "carbs": {"max": 45}
    },
    r"heart-?healthy": {
        "fat": {"max": 15},
        "exclude_ingredients": ["butter", "lard", "palm oil"],
        "sodium": {"max": 600}  # mg
    },
    r"kidney-?friendly": {
        "sodium": {"max": 400},
        "protein": {"max": 20},
        "exclude_ingredients": ["salt", "soy sauce", "cheese"]
    },
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_exclude_ingredients():
    """Get all ingredients that should be excluded based on patterns."""
    all_excludes = []
    
    # Add allergy exclusions
    for ingredients in ALLERGY_PATTERNS.values():
        all_excludes.extend(ingredients)
    
    # Add dietary restriction exclusions  
    for ingredients in DIETARY_PATTERNS.values():
        all_excludes.extend(ingredients)
    
    # Add religious dietary exclusions
    for ingredients in RELIGIOUS_DIETARY_PATTERNS.values():
        all_excludes.extend(ingredients)
    
    return list(set(all_excludes))  # Remove duplicates

def get_common_substitutions():
    """Common ingredient substitutions for restricted diets."""
    return {
        "gluten-free_flour": ["almond flour", "coconut flour", "rice flour", "oat flour"],
        "dairy-free_milk": ["almond milk", "oat milk", "coconut milk", "soy milk"],
        "egg_replacer": ["flax egg", "chia egg", "aquafaba", "applesauce"],
        "sugar_alternatives": ["stevia", "monk fruit", "erythritol", "xylitol"]
    }