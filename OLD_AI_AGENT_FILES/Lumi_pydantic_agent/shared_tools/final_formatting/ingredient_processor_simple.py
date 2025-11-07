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
                # Spice blends (most specific first)
                "italian seasoning", "italian herbs",
                "taco seasoning", "taco spice", "fajita seasoning",
                "curry powder", "curry spice", "madras curry",
                "garam masala", "tikka masala",
                "chinese five spice", "five spice",
                "cajun seasoning", "creole seasoning",
                "ranch seasoning", "ranch mix",
                "poultry seasoning", "chicken seasoning",
                "pumpkin pie spice", "pumpkin spice",
                "herbes de provence",
                "za'atar", "dukkah",
                "everything bagel seasoning",
                "old bay seasoning", "old bay",
                "adobo seasoning",
                # Specific spice powders (before raw ingredients to avoid false matches)
                "garlic powder", "onion powder", "chili powder", "cayenne pepper", "cumin powder",
                "ground ginger", "ginger powder",
                "ground cloves", "ground cardamom", "ground mustard",
                "smoked paprika", "sweet paprika",
                "chipotle powder",
                # Salts
                "kosher salt", "garlic salt", "onion salt", "seasoned salt", "celery salt",
                "salt",
                # Peppers
                "black pepper", "white pepper", "cayenne",
                "red pepper flakes", "pepper flakes",
                "green peppercorns", "peppercorns",
                "pepper",
                # Individual spices
                "cinnamon", "paprika", "cumin", "turmeric", 
                "nutmeg", "allspice",
                "cardamom", "cardamom pods",
                "star anise", "anise seed",
                "whole cloves",
                "mustard seed", "mustard powder",
                "celery seed",
                "fennel seed", "caraway seed",
                "coriander seeds",
                "fenugreek",
                "saffron",
                "sumac",
                "msg",
                # Dried herbs
                "bay leaves", "bay leaf",
                "dried oregano", "dried basil", "dried thyme",
                "dried marjoram", "dried tarragon",
                "dried dill", "dill weed",
                "dried parsley", "dried cilantro",
                "dried rosemary", "dried sage", "dried mint",
                "herbes"
            ],
            "Produce": [
                # Vegetables - Alliums (specific varieties first)
                "white onion", "red onion", "shallots", "shallot",
                "green onions", "scallions",
                "leeks",
                "onion", "onions",
                "garlic",
                # Peppers & Chiles (fresh varieties - specific first)
                "bell pepper", "bell peppers", "red bell pepper", "green bell pepper", "yellow bell pepper",
                "capsicum",
                "fresh jalapeño", "fresh jalapenos", "jalapeño peppers",
                "serrano pepper", "serrano peppers", "serranos",
                "habanero", "habanero pepper",
                "poblano", "poblano pepper",
                "anaheim pepper",
                "pasilla", "arbol",
                "chiles",
                "peppers",
                # Tomatoes
                "roma tomato", "cherry tomatoes", "grape tomatoes",
                "tomatillos",
                "tomato", "tomatoes",
                # Leafy Greens
                "spinach", "kale", "arugula",
                "lettuce", "mixed greens", "spring mix", "salad mix",
                "cabbage", "napa cabbage", "chinese cabbage",
                "bok choy", "baby bok choy",
                "brussels sprouts", "brussel sprouts",
                # Root Vegetables
                "carrot", "carrots", "baby carrots",
                "potato", "potatoes",
                "sweet potato",
                "beets", "beet", "beetroot",
                "turnip", "turnips",
                "parsnip", "parsnips",
                "radish", "radishes",
                "ginger root", "ginger", "fresh ginger",
                "horseradish root", "fresh horseradish",
                "fresh turmeric", "turmeric root",
                "jicama",
                # Squashes
                "butternut squash", "acorn squash", "spaghetti squash",
                "zucchini",
                "eggplant",
                "pumpkin",
                "squash",
                # Other Vegetables
                "broccoli", "cauliflower",
                "celery",
                "cucumber",
                "mushroom", "mushrooms",
                "asparagus",
                "artichoke", "artichokes", "artichoke hearts",
                "fennel", "fennel bulb",
                "corn kernels", "corn cob", "fresh corn",
                "peas", "snap peas", "sugar snap peas", "snow peas",
                "green beans", "beans",
                "edamame",
                "bean sprouts", "sprouts", "alfalfa sprouts", "mung bean sprouts",
                "water chestnuts",
                "lemongrass", "lemongrass stalks",
                # Packaged Produce
                "coleslaw mix", "slaw mix",
                "sun dried tomatoes",
                "packaged herbs",
                # Fruits - Berries
                "strawberry", "strawberries",
                "blueberry", "blueberries",
                "raspberry", "raspberries",
                "blackberry", "blackberries",
                # Fruits - Citrus
                "lemon", "lemons",
                "lime", "limes",
                "orange", "oranges",
                "grapefruit",
                # Fruits - Tree Fruits
                "apple", "apples",
                "pear", "pears",
                "peach", "peaches",
                "nectarine", "nectarines",
                "plum", "plums",
                "apricot", "apricots",
                "cherry", "cherries",
                # Fruits - Tropical
                "banana", "bananas",
                "pineapple",
                "mango",
                "papaya",
                "kiwi",
                "avocado", "avocados",
                "coconut", "fresh coconut",
                "plantain", "plantains",
                "dragon fruit", "pitaya",
                "star fruit",
                "guava",
                "passion fruit",
                # Fruits - Melons
                "watermelon",
                "cantaloupe",
                "honeydew", "honeydew melon",
                "melon",
                # Fruits - Grapes
                "grape", "grapes",
                # Fruits - Other
                "pomegranate", "pomegranate seeds",
                "fig", "figs",
                "dates", "date",
                "persimmon",
                "raisins",
                # Fresh herbs (at end to avoid conflicts with dried)
                "fresh thyme", "fresh basil",
                "fresh herbs",
                "basil", "cilantro", "parsley", "thyme", "rosemary", "sage", "mint", "oregano",
                "dill", "chives",
                "sprigs dill", "sprigs"
            ],
            "Meat & Seafood": [
                # Beef - Specific cuts first
                "ground beef", "ground chuck", "lean ground beef",
                "chuck roast",
                "ribeye", "sirloin",
                "flank steak", "skirt steak",
                "t-bone", "porterhouse",
                "filet mignon",
                "beef tenderloin",
                "beef brisket", "brisket",
                "short ribs", "beef short ribs", "beef ribs",
                "pot roast", "roast beef",
                "stew meat", "beef stew meat",
                "oxtail",
                "beef", "steak",
                # Poultry - Specific cuts first
                "chicken breast", "chicken thighs",
                "chicken wings", "wings",
                "chicken drumsticks", "drumsticks", "chicken legs",
                "whole chicken", "roasting chicken",
                "rotisserie chicken",
                "ground turkey", "ground chicken",
                "turkey breast", "turkey tenderloin",
                "cornish hen", "game hen",
                "chicken", "turkey", "duck",
                # Pork - Specific cuts first
                "ground pork",
                "pork chops", "pork tenderloin",
                "pork belly",
                "pork ribs", "baby back ribs", "spare ribs",
                "pork shoulder", "pork butt",
                "pork loin",
                "pork roast",
                "italian sausage", "breakfast sausage", "bratwurst", "kielbasa",
                "sausage",
                "bacon", "pancetta", "prosciutto",
                "ham",
                "salami", "pepperoni",
                "chorizo",
                "hot dogs", "frankfurters",
                "pork",
                # Fish - Specific types
                "salmon",
                "tuna",
                "cod",
                "tilapia",
                "trout",
                "halibut",
                "mahi mahi", "mahi-mahi",
                "swordfish",
                "sea bass", "chilean sea bass",
                "catfish",
                "flounder", "sole",
                "snapper", "red snapper",
                "grouper",
                "fresh sardines", "sardines",
                "fresh anchovies", "anchovies",
                "fish",
                # Shellfish
                "shrimp", "prawns",
                "crab",
                "lobster",
                "scallops",
                "mussels",
                "clams",
                "oysters", "fresh oysters",
                "squid", "calamari",
                "octopus",
                "crawfish", "crayfish",
                # Lamb
                "lamb chops", "lamb shanks", "lamb shoulder", "lamb leg",
                "ground lamb",
                "lamb"
            ],
            "Dairy": [
                # Milk varieties
                "whole milk", "skim milk", "2% milk", "1% milk",
                "buttermilk",
                "evaporated milk", "condensed milk", "sweetened condensed milk",
                "milk",
                # Cream varieties
                "heavy cream", "heavy whipping cream", "whipping cream",
                "sour cream",
                "half and half", "half-and-half",
                "whipped cream",
                "cream cheese", "cream cheese spread",
                "cream",
                # Yogurt
                "greek yogurt", "plain yogurt", "flavored yogurt",
                "yogurt",
                "kefir",
                # Cheese - Specific varieties first
                "monterey jack", "pepper jack", "jack cheese",
                "american cheese",
                "mexican cheese", "cheese blend",
                "cheddar cheese", "shredded cheese",
                "mozzarella",
                "cheddar",
                "parmesan", "grated parmesan",
                "ricotta",
                "feta",
                "goat cheese",
                "cottage cheese",
                "swiss cheese", "swiss",
                "provolone", "provolone cheese",
                "blue cheese", "bleu cheese", "gorgonzola",
                "brie", "brie cheese", "camembert",
                "gouda", "gouda cheese",
                "havarti",
                "muenster", "munster",
                "gruyere", "gruyère",
                "manchego",
                "queso fresco", "queso blanco",
                "cotija", "cotija cheese",
                "string cheese", "cheese sticks",
                "shredded cheddar", "shredded mozzarella",
                "sliced cheese", "cheese slices",
                "cheese curds",
                "cheese sauce", "nacho cheese",
                "velveeta",
                "cheese",
                # Eggs & Butter
                "egg", "eggs",
                "butter"
            ],
            "Frozen": [
                # Frozen vegetables
                "frozen spinach", "frozen broccoli", "frozen cauliflower",
                "frozen mixed vegetables", "frozen vegetable medley",
                "frozen green beans", "frozen peas and carrots",
                "frozen onions", "frozen peppers", "frozen stir fry vegetables",
                "frozen edamame",
                "frozen brussels sprouts",
                "frozen vegetables", "frozen vegetable",
                # Frozen proteins
                "frozen chicken", "frozen chicken breast", "frozen chicken tenders",
                "frozen fish", "frozen salmon", "frozen tilapia",
                "frozen shrimp", "frozen prawns",
                "frozen meatballs", "frozen burgers", "frozen patties",
                # Frozen starches
                "frozen french fries", "frozen fries", "french fries",
                "tater tots", "frozen tater tots",
                "frozen hash browns", "hash browns",
                "frozen onion rings",
                # Frozen breakfast
                "frozen waffles", "waffles",
                "frozen pancakes", "pancakes",
                "frozen breakfast sandwiches",
                # Frozen meals
                "frozen pizza", "frozen dinner", "frozen meal", "tv dinner",
                "frozen lasagna",
                "frozen pot pie", "chicken pot pie",
                # Frozen desserts
                "ice cream",
                "frozen yogurt", "gelato", "sorbet", "sherbet",
                "popsicles", "ice pops",
                "frozen pie", "frozen cheesecake",
                # Frozen dough
                "frozen pie crust", "frozen pizza dough",
                "frozen bread dough", "frozen rolls",
                "frozen puff pastry", "puff pastry",
                # Frozen fruits
                "frozen berries", "frozen fruit",
                "frozen fruit cocktail",
                # Other frozen
                "ice", "ice cubes", "bagged ice",
                "frozen corn", "frozen peas",
                "frozen"
            ],
            "Pantry & Dry Goods": [
                # Pasta - Specific types first
                "lasagna noodles", "lasagne",
                "egg noodles", "lo mein noodles",
                "rice noodles", "pad thai noodles",
                "soba noodles", "udon noodles",
                "angel hair",
                "spaghetti", "linguine", "fettuccine",
                "penne", "rigatoni", "ziti", "mostaccioli",
                "macaroni", "elbow macaroni",
                "rotini", "fusilli", "farfalle", "bow tie pasta",
                "ravioli", "tortellini",
                "orzo", "ditalini",
                "ramen", "instant ramen", "instant noodles",
                "pasta", "noodles",
                # Rice - Specific types first
                "white rice", "brown rice",
                "jasmine rice", "basmati rice",
                "wild rice", "black rice",
                "arborio rice", "risotto rice",
                "minute rice", "instant rice",
                "rice pilaf",
                "rice",
                # Grains
                "quinoa",
                "oats", "oatmeal", "rolled oats", "steel cut oats", "instant oatmeal",
                "barley",
                "wheat",
                "polenta", "cornmeal",
                "grits", "corn grits",
                "bulgur", "bulgur wheat",
                "farro",
                "couscous",
                "millet",
                "amaranth",
                "teff",
                # Tortillas (specific before generic)
                "white corn tortillas", "corn tortillas", "flour tortillas",
                "tortilla", "tortillas",
                # Bread & Baked Goods
                "english muffins",
                "pita bread", "pita", "pita chips",
                "naan", "naan bread",
                "bagel",
                "dinner rolls", "sandwich rolls",
                "hot dog buns", "hamburger buns",
                "brioche rolls", "rolls",
                "burger buns", "buns",
                "taco shells", "hard taco shells", "soft taco shells",
                "tostadas", "tostada shells",
                "bread",
                # Breadcrumbs
                "panko breadcrumbs",
                "graham cracker crumbs",
                "breadcrumbs", "bread crumbs",
                "croutons",
                # Flours (specific first)
                "almond flour", "lupin flour",
                "coconut flour", "oat flour",
                "chickpea flour", "garbanzo bean flour", "besan",
                "tapioca flour", "arrowroot flour",
                "rice flour",
                "soy flour",
                "flour",
                # Cereals & Breakfast
                "corn flakes", "frosted flakes", "cheerios",
                "granola",
                "cereal",
                # Crackers
                "graham cracker", "graham crackers",
                "saltines", "ritz crackers",
                "crackers",
                # Legumes (dried)
                "dried beans", "dried lentils",
                "split peas",
                "pinto beans", "great northern beans",
                "lentils", "chickpeas",
                "black beans", "kidney beans", "navy beans",
                # Nuts & Seeds
                "almonds", "walnuts", "pecans", "cashews", "peanuts",
                "sunflower seeds", "chia seeds",
                # Canned goods
                "canned diced tomatoes", "canned crushed tomatoes", "canned whole tomatoes",
                "canned tomatoes",
                "tomato paste",
                "canned green chiles", "canned diced green chiles",
                "canned black beans", "canned kidney beans", "canned pinto beans",
                "canned chickpeas", "canned garbanzo beans",
                "canned beans",
                "refried beans",
                "canned corn", "canned peas",
                "canned tuna", "canned salmon", "canned sardines",
                "canned chicken", "canned ham",
                "chicken broth", "beef broth", "vegetable broth",
                "chicken stock", "beef stock", "vegetable stock",
                "broth", "stock",
                "canned soup", "condensed soup",
                "canned pumpkin", "pumpkin puree",
                "canned coconut cream",
                "canned evaporated milk",
                "canned olives",
                "coconut milk",
                "hominy",
                # Snacks
                "tortilla chips", "potato chips", "chips",
                "pretzel sticks", "pretzels",
                "microwave popcorn", "popcorn",
                "saltines", "ritz crackers",
                "rice cakes",
                "trail mix", "mixed nuts",
                "granola bars", "protein bars", "energy bars",
                # Nut butters & spreads
                "peanut butter", "almond butter", "cashew butter", "nut butter",
                "nutella", "chocolate spread",
                "jam", "jelly", "preserves", "marmalade",
                "raw honey", "manuka honey", "honey",
                "maple syrup", "pancake syrup",
                "agave nectar", "agave syrup",
                "molasses", "blackstrap molasses",
                # Dried fruits
                "dried cranberries", "craisins",
                "dried apricots", "dried cherries",
                "prunes", "dried figs",
                "dried mango",
                # Other pantry
                "stuffing", "stuffing mix", "bread stuffing",
                "vital wheat gluten"
            ],
            "Condiments & Sauces": [
                # Classic condiments
                "ketchup",
                "dijon mustard", "yellow mustard", "american mustard",
                "mustard",
                "mayonnaise", "mayo",
                "pickle relish", "sweet relish", "relish",
                "tartar sauce", "cocktail sauce",
                "prepared horseradish", "horseradish",
                "wasabi", "wasabi paste",
                # Hot sauces
                "buffalo wing sauce", "wing sauce",
                "hot sauce",
                "bbq sauce",
                "sriracha", "tabasco", "frank's red hot",
                "sweet chili sauce", "chili garlic sauce", "chili sauce",
                # Asian sauces
                "soy sauce",
                "fish sauce", "oyster sauce", "hoisin sauce",
                "teriyaki sauce", "teriyaki",
                "stir fry sauce", "stir-fry sauce",
                # Worcestershire
                "worcestershire",
                # Vinegars (specific first)
                "apple cider vinegar", "cider vinegar",
                "balsamic vinegar", "balsamic",
                "red wine vinegar", "white wine vinegar",
                "rice vinegar", "rice wine vinegar",
                "sherry vinegar",
                "malt vinegar",
                "white vinegar", "distilled vinegar",
                "vinegar",
                # Dressings
                "salad dressing",
                "ranch",
                "italian dressing",
                "thousand island", "thousand island dressing",
                "caesar dressing", "caesar",
                "blue cheese dressing",
                "balsamic vinaigrette", "vinaigrette",
                "honey mustard", "honey mustard dressing",
                "french dressing",
                "greek dressing",
                # Pasta & Pizza sauces
                "marinara", "marinara sauce",
                "tomato sauce", "pasta sauce",
                "alfredo sauce", "alfredo",
                "basil pesto", "pesto sauce", "pesto",
                "vodka sauce",
                "pizza sauce",
                "bolognese", "bolognese sauce",
                "enchilada sauce",
                "tomato passata",
                # Other sauces
                "brown gravy", "turkey gravy", "gravy",
                "au jus",
                "hollandaise", "hollandaise sauce",
                "bearnaise", "béarnaise sauce",
                "chimichurri",
                "tahini sauce",
                "tzatziki", "tzatziki sauce",
                "curry sauce",
                "pad thai sauce",
                "satay sauce", "peanut sauce",
                "mole sauce",
                # Pickled items
                "dill pickles", "pickles",
                "gherkins",
                "pickled jalapenos", "pickled onions", "pickled peppers", "pickled vegetables",
                "capers", "caper berries",
                "pepperoncini", "banana peppers",
                # Mexican condiments
                "salsa verde", "salsa",
                "pico de gallo",
                "guacamole",
                "jalapeño",
                "jalapenos",
                "crema",
                # Specialty
                "anchovy paste",
                "burger sauce",
                "puree",
                "black olives", "olives"
            ],
            "Baking": [
                # Baking mixes
                "yellow cake mix", "chocolate cake mix", "cake mix",
                "brownie mix", "muffin mix",
                "pancake mix", "bisquick", "biscuit mix",
                "cornbread mix",
                "cookie mix",
                # Leavening
                "baking powder",
                "baking soda", "bicarbonate of soda",
                "active dry yeast", "instant yeast", "yeast",
                "cream of tartar",
                # Sugars (specific first)
                "light brown sugar", "dark brown sugar", "brown sugar",
                "powdered sugar", "confectioners' sugar", "icing sugar",
                "granulated sugar",
                "caster sugar", "superfine sugar",
                "raw sugar", "turbinado sugar",
                "demerara sugar",
                "coconut sugar",
                "sugar",
                # Syrups
                "light corn syrup", "dark corn syrup", "corn syrup",
                "golden syrup",
                # Sweeteners (specific first)
                "monkfruit sweetener", "keto sweetener",
                "artificial sweetener", "stevia", "truvia",
                "splenda",
                "erythritol", "xylitol",
                "sweetener",
                # Extracts & flavorings
                "vanilla extract",
                "almond extract",
                "peppermint extract", "mint extract",
                "lemon extract", "orange extract",
                "coconut extract",
                "maple extract",
                "vanilla bean", "vanilla beans",
                "vanilla",
                "food coloring", "food dye",
                "rose water", "orange blossom water",
                # Chocolate
                "semi-sweet chocolate chips", "milk chocolate chips", "dark chocolate chips", "white chocolate chips",
                "mini chocolate chips",
                "chocolate chips",
                "unsweetened chocolate", "bittersweet chocolate", "baking chocolate",
                "dutch process cocoa",
                "cocoa powder",
                "chocolate bars", "baking bars",
                "chocolate chunks",
                "butterscotch chips", "peanut butter chips", "cinnamon chips",
                # Powder/spices for baking
                "espresso powder",
                # Fats
                "vegetable shortening", "shortening", "crisco",
                "lard",
                # Mix-ins
                "shredded coconut", "coconut flakes", "sweetened coconut",
                "coconut",
                "golden raisins",
                "toffee bits", "heath bits",
                "sprinkles", "jimmies", "nonpareils",
                "candy melts", "almond bark",
                # Other baking
                "mini marshmallows", "marshmallows", "marshmallow fluff",
                "cherry pie filling", "apple pie filling", "pie filling",
                "graham cracker crust", "pie crust",
                "phyllo dough", "filo dough",
                "frosting", "icing", "buttercream",
                "fondant",
                "meringue powder",
                "tapioca", "tapioca pearls",
                "candied ginger", "crystallized ginger",
                "cornstarch",
                "gelatin"
            ],
            "Beverages": [
                # Juices (specific first)
                "orange juice",
                "apple juice",
                "cranberry juice",
                "grape juice",
                "pineapple juice",
                "grapefruit juice",
                "tomato juice", "vegetable juice", "v8",
                "lemonade", "limeade",
                "fruit punch",
                "juice",
                # Water
                "bottled water", "spring water",
                "sparkling water", "seltzer", "club soda", "tonic water",
                "mineral water",
                "coconut water",
                "water",
                # Soft drinks
                "cola", "coke", "pepsi",
                "sprite", "7up", "ginger ale",
                "root beer", "dr pepper",
                "mountain dew",
                "soda",
                # Energy & sports
                "gatorade", "powerade", "sports drink",
                "energy drink", "red bull", "monster",
                "vitamin water", "enhanced water",
                # Coffee (specific first)
                "ground coffee", "coffee beans", "instant coffee",
                "espresso", "espresso beans",
                "iced coffee", "cold brew",
                "coffee",
                # Tea
                "chai", "chai tea",
                "black tea", "green tea", "herbal tea",
                "iced tea", "sweet tea",
                "matcha", "matcha powder",
                "tea",
                # Hot beverages
                "hot chocolate", "hot cocoa mix", "cocoa",
                "apple cider", "hot cider", "cider",
                # Alcohol
                "red wine", "white wine", "rosé", "wine",
                "lager", "ale", "ipa", "beer",
                "champagne", "prosecco", "sparkling wine",
                "vodka", "rum", "whiskey", "bourbon", "tequila", "gin",
                "liqueur", "schnapps",
                "sake",
                # Other
                "protein shake", "protein drink",
                "meal replacement", "ensure", "slim fast",
                "kombucha",
                "horchata",
                "eggnog",
                # Plant-based milks
                "almond milk", "oat milk", "soy milk",
                "cashew milk", "rice milk", "hemp milk"
            ],
            "Specialty Items": [
                # Oils (specific first)
                "olive oil",
                "coconut oil",
                "sesame oil",
                "avocado oil",
                "vegetable oil", "canola oil",
                "peanut oil", "grapeseed oil",
                "sunflower oil", "safflower oil",
                "walnut oil", "hazelnut oil",
                "flaxseed oil", "hemp oil",
                "mct oil",
                "ghee", "clarified butter",
                # Seeds
                "flax seed", "flaxseed", "ground flaxseed",
                "hemp seeds", "hemp hearts",
                "pumpkin seeds", "pepitas",
                "black sesame seeds", "sesame seeds",
                "poppy seeds",
                # Plant proteins
                "plant protein",
                "vanilla protein",
                "protein powder",
                "protein cookies",
                "scoops",
                "beyond meat", "impossible meat", "plant-based meat",
                "vegan sausage", "vegan burger", "veggie burger",
                "tvp", "textured vegetable protein",
                "tofu", "tempeh", "seitan",
                # Plant-based dairy
                "vegan cheese", "dairy-free cheese",
                "vegan butter", "dairy-free butter",
                "coconut cream",
                # Fermented foods
                "kimchi",
                "sauerkraut", "fermented cabbage",
                "white miso", "red miso", "miso", "miso paste",
                # Asian specialty
                "nori", "seaweed", "seaweed sheets",
                "wakame", "kombu", "kelp",
                "rice paper", "spring roll wrappers",
                "wonton wrappers", "dumpling wrappers",
                "panko", "japanese breadcrumbs",
                # Nutrition supplements
                "protein bar", "quest bar", "clif bar",
                "fiber supplement", "psyllium husk",
                "collagen powder",
                "spirulina", "chlorella",
                "whey protein",
                # Thickeners & binders
                "xanthan gum", "guar gum",
                "agar agar",
                # Other specialty
                "truffle oil",
                "tahini",
                "nutritional yeast",
                "agave",
                "liquid smoke",
                "activated charcoal"
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
            # ========== NEW PATTERNS (Added for better coverage) ==========
            
            # Pattern 0: Parenthetical can sizes - "2 (15-ounce) cans" or "1 (28 oz) can"
            r'^(\d+)\s*\((\d+(?:\.\d+)?)\s*[-–]?\s*(' + '|'.join(accepted_units) + r')\)\s*(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 1: Can size without outer quantity - "(15-ounce) can tomatoes" or "(28 oz) can"
            r'^\((\d+(?:\.\d+)?)\s*[-–]?\s*(' + '|'.join(accepted_units) + r')\)\s*(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 2: Approximations with fractions - "about 1/2 cup", "roughly 2 3/4 cups"
            r'^(?:about|roughly|around|approximately)\s+(\d+)\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 3: Approximations with decimals - "about 2.5 cups", "roughly 1.25 tablespoons"
            r'^(?:about|roughly|around|approximately)\s+(\d+\.\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 4: Approximations with integers - "about 2 cups", "approximately 3 tablespoons"
            r'^(?:about|roughly|around|approximately)\s+(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 5: Approximations with unicode fractions - "about ½ cup", "roughly 1 ¼ cups"
            r'^(?:about|roughly|around|approximately)\s+(\d+)\s+([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 6: "to" ranges with fractions - "1/2 to 3/4 cup", "1 to 1 1/2 cups"
            r'^(\d+)/(\d+)\s+to\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 7: "to" ranges with mixed - "1 to 2 cups", "2 to 3 tablespoons"  
            r'^(\d+)\s+to\s+(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 8: "or" alternatives - "1 or 2 tablespoons", "2 or 3 cloves"
            r'^(\d+)\s+or\s+(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 9: Hyphenated mixed fractions - "1-1/2 cup" (common typo/style)
            r'^(\d+)-(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 10: No-space fraction before unit - "1/2cup", "3/4tsp"
            r'^(\d+)/(\d+)(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 11: No-space unicode fraction before unit - "½cup", "¼tsp"
            r'^([¼⅓½⅔¾])(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 12: No-space decimal before unit - "2.5tsp", "1.25cup"
            r'^(\d+\.\d+)(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 13: Plus ranges - "1+ cup", "2+ tablespoons" (meaning "at least")
            r'^(\d+)\+\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 14: Tilde approximations - "~2 cups", "~1/2 teaspoon"
            r'^~\s*(\d+(?:\.\d+)?)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 15: Tilde with fractions - "~1/2 cup", "~2 1/2 cups"
            r'^~\s*(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # ========== EXISTING PATTERNS (Preserved, renumbered) ==========
            
            # Pattern 16: Complex fractions with "and" - "1 and 1/3 cup flour"
            r'^(\d+)\s+and\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 17: Range-fraction combo - "1-¼ cups", "2-½ tsp"
            r'^(\d+)[-–]([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 18: Decimals starting with period - ".25 oz", ".5 cup"  
            r'^(\.\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 19: NO-SPACE units (integers/decimals only) - "300g flour", "9g salt"
            r'^(\d+(?:\.\d+)?)(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 20: Unicode fractions WITH SPACE - "1 ½ teaspoons", "2 ¼ cups"
            r'^(\d+)\s+([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s*(.+)$',
            
            # Pattern 21: Mixed number with Unicode fractions NO SPACE - "1¼ cup", "2½ ounces"
            r'^(\d+)([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 22: Mixed number with text fractions - "1 1/2 cup", "2 3/4 ounces"
            r'^(\d+)\s+(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 23: Pure Unicode fractions - "¼ cup", "⅓ cup", "½ teaspoon"
            r'^([¼⅓½⅔¾])\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 24: Text fractions - "1/2 cup sugar", "3/4 cup flour"
            r'^(\d+)/(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 25: Range quantities with spaces - "2 - 3 tbsp" or "4 - 8 slices"
            r'^(\d+)\s*[-–]\s*(\d+)\s+(' + '|'.join(accepted_units) + r')\s*(.+)$',
            
            # Pattern 26: Decimal quantities - "2.5 teaspoon salt"
            r'^(\d+\.\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 27: Integer quantities - "16 ounce pizza dough"
            r'^(\d+)\s+(' + '|'.join(accepted_units) + r')\s+(.+)$',
            
            # Pattern 28: Quantities with no accepted unit - "15 graham crackers"
            r'^(\d+(?:\.\d+)?)\s+(.+)$',
            
            # Pattern 29: Descriptive only - "salt to taste"
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