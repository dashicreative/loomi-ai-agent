"""
Dependencies for Macro Calculation Agent
Handles shared resources like USDA API client, unit conversions, and session state.
"""

import os
import httpx
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MacroDeps:
    """
    Dependency container for macro calculation agent.
    Shares resources across all tools and maintains session state.
    """
    
    # HTTP client for API calls
    http_client: httpx.AsyncClient
    
    # USDA API configuration
    usda_api_key: Optional[str] = None
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    
    # Google Custom Search API (for web nutrition fallback)
    google_api_key: Optional[str] = None
    google_search_engine_id: Optional[str] = None
    
    # Session cache for looked-up ingredients (avoid duplicate API calls)
    ingredient_cache: Dict[str, dict] = None
    
    # Unit conversion tables (common cooking conversions)
    volume_to_grams: Dict[str, float] = None
    weight_conversions: Dict[str, float] = None
    
    def __post_init__(self):
        """Initialize default values and conversion tables"""
        if self.ingredient_cache is None:
            self.ingredient_cache = {}
            
        if self.volume_to_grams is None:
            # Common ingredient density conversions (1 cup = X grams)
            self.volume_to_grams = {
                # Flours & Grains (dry)
                "flour": 120,  # all-purpose flour
                "all-purpose flour": 120,
                "wheat flour": 120,
                "bread flour": 127,
                "cake flour": 114,
                "oats": 80,    # dry old-fashioned oats
                "oat": 80,
                "rolled oats": 80,
                "old-fashioned oats": 80,
                "quick oats": 80,
                "rice": 185,   # cooked rice
                "quinoa": 170,  # cooked
                "cornmeal": 138,

                # Sugars
                "sugar": 200,  # granulated white sugar
                "white sugar": 200,
                "granulated sugar": 200,
                "brown sugar": 220,  # packed
                "dark brown sugar": 220,
                "light brown sugar": 220,
                "powdered sugar": 120,
                "confectioners sugar": 120,
                "honey": 340,
                "maple syrup": 315,

                # Fats
                "butter": 227,  # 1 cup = 2 sticks
                "oil": 220,     # vegetable/canola oil
                "olive oil": 216,
                "coconut oil": 218,

                # Liquids
                "water": 240,
                "milk": 240,
                "cream": 240,
                "yogurt": 245,
                "sour cream": 230,

                # Nuts & Seeds
                "almond": 140,
                "walnut": 120,
                "pecan": 110,
                "peanut": 145,
                "cashew": 130,

                # Other
                "cocoa powder": 85,
                "chocolate chips": 170,
                "peanut butter": 250,
            }
            
        if self.weight_conversions is None:
            # Weight unit conversions to grams
            self.weight_conversions = {
                "g": 1.0,
                "gram": 1.0,
                "grams": 1.0,
                "kg": 1000.0,
                "kilogram": 1000.0,
                "kilograms": 1000.0,
                "oz": 28.35,
                "ounce": 28.35,
                "ounces": 28.35,
                "lb": 453.59,
                "lbs": 453.59,
                "pound": 453.59,
                "pounds": 453.59,
            }


def create_macro_deps() -> MacroDeps:
    """
    Factory function to create MacroDeps with HTTP client and API credentials.
    Call this when starting the agent.
    """
    return MacroDeps(
        http_client=httpx.AsyncClient(timeout=30.0),
        ingredient_cache={},
        # Load USDA API key from environment
        usda_api_key=os.getenv('USDA_API_KEY'),  # Optional - works without key but with rate limits
        # Load Google Custom Search credentials
        google_api_key=os.getenv('GOOGLE_API_KEY'),  # Required for web fallback
        google_search_engine_id=os.getenv('GOOGLE_SEARCH_ENGINE_ID'),  # Required for web fallback
    )