"""
Recipe Accuracy Evaluation for Recipe Discovery Agent

Evaluates the accuracy and quality of returned recipe data, including requirement
matching, dietary compliance, and data completeness using Pydantic AI framework.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Set
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge
from urllib.parse import urlparse
import re


@dataclass
class NutritionRequirementEvaluator(Evaluator[str, Dict]):
    """
    Evaluates if returned recipes meet specified nutrition requirements.
    Handles min/max constraints and fallback tolerance.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        # Extract nutrition requirements from test case metadata
        metadata = getattr(ctx.case, 'metadata', {})
        nutrition_reqs = metadata.get('nutrition_requirements', {})
        
        if not nutrition_reqs:
            return 1.0  # No requirements to check
        
        # Extract recipes from tool output
        recipes = self._extract_recipes(ctx.output)
        if not recipes:
            return 0.0
        
        total_score = 0.0
        recipe_count = 0
        
        for recipe in recipes:
            recipe_score = self._evaluate_recipe_nutrition(recipe, nutrition_reqs)
            total_score += recipe_score
            recipe_count += 1
        
        return total_score / recipe_count if recipe_count > 0 else 0.0
    
    def _extract_recipes(self, tool_output: Dict) -> List[Dict]:
        """Extract recipe list from agent tool output."""
        recipes = []
        
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'full_recipes' in output:
                                recipes.extend(output['full_recipes'])
        
        return recipes
    
    def _evaluate_recipe_nutrition(self, recipe: Dict, requirements: Dict) -> float:
        """Evaluate single recipe against nutrition requirements."""
        nutrition_data = recipe.get('nutrition', [])
        
        # Parse nutrition into dict
        nutrition_values = {}
        for nutrient in nutrition_data:
            if isinstance(nutrient, dict):
                name = nutrient.get('name', '').lower()
                amount_str = nutrient.get('amount', '0')
                try:
                    amount = float(''.join(c for c in str(amount_str) if c.isdigit() or c == '.'))
                    
                    if 'calorie' in name:
                        nutrition_values['calories'] = amount
                    elif 'protein' in name:
                        nutrition_values['protein'] = amount
                    elif 'fat' in name:
                        nutrition_values['fat'] = amount
                    elif 'carb' in name:
                        nutrition_values['carbs'] = amount
                except:
                    continue
        
        # Check each requirement
        violations = 0
        total_checks = 0
        
        for nutrient, constraints in requirements.items():
            if nutrient in nutrition_values:
                actual_value = nutrition_values[nutrient]
                total_checks += 1
                
                if 'min' in constraints and actual_value < constraints['min']:
                    violations += 1
                elif 'max' in constraints and actual_value > constraints['max']:
                    violations += 1
        
        # Score: 1.0 for perfect compliance, deduct for violations
        if total_checks == 0:
            return 1.0  # No constraints to check
        
        compliance_rate = (total_checks - violations) / total_checks
        return compliance_rate


@dataclass
class DietaryRestrictionEvaluator(Evaluator[str, Dict]):
    """
    Evaluates compliance with dietary restrictions by checking ingredient lists.
    """
    
    # Common dietary restriction mappings
    RESTRICTION_MAPPINGS = {
        'gluten-free': ['wheat', 'flour', 'bread', 'pasta', 'barley', 'rye', 'oats'],
        'vegan': ['meat', 'chicken', 'beef', 'pork', 'fish', 'dairy', 'milk', 'cheese', 'butter', 'eggs'],
        'dairy-free': ['milk', 'cheese', 'butter', 'cream', 'yogurt', 'dairy'],
        'nut-free': ['nuts', 'almonds', 'peanuts', 'cashews', 'walnuts'],
        'vegetarian': ['meat', 'chicken', 'beef', 'pork', 'fish']
    }
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        metadata = getattr(ctx.case, 'metadata', {})
        restrictions = metadata.get('dietary_restrictions', [])
        
        if not restrictions:
            return 1.0  # No restrictions to check
        
        recipes = self._extract_recipes(ctx.output)
        if not recipes:
            return 0.0
        
        total_compliance = 0.0
        
        for recipe in recipes:
            recipe_compliance = self._check_recipe_restrictions(recipe, restrictions)
            total_compliance += recipe_compliance
        
        return total_compliance / len(recipes)
    
    def _extract_recipes(self, tool_output: Dict) -> List[Dict]:
        """Extract recipes from tool output."""
        recipes = []
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'full_recipes' in output:
                                recipes.extend(output['full_recipes'])
        return recipes
    
    def _check_recipe_restrictions(self, recipe: Dict, restrictions: List[str]) -> float:
        """Check single recipe against dietary restrictions."""
        ingredients = recipe.get('ingredients', [])
        ingredient_text = ' '.join([
            str(ing.get('ingredient', '')) + ' ' + str(ing.get('original', ''))
            for ing in ingredients if isinstance(ing, dict)
        ]).lower()
        
        violations = 0
        total_restrictions = len(restrictions)
        
        for restriction in restrictions:
            forbidden_items = self.RESTRICTION_MAPPINGS.get(restriction, [])
            for forbidden in forbidden_items:
                if forbidden in ingredient_text:
                    violations += 1
                    break  # One violation per restriction type
        
        return (total_restrictions - violations) / total_restrictions if total_restrictions > 0 else 1.0


