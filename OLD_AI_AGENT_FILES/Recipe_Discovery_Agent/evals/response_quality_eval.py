"""
Response Quality Evaluation for Recipe Discovery Agent

Evaluates the conversational appropriateness, accuracy, and adherence to guidelines
of the agent's text responses using Pydantic AI evaluation framework.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge
import re


@dataclass
class FallbackAccuracyEvaluator(Evaluator[str, Dict]):
    """
    Evaluates if response correctly indicates exact matches vs closest alternatives
    based on the tool's fallback_used field.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        # Extract tool output data
        tool_output = ctx.output
        response_text = ""
        fallback_used = False
        exact_matches = 0
        
        # Parse agent result structure
        if isinstance(tool_output, dict):
            if 'data' in tool_output:
                response_text = str(tool_output['data'])
            
            # Look for tool output in messages
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            if 'fallback_used' in output:
                                fallback_used = output['fallback_used']
                                exact_matches = output.get('exact_matches', 0)
                                break
        
        response_lower = response_text.lower()
        
        # If fallback was used, response should indicate alternatives/close matches
        if fallback_used:
            if exact_matches > 0:
                # Mixed results - should mention both
                has_alternatives = any(phrase in response_lower for phrase in [
                    'close alternative', 'might work', 'come close', 'plus some'
                ])
                return 1.0 if has_alternatives else 0.3
            else:
                # Only closest matches - should be clear about this
                has_closest_language = any(phrase in response_lower for phrase in [
                    'close', 'best matches available', 'come close to'
                ])
                return 1.0 if has_closest_language else 0.2
        else:
            # Exact matches only - should be confident
            has_confident_language = any(phrase in response_lower for phrase in [
                'found some', 'meet your requirements', 'found recipes'
            ])
            no_uncertainty = not any(phrase in response_lower for phrase in [
                'close', 'alternative', 'might'
            ])
            return 1.0 if (has_confident_language and no_uncertainty) else 0.6


@dataclass 
class ContentBoundaryEvaluator(Evaluator[str, Dict]):
    """
    Ensures response never includes recipe names, ingredients, URLs, or structured data.
    Critical for maintaining UI separation.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        tool_output = ctx.output
        response_text = ""
        
        # Extract response text
        if isinstance(tool_output, dict) and 'data' in tool_output:
            response_text = str(tool_output['data'])
        
        violations = []
        
        # Check for recipe names (titles in quotes or numbered lists)
        if re.search(r'["\']\w+.*["\']\s*recipe', response_text, re.IGNORECASE):
            violations.append("recipe_names_detected")
            
        # Check for numbered recipe lists
        if re.search(r'\d+\.\s+\w+.*(?:recipe|with|ingredients)', response_text, re.IGNORECASE):
            violations.append("numbered_recipe_list")
            
        # Check for URLs
        if re.search(r'https?://|www\.', response_text):
            violations.append("urls_detected")
            
        # Check for ingredient lists
        if re.search(r'ingredients?:\s*[\[\(]|cups?\s+of|tablespoons?', response_text, re.IGNORECASE):
            violations.append("ingredients_detected")
            
        # Check for cooking instructions
        if re.search(r'step\s+\d+|preheat|bake\s+for|cook\s+until', response_text, re.IGNORECASE):
            violations.append("cooking_instructions")
        
        # Score: 1.0 for no violations, deduct 0.3 per violation type
        return max(0.0, 1.0 - (len(violations) * 0.3))


@dataclass
class ResponseLengthEvaluator(Evaluator[str, Dict]):
    """
    Evaluates response brevity - should be 1-2 sentences as per system prompt.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        tool_output = ctx.output
        response_text = ""
        
        if isinstance(tool_output, dict) and 'data' in tool_output:
            response_text = str(tool_output['data'])
        
        # Count sentences (split by . ! ?)
        sentences = [s.strip() for s in re.split(r'[.!?]+', response_text) if s.strip()]
        sentence_count = len(sentences)
        
        # Ideal: 1-2 sentences (1.0), acceptable: 3 sentences (0.8), poor: 4+ (0.4)
        if sentence_count <= 2:
            return 1.0
        elif sentence_count == 3:
            return 0.8
        elif sentence_count <= 5:
            return 0.4
        else:
            return 0.1


