"""
Stage 9B: Ingredient Categorization
Hybrid approach: keyword matching first, then LLM for uncategorized ingredients.

Architecture:
1. Keyword matching for common ingredients using 17 predefined categories
2. Parallel LLM calls (5 concurrent) for uncategorized ingredients per recipe
3. Updates ingredient structures with category metadata

Categories: Fruits, Vegetables, Canned Goods, Dairy, Meat, Fish & Seafood, Deli, 
Condiments & Spices, Snacks, Bread & Bakery, Beverages, Pasta/Rice/Cereal, 
Baking, Frozen Foods, Personal Care, Health Care, Household & Cleaning, Baby Items, Pet Care
"""

import asyncio
import httpx
import json
import time
from typing import Dict, List, Optional
import os


# 17 Category keyword mappings
CATEGORY_KEYWORDS = {
    "Fruits": [
        "apple", "apples", "banana", "bananas", "grape", "grapes", "orange", "oranges", 
        "strawberry", "strawberries", "avocado", "avocados", "peach", "peaches", "berry", "berries",
        "lemon", "lemons", "lime", "limes", "pear", "pears", "cherry", "cherries", "mango", "mangos",
        "pineapple", "blueberry", "blueberries", "raspberry", "raspberries", "blackberry", "blackberries",
        "kiwi", "coconut", "watermelon", "cantaloupe", "honeydew"
    ],
    "Vegetables": [
        "potato", "potatoes", "onion", "onions", "carrot", "carrots", "lettuce", "salad", "broccoli",
        "pepper", "peppers", "bell pepper", "tomato", "tomatoes", "cucumber", "cucumbers", "celery",
        "spinach", "kale", "cabbage", "cauliflower", "zucchini", "squash", "eggplant", "mushroom", "mushrooms",
        "garlic", "ginger", "scallion", "scallions", "green onion", "radish", "beet", "beets"
    ],
    "Canned Goods": [
        "canned", "can", "soup", "tuna", "canned fruit", "beans", "canned vegetables", 
        "pasta sauce", "tomato sauce", "diced tomatoes", "crushed tomatoes", "tomato paste",
        "coconut milk", "broth", "stock", "canned corn", "canned beans"
    ],
    "Dairy": [
        "butter", "cheese", "egg", "eggs", "milk", "yogurt", "cream cheese", "sour cream",
        "heavy cream", "whipping cream", "mozzarella", "cheddar", "parmesan", "ricotta",
        "cottage cheese", "feta", "goat cheese", "cream", "half and half"
    ],
    "Meat": [
        "chicken", "beef", "pork", "sausage", "bacon", "ham", "turkey", "lamb", "veal",
        "ground beef", "ground turkey", "ground chicken", "steak", "ribs", "brisket", 
        "chicken breast", "chicken thigh", "pork chop", "ground pork"
    ],
    "Fish & Seafood": [
        "shrimp", "crab", "cod", "tuna", "salmon", "fish", "seafood", "scallops", "lobster",
        "halibut", "mahi mahi", "tilapia", "catfish", "sole", "flounder", "anchovy", "anchovies"
    ],
    "Deli": [
        "deli cheese", "salami", "ham", "turkey", "roast beef", "pastrami", "prosciutto",
        "deli meat", "lunch meat", "sliced cheese", "deli turkey", "deli ham"
    ],
    "Condiments & Spices": [
        "salt", "pepper", "black pepper", "oregano", "cinnamon", "sugar", "olive oil", "ketchup", 
        "mayonnaise", "mustard", "vinegar", "soy sauce", "hot sauce", "garlic powder", "onion powder",
        "paprika", "cumin", "thyme", "rosemary", "basil", "parsley", "cilantro", "dill", "sage",
        "nutmeg", "vanilla", "vanilla extract", "honey", "maple syrup", "barbecue sauce", "ranch"
    ],
    "Snacks": [
        "chips", "pretzels", "popcorn", "crackers", "nuts", "peanuts", "almonds", "cashews",
        "walnuts", "pecans", "trail mix", "granola bars", "cookies", "candy"
    ],
    "Bread & Bakery": [
        "bread", "tortillas", "pita", "bagels", "muffins", "croissant", "rolls", "buns",
        "pie crust", "pizza dough", "naan", "biscuits", "cake", "cookies", "pastry"
    ],
    "Beverages": [
        "coffee", "tea", "teabags", "juice", "soda", "beer", "wine", "water", "sparkling water",
        "energy drink", "sports drink", "lemonade", "iced tea"
    ],
    "Pasta, Rice & Cereal": [
        "pasta", "rice", "brown rice", "white rice", "macaroni", "noodles", "spaghetti", "penne",
        "fusilli", "linguine", "oats", "oatmeal", "granola", "cereal", "quinoa", "barley", "couscous"
    ],
    "Baking": [
        "flour", "all-purpose flour", "whole wheat flour", "powdered sugar", "confectioners sugar",
        "baking powder", "baking soda", "cocoa", "cocoa powder", "yeast", "cornstarch", "vanilla extract"
    ],
    "Frozen Foods": [
        "frozen", "ice cream", "frozen pizza", "frozen vegetables", "frozen fruit", "frozen fish",
        "frozen chicken", "frozen fries", "frozen meals", "popsicles"
    ],
    "Personal Care": [
        "shampoo", "conditioner", "deodorant", "toothpaste", "dental floss", "soap", "body wash",
        "lotion", "moisturizer", "sunscreen"
    ],
    "Health Care": [
        "saline", "band-aid", "bandage", "cleaning alcohol", "rubbing alcohol", "pain killers",
        "antacids", "vitamins", "medicine", "first aid"
    ],
    "Household & Cleaning Supplies": [
        "laundry detergent", "dish soap", "dishwashing liquid", "paper towels", "tissues", 
        "trash bags", "aluminum foil", "plastic wrap", "zip bags", "cleaning supplies", "bleach"
    ],
    "Baby Items": [
        "baby food", "diapers", "wet wipes", "baby lotion", "formula", "baby cereal"
    ],
    "Pet Care": [
        "pet food", "dog food", "cat food", "kitty litter", "chew toys", "pet treats", 
        "pet shampoo", "dog treats", "cat treats"
    ]
}


