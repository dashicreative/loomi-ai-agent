"""
Main recipe parser entry point.
Provides unified interface to the modular parsing system.
"""

from .coordination.hybrid_coordinator import hybrid_recipe_parser


async def parse_recipe(url: str, openai_key: str = None) -> dict:
    """
    Main entry point for recipe parsing.
    
    Args:
        url: Recipe URL to parse
        openai_key: OpenAI API key for processing
        
    Returns:
        Dict with recipe data or error information
    """
    return await hybrid_recipe_parser(url, openai_key)