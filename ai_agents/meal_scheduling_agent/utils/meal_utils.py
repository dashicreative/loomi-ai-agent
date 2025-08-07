"""
Meal Utilities - Meal selection and matching logic
"""

import random
from typing import List, Optional, Dict
from difflib import SequenceMatcher


class MealUtils:
    """
    Utilities for meal selection, matching, and randomization
    """
    
    @staticmethod
    def select_random_meals(available_meals: List[str], count: int = 1) -> List[str]:
        """
        Select random meals from available options
        
        Args:
            available_meals: List of available meal names
            count: Number of random meals to select
            
        Returns:
            List of randomly selected meal names
        """
        if not available_meals:
            return []
        
        # Ensure we don't try to select more meals than available
        count = min(count, len(available_meals))
        
        return random.sample(available_meals, count)
    
    @staticmethod
    def find_meal_by_name(meal_name: str, available_meals: List[str], 
                         threshold: float = 0.6) -> Optional[str]:
        """
        Find a meal by name with fuzzy matching
        
        Args:
            meal_name: The meal name to search for
            available_meals: List of available meal names
            threshold: Similarity threshold (0-1)
            
        Returns:
            Best matching meal name or None if no good match
        """
        if not meal_name or not available_meals:
            return None
        
        meal_name_lower = meal_name.lower().strip()
        
        # First try exact match
        for meal in available_meals:
            if meal.lower() == meal_name_lower:
                return meal
        
        # Then try fuzzy matching
        best_match = None
        best_score = 0
        
        for meal in available_meals:
            score = SequenceMatcher(None, meal_name_lower, meal.lower()).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = meal
        
        return best_match
    
    @staticmethod
    def suggest_alternatives(requested_meal: str, available_meals: List[str], 
                           max_suggestions: int = 3) -> List[str]:
        """
        Suggest alternative meals when requested meal is not found
        
        Args:
            requested_meal: The meal that wasn't found
            available_meals: List of available meal names
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested meal names
        """
        if not available_meals:
            return []
        
        # For now, return random suggestions
        # In future, could use similarity scoring or meal categories
        suggestions = MealUtils.select_random_meals(available_meals, max_suggestions)
        
        return suggestions
    
    @staticmethod
    def extract_meal_type(request: str) -> str:
        """
        Extract meal type from request string
        
        Args:
            request: User request string
            
        Returns:
            Meal type (breakfast, lunch, dinner, or snack)
        """
        request_lower = request.lower()
        
        if "breakfast" in request_lower:
            return "breakfast"
        elif "lunch" in request_lower:
            return "lunch"
        elif "dinner" in request_lower:
            return "dinner"
        elif "snack" in request_lower:
            return "snack"
        else:
            # Default to dinner if not specified
            return "dinner"
    
    @staticmethod
    def parse_meal_count(request: str) -> Optional[int]:
        """
        Extract number of meals from request
        
        Args:
            request: User request string
            
        Returns:
            Number of meals or None if not specified
        """
        request_lower = request.lower()
        
        # Check for specific numbers
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        
        for word, num in number_words.items():
            if word in request_lower:
                return num
        
        # Check for digits
        words = request_lower.split()
        for word in words:
            if word.isdigit():
                return int(word)
        
        # Check for vague quantities
        if any(word in request_lower for word in ["a few", "some", "several"]):
            return 3  # Default to 3 for vague quantities
        
        return None