def categorize_ingredient_by_keywords(ingredient_name: str) -> Optional[str]:
    """
    Categorize ingredient using keyword matching.
    
    Args:
        ingredient_name: Clean ingredient name to categorize
        
    Returns:
        Category name if found, None if no match
    """
    ingredient_lower = ingredient_name.lower().strip()
    
    # Check each category for keyword matches
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in ingredient_lower:
                return category
    
    return None


async def categorize_uncategorized_ingredients_parallel(recipes: List[Dict], api_key: str = None) -> List[Dict]:
    """
    Stage 9B: Categorize uncategorized ingredients using parallel LLM calls.
    
    Args:
        recipes: List of recipes with parsed ingredients (from Stage 9A)
        api_key: OpenAI API key (optional, uses env if not provided)
        
    Returns:
        List of recipes with categorized ingredients
    """
    if not recipes:
        return recipes
        
    api_key = api_key or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("⚠️  No OpenAI API key found - skipping LLM categorization")
        return recipes
    
    print(f"\n🏷️ STAGE 9B: Ingredient Categorization ({len(recipes)} recipes)")
    print("=" * 60)
    
    total_start = time.time()
    
    # Stage 1: Apply keyword categorization to all recipes
    print("🔍 Stage 1: Keyword categorization...")
    keyword_start = time.time()
    
    recipes_with_keywords = []
    uncategorized_counts = []
    
    for recipe in recipes:
        ingredients = recipe.get('ingredients', [])
        categorized_ingredients = []
        uncategorized_count = 0
        
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                ingredient_name = ingredient.get('ingredient', '')
                category = categorize_ingredient_by_keywords(ingredient_name)
                
                # Add category field to ingredient structure
                ingredient_copy = ingredient.copy()
                ingredient_copy['category'] = category
                categorized_ingredients.append(ingredient_copy)
                
                if category is None:
                    uncategorized_count += 1
            else:
                # Handle string ingredients (fallback case)
                ingredient_name = str(ingredient)
                category = categorize_ingredient_by_keywords(ingredient_name)
                categorized_ingredients.append({
                    'ingredient': ingredient_name,
                    'category': category
                })
                if category is None:
                    uncategorized_count += 1
        
        recipe_copy = recipe.copy()
        recipe_copy['ingredients'] = categorized_ingredients
        recipes_with_keywords.append(recipe_copy)
        uncategorized_counts.append(uncategorized_count)
    
    keyword_time = time.time() - keyword_start
    total_uncategorized = sum(uncategorized_counts)
    
    print(f"   ✅ Keyword categorization completed: {keyword_time:.2f}s")
    print(f"   📊 {total_uncategorized} ingredients need LLM categorization")
    
    # Stage 2: Parallel LLM categorization for uncategorized ingredients
    if total_uncategorized > 0:
        print("🤖 Stage 2: Parallel LLM categorization...")
        llm_start = time.time()
        
        # Create tasks for parallel processing (one per recipe)
        llm_tasks = []
        for i, recipe in enumerate(recipes_with_keywords):
            if uncategorized_counts[i] > 0:
                task = _categorize_recipe_ingredients_llm(recipe, api_key)
                llm_tasks.append(task)
            else:
                # No uncategorized ingredients, return as-is
                async def return_recipe():
                    return recipe
                llm_tasks.append(return_recipe())
        
        # Execute all LLM calls in parallel
        llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        final_recipes = []
        for i, result in enumerate(llm_results):
            if isinstance(result, Exception):
                print(f"   ⚠️  LLM categorization failed for recipe {i+1}: {result}")
                # Keep keyword-only results
                final_recipes.append(recipes_with_keywords[i])
            else:
                final_recipes.append(result)
        
        llm_time = time.time() - llm_start
        print(f"   ✅ LLM categorization completed: {llm_time:.2f}s")
        
    else:
        print("   ✅ All ingredients categorized by keywords - no LLM needed")
        final_recipes = recipes_with_keywords
    
    total_time = time.time() - total_start
    print(f"🎉 Total categorization time: {total_time:.2f}s")
    print("=" * 60)
    
    return final_recipes


