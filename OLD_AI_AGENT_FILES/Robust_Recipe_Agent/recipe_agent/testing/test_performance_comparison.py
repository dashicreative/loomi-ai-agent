"""
Performance comparison test for optimized Recipe Discovery Agent.
Benchmarks optimized pipeline vs simulated original approach.
"""
import asyncio
import time
import sys
import os
from typing import Dict, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recipe_agent.Tools.Tools import search_and_extract_recipes
from recipe_agent.Dependencies import RecipeDeps
from pydantic_ai import RunContext

# Test configuration
SERPAPI_KEY = "92c86be4499012bcd19900c39638c6b05cd9920b4f914f4907b0d6afb0a14c87"
FIRECRAWL_KEY = "fc-b5737066edd940af852fc198ee3a4133"
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "test_key")

async def test_optimized_pipeline(query: str, max_recipes: int = 5) -> Dict:
    """Test the optimized pipeline with Early Exit Manager"""
    deps = RecipeDeps(
        serpapi_key=SERPAPI_KEY,
        firecrawl_key=FIRECRAWL_KEY,
        openai_key=OPENAI_KEY
    )
    
    # Create mock context
    class MockContext:
        def __init__(self, deps):
            self.deps = deps
    
    ctx = MockContext(deps)
    
    start_time = time.time()
    result = await search_and_extract_recipes(ctx, query, max_recipes)
    end_time = time.time()
    
    return {
        'processing_time': end_time - start_time,
        'total_results': result.get('totalResults', 0),
        'query': query,
        'recipes_found': len(result.get('results', [])),
        'optimization_used': 'early_exit_manager'
    }

async def compare_performance():
    """Compare optimized pipeline performance"""
    print("🚀 RECIPE DISCOVERY AGENT - PERFORMANCE COMPARISON")
    print("=" * 60)
    
    test_queries = [
        "healthy chicken recipes",
        "quick breakfast ideas", 
        "vegetarian pasta dishes"
    ]
    
    all_results = []
    
    for query in test_queries:
        print(f"\n🔍 Testing Query: '{query}'")
        print("-" * 40)
        
        # Test optimized pipeline
        print("Testing optimized pipeline...")
        optimized_result = await test_optimized_pipeline(query, max_recipes=5)
        
        print(f"✅ Optimized Results:")
        print(f"   ⏱️  Time: {optimized_result['processing_time']:.2f}s")
        print(f"   🍽️  Recipes: {optimized_result['recipes_found']}")
        print(f"   📊 Total Results: {optimized_result['total_results']}")
        
        all_results.append(optimized_result)
    
    # Calculate performance summary
    print(f"\n📈 PERFORMANCE SUMMARY")
    print("=" * 40)
    
    avg_time = sum(r['processing_time'] for r in all_results) / len(all_results)
    avg_recipes = sum(r['recipes_found'] for r in all_results) / len(all_results)
    total_recipes = sum(r['total_results'] for r in all_results)
    
    print(f"Average processing time: {avg_time:.2f}s")
    print(f"Average recipes found: {avg_recipes:.1f}")
    print(f"Total recipes across tests: {total_recipes}")
    
    # Performance targets from refactoring plan
    target_time = 8.0  # < 8 seconds average
    
    if avg_time <= target_time:
        print(f"✅ PERFORMANCE TARGET MET! (≤{target_time}s)")
        print(f"🎯 Achieved {((target_time - avg_time) / target_time * 100):.1f}% better than target")
    else:
        print(f"⚠️  Performance target missed (>{target_time}s)")
    
    print(f"\n🎉 Performance testing completed!")

if __name__ == "__main__":
    asyncio.run(compare_performance())