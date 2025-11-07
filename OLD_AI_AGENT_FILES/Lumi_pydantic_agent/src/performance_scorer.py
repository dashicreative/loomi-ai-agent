"""
AgentPerformanceScorer - Three Pillar Performance Tracking
Tracks Speed, Quality, and Accuracy scores for both tactical and strategic intelligence.
"""

import time
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class OverallSearchScore:
    """Overall performance score for a complete search operation."""
    speed: float  # 0-100
    quality: float  # 0-100  
    accuracy: float  # 0-100
    overall: float  # 0-100 weighted
    search_time: float  # actual elapsed seconds
    recipes_found: int
    constraints_identified: List[str]
    constraints_met: List[str]


@dataclass  
class IndividualRecipeScore:
    """Performance score for a single recipe."""
    recipe_url: str
    site_domain: str
    quality_score: float  # 0-100 (site trust + photo quality)
    accuracy_score: float  # 0-100 (constraint matching)
    completeness_score: float  # 0-100 (data completeness)
    overall_recipe_score: float  # 0-100 weighted


class AgentPerformanceScorer:
    """
    Dual scoring system for tactical decisions and strategic learning.
    """
    
    def __init__(self):
        self.priority_sites = {
            'allrecipes.com', 'simplyrecipes.com', 'seriouseats.com',
            'bonappetit.com', 'cookinglight.com', 'eatingwell.com',
            'food52.com', 'thekitchn.com', 'budgetbytes.com',
            'skinnytaste.com', 'minimalistbaker.com', 'loveandlemons.com',
            'cookieandkate.com', 'ambitiouskitchen.com', 'cafedelites.com',
            'natashaskitchen.com', 'sallysbakingaddiction.com', 'gimmesomeoven.com',
            'recipetineats.com', 'damndelicious.net'
        }
        
        # Known high-quality sites (not priority but still excellent)
        self.high_quality_sites = {
            'joyfoodsunshine.com', 'pinchofyum.com', 'handletheheat.com',
            'tasteofhome.com', 'bettycrocker.com', 'kingarthurbaking.com',
            'southernliving.com', 'delish.com', 'foodandwine.com'
        }
    
    def score_overall_search(
        self, 
        user_query: str, 
        search_result: Dict, 
        elapsed_seconds: float,
        target_count: int = 4
    ) -> OverallSearchScore:
        """
        Score the overall search performance across three pillars.
        Used for tactical decision-making and session adaptation.
        """
        recipes = search_result.get("recipes", [])
        
        # SPEED SCORE (Updated targets: 12s=100%, 20s=80%, 40s=60%)
        speed_score = self._calculate_speed_score(elapsed_seconds)
        
        # QUALITY SCORE (Source trust + photo availability)
        quality_score = self._calculate_overall_quality_score(recipes)
        
        # ACCURACY SCORE (Constraint satisfaction)
        constraints = self._extract_constraints_from_query(user_query)
        accuracy_score = self._calculate_overall_accuracy_score(user_query, recipes, constraints)
        
        # OVERALL SCORE (Speed > Quality > Accuracy: 50% + 30% + 20%)
        overall_score = (speed_score * 0.50) + (quality_score * 0.30) + (accuracy_score * 0.20)
        
        return OverallSearchScore(
            speed=round(speed_score, 1),
            quality=round(quality_score, 1),
            accuracy=round(accuracy_score, 1),
            overall=round(overall_score, 1),
            search_time=round(elapsed_seconds, 1),
            recipes_found=len(recipes),
            constraints_identified=constraints,
            constraints_met=self._identify_constraints_met(recipes, constraints)
        )
    
    def score_individual_recipes(self, recipes: List[Dict], user_query: str) -> List[IndividualRecipeScore]:
        """
        Score each individual recipe for strategic learning and ranking.
        Used for site optimization and recipe quality patterns.
        """
        constraints = self._extract_constraints_from_query(user_query)
        individual_scores = []
        
        for recipe in recipes:
            source_url = recipe.get('source_url', '')
            domain = self._extract_domain(source_url)
            
            # QUALITY SCORE (Site reputation + photo + completeness)
            quality_score = self._calculate_recipe_quality_score(recipe, domain)
            
            # ACCURACY SCORE (Constraint matching for this recipe)
            accuracy_score = self._calculate_recipe_accuracy_score(recipe, constraints, user_query)
            
            # COMPLETENESS SCORE (Recipe data completeness)
            completeness_score = self._calculate_recipe_completeness_score(recipe)
            
            # OVERALL RECIPE SCORE (Quality=40%, Accuracy=35%, Completeness=25%)
            overall = (quality_score * 0.40) + (accuracy_score * 0.35) + (completeness_score * 0.25)
            
            individual_scores.append(IndividualRecipeScore(
                recipe_url=source_url,
                site_domain=domain,
                quality_score=round(quality_score, 1),
                accuracy_score=round(accuracy_score, 1), 
                completeness_score=round(completeness_score, 1),
                overall_recipe_score=round(overall, 1)
            ))
        
        return individual_scores
    
    def _calculate_speed_score(self, elapsed_seconds: float) -> float:
        """Calculate speed score with aggressive targets."""
        if elapsed_seconds <= 12:
            return 100.0  # Excellent
        elif elapsed_seconds <= 20:
            return 80.0   # Good  
        elif elapsed_seconds <= 40:
            return 60.0   # Acceptable
        else:
            # Linear decay after 40s, minimum 10 points
            return max(10.0, 60.0 - ((elapsed_seconds - 40) * 1.5))
    
    def _calculate_overall_quality_score(self, recipes: List[Dict]) -> float:
        """Calculate overall quality score for the recipe set."""
        if not recipes:
            return 0.0
        
        total_score = 0.0
        
        for recipe in recipes:
            recipe_quality = self._calculate_recipe_quality_score(recipe, self._extract_domain(recipe.get('source_url', '')))
            total_score += recipe_quality
        
        return total_score / len(recipes)
    
    def _calculate_recipe_quality_score(self, recipe: Dict, domain: str) -> float:
        """Calculate quality score for individual recipe."""
        score = 0.0
        
        # Site reputation (0-60 points)
        if domain in self.priority_sites:
            score += 60.0  # Priority sites get maximum
        elif domain in self.high_quality_sites:
            score += 45.0  # High-quality sites
        elif any(term in domain for term in ['blog', 'kitchen', 'baking', 'cooking']):
            score += 30.0  # Food blogs (variable quality)
        else:
            score += 15.0  # Unknown sites (lower trust)
        
        # Photo quality (0-25 points)
        image_url = recipe.get('image_url', '')
        if image_url:
            if any(quality_indicator in image_url for quality_indicator in ['1200', '1500', 'large', 'hero']):
                score += 25.0  # High-resolution images
            elif 'thumb' in image_url or '150' in image_url:
                score += 10.0  # Thumbnail quality
            else:
                score += 15.0  # Standard image
        else:
            score += 0.0   # No image
        
        # Recipe completeness (0-15 points)  
        ingredients_count = len(recipe.get('ingredients', []))
        instructions_count = len(recipe.get('instructions', []))
        
        if ingredients_count >= 5 and instructions_count >= 3:
            score += 15.0  # Complete recipe
        elif ingredients_count >= 3 and instructions_count >= 2:
            score += 10.0  # Good recipe
        else:
            score += 5.0   # Minimal recipe
        
        return min(100.0, score)
    
    def _calculate_overall_accuracy_score(self, user_query: str, recipes: List[Dict], constraints: List[str]) -> float:
        """Calculate overall accuracy for constraint satisfaction."""
        if not constraints:
            return 85.0  # No specific constraints = good baseline score
        
        if not recipes:
            return 0.0
        
        total_accuracy = 0.0
        
        for recipe in recipes:
            recipe_accuracy = self._calculate_recipe_accuracy_score(recipe, constraints, user_query)
            total_accuracy += recipe_accuracy
        
        return total_accuracy / len(recipes)
    
    def _calculate_recipe_accuracy_score(self, recipe: Dict, constraints: List[str], user_query: str) -> float:
        """Calculate how well individual recipe matches user constraints."""
        if not constraints:
            # No specific constraints - score based on query relevance
            return self._calculate_query_relevance(recipe, user_query)
        
        constraint_matches = 0
        total_constraints = len(constraints)
        
        # Check each constraint
        for constraint in constraints:
            if self._recipe_satisfies_constraint(recipe, constraint):
                constraint_matches += 1
        
        # Calculate percentage match
        match_percentage = (constraint_matches / total_constraints) * 100 if total_constraints > 0 else 85.0
        
        return min(100.0, match_percentage)
    
    def _calculate_recipe_completeness_score(self, recipe: Dict) -> float:
        """Calculate recipe data completeness."""
        score = 0.0
        
        # Essential fields (70 points total)
        if recipe.get('title'): score += 10.0
        if recipe.get('ingredients'): 
            ingredients_count = len(recipe.get('ingredients', []))
            score += min(25.0, ingredients_count * 3)  # 3 points per ingredient, max 25
        if recipe.get('instructions'):
            instructions_count = len(recipe.get('instructions', []))  
            score += min(25.0, instructions_count * 4)  # 4 points per step, max 25
        if recipe.get('image_url'): score += 10.0
        
        # Bonus fields (30 points total)
        if recipe.get('cook_time'): score += 10.0
        if recipe.get('servings'): score += 10.0
        if recipe.get('nutrition'): score += 10.0
        
        return min(100.0, score)
    
    def _extract_constraints_from_query(self, user_query: str) -> List[str]:
        """Extract specific constraints from user query."""
        constraints = []
        query_lower = user_query.lower()
        
        # Dietary restrictions
        dietary_terms = ['vegan', 'vegetarian', 'gluten-free', 'dairy-free', 'keto', 'paleo', 'nut-free']
        for term in dietary_terms:
            if term in query_lower:
                constraints.append(f"dietary_{term.replace('-', '_')}")
        
        # Nutrition constraints  
        protein_match = re.search(r'(\d+)g?\s*protein', query_lower)
        if protein_match:
            constraints.append(f"protein_min_{protein_match.group(1)}")
            
        calorie_match = re.search(r'(\d+)\s*calorie', query_lower)
        if calorie_match:
            constraints.append(f"calories_max_{calorie_match.group(1)}")
        
        # Time constraints
        time_match = re.search(r'(\d+)\s*min', query_lower)
        if time_match:
            constraints.append(f"cook_time_max_{time_match.group(1)}")
        
        # Specific ingredients
        if 'no ' in query_lower:
            exclude_match = re.search(r'no\s+(\w+)', query_lower)
            if exclude_match:
                constraints.append(f"exclude_{exclude_match.group(1)}")
        
        return constraints
    
    def _recipe_satisfies_constraint(self, recipe: Dict, constraint: str) -> bool:
        """Check if recipe satisfies a specific constraint."""
        # Basic constraint checking (can be enhanced)
        if constraint.startswith('dietary_'):
            # Check ingredients for dietary compliance
            ingredients_text = ' '.join(recipe.get('ingredients', [])).lower()
            if 'vegan' in constraint:
                return not any(non_vegan in ingredients_text for non_vegan in ['chicken', 'beef', 'pork', 'fish', 'egg', 'milk', 'cheese', 'butter'])
            elif 'gluten_free' in constraint:
                return not any(gluten in ingredients_text for gluten in ['flour', 'wheat', 'bread', 'pasta'])
        
        elif constraint.startswith('protein_min_'):
            protein_amount = int(constraint.split('_')[-1])
            nutrition = recipe.get('nutrition', [])
            for nutrient in nutrition:
                if 'protein' in nutrient.lower():
                    protein_match = re.search(r'(\d+)', nutrient)
                    if protein_match and int(protein_match.group(1)) >= protein_amount:
                        return True
        
        elif constraint.startswith('calories_max_'):
            calorie_limit = int(constraint.split('_')[-1])
            nutrition = recipe.get('nutrition', [])
            for nutrient in nutrition:
                if 'calorie' in nutrient.lower():
                    calorie_match = re.search(r'(\d+)', nutrient)
                    if calorie_match and int(calorie_match.group(1)) <= calorie_limit:
                        return True
        
        # Default: assume constraint is met (conservative)
        return True
    
    def _calculate_query_relevance(self, recipe: Dict, user_query: str) -> float:
        """Calculate recipe relevance when no specific constraints."""
        title = recipe.get('title', '').lower()
        ingredients = ' '.join(recipe.get('ingredients', [])).lower()
        
        query_words = user_query.lower().split()
        recipe_text = f"{title} {ingredients}"
        
        matches = sum(1 for word in query_words if word in recipe_text and len(word) > 3)
        relevance_score = min(100.0, (matches / len(query_words)) * 100 + 50)  # Baseline 50 + relevance
        
        return relevance_score
    
    def _identify_constraints_met(self, recipes: List[Dict], constraints: List[str]) -> List[str]:
        """Identify which constraints were satisfied by the recipe set."""
        met_constraints = []
        
        for constraint in constraints:
            # Check if ANY recipe in the set satisfies this constraint
            if any(self._recipe_satisfies_constraint(recipe, constraint) for recipe in recipes):
                met_constraints.append(constraint)
        
        return met_constraints
    
    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL."""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"
    
    def generate_performance_report(self, overall_score: OverallSearchScore, individual_scores: List[IndividualRecipeScore]) -> Dict:
        """Generate comprehensive performance report for agent and developer insight."""
        
        # Site performance analysis
        site_performance = {}
        for recipe_score in individual_scores:
            domain = recipe_score.site_domain
            if domain not in site_performance:
                site_performance[domain] = {
                    'count': 0, 
                    'avg_quality': 0, 
                    'avg_accuracy': 0, 
                    'avg_completeness': 0
                }
            
            site_data = site_performance[domain]
            site_data['count'] += 1
            site_data['avg_quality'] += recipe_score.quality_score
            site_data['avg_accuracy'] += recipe_score.accuracy_score
            site_data['avg_completeness'] += recipe_score.completeness_score
        
        # Calculate averages
        for domain, data in site_performance.items():
            count = data['count']
            data['avg_quality'] = round(data['avg_quality'] / count, 1)
            data['avg_accuracy'] = round(data['avg_accuracy'] / count, 1)
            data['avg_completeness'] = round(data['avg_completeness'] / count, 1)
        
        return {
            "overall_performance": {
                "speed": overall_score.speed,
                "quality": overall_score.quality, 
                "accuracy": overall_score.accuracy,
                "overall": overall_score.overall,
                "search_time": overall_score.search_time,
                "grade": self._get_performance_grade(overall_score.overall)
            },
            "constraint_analysis": {
                "identified": overall_score.constraints_identified,
                "satisfied": overall_score.constraints_met,
                "satisfaction_rate": round(len(overall_score.constraints_met) / len(overall_score.constraints_identified) * 100, 1) if overall_score.constraints_identified else 100
            },
            "site_performance": site_performance,
            "recipe_scores": [
                {
                    "url": score.recipe_url[:50] + "...",
                    "domain": score.site_domain,
                    "quality": score.quality_score,
                    "accuracy": score.accuracy_score,
                    "completeness": score.completeness_score,
                    "overall": score.overall_recipe_score
                }
                for score in individual_scores
            ],
            "insights": self._generate_insights(overall_score, site_performance)
        }
    
    def _get_performance_grade(self, score: float) -> str:
        """Convert numerical score to grade."""
        if score >= 90: return "A"
        elif score >= 80: return "B" 
        elif score >= 70: return "C"
        elif score >= 60: return "D"
        else: return "F"
    
    def _generate_insights(self, overall_score: OverallSearchScore, site_performance: Dict) -> List[str]:
        """Generate actionable insights for improvement."""
        insights = []
        
        # Speed insights
        if overall_score.speed < 70:
            insights.append(f"Speed improvement needed - search took {overall_score.search_time}s (target ≤20s)")
        
        # Quality insights  
        if overall_score.quality < 80:
            insights.append("Consider prioritizing higher-quality recipe sources")
        
        # Accuracy insights
        if overall_score.accuracy < 70:
            insights.append("Constraint matching could be improved - consider broader search or relaxed requirements")
        
        # Site insights
        best_sites = sorted(site_performance.items(), key=lambda x: x[1]['avg_quality'], reverse=True)[:3]
        if best_sites:
            insights.append(f"Best performing sites this search: {', '.join(site[0] for site in best_sites)}")
        
        return insights


class SessionPerformanceTracker:
    """Track performance across multiple searches in a session."""
    
    def __init__(self):
        self.session_scores = []
        self.session_start_time = time.time()
    
    def add_search_score(self, overall_score: OverallSearchScore):
        """Add a search performance score to session tracking."""
        self.session_scores.append(overall_score)
    
    def get_session_insights(self) -> Dict:
        """Generate session-wide performance insights."""
        if not self.session_scores:
            return {"message": "No searches completed yet"}
        
        avg_speed = sum(score.speed for score in self.session_scores) / len(self.session_scores)
        avg_quality = sum(score.quality for score in self.session_scores) / len(self.session_scores)
        avg_accuracy = sum(score.accuracy for score in self.session_scores) / len(self.session_scores)
        
        return {
            "searches_completed": len(self.session_scores),
            "session_averages": {
                "speed": round(avg_speed, 1),
                "quality": round(avg_quality, 1),
                "accuracy": round(avg_accuracy, 1)
            },
            "performance_trend": self._analyze_performance_trend(),
            "recommendations": self._generate_session_recommendations()
        }
    
    def _analyze_performance_trend(self) -> str:
        """Analyze if performance is improving or declining."""
        if len(self.session_scores) < 2:
            return "insufficient_data"
        
        recent_scores = self.session_scores[-2:]
        if recent_scores[-1].overall > recent_scores[-2].overall:
            return "improving"
        elif recent_scores[-1].overall < recent_scores[-2].overall:
            return "declining" 
        else:
            return "stable"
    
    def _generate_session_recommendations(self) -> List[str]:
        """Generate recommendations for improving session performance."""
        if not self.session_scores:
            return []
        
        recommendations = []
        avg_speed = sum(score.speed for score in self.session_scores) / len(self.session_scores)
        avg_quality = sum(score.quality for score in self.session_scores) / len(self.session_scores)
        
        if avg_speed < 70:
            recommendations.append("Consider using fewer URLs or priority_only strategy for faster results")
        if avg_quality < 80:
            recommendations.append("Focus more on priority recipe sites for better photo quality")
        
        return recommendations