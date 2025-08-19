from dataclasses import dataclass


@dataclass
class RecipeDeps:
    """Dependencies for the Recipe Discovery Agent"""
    api_key: str  # Spoonacular API key