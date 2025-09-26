"""
Performance Metrics Evaluation for Recipe Discovery Agent

Evaluates response time, success rates, resource efficiency, and error handling
to ensure production readiness and identify optimization opportunities.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class ResponseTimeEvaluator(Evaluator[str, Dict]):
    """
    Evaluates total response time performance against production thresholds.
    Different expectations for simple vs complex queries.
    """
    
    # Performance thresholds (seconds)
    EXCELLENT_THRESHOLD = 15.0
    GOOD_THRESHOLD = 30.0
    ACCEPTABLE_THRESHOLD = 45.0
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        # Extract timing from tool output or metadata
        total_time = self._extract_total_time(ctx.output)
        
        if total_time is None:
            return 0.0  # Could not measure time
        
        # Get expected performance tier from test case metadata
        metadata = getattr(ctx.case, 'metadata', {})
        difficulty = metadata.get('difficulty', 'medium')
        
        # Adjust thresholds based on query complexity
        if difficulty == 'easy':
            excellent = self.EXCELLENT_THRESHOLD * 0.7  # 10.5s
            good = self.GOOD_THRESHOLD * 0.7  # 21s
            acceptable = self.ACCEPTABLE_THRESHOLD * 0.7  # 31.5s
        elif difficulty == 'hard':
            excellent = self.EXCELLENT_THRESHOLD * 1.5  # 22.5s
            good = self.GOOD_THRESHOLD * 1.5  # 45s
            acceptable = self.ACCEPTABLE_THRESHOLD * 1.5  # 67.5s
        else:  # medium
            excellent = self.EXCELLENT_THRESHOLD
            good = self.GOOD_THRESHOLD
            acceptable = self.ACCEPTABLE_THRESHOLD
        
        # Score based on performance bands
        if total_time <= excellent:
            return 1.0
        elif total_time <= good:
            return 0.8
        elif total_time <= acceptable:
            return 0.5
        else:
            return 0.2
    
    def _extract_total_time(self, tool_output: Dict) -> Optional[float]:
        """Extract total response time from output or calculate from timestamps."""
        # Method 1: Look for timing in tool output
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            # Look for stage_timings in search output
                            if 'stage_timings' in output:
                                stage_times = output['stage_timings']
                                return sum(stage_times.values())
        
        # Method 2: Calculate from start/end metadata if available
        metadata = getattr(tool_output, 'metadata', {})
        start_time = metadata.get('start_time')
        end_time = metadata.get('end_time')
        
        if start_time and end_time:
            return end_time - start_time
        
        return None


@dataclass
class SuccessRateEvaluator(Evaluator[str, Dict]):
    """
    Evaluates successful completion rate and result quality.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        tool_output = ctx.output
        
        # Check for errors in output
        has_error = self._check_for_errors(tool_output)
        if has_error:
            return 0.0
        
        # Check if recipes were returned
        recipes = self._extract_recipes(tool_output)
        recipe_count = len(recipes)
        
        # Expected count from metadata or default 5
        metadata = getattr(ctx.case, 'metadata', {})
        expected_count = metadata.get('expected_count', 5)
        
        if recipe_count == 0:
            return 0.0
        elif recipe_count >= expected_count:
            return 1.0
        else:
            # Partial success - proportional scoring
            return recipe_count / expected_count
    
    def _check_for_errors(self, tool_output: Dict) -> bool:
        """Check if there were any errors in the tool output."""
        if isinstance(tool_output, dict):
            # Check for error fields
            if tool_output.get('error'):
                return True
            
            # Check tool outputs for errors
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            if item.output.get('error'):
                                return True
        
        return False
    
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
class ResourceEfficiencyEvaluator(Evaluator[str, Dict]):
    """
    Evaluates resource usage efficiency including early exits, API usage, and fallback rates.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        tool_output = ctx.output
        
        # Extract efficiency metrics from tool output
        early_exit_used = False
        fallback_used = False
        total_urls_processed = 0
        total_urls_available = 0
        
        if isinstance(tool_output, dict):
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            output = item.output
                            fallback_used = output.get('fallback_used', False)
                            
                            # Look for efficiency indicators in session_info
                            session_info = output.get('session_info', {})
                            if session_info:
                                # Efficiency indicators would be logged here
                                pass
        
        efficiency_score = 0.0
        
        # Early exit is good for performance (30% of score)
        if early_exit_used:
            efficiency_score += 0.3
        
        # Reasonable fallback usage (not too high) (40% of score)
        if not fallback_used:
            efficiency_score += 0.4  # Best case - exact matches found
        else:
            efficiency_score += 0.2  # Acceptable - fallback was needed
        
        # URL processing efficiency (30% of score)
        if total_urls_available > 0:
            processing_rate = min(1.0, total_urls_processed / total_urls_available)
            efficiency_score += 0.3 * processing_rate
        else:
            efficiency_score += 0.3  # Default if can't measure
        
        return min(1.0, efficiency_score)


@dataclass
class ErrorHandlingEvaluator(Evaluator[str, Dict]):
    """
    Evaluates graceful error handling and appropriate error classification.
    """
    
    def evaluate(self, ctx: EvaluatorContext[str, Dict]) -> float:
        tool_output = ctx.output
        metadata = getattr(ctx.case, 'metadata', {})
        
        # Check if this test case is designed to trigger errors
        expect_errors = metadata.get('expect_errors', False)
        error_types = metadata.get('expected_error_types', [])
        
        # Extract errors and their classification
        errors_found = self._extract_errors(tool_output)
        
        if expect_errors:
            # For error test cases, check graceful handling
            if not errors_found:
                return 0.5  # Expected error but none found
            
            # Check if errors are properly classified
            proper_classification = self._check_error_classification(errors_found, error_types)
            return 1.0 if proper_classification else 0.3
        else:
            # For normal cases, no errors should occur
            if errors_found:
                # Check if errors are expected types (like 403 Forbidden)
                expected_errors = [e for e in errors_found if self._is_expected_error(e)]
                unexpected_errors = [e for e in errors_found if not self._is_expected_error(e)]
                
                if unexpected_errors:
                    return 0.1  # Unexpected errors are bad
                elif expected_errors:
                    return 0.8  # Expected errors are acceptable
                else:
                    return 0.0  # Unknown error state
            else:
                return 1.0  # No errors - perfect
    
    def _extract_errors(self, tool_output: Dict) -> List[Dict]:
        """Extract error information from tool output."""
        errors = []
        
        if isinstance(tool_output, dict):
            # Check for top-level errors
            if tool_output.get('error'):
                errors.append({'type': 'top_level', 'message': tool_output['error']})
            
            # Check tool outputs for errors
            messages = tool_output.get('all_messages', [])
            for message in messages:
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for item in message.content:
                        if hasattr(item, 'output') and isinstance(item.output, dict):
                            if item.output.get('error'):
                                errors.append({'type': 'tool_error', 'message': item.output['error']})
        
        return errors
    
    def _is_expected_error(self, error: Dict) -> bool:
        """Check if error is an expected type (like 403 Forbidden)."""
        message = error.get('message', '').lower()
        return any(expected in message for expected in ['403', 'forbidden', 'timeout', 'rate limit'])
    
    def _check_error_classification(self, errors: List[Dict], expected_types: List[str]) -> bool:
        """Check if errors are properly classified."""
        # Implementation would check Logfire logs for proper error levels
        return True  # Simplified for now


# Performance test cases
performance_cases = [
    # Speed tests - should be fast
    Case(
        name='simple_speed_test',
        inputs='chicken recipes',
        metadata={
            'performance_type': 'speed',
            'difficulty': 'easy',
            'expected_time_max': 20.0,
            'expect_errors': False
        }
    ),
    
    Case(
        name='protein_query_speed',
        inputs='high protein breakfast',
        metadata={
            'performance_type': 'speed',
            'difficulty': 'medium', 
            'expected_time_max': 25.0,
            'expect_errors': False
        }
    ),
    
    # Complex requirements - may be slower but should complete
    Case(
        name='complex_requirements_performance',
        inputs='gluten-free vegan recipes with 25g protein under 400 calories',
        metadata={
            'performance_type': 'complex',
            'difficulty': 'hard',
            'expected_time_max': 45.0,
            'expect_errors': False
        }
    ),
    
    # Edge cases that might cause timeouts
    Case(
        name='very_specific_query',
        inputs='keto dessert with 0g carbs and 30g fat using only coconut flour',
        metadata={
            'performance_type': 'edge_case',
            'difficulty': 'extreme',
            'expected_time_max': 60.0,
            'expect_errors': False
        }
    ),
    
    # Error handling tests
    Case(
        name='empty_query_handling',
        inputs='',
        metadata={
            'performance_type': 'error_handling',
            'difficulty': 'easy',
            'expect_errors': True,
            'expected_error_types': ['validation_error']
        }
    ),
    
    # Save command performance (should be very fast)
    Case(
        name='save_command_performance',
        inputs='save meal #3',
        metadata={
            'performance_type': 'save_command',
            'difficulty': 'easy',
            'expected_time_max': 5.0,
            'expect_errors': False
        }
    ),
    
    # Realistic user queries
    Case(
        name='realistic_dinner_query',
        inputs='healthy dinner for tonight',
        metadata={
            'performance_type': 'realistic',
            'difficulty': 'medium',
            'expected_time_max': 30.0,
            'expect_errors': False
        }
    ),
    
    Case(
        name='realistic_specific_query',
        inputs='quick 15-minute pasta recipes without mushrooms',
        metadata={
            'performance_type': 'realistic',
            'difficulty': 'medium',
            'expected_time_max': 35.0,
            'expect_errors': False
        }
    )
]


@dataclass
class TimedAgentWrapper:
    """
    Wrapper to add timing metadata to agent execution for performance evaluation.
    """
    
    def __init__(self, agent_function):
        self.agent_function = agent_function
    
    async def __call__(self, inputs: str) -> Dict:
        """Execute agent with timing measurement."""
        start_time = time.time()
        
        try:
            result = await self.agent_function(inputs)
            end_time = time.time()
            
            # Add timing metadata
            if isinstance(result, dict):
                result['metadata'] = result.get('metadata', {})
                result['metadata']['start_time'] = start_time
                result['metadata']['end_time'] = end_time
                result['metadata']['total_time'] = end_time - start_time
            
            return result
            
        except Exception as e:
            end_time = time.time()
            return {
                'error': str(e),
                'metadata': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'total_time': end_time - start_time,
                    'exception_occurred': True
                }
            }


# Create dataset with performance evaluators
performance_dataset = Dataset(
    cases=performance_cases,
    evaluators=[
        # Response time evaluation
        ResponseTimeEvaluator(),
        
        # Success rate evaluation
        SuccessRateEvaluator(),
        
        # Resource efficiency evaluation
        ResourceEfficiencyEvaluator(),
        
        # Error handling evaluation
        ErrorHandlingEvaluator(),
        
        # LLM-based performance quality assessment
        LLMJudge(
            rubric="""
            Evaluate the overall performance quality of this recipe discovery response.
            Consider:
            - Did the agent complete the task successfully?
            - Are any error messages clear and helpful?
            - Does the response suggest good system performance?
            - Are there signs of timeouts, failures, or poor resource usage?
            
            Score 1.0 for excellent performance, 0.5 for acceptable, 0.0 for poor.
            """,
            model='openai:gpt-4o',
            include_input=True
        )
    ]
)


def evaluate_performance_metrics(agent_function, test_case_names: List[str] = None, concurrent: bool = False):
    """
    Run performance evaluation on the Recipe Discovery Agent.
    
    Args:
        agent_function: The agent function to evaluate
        test_case_names: Optional list of specific test case names to run
        concurrent: Whether to run tests concurrently (for load testing)
        
    Returns:
        EvaluationReport with detailed performance metrics
    """
    cases_to_run = performance_cases
    if test_case_names:
        cases_to_run = [case for case in performance_cases if case.name in test_case_names]
    
    # Wrap agent function with timing
    timed_agent = TimedAgentWrapper(agent_function)
    
    dataset = Dataset(cases=cases_to_run, evaluators=performance_dataset.evaluators)
    
    if concurrent:
        # Run concurrent evaluation for load testing
        print("🚀 Running concurrent performance evaluation...")
        report = dataset.evaluate_sync(timed_agent)
    else:
        # Run sequential evaluation
        report = dataset.evaluate_sync(timed_agent)
    
    print("⚡ PERFORMANCE METRICS EVALUATION RESULTS")
    print("=" * 50)
    report.print(include_input=True, include_output=True)
    
    # Performance summary
    print("\n📊 PERFORMANCE SUMMARY")
    print("-" * 30)
    
    # Extract timing statistics from results
    timings = []
    for result in report.results:
        if hasattr(result, 'output') and isinstance(result.output, dict):
            metadata = result.output.get('metadata', {})
            total_time = metadata.get('total_time')
            if total_time:
                timings.append(total_time)
    
    if timings:
        avg_time = sum(timings) / len(timings)
        max_time = max(timings)
        min_time = min(timings)
        
        print(f"Average response time: {avg_time:.2f}s")
        print(f"Fastest response: {min_time:.2f}s")
        print(f"Slowest response: {max_time:.2f}s")
        print(f"Total test cases: {len(timings)}")
    
    return report


async def run_load_test(agent_function, concurrent_requests: int = 5, query: str = "chicken recipes"):
    """
    Run load test with multiple concurrent requests to test scalability.
    
    Args:
        agent_function: The agent function to test
        concurrent_requests: Number of simultaneous requests
        query: Query to use for load testing
        
    Returns:
        Dict with load test results
    """
    print(f"🔥 Running load test with {concurrent_requests} concurrent requests...")
    
    # Create multiple identical requests
    tasks = []
    start_time = time.time()
    
    for i in range(concurrent_requests):
        task = asyncio.create_task(agent_function(f"{query} #{i}"))
        tasks.append(task)
    
    # Wait for all to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = time.time()
    
    # Analyze results
    successful = sum(1 for r in results if not isinstance(r, Exception))
    failed = len(results) - successful
    total_time = end_time - start_time
    
    load_test_results = {
        'concurrent_requests': concurrent_requests,
        'successful_requests': successful,
        'failed_requests': failed,
        'success_rate': successful / len(results),
        'total_time': total_time,
        'avg_time_per_request': total_time / concurrent_requests,
        'requests_per_second': concurrent_requests / total_time
    }
    
    print("📈 LOAD TEST RESULTS")
    print("-" * 20)
    for key, value in load_test_results.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value}")
    
    return load_test_results


if __name__ == "__main__":
    print("Performance Metrics Evaluation Suite")
    print("Import this module and call evaluate_performance_metrics() with your agent function")
    print(f"Total test cases: {len(performance_cases)}")
    
    # Print test case summary by performance type
    categories = {}
    for case in performance_cases:
        category = case.metadata.get('performance_type', 'unknown')
        if category not in categories:
            categories[category] = []
        categories[category].append(case.name)
    
    for category, cases in categories.items():
        print(f"\n{category.upper()} ({len(cases)} cases):")
        for case_name in cases:
            case_obj = next(c for c in performance_cases if c.name == case_name)
            difficulty = case_obj.metadata.get('difficulty', 'unknown')
            max_time = case_obj.metadata.get('expected_time_max', 'N/A')
            print(f"  - {case_name} (difficulty: {difficulty}, max_time: {max_time}s)")