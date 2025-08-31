"""
Recipe Search Tool Module

Modular recipe search system with pipeline stages, batch processing, and domain filtering.
"""

from .batch_processor import search_and_process_recipes_tool

__all__ = ['search_and_process_recipes_tool']