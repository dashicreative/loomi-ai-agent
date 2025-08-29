"""
Recipe Search Stages Module

This module contains all the modularized stages of the recipe discovery pipeline.
Each stage is responsible for a specific part of the recipe search and processing flow.
"""

# Import all stages for easy access
from . import (
    stage_1_web_search,
    stage_2_url_ranking,
    stage_3_url_classification,
    stage_4_recipe_parsing,
    stage_5_nutrition_normalization,
    stage_6_requirements_verification,
    stage_7_relevance_ranking,
    stage_8_list_processing,
    stage_9_final_formatting,
)

__all__ = [
    'stage_1_web_search',
    'stage_2_url_ranking',
    'stage_3_url_classification',
    'stage_4_recipe_parsing',
    'stage_5_nutrition_normalization',
    'stage_6_requirements_verification',
    'stage_7_relevance_ranking',
    'stage_8_list_processing',
    'stage_9_final_formatting',
]