@dataclass
class SaveCommandEvaluator(Evaluator[str, Dict]):
    """
    Evaluates appropriate handling of save commands vs search commands.
    Save commands should not trigger search tool.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        user_input = ctx.inputs
        tool_output = ctx.output
        
        # Detect if input was a save command
        is_save_command = bool(re.search(r'save\s+(?:meal|recipe)\s*#?\d+|save\s+the\s+\w+\s+one', user_input.lower()))
        
        # Check if search tool was called (should not happen for save commands)
        search_tool_called = False
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            if 'full_recipes' in item.output:
                                search_tool_called = True
                                break
        
        if is_save_command:
            # Save command should NOT trigger search tool
            return 0.0 if search_tool_called else 1.0
        else:
            # Food queries should trigger search tool
            return 1.0 if search_tool_called else 0.2


# Create comprehensive test cases
response_quality_cases = [
    # Basic search queries - should find exact matches
    Case(
        name='simple_protein_query',
        inputs='high protein breakfast',
        metadata={'query_type': 'nutrition_basic', 'expected_fallback': False, 'difficulty': 'easy'}
    ),
    
    Case(
        name='simple_food_query', 
        inputs='chicken recipes',
        metadata={'query_type': 'basic_search', 'expected_fallback': False, 'difficulty': 'easy'}
    ),
    
    # Requirement queries - might trigger fallbacks
    Case(
        name='strict_nutrition_requirement',
        inputs='recipes with exactly 40g protein and under 300 calories',
        metadata={'query_type': 'strict_requirements', 'expected_fallback': True, 'difficulty': 'hard'}
    ),
    
    Case(
        name='dietary_restriction',
        inputs='gluten-free chocolate desserts',
        metadata={'query_type': 'dietary_restriction', 'expected_fallback': False, 'difficulty': 'medium'}
    ),
    
    # Save commands - should NOT trigger search
    Case(
        name='save_command_numeric',
        inputs='save meal #3',
        metadata={'query_type': 'save_command', 'expected_search': False, 'difficulty': 'easy'}
    ),
    
    Case(
        name='save_command_ordinal',
        inputs='save the second one',
        metadata={'query_type': 'save_command', 'expected_search': False, 'difficulty': 'easy'}
    ),
    
    # Edge cases
    Case(
        name='vague_query',
        inputs='something healthy',
        metadata={'query_type': 'vague', 'expected_fallback': True, 'difficulty': 'medium'}
    ),
    
    Case(
        name='impossible_requirements',
        inputs='zero calorie chocolate cake with 50g protein',
        metadata={'query_type': 'impossible', 'expected_fallback': True, 'difficulty': 'hard'}
    ),
    
    # Context-aware queries
    Case(
        name='find_more_query',
        inputs='find me more options',
        metadata={'query_type': 'context_dependent', 'expected_fallback': False, 'difficulty': 'medium'}
    )
]

# Create dataset with comprehensive evaluators
response_quality_dataset = Dataset(
    cases=response_quality_cases,
    evaluators=[
        # Overall conversational quality using LLMJudge
        LLMJudge(
            rubric="""
            Evaluate if this response from a recipe discovery agent is conversational, helpful, and appropriate.
            Good responses are:
            - Friendly and encouraging (1-2 sentences)
            - Accurately indicate if exact matches or alternatives were found
            - Never include recipe names, ingredients, or cooking details
            - Professional but warm tone
            
            Score 1.0 for excellent conversational responses, 0.5 for adequate, 0.0 for poor.
            """,
            model='openai:gpt-4o'
        ),
        
        # Custom evaluators for specific requirements
        FallbackAccuracyEvaluator(),
        ContentBoundaryEvaluator(), 
        ResponseLengthEvaluator(),
        SaveCommandEvaluator(),
        
        # Professional tone check
        LLMJudge(
            rubric="""
            Rate the professionalism and helpfulness of this recipe discovery response.
            Should sound like a knowledgeable food assistant, not robotic.
            Avoid overly casual language but maintain warmth.
            Score: 1.0 for perfect professional tone, 0.0 for poor tone.
            """,
            model='openai:gpt-4o'
        )
    ]
)


def evaluate_response_quality(agent_function, test_case_names: List[str] = None):
    """
    Run response quality evaluation on the Recipe Discovery Agent.
    
    Args:
        agent_function: The agent function to evaluate (should return AgentRunResult)
        test_case_names: Optional list of specific test case names to run
        
    Returns:
        EvaluationReport with detailed scoring and analysis
    """
    cases_to_run = response_quality_cases
    if test_case_names:
        cases_to_run = [case for case in response_quality_cases if case.name in test_case_names]
    
    dataset = Dataset(cases=cases_to_run, evaluators=response_quality_dataset.evaluators)
    
    # Run evaluation
    report = dataset.evaluate_sync(agent_function)
    
    print("🎯 RESPONSE QUALITY EVALUATION RESULTS")
    print("=" * 50)
    report.print(include_input=True, include_output=True)
    
    return report


if __name__ == "__main__":
    # Example usage - would need to import and adapt your agent
    print("Response Quality Evaluation Suite")
    print("Import this module and call evaluate_response_quality() with your agent function")
    print(f"Total test cases: {len(response_quality_cases)}")
    
    # Print test case summary
    for case in response_quality_cases:
        print(f"- {case.name}: {case.metadata.get('query_type', 'unknown')} (difficulty: {case.metadata.get('difficulty', 'unknown')})")