"""
Recipe Discovery Agent Evaluation Suite

Comprehensive evaluation framework for testing response quality, recipe accuracy,
and performance metrics using Pydantic AI evaluation tools.

Usage:
    from evals.response_quality_eval import evaluate_response_quality
    from evals.recipe_accuracy_eval import evaluate_recipe_accuracy  
    from evals.performance_metrics_eval import evaluate_performance_metrics
    
    # Run individual evaluations
    response_report = evaluate_response_quality(your_agent_function)
    accuracy_report = evaluate_recipe_accuracy(your_agent_function)
    performance_report = evaluate_performance_metrics(your_agent_function)
"""

from .response_quality_eval import evaluate_response_quality, response_quality_dataset
from .recipe_accuracy_eval import evaluate_recipe_accuracy, recipe_accuracy_dataset
from .performance_metrics_eval import evaluate_performance_metrics, performance_dataset, run_load_test

__all__ = [
    'evaluate_response_quality',
    'evaluate_recipe_accuracy', 
    'evaluate_performance_metrics',
    'run_load_test',
    'response_quality_dataset',
    'recipe_accuracy_dataset', 
    'performance_dataset'
]