"""
Recipe Quality Scorer for early exit optimization.
Evaluates recipe quality based on completeness, relevance, and data quality.
"""
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import re


@dataclass
class QualityScore:
    """Represents a recipe quality score with breakdown"""
    total_score: float
    completeness_score: float
    relevance_score: float
    data_quality_score: float
    has_required_data: bool
    details: Dict[str, float]


class RecipeQualityScorer:
    """Evaluates recipe quality for early exit decisions"""
    
    def __init__(self, priority_sites: List[str] = None):
        # Import priority sites from recipe_agent.Tools.py to maintain consistency  
        try:
            from .Tools import PRIORITY_SITES
        except ImportError:
            # Fallback if import fails (e.g., in testing)
            PRIORITY_SITES = [
                "allrecipes.com", "simplyrecipes.com", "eatingwell.com",
                "foodnetwork.com", "delish.com", "seriouseats.com",
                "foodandwine.com", "thepioneerwoman.com", "food.com",
                "epicurious.com"
            ]
        
        # Weight distribution for scoring (binary pass/fail not included)
        self.weights = {
            'relevance': 0.70,          # 70% - Matches user query
            'nutrition_quality': 0.13,   # 13% - Has nutrition data
            'other_data_quality': 0.02, # 2% - Timing, servings, etc.
            'priority_site': 0.15       # 15% - From trusted sites
        }
        
        # Required fields - BINARY pass/fail (must have ALL for app import)
        self.required_fields = ['title', 'image', 'ingredients', 'instructions']
        
        # Priority nutrition fields (main scoring factor for data quality)
        self.nutrition_fields = ['fat', 'carbs', 'protein', 'calories']
        
        # Other data fields (minor scoring factor)
        self.other_data_fields = ['cookTime', 'prepTime', 'servings', 'description']
        
        # Use priority sites from recipe_agent.Tools.py (maintains consistency)
        self.priority_sites = priority_sites or PRIORITY_SITES
    
    def score_recipe(self, recipe: Dict, query: str) -> QualityScore:
        """
        Score a recipe based on binary requirements, relevance, and quality factors.
        Returns QualityScore with total score and breakdown.
        """
        details = {}
        
        # BINARY CHECK: Must have all required fields or score = 0
        has_required_data = self._has_required_data(recipe)
        if not has_required_data:
            return QualityScore(
                total_score=0.0,
                completeness_score=0.0,
                relevance_score=0.0,
                data_quality_score=0.0,
                has_required_data=False,
                details={'rejected': 'missing_required_fields'}
            )
        
        # 1. Relevance Score (70%)
        relevance = self._score_relevance(recipe, query, details)
        
        # 2. Nutrition Data Quality (13%)
        nutrition_quality = self._score_nutrition_quality(recipe, details)
        
        # 3. Other Data Quality (2%)
        other_quality = self._score_other_data_quality(recipe, details)
        
        # 4. Priority Site Bonus (15%)
        site_bonus = self._score_priority_site(recipe, details)
        
        # Calculate weighted total
        total_score = (
            relevance * self.weights['relevance'] +
            nutrition_quality * self.weights['nutrition_quality'] +
            other_quality * self.weights['other_data_quality'] +
            site_bonus * self.weights['priority_site']
        )
        
        return QualityScore(
            total_score=min(total_score, 1.0),
            completeness_score=1.0,  # Passed binary check
            relevance_score=relevance,
            data_quality_score=nutrition_quality + other_quality,
            has_required_data=True,
            details=details
        )
    
    def _score_nutrition_quality(self, recipe: Dict, details: Dict[str, float]) -> float:
        """Score nutrition data quality (13% of total)"""
        nutrition_data = recipe.get('nutrition', {})
        if not nutrition_data:
            details['nutrition_present'] = 0.0
            return 0.0
        
        # Check for key nutrition fields
        nutrition_present = 0
        for field in self.nutrition_fields:
            if nutrition_data.get(field) is not None:
                nutrition_present += 1
        
        nutrition_score = nutrition_present / len(self.nutrition_fields)
        details['nutrition_present'] = nutrition_score
        
        return nutrition_score
    
    def _score_other_data_quality(self, recipe: Dict, details: Dict[str, float]) -> float:
        """Score other data quality (2% of total)"""
        score = 0.0
        
        # Check for other data fields
        other_data_present = 0
        for field in self.other_data_fields:
            if recipe.get(field) and len(str(recipe[field]).strip()) > 0:
                other_data_present += 1
        
        if self.other_data_fields:
            other_score = other_data_present / len(self.other_data_fields)
            details['other_data_present'] = other_score
            score = other_score
        
        return score
    
    def _score_priority_site(self, recipe: Dict, details: Dict[str, float]) -> float:
        """Score priority site bonus (15% of total)"""
        url = recipe.get('source_url', recipe.get('url', ''))
        
        if not url:
            details['priority_site'] = 0.0
            return 0.0
        
        # Check if URL is from a priority site
        url_lower = url.lower()
        for site in self.priority_sites:
            if site in url_lower:
                details['priority_site'] = 1.0
                details['priority_site_name'] = site
                return 1.0
        
        details['priority_site'] = 0.0
        return 0.0
    
    def _score_relevance(self, recipe: Dict, query: str, details: Dict[str, float]) -> float:
        """Score recipe relevance to query (70% of total)"""
        if not query:
            return 0.5  # Neutral score if no query
        
        score = 0.0
        query_words = set(query.lower().split())
        
        # Title relevance (40% of relevance)
        title = recipe.get('title', '').lower()
        if title:
            title_words = set(re.findall(r'\w+', title))
            title_overlap = len(query_words & title_words) / max(len(query_words), 1)
            details['title_overlap'] = title_overlap
            score += title_overlap * 0.4
        
        # Ingredient relevance (30% of relevance)
        ingredients = recipe.get('ingredients', [])
        if ingredients:
            ingredients_text = ' '.join(str(ing) for ing in ingredients).lower()
            ingredient_matches = sum(1 for word in query_words if word in ingredients_text)
            ingredient_score = min(ingredient_matches / max(len(query_words), 1), 1.0)
            details['ingredient_score'] = ingredient_score
            score += ingredient_score * 0.3
        
        # Description/instructions relevance (20% of relevance)
        text_fields = []
        for field in ['description', 'instructions', 'summary']:
            if recipe.get(field):
                text_fields.append(str(recipe[field]).lower())
        
        if text_fields:
            combined_text = ' '.join(text_fields)
            text_matches = sum(1 for word in query_words if word in combined_text)
            text_score = min(text_matches / max(len(query_words), 1), 1.0)
            details['text_relevance'] = text_score
            score += text_score * 0.2
        
        # Cuisine/category match (10% of relevance)
        category_fields = []
        for field in ['cuisine', 'category', 'tags', 'recipeCategory']:
            if recipe.get(field):
                category_fields.append(str(recipe[field]).lower())
        
        if category_fields:
            combined_categories = ' '.join(category_fields)
            category_matches = sum(1 for word in query_words if word in combined_categories)
            category_score = min(category_matches / max(len(query_words), 1), 1.0)
            details['category_relevance'] = category_score
            score += category_score * 0.1
        
        return min(score, 1.0)
    
    def _has_required_data(self, recipe: Dict) -> bool:
        """Check if recipe has minimum required data for app import"""
        # Must have ALL required fields: title, image, ingredients, instructions
        
        # 1. Title (recipe name)
        has_title = (
            recipe.get('title') and 
            len(str(recipe['title']).strip()) > 0
        )
        
        # 2. Image (main photo/thumbnail)
        has_image = (
            recipe.get('image') and 
            len(str(recipe['image']).strip()) > 0 and
            (str(recipe['image']).startswith('http') or str(recipe['image']).startswith('/'))
        )
        
        # 3. Ingredients
        has_ingredients = (
            recipe.get('ingredients') and 
            len(recipe['ingredients']) > 0 and
            any(len(str(ing).strip()) > 0 for ing in recipe['ingredients'])
        )
        
        # 4. Instructions
        has_instructions = (
            recipe.get('instructions') and
            len(str(recipe['instructions']).strip()) > 10  # At least basic instructions
        )
        
        return has_title and has_image and has_ingredients and has_instructions
    
    def batch_score_recipes(self, recipes: List[Dict], query: str) -> List[QualityScore]:
        """Score multiple recipes efficiently"""
        return [self.score_recipe(recipe, query) for recipe in recipes]
    
    def filter_by_quality(
        self, 
        recipes: List[Dict], 
        query: str, 
        min_score: float = 0.6,
        require_complete: bool = True
    ) -> List[Dict]:
        """Filter recipes by quality score"""
        scored_recipes = []
        
        for recipe in recipes:
            score = self.score_recipe(recipe, query)
            
            # Apply filters
            if score.total_score >= min_score:
                if not require_complete or score.has_required_data:
                    recipe_with_score = recipe.copy()
                    recipe_with_score['_quality_score'] = score.total_score
                    recipe_with_score['_quality_details'] = score.details
                    scored_recipes.append(recipe_with_score)
        
        # Sort by quality score (highest first)
        scored_recipes.sort(key=lambda r: r['_quality_score'], reverse=True)
        
        return scored_recipes