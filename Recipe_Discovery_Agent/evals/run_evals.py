"""
Simple evaluation runner - just hit "play" to run evaluations!

Choose which evaluation to run by uncommenting the desired section.
"""

from agent_wrapper import agent_for_evaluation_sync
from response_quality_eval import evaluate_response_quality
from recipe_accuracy_eval import evaluate_recipe_accuracy  
from performance_metrics_eval import evaluate_performance_metrics

def main():
    print("🎯 Recipe Discovery Agent Evaluation Runner")
    print("=" * 50)
    
    # OPTION 1: Run single response quality test (fast)
    print("\n1️⃣ Running Response Quality Test...")
    evaluate_response_quality(agent_for_evaluation_sync, ['simple_food_query'])
    
    # OPTION 2: Run single recipe accuracy test (medium speed)
    # print("\n2️⃣ Running Recipe Accuracy Test...")
    # evaluate_recipe_accuracy(agent_for_evaluation_sync, ['high_protein_requirement'])
    
    # OPTION 3: Run single performance test (slow - actual agent execution)
    # print("\n3️⃣ Running Performance Test...")
    # evaluate_performance_metrics(agent_for_evaluation_sync, ['simple_speed_test'])
    
    # OPTION 4: Run ALL tests (very slow - full evaluation suite)
    # print("\n🚀 Running ALL Evaluations...")
    # evaluate_response_quality(agent_for_evaluation_sync)
    # evaluate_recipe_accuracy(agent_for_evaluation_sync) 
    # evaluate_performance_metrics(agent_for_evaluation_sync)
    
    print("\n✅ Evaluation completed!")

if __name__ == "__main__":
    main()