"""
Time Processor Simple - Ultra-lean time parsing for recipe data
Converts raw time data to structured, app-ready format.

PURE REGEX PIPELINE (NO LLM CALLS):
1. Format Detection: Handle ISO 8601 (PT40M) vs plain numbers (50)
2. Time Extraction: Extract minutes from various formats
3. Field Normalization: Convert cook_time/prep_time to cookTime/prepTime
4. Ready Time Calculation: Calculate total readyInMinutes

Performance optimized: NO API calls, fully parallel processing capable
Input: Raw recipe dict → Output: Recipe dict with normalized time fields
"""

import re
from typing import Dict, Union, Any


class TimeProcessorSimple:
    """
    Simplified time processor - lean and focused.
    Only processes timing: raw time data in → structured time fields out.
    """
    
    def __init__(self):
        """Initialize processor with time parsing patterns."""
        
        # Regex patterns for extracting time values
        self.time_patterns = [
            # ISO 8601 duration format: PT40M, PT1H30M, PT2H
            r'PT(?:(\d+)H)?(?:(\d+)M)?',
            # Plain number: 40, 50, 65
            r'^(\d+)$',
            # Number with units: "40 minutes", "1 hour", "2 hrs"
            r'(\d+)\s*(?:minutes?|mins?|m)',
            r'(\d+)\s*(?:hours?|hrs?|h)',
            # Fractional: "1.5 hours", "0.5 hour"
            r'(\d+\.?\d*)\s*(?:hours?|hrs?|h)'
        ]


    def process_time_fields(self, recipe: Dict) -> Dict:
        """
        Main entry point: Process recipe time fields into app-ready format.
        
        Args:
            recipe: Recipe dict with raw time fields
            
        Returns:
            Recipe dict with normalized time fields
        """
        if not recipe:
            return recipe
        
        try:
            # Extract raw time values
            raw_cook_time = recipe.get('cook_time', '')
            raw_prep_time = recipe.get('prep_time', '')
            raw_total_time = recipe.get('total_time', '')
            
            # Parse time values to minutes
            cook_minutes = self._parse_time_to_minutes(raw_cook_time)
            prep_minutes = self._parse_time_to_minutes(raw_prep_time)
            total_minutes = self._parse_time_to_minutes(raw_total_time)
            
            # Calculate readyInMinutes if not explicitly provided
            ready_minutes = total_minutes
            if not ready_minutes and (cook_minutes or prep_minutes):
                ready_minutes = (cook_minutes or 0) + (prep_minutes or 0)
            
            # Create updated recipe with normalized fields
            updated_recipe = recipe.copy()
            
            # Add app-ready time fields (camelCase for consistency)
            if cook_minutes:
                updated_recipe['cookTime'] = cook_minutes
            if prep_minutes:
                updated_recipe['prepTime'] = prep_minutes
            if ready_minutes:
                updated_recipe['readyInMinutes'] = ready_minutes
                updated_recipe['totalTime'] = ready_minutes
            
            return updated_recipe
            
        except Exception as e:
            print(f"   ⚠️ Time processing failed: {e}")
            return recipe


    def _parse_time_to_minutes(self, time_value: Union[str, int, None]) -> Union[int, None]:
        """Parse various time formats to minutes."""
        if not time_value:
            return None
        
        # Convert to string for processing
        time_str = str(time_value).strip()
        if not time_str:
            return None
        
        # Try different parsing patterns
        
        # Pattern 1: ISO 8601 duration (PT40M, PT1H30M)
        iso_match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', time_str, re.IGNORECASE)
        if iso_match:
            hours = int(iso_match.group(1) or 0)
            minutes = int(iso_match.group(2) or 0)
            return hours * 60 + minutes
        
        # Pattern 2: Plain number (assume minutes)
        number_match = re.match(r'^(\d+)$', time_str)
        if number_match:
            return int(number_match.group(1))
        
        # Pattern 3: Number with "minutes" unit
        minutes_match = re.search(r'(\d+)\s*(?:minutes?|mins?|m)', time_str, re.IGNORECASE)
        if minutes_match:
            return int(minutes_match.group(1))
        
        # Pattern 4: Number with "hours" unit
        hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)', time_str, re.IGNORECASE)
        if hours_match:
            hours = float(hours_match.group(1))
            return int(hours * 60)
        
        # Pattern 5: Try to extract any number (fallback)
        fallback_match = re.search(r'(\d+)', time_str)
        if fallback_match:
            return int(fallback_match.group(1))
        
        return None


# Main function for external use
def process_time_simple(recipe: Dict) -> Dict:
    """
    Process recipe time fields into structured format using pure regex parsing.
    
    Args:
        recipe: Recipe dict with raw time fields
        
    Returns:
        Recipe dict with normalized time fields
    """
    processor = TimeProcessorSimple()
    return processor.process_time_fields(recipe)