@dataclass
class DomainDiversityEvaluator(Evaluator[str, Dict]):
    """
    Evaluates domain diversity - ensures max 2 recipes per domain for variety.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        recipes = self._extract_recipes(ctx.output)
        if not recipes:
            return 0.0
        
        # Count recipes per domain
        domain_counts = {}
        for recipe in recipes:
            source_url = recipe.get('source_url', '')
            if source_url:
                try:
                    domain = urlparse(source_url).netloc.lower().replace('www.', '')
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                except:
                    continue
        
        # Check compliance with max 2 per domain rule
        violations = sum(1 for count in domain_counts.values() if count > 2)
        total_domains = len(domain_counts)
        
        if total_domains == 0:
            return 0.0
        
        # Score: 1.0 for perfect compliance, deduct for violations
        compliance_rate = (total_domains - violations) / total_domains
        
        # Bonus for good diversity (3+ unique domains)
        diversity_bonus = min(0.2, (total_domains - 2) * 0.1) if total_domains >= 3 else 0
        
        return min(1.0, compliance_rate + diversity_bonus)
    
    def _extract_recipes(self, tool_output: Dict) -> List[Dict]:
        """Extract recipes from tool output."""
        recipes = []
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'full_recipes' in output:
                                recipes.extend(output['full_recipes'])
        return recipes


@dataclass
class RecipeCompletenessEvaluator(Evaluator[str, Dict]):
    """
    Evaluates completeness of recipe data - ensures all required fields present.
    """
    
    REQUIRED_FIELDS = ['title', 'ingredients', 'nutrition', 'source_url']
    OPTIONAL_FIELDS = ['servings', 'readyInMinutes', 'image']
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        recipes = self._extract_recipes(ctx.output)
        if not recipes:
            return 0.0
        
        total_completeness = 0.0
        
        for recipe in recipes:
            recipe_completeness = self._evaluate_recipe_completeness(recipe)
            total_completeness += recipe_completeness
        
        return total_completeness / len(recipes)
    
    def _evaluate_recipe_completeness(self, recipe: Dict) -> float:
        """Evaluate completeness of single recipe."""
        score = 0.0
        
        # Required fields (0.8 total weight)
        required_score = 0.0
        for field in self.REQUIRED_FIELDS:
            if field in recipe and recipe[field]:
                if field == 'ingredients' and isinstance(recipe[field], list) and len(recipe[field]) > 0:
                    required_score += 1.0
                elif field == 'nutrition' and isinstance(recipe[field], list) and len(recipe[field]) > 0:
                    required_score += 1.0
                elif isinstance(recipe[field], str) and len(recipe[field].strip()) > 0:
                    required_score += 1.0
        
        score += (required_score / len(self.REQUIRED_FIELDS)) * 0.8
        
        # Optional fields (0.2 total weight)
        optional_score = 0.0
        for field in self.OPTIONAL_FIELDS:
            if field in recipe and recipe[field]:
                optional_score += 1.0
        
        score += (optional_score / len(self.OPTIONAL_FIELDS)) * 0.2
        
        return score
    
    def _extract_recipes(self, tool_output: Dict) -> List[Dict]:
        """Extract recipes from tool output."""
        recipes = []
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'full_recipes' in output:
                                recipes.extend(output['full_recipes'])
        return recipes


# Comprehensive test cases for recipe accuracy
recipe_accuracy_cases = [
    # Nutrition requirement tests
    Case(
        name='high_protein_requirement',
        inputs='high protein breakfast recipes',
        metadata={
            'nutrition_requirements': {'protein': {'min': 25}},
            'query_type': 'nutrition',
            'difficulty': 'medium'
        }
    ),
    
    Case(
        name='calorie_limit',
        inputs='low calorie dinner under 400 calories',
        metadata={
            'nutrition_requirements': {'calories': {'max': 400}},
            'query_type': 'nutrition',
            'difficulty': 'medium'
        }
    ),
    
    Case(
        name='strict_nutrition_combo',
        inputs='recipes with 30g protein and under 500 calories',
        metadata={
            'nutrition_requirements': {'protein': {'min': 30}, 'calories': {'max': 500}},
            'query_type': 'nutrition_strict',
            'difficulty': 'hard'
        }
    ),
    
    # Dietary restriction tests
    Case(
        name='gluten_free_requirement',
        inputs='gluten-free pasta recipes',
        metadata={
            'dietary_restrictions': ['gluten-free'],
            'query_type': 'dietary',
            'difficulty': 'medium'
        }
    ),
    
    Case(
        name='vegan_requirement',
        inputs='vegan chocolate desserts',
        metadata={
            'dietary_restrictions': ['vegan'],
            'query_type': 'dietary',
            'difficulty': 'medium'
        }
    ),
    
    Case(
        name='multiple_restrictions',
        inputs='gluten-free vegan dinner recipes',
        metadata={
            'dietary_restrictions': ['gluten-free', 'vegan'],
            'query_type': 'dietary_multiple',
            'difficulty': 'hard'
        }
    ),
    
    # Ingredient inclusion/exclusion tests
    Case(
        name='ingredient_inclusion',
        inputs='recipes with chicken and avocado',
        metadata={
            'required_ingredients': ['chicken', 'avocado'],
            'query_type': 'ingredient_inclusion',
            'difficulty': 'medium'
        }
    ),
    
    Case(
        name='ingredient_exclusion',
        inputs='pasta recipes without onions',
        metadata={
            'excluded_ingredients': ['onion', 'onions'],
            'query_type': 'ingredient_exclusion', 
            'difficulty': 'medium'
        }
    ),
    
    # Time constraint tests
    Case(
        name='time_constraint',
        inputs='quick 15-minute breakfast recipes',
        metadata={
            'time_requirements': {'max_minutes': 15},
            'query_type': 'time',
            'difficulty': 'medium'
        }
    ),
    
    # Edge cases
    Case(
        name='impossible_requirements',
        inputs='zero calorie chocolate cake with 50g protein',
        metadata={
            'nutrition_requirements': {'calories': {'max': 10}, 'protein': {'min': 50}},
            'query_type': 'impossible',
            'difficulty': 'extreme',
            'expect_fallback': True
        }
    ),
    
    # Basic diversity test
    Case(
        name='domain_diversity_test',
        inputs='popular chicken recipes',
        metadata={
            'query_type': 'diversity',
            'difficulty': 'easy',
            'expect_diverse_domains': True
        }
    )
]

# Create dataset with comprehensive evaluators
recipe_accuracy_dataset = Dataset(
    cases=recipe_accuracy_cases,
    evaluators=[
        # Nutrition requirement compliance
        NutritionRequirementEvaluator(),
        
        # Dietary restriction compliance
        DietaryRestrictionEvaluator(),
        
        # Domain diversity compliance
        DomainDiversityEvaluator(),
        
        # Recipe data completeness
        RecipeCompletenessEvaluator(),
        
        # LLM-based relevance judgment
        LLMJudge(
            rubric="""
            Evaluate if the returned recipes are relevant to the user's search query.
            Consider:
            - Do recipe titles/ingredients match the query intent?
            - Are dietary restrictions properly respected?
            - Do nutrition values align with stated requirements?
            - Overall quality and appropriateness of results
            
            Score 1.0 for highly relevant results, 0.5 for somewhat relevant, 0.0 for irrelevant.
            """,
            model='openai:gpt-4o',
            include_input=True
        ),
        
        # Ingredient quality assessment
        LLMJudge(
            rubric="""
            Evaluate the quality and completeness of ingredient lists in these recipes.
            Good ingredient lists should be:
            - Complete and specific (not vague)
            - Properly structured with quantities and units
            - Realistic and achievable for home cooking
            
            Score 1.0 for excellent ingredient quality, 0.0 for poor quality.
            """,
            model='openai:gpt-4o'
        )
    ]
)


def evaluate_recipe_accuracy(agent_function, test_case_names: List[str] = None):
    """
    Run recipe accuracy evaluation on the Recipe Discovery Agent.
    
    Args:
        agent_function: The agent function to evaluate
        test_case_names: Optional list of specific test case names to run
        
    Returns:
        EvaluationReport with detailed accuracy scoring
    """
    cases_to_run = recipe_accuracy_cases
    if test_case_names:
        cases_to_run = [case for case in recipe_accuracy_cases if case.name in test_case_names]
    
    dataset = Dataset(cases=cases_to_run, evaluators=recipe_accuracy_dataset.evaluators)
    
    # Run evaluation
    report = dataset.evaluate_sync(agent_function)
    
    print("🎯 RECIPE ACCURACY EVALUATION RESULTS")
    print("=" * 50)
    report.print(include_input=True, include_output=True)
    
    return report


if __name__ == "__main__":
    print("Recipe Accuracy Evaluation Suite")
    print("Import this module and call evaluate_recipe_accuracy() with your agent function")
    print(f"Total test cases: {len(recipe_accuracy_cases)}")
    
    # Print test case summary by category
    categories = {}
    for case in recipe_accuracy_cases:
        category = case.metadata.get('query_type', 'unknown')
        if category not in categories:
            categories[category] = []
        categories[category].append(case.name)
    
    for category, cases in categories.items():
        print(f"\n{category.upper()} ({len(cases)} cases):")
        for case_name in cases:
            print(f"  - {case_name}")