async def _categorize_recipe_ingredients_llm(recipe: Dict, api_key: str) -> Dict:
    """
    Categorize uncategorized ingredients for a single recipe using LLM.
    
    Args:
        recipe: Recipe with ingredients that may have null/None categories
        api_key: OpenAI API key
        
    Returns:
        Recipe with all ingredients categorized
    """
    ingredients = recipe.get('ingredients', [])
    uncategorized_ingredients = []
    
    # Find ingredients without categories
    for i, ingredient in enumerate(ingredients):
        if isinstance(ingredient, dict) and ingredient.get('category') is None:
            uncategorized_ingredients.append({
                'index': i,
                'name': ingredient.get('ingredient', '')
            })
    
    if not uncategorized_ingredients:
        return recipe
    
    # Create LLM prompt for uncategorized ingredients
    ingredients_text = "\n".join([f"- {ing['name']}" for ing in uncategorized_ingredients])
    
    prompt = f"""Categorize these food ingredients into the correct category. Use only these 17 categories:

CATEGORIES:
Fruits, Vegetables, Canned Goods, Dairy, Meat, Fish & Seafood, Deli, Condiments & Spices, Snacks, Bread & Bakery, Beverages, Pasta Rice & Cereal, Baking, Frozen Foods, Personal Care, Health Care, Household & Cleaning Supplies, Baby Items, Pet Care

INGREDIENTS TO CATEGORIZE:
{ingredients_text}

EXAMPLES:
- butter → Dairy
- chicken breast → Meat
- olive oil → Condiments & Spices
- flour → Baking
- frozen peas → Frozen Foods

Return JSON array with categories in same order: ["Dairy", "Meat", "Condiments & Spices", ...]"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",  # Fast model for categorization
                    "max_tokens": 200,
                    "temperature": 0.1,
                    "messages": [
                        {
                            "role": "system", 
                            "content": "You categorize food ingredients. Return only a JSON array of categories in order."
                        },
                        {"role": "user", "content": prompt}
                    ]
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Extract JSON array
            if '[' in llm_response and ']' in llm_response:
                start = llm_response.find('[')
                end = llm_response.rfind(']') + 1
                json_str = llm_response[start:end]
                categories = json.loads(json_str)
                
                # Update ingredients with LLM categories
                recipe_copy = recipe.copy()
                ingredients_copy = recipe_copy['ingredients'].copy()
                
                for i, category in enumerate(categories):
                    if i < len(uncategorized_ingredients):
                        ingredient_index = uncategorized_ingredients[i]['index']
                        if ingredient_index < len(ingredients_copy):
                            ingredients_copy[ingredient_index] = ingredients_copy[ingredient_index].copy()
                            ingredients_copy[ingredient_index]['category'] = category
                
                recipe_copy['ingredients'] = ingredients_copy
                return recipe_copy
        
        # Fallback: return with "Other" category for uncategorized
        recipe_copy = recipe.copy()
        ingredients_copy = recipe_copy['ingredients'].copy()
        
        for unc_ing in uncategorized_ingredients:
            ingredient_index = unc_ing['index']
            if ingredient_index < len(ingredients_copy):
                ingredients_copy[ingredient_index] = ingredients_copy[ingredient_index].copy()
                ingredients_copy[ingredient_index]['category'] = "Condiments & Spices"  # Safe fallback
        
        recipe_copy['ingredients'] = ingredients_copy
        return recipe_copy
        
    except Exception as e:
        print(f"   ⚠️  LLM categorization failed: {e}")
        # Return original recipe with fallback categories
        recipe_copy = recipe.copy()
        ingredients_copy = recipe_copy['ingredients'].copy()
        
        for unc_ing in uncategorized_ingredients:
            ingredient_index = unc_ing['index']
            if ingredient_index < len(ingredients_copy):
                ingredients_copy[ingredient_index] = ingredients_copy[ingredient_index].copy()
                ingredients_copy[ingredient_index]['category'] = "Condiments & Spices"  # Safe fallback
        
        recipe_copy['ingredients'] = ingredients_copy
        return recipe_copy