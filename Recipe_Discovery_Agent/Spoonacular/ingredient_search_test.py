#!/usr/bin/env python3

import requests
import json
import os
from typing import Optional, Dict, Any

def search_ingredient(ingredient_name: str, api_key: str) -> Optional[str]:
    """
    Search for an ingredient using Spoonacular API and return its URL.
    
    Args:
        ingredient_name: Name of the ingredient to search for
        api_key: Spoonacular API key
        
    Returns:
        URL string if ingredient found, None otherwise
    """
    base_url = "https://api.spoonacular.com/food/ingredients/search"
    
    params = {
        "query": ingredient_name,
        "number": 1,
        "apiKey": api_key
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("results") and len(data["results"]) > 0:
            ingredient = data["results"][0]
            ingredient_id = ingredient.get("id")
            ingredient_name = ingredient.get("name")
            
            # Create ingredient detail URL
            ingredient_url = f"https://spoonacular.com/ingredients/{ingredient_id}-{ingredient_name.replace(' ', '-').lower()}"
            
            print(f"Found ingredient: {ingredient['name']}")
            print(f"Ingredient ID: {ingredient_id}")
            return ingredient_url
        else:
            print(f"No ingredients found for: {ingredient_name}")
            return None
            
    except requests.RequestException as e:
        print(f"API request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse API response: {e}")
        return None

def main():
    """
    Interactive ingredient search tool.
    """
    print("=== Spoonacular Ingredient Search Test ===")
    print("This tool searches for ingredients and returns their Spoonacular URLs.")
    print()
    
    # Check for API key
    api_key = os.getenv("SPOONACULAR_API_KEY")
    if not api_key:
        print("ERROR: SPOONACULAR_API_KEY environment variable not set.")
        print("Please set your API key with: export SPOONACULAR_API_KEY='your_key_here'")
        print("Get your API key at: https://spoonacular.com/food-api/console")
        return
    
    print("Enter ingredient names to search (press Ctrl+C to exit)")
    print("-" * 50)
    
    try:
        while True:
            ingredient_name = input("\nEnter ingredient name: ").strip()
            
            if not ingredient_name:
                print("Please enter a valid ingredient name.")
                continue
                
            print(f"Searching for: {ingredient_name}")
            
            ingredient_url = search_ingredient(ingredient_name, api_key)
            
            if ingredient_url:
                print(f"Ingredient URL: {ingredient_url}")
            else:
                print("No URL found for this ingredient.")
                
    except KeyboardInterrupt:
        print("\n\nExiting ingredient search. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")

if __name__ == "__main__":
    main()