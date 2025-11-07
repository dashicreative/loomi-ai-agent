"""
Nutrition Processor Simple - Ultra-lean nutrition parsing for recipe data
Converts raw nutrition data to structured, app-ready format.

PURE REGEX PIPELINE (NO LLM CALLS):
1. Format Detection: Handle JSON-LD arrays vs recipe-scrapers dicts
2. Enhanced Regex Parsing: Extract numeric values from various formats
3. Standardization: Output consistent numeric nutrition object

Performance optimized: NO API calls, fully parallel processing capable
Input: Raw nutrition data (list, dict, or None) → Output: Structured nutrition object
"""

import re
from typing import Dict, List, Union, Any


class NutritionProcessorSimple:
    """
    Simplified nutrition processor - lean and focused.
    Only processes nutrition: raw data in → structured objects out.
    """
    
    def __init__(self):
        """Initialize processor with regex patterns."""
        
        # Regex patterns for extracting nutrition values
        self.nutrition_patterns = {
            'calories': [
                r'(\d+(?:\.\d+)?)\s*(?:kcal|calories)',
                r'(\d+(?:\.\d+)?)\s*cal(?:ories)?'
            ],
            'protein': [
                r'(\d+(?:\.\d+)?)\s*g\s*protein',
                r'(\d+(?:\.\d+)?)\s*grams?\s*protein'
            ],
            'fat': [
                r'(\d+(?:\.\d+)?)\s*g\s*fat',
                r'(\d+(?:\.\d+)?)\s*grams?\s*fat',
                r'(\d+(?:\.\d+)?)\s*g\s*total\s*fat'
            ],
            'carbs': [
                r'(\d+(?:\.\d+)?)\s*g\s*carbs?',
                r'(\d+(?:\.\d+)?)\s*grams?\s*carbs?',
                r'(\d+(?:\.\d+)?)\s*g\s*carbohydrates?'
            ],
            'fiber': [
                r'(\d+(?:\.\d+)?)\s*g\s*fiber',
                r'(\d+(?:\.\d+)?)\s*grams?\s*fiber',
                r'(\d+(?:\.\d+)?)\s*g\s*dietary\s*fiber'
            ],
            'sugar': [
                r'(\d+(?:\.\d+)?)\s*g\s*sugar',
                r'(\d+(?:\.\d+)?)\s*grams?\s*sugar',
                r'(\d+(?:\.\d+)?)\s*g\s*total\s*sugar'
            ],
            'sodium': [
                r'(\d+(?:\.\d+)?)\s*mg\s*sodium',
                r'(\d+(?:\.\d+)?)\s*milligrams?\s*sodium',
                r'(\d+(?:\.\d+)?)\s*g\s*sodium'
            ]
        }


    def process_nutrition(self, nutrition_data: Union[List, Dict, None]) -> Dict:
        """
        Main entry point: Process raw nutrition data into structured format.
        
        Args:
            nutrition_data: Raw nutrition data (list, dict, or None)
            
        Returns:
            Structured nutrition object with numeric values
        """
        if not nutrition_data:
            return self._create_default_nutrition()
        
        try:
            if isinstance(nutrition_data, list):
                # JSON-LD format: ['209 kcal calories', '3 g protein', '9 g fat', '29 g carbs']
                return self._process_array_format(nutrition_data)
            elif isinstance(nutrition_data, dict):
                # Recipe-scrapers format: {'calories': '339 kcal', 'protein': '5g'}
                return self._process_dict_format(nutrition_data)
            else:
                # Unknown format
                return self._create_default_nutrition()
                
        except Exception as e:
            print(f"   ⚠️ Nutrition processing failed: {e}")
            return self._create_default_nutrition()


    def _process_array_format(self, nutrition_list: List[str]) -> Dict:
        """Process JSON-LD array format nutrition data."""
        nutrition_result = self._create_default_nutrition()
        
        # Combine all nutrition strings into one text for parsing
        combined_text = ' '.join(str(item) for item in nutrition_list).lower()
        
        # Extract values using regex patterns
        for nutrient, patterns in self.nutrition_patterns.items():
            value = self._extract_value_from_text(combined_text, patterns)
            if value is not None:
                nutrition_result[nutrient] = value
        
        return nutrition_result


    def _process_dict_format(self, nutrition_dict: Dict) -> Dict:
        """Process recipe-scrapers dictionary format nutrition data."""
        nutrition_result = self._create_default_nutrition()
        
        # Process each key-value pair in the dictionary
        for key, value in nutrition_dict.items():
            key_lower = key.lower()
            value_str = str(value).lower()
            
            # Direct key matching
            if 'calorie' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['calories'] = extracted
            elif 'protein' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['protein'] = extracted
            elif 'fat' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['fat'] = extracted
            elif 'carb' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['carbs'] = extracted
            elif 'fiber' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['fiber'] = extracted
            elif 'sugar' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['sugar'] = extracted
            elif 'sodium' in key_lower:
                extracted = self._extract_numeric_value(value_str)
                if extracted is not None:
                    nutrition_result['sodium'] = extracted
        
        return nutrition_result


    def _extract_value_from_text(self, text: str, patterns: List[str]) -> Union[float, None]:
        """Extract numeric value from text using regex patterns."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None


    def _extract_numeric_value(self, value_str: str) -> Union[float, None]:
        """Extract first numeric value from a string."""
        # Simple regex to find first number (integer or decimal)
        match = re.search(r'(\d+(?:\.\d+)?)', value_str)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None


    def _create_default_nutrition(self) -> Dict:
        """Create default nutrition structure when no data is available."""
        return {
            "calories": 0,
            "protein": 0,
            "fat": 0,
            "carbs": 0,
            "fiber": 0,
            "sugar": 0,
            "sodium": 0
        }


# Main function for external use
def process_nutrition_simple(nutrition_data: Union[List, Dict, None]) -> Dict:
    """
    Process nutrition data into structured format using pure regex parsing.
    
    Args:
        nutrition_data: Raw nutrition data (list, dict, or None)
        
    Returns:
        Structured nutrition object with numeric values
    """
    processor = NutritionProcessorSimple()
    return processor.process_nutrition(nutrition_data)