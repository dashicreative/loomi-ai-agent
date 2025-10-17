import os
import json
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)  # Force reload of .env file

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")

INGREDIENT_CATEGORIES = [
    "Poultry", "Fish", "Vegetable", "Spice", "Oil", "Grain", 
    "Fruit", "Condiment", "Shellfish", "Baking Ingredient", 
    "Nut/Seed", "Plant Protein", "Legume", "Lamb", "Frozen",
    "Beverage", "Specialty Ingredient", "Beef", "Seasoning Mix",
    "Pork", "Dairy", "International/Ethnic", "Pasta", "Sauce",
    "Sweetener", "Flour", "Canned Good", "Pickled/Fermented", 
    "Herb", "Game Meat", "Spread", "Bread/Grain Product", 
    "Dried Fruit/Nut", "Vinegar/Acid"
]

CATEGORY_IMAGE_BASE = "https://pub-4559f4553008447b97be2209a19f3b75.r2.dev/categories/"

CATEGORY_IMAGES = {
    "Poultry": f"{CATEGORY_IMAGE_BASE}poultry_Category.jpg",
    "Fish": f"{CATEGORY_IMAGE_BASE}fish.jpg",
    "Vegetable": f"{CATEGORY_IMAGE_BASE}vegetables.jpg",
    "Spice": f"{CATEGORY_IMAGE_BASE}Spice.jpg",
    "Oil": f"{CATEGORY_IMAGE_BASE}oil.jpg",
    "Grain": f"{CATEGORY_IMAGE_BASE}grain.jpg",
    "Fruit": f"{CATEGORY_IMAGE_BASE}fruit.jpg",
    "Condiment": f"{CATEGORY_IMAGE_BASE}condiments.jpg",
    "Shellfish": f"{CATEGORY_IMAGE_BASE}shellfish.jpg",
    "Baking Ingredient": f"{CATEGORY_IMAGE_BASE}baking.jpg",
    "Nut/Seed": f"{CATEGORY_IMAGE_BASE}Nut%3ASeed.jpg",
    "Plant Protein": f"{CATEGORY_IMAGE_BASE}plantprotein.jpg",
    "Legume": f"{CATEGORY_IMAGE_BASE}legume.jpg",
    "Lamb": f"{CATEGORY_IMAGE_BASE}lamb.jpg",
    "Frozen": f"{CATEGORY_IMAGE_BASE}frozen_food.jpg",
    "Beverage": f"{CATEGORY_IMAGE_BASE}beverage.jpg",
    "Specialty Ingredient": f"{CATEGORY_IMAGE_BASE}Specialty_ingredient.jpg",
    "Beef": f"{CATEGORY_IMAGE_BASE}Beef_Category.jpg",
    "Pork": f"{CATEGORY_IMAGE_BASE}pork_Category.jpg",
    "Dairy": f"{CATEGORY_IMAGE_BASE}dairy.jpg",
    "Herb": f"{CATEGORY_IMAGE_BASE}herb.jpg",
    "Canned Good": f"{CATEGORY_IMAGE_BASE}canned_good.jpg"
}

client = OpenAI(api_key=OPENAI_API_KEY)

async def validate_food_item(ingredient_name: str) -> Tuple[bool, str]:
    """Validate if the input is actually a food item"""
    
    validation_prompt = f"""Determine if "{ingredient_name}" is an edible food item or ingredient that would be used in cooking/meal preparation.

    Consider:
    - Is this something people eat or drink?
    - Is this a cooking ingredient (spices, oils, etc)?
    - Is this a food product or beverage?
    
    Non-food examples: broom, dirt, plastic, metal, cleaning products, furniture, electronics, etc.
    
    Respond with ONLY a JSON object:
    {{"is_food": boolean, "message": "string"}}
    
    If not food, the message should explain why (e.g., "This is a cleaning tool, not a food item")
    If it is food, the message should be "Valid food item"
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a food validation expert. Respond only with valid JSON."},
                {"role": "user", "content": validation_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("is_food", False), result.get("message", "Unable to validate")
    except Exception as e:
        print(f"Validation error: {e}")
        return False, "Error during validation"

async def search_nutrition_data(ingredient_name: str) -> Dict:
    """Search web for nutritional information using OpenAI"""
    
    prompt = f"""For the food ingredient "{ingredient_name}", provide accurate nutritional information per 100 grams (or 100ml if liquid).
    
    Use your knowledge of common food databases and nutritional information to provide:
    1. Calories per 100g/100ml
    2. Carbohydrates in grams per 100g/100ml  
    3. Protein in grams per 100g/100ml
    4. Fat in grams per 100g/100ml
    5. Whether this is typically measured as solid (false) or liquid (true)
    6. The most appropriate category from: {', '.join(INGREDIENT_CATEGORIES)}
    
    Respond with ONLY a JSON object, no other text:
    {{"calories": number, "carbs_g": number, "protein_g": number, "fat_g": number, "is_liquid": boolean, "category": "string"}}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a nutrition expert. Respond only with valid JSON, no additional text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        return {
            "calories": float(result.get("calories", 0)),
            "carbs_g": float(result.get("carbs_g", 0)),
            "protein_g": float(result.get("protein_g", 0)),
            "fat_g": float(result.get("fat_g", 0)),
            "per_100": "ml" if result.get("is_liquid", False) else "g",
            "category": result.get("category", "Specialty Ingredient")
        }
    except Exception as e:
        print(f"Error fetching nutrition data: {e}")
        print(f"Response content: {response.choices[0].message.content if 'response' in locals() else 'No response'}")
        return {
            "calories": 0,
            "carbs_g": 0,
            "protein_g": 0,
            "fat_g": 0,
            "per_100": "g",
            "category": "Specialty Ingredient"
        }

async def get_spoonacular_image(ingredient_name: str) -> Tuple[bool, str]:
    """Fetch ingredient image URL from Spoonacular API"""
    
    base_url = "https://api.spoonacular.com/food/ingredients/search"
    params = {
        "apiKey": SPOONACULAR_API_KEY,
        "query": ingredient_name,
        "number": 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results") and len(data["results"]) > 0:
                        image_name = data["results"][0].get("image", "")
                        if image_name:
                            image_url = f"https://img.spoonacular.com/ingredients_250x250/{image_name}"
                            return True, image_url
    except Exception as e:
        print(f"Spoonacular API error: {e}")
    
    return False, ""

async def process_ingredient(ingredient_name: str) -> Dict:
    """Main function to process ingredient and return all required data"""
    
    # First validate if it's actually a food item
    is_food, validation_message = await validate_food_item(ingredient_name)
    
    if not is_food:
        return {
            "success": False,
            "error": "NOT_FOOD_ITEM",
            "message": validation_message,
            "ingredient_name": ingredient_name
        }
    
    # If it's valid food, run both tasks in parallel
    nutrition_task = asyncio.create_task(search_nutrition_data(ingredient_name))
    image_task = asyncio.create_task(get_spoonacular_image(ingredient_name))
    
    # Wait for both to complete
    nutrition_data = await nutrition_task
    image_hit, image_url = await image_task
    
    # Get category image URL (default to Specialty Ingredient if not found)
    category = nutrition_data["category"]
    category_image_url = CATEGORY_IMAGES.get(
        category, 
        CATEGORY_IMAGES.get("Specialty Ingredient", "")
    )
    
    return {
        "success": True,
        "ingredient_name": ingredient_name,
        "nutrition": {
            "calories": nutrition_data["calories"],
            "carbs_g": nutrition_data["carbs_g"],
            "protein_g": nutrition_data["protein_g"],
            "fat_g": nutrition_data["fat_g"],
            "per_100": nutrition_data["per_100"]
        },
        "category": category,
        "category_image_url": category_image_url,
        "spoonacular_image_hit": image_hit,
        "image_url": image_url
    }