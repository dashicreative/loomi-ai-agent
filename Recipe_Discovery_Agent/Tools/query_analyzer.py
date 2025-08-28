"""
Stage 1: Query Analysis and Requirement Extraction

Parses user queries to extract hard requirements for recipe filtering.
This is a helper for the LLM ranking stage - provides structured requirements
but does NOT filter recipes itself.
"""

import re
from typing import Dict, List, Any, Union, Callable
from .query_patterns import (
    NUTRITION_PATTERNS,
    ALLERGY_PATTERNS, 
    DIETARY_PATTERNS,
    RELIGIOUS_DIETARY_PATTERNS,
    TIME_PATTERNS,
    COOKING_METHOD_PATTERNS,
    MEAL_TYPE_PATTERNS,
    SERVING_PATTERNS,
    SPECIAL_DIETARY_COMBINATIONS
)


class QueryAnalyzer:
    """Extracts structured requirements from recipe search queries."""
    
    def __init__(self):
        self.extracted_requirements = {}
        
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze a query and extract all hard requirements.
        
        Args:
            query: User's search query (e.g., "breakfast with 30g protein gluten-free")
            
        Returns:
            Dict containing extracted requirements:
            {
                "nutrition": {"protein": {"min": 30}},
                "exclude_ingredients": ["wheat", "flour"],
                "meal_type": "breakfast",
                "dietary_restrictions": ["gluten-free"],
                "success": True,
                "extracted_patterns": ["30g protein", "gluten-free", "breakfast"]
            }
        """
        try:
            query_lower = query.lower()
            self.extracted_requirements = {
                "success": True,
                "extracted_patterns": [],
                "error": None
            }
            
            # Extract nutrition requirements
            self._extract_nutrition_requirements(query_lower)
            
            # Extract ingredient exclusions (allergies + dietary restrictions)
            self._extract_ingredient_exclusions(query_lower)
            
            # Extract cooking constraints
            self._extract_cooking_constraints(query_lower)
            
            # Extract meal type
            self._extract_meal_type(query_lower)
            
            # Extract serving requirements
            self._extract_serving_requirements(query_lower)
            
            # Handle special dietary combinations
            self._extract_special_dietary_requirements(query_lower)
            
            # Clean up and return
            return self._finalize_requirements()
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "extracted_patterns": [],
                "fallback_to_llm": True
            }
    
    def _extract_nutrition_requirements(self, query: str):
        """Extract nutrition thresholds from query."""
        nutrition_reqs = {}
        
        for pattern, requirement in NUTRITION_PATTERNS.items():
            if isinstance(requirement, dict):
                # Static requirement
                if re.search(pattern, query):
                    self.extracted_requirements["extracted_patterns"].append(pattern)
                    nutrition_reqs.update(requirement)
            else:
                # Dynamic requirement (function)
                match = re.search(pattern, query)
                if match:
                    self.extracted_requirements["extracted_patterns"].append(match.group(0))
                    nutrition_reqs.update(requirement(match))
        
        if nutrition_reqs:
            self.extracted_requirements["nutrition"] = nutrition_reqs
    
    def _extract_ingredient_exclusions(self, query: str):
        """Extract ingredients to exclude based on allergies and dietary restrictions."""
        exclude_ingredients = []
        dietary_restrictions = []
        
        # Check allergy patterns
        for pattern, ingredients in ALLERGY_PATTERNS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                exclude_ingredients.extend(ingredients)
                dietary_restrictions.append(pattern.replace(r"\\", "").replace("?", "").replace("-", " "))
        
        # Check dietary restriction patterns
        for pattern, ingredients in DIETARY_PATTERNS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                exclude_ingredients.extend(ingredients)
                dietary_restrictions.append(pattern.replace(r"\\", "").replace("?", "").replace("-", " "))
        
        # Check religious dietary patterns
        for pattern, ingredients in RELIGIOUS_DIETARY_PATTERNS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                exclude_ingredients.extend(ingredients)
                dietary_restrictions.append(pattern.replace(r"\\", "").replace("?", "").replace("-", " "))
        
        if exclude_ingredients:
            self.extracted_requirements["exclude_ingredients"] = list(set(exclude_ingredients))
        if dietary_restrictions:
            self.extracted_requirements["dietary_restrictions"] = list(set(dietary_restrictions))
    
    def _extract_cooking_constraints(self, query: str):
        """Extract time and cooking method constraints."""
        cooking_constraints = {}
        
        # Time constraints
        for pattern, requirement in TIME_PATTERNS.items():
            if isinstance(requirement, dict):
                if re.search(pattern, query):
                    self.extracted_requirements["extracted_patterns"].append(pattern)
                    cooking_constraints.update(requirement)
            else:
                match = re.search(pattern, query)
                if match:
                    self.extracted_requirements["extracted_patterns"].append(match.group(0))
                    cooking_constraints.update(requirement(match))
        
        # Cooking method constraints
        for pattern, requirement in COOKING_METHOD_PATTERNS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                cooking_constraints.update(requirement)
        
        if cooking_constraints:
            self.extracted_requirements["cooking_constraints"] = cooking_constraints
    
    def _extract_meal_type(self, query: str):
        """Extract meal type from query."""
        for pattern, meal_type in MEAL_TYPE_PATTERNS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                self.extracted_requirements["meal_type"] = meal_type
                break  # Only take first match
    
    def _extract_serving_requirements(self, query: str):
        """Extract serving size requirements."""
        serving_reqs = {}
        
        for pattern, requirement in SERVING_PATTERNS.items():
            if isinstance(requirement, dict):
                if re.search(pattern, query):
                    self.extracted_requirements["extracted_patterns"].append(pattern)
                    serving_reqs.update(requirement)
            else:
                match = re.search(pattern, query)
                if match:
                    self.extracted_requirements["extracted_patterns"].append(match.group(0))
                    serving_reqs.update(requirement(match))
        
        if serving_reqs:
            self.extracted_requirements["serving_requirements"] = serving_reqs
    
    def _extract_special_dietary_requirements(self, query: str):
        """Handle special dietary combinations that need multiple constraints."""
        for pattern, requirements in SPECIAL_DIETARY_COMBINATIONS.items():
            if re.search(pattern, query):
                self.extracted_requirements["extracted_patterns"].append(pattern)
                
                # Merge requirements
                for key, value in requirements.items():
                    if key == "exclude_ingredients":
                        existing = self.extracted_requirements.get("exclude_ingredients", [])
                        self.extracted_requirements["exclude_ingredients"] = list(set(existing + value))
                    elif key in ["nutrition", "cooking_constraints", "serving_requirements"]:
                        existing = self.extracted_requirements.get(key, {})
                        existing.update(value)
                        self.extracted_requirements[key] = existing
                    else:
                        self.extracted_requirements[key] = value
    
    def _finalize_requirements(self) -> Dict[str, Any]:
        """Clean up and finalize the extracted requirements."""
        # Remove duplicates from extracted patterns
        self.extracted_requirements["extracted_patterns"] = list(set(self.extracted_requirements["extracted_patterns"]))
        
        # Add summary for LLM
        self.extracted_requirements["summary"] = self._create_summary()
        
        return self.extracted_requirements
    
    def _create_summary(self) -> str:
        """Create a human-readable summary of extracted requirements."""
        summary_parts = []
        
        if "nutrition" in self.extracted_requirements:
            nutrition = self.extracted_requirements["nutrition"]
            for nutrient, constraints in nutrition.items():
                if "min" in constraints:
                    summary_parts.append(f"Minimum {constraints['min']}g {nutrient}")
                if "max" in constraints:
                    summary_parts.append(f"Maximum {constraints['max']}g {nutrient}")
        
        if "exclude_ingredients" in self.extracted_requirements:
            ingredients = self.extracted_requirements["exclude_ingredients"]
            if len(ingredients) <= 3:
                summary_parts.append(f"Exclude: {', '.join(ingredients)}")
            else:
                summary_parts.append(f"Exclude: {', '.join(ingredients[:3])} and {len(ingredients)-3} more")
        
        if "meal_type" in self.extracted_requirements:
            summary_parts.append(f"Meal type: {self.extracted_requirements['meal_type']}")
        
        if "cooking_constraints" in self.extracted_requirements:
            constraints = self.extracted_requirements["cooking_constraints"]
            if "cook_time" in constraints:
                time_constraint = constraints["cook_time"]
                if "max" in time_constraint:
                    summary_parts.append(f"Max cooking time: {time_constraint['max']} minutes")
        
        if "dietary_restrictions" in self.extracted_requirements:
            restrictions = self.extracted_requirements["dietary_restrictions"]
            summary_parts.append(f"Dietary: {', '.join(restrictions[:3])}")
        
        return "; ".join(summary_parts) if summary_parts else "No specific requirements detected"


# Convenience function for easy integration
def analyze_query(query: str) -> Dict[str, Any]:
    """
    Analyze a recipe search query and extract requirements.
    
    Args:
        query: User's search query
        
    Returns:
        Dict with extracted requirements and metadata
    """
    analyzer = QueryAnalyzer()
    return analyzer.analyze_query(query)