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
            # Common ingredient density conversions (approximate)
            self.volume_to_grams = {
                "flour": 120,  # 1 cup flour = ~120g
                "sugar": 200,  # 1 cup sugar = ~200g
                "water": 240,  # 1 cup water = 240g
                "milk": 240,   # 1 cup milk = ~240g
                "oil": 220,    # 1 cup oil = ~220g
                "rice": 185,   # 1 cup cooked rice = ~185g
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