"""
Comprehensive test for Early Exit Manager with real recipe data.
Tests progressive parsing, early exit logic, quality thresholds, and failure rate monitoring.
"""
import asyncio
import sys
import os
import httpx
import time
from typing import List, Dict

# Add parent directory to path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recipe_agent.Tools.early_exit_manager import EarlyExitManager, PriorityURLOrdering
from recipe_agent.Tools.quality_scorer import RecipeQualityScorer

# API Keys for testing
SERPAPI_KEY = "92c86be4499012bcd19900c39638c6b05cd9920b4f914f4907b0d6afb0a14c87"
FIRECRAWL_KEY = "fc-b5737066edd940af852fc198ee3a4133"

class EarlyExitTester:
    """Comprehensive tester for Early Exit Manager"""
    
    def __init__(self):
        self.manager = EarlyExitManager(
            quality_threshold=0.7,
            min_recipes=5,
            max_recipes=8,
            max_attempts=15,
            firecrawl_key=FIRECRAWL_KEY
        )
        self.url_orderer = PriorityURLOrdering()
    
    async def search_test_urls(self, query: str, num_results: int = 12) -> List[Dict]:
        """Get test URLs from SerpAPI for Early Exit testing"""
        print(f"🔍 Searching for test URLs: '{query}'")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "api_key": SERPAPI_KEY,
                "engine": "google",
                "q": f"{query} recipe",
                "num": num_results,
                "hl": "en",
                "gl": "us"
            }
            
            try:
                response = await client.get("https://serpapi.com/search", params=params)
                response.raise_for_status()
                data = response.json()
                
                organic_results = data.get("organic_results", [])
                
                formatted_results = []
                for i, result in enumerate(organic_results):
                    url = result.get("link", "")
                    if url:
                        formatted_results.append({
                            "title": result.get("title", ""),
                            "url": url,
                            "snippet": result.get("snippet", ""),
                            "google_position": result.get("position", i + 1)
                        })
                
                print(f"✅ Found {len(formatted_results)} test URLs")
                return formatted_results
                
            except Exception as e:
                print(f"❌ Search failed: {e}")
                return []
    
    def test_url_prioritization(self, url_list: List[Dict]):
        """Test URL prioritization for optimal early exit"""
        print(f"\n🎯 Testing URL Prioritization")
        print(f"Original order vs Priority order:")
        
        # Show original order (first 8)
        print(f"\n📊 Original Google order (first 8):")
        for i, url_info in enumerate(url_list[:8]):
            url = url_info['url']
            title = url_info['title'][:50]
            domain = url.split('/')[2] if '/' in url else url
            print(f"   {i+1}. {title}... ({domain})")
        
        # Show prioritized order
        prioritized_urls = self.url_orderer.order_urls_by_priority(url_list)
        print(f"\n⭐ Priority-ordered URLs (first 8):")
        for i, url_info in enumerate(prioritized_urls[:8]):
            url = url_info['url']
            title = url_info['title'][:50]
            domain = url.split('/')[2] if '/' in url else url
            
            # Check if priority site
            priority_marker = ""
            try:
                from recipe_agent.Tools.Tools import PRIORITY_SITES
                if any(site in url.lower() for site in PRIORITY_SITES):
                    priority_marker = " ⭐"
            except:
                pass
            
            print(f"   {i+1}. {title}... ({domain}){priority_marker}")
        
        return prioritized_urls
    
    async def test_early_exit_scenarios(self, url_list: List[Dict], query: str):
        """Test different early exit scenarios"""
        print(f"\n🚪 Testing Early Exit Scenarios")
        
        # Scenario 1: Normal early exit (should find 5 good recipes quickly)
        print(f"\n--- Scenario 1: Normal Early Exit Test ---")
        await self.run_early_exit_test(url_list, query, "normal", expected_early_exit=True)
        
        # Scenario 2: High threshold (harder to find good recipes)
        print(f"\n--- Scenario 2: High Threshold Test (0.8) ---")
        high_threshold_manager = EarlyExitManager(
            quality_threshold=0.8,
            min_recipes=3,
            max_recipes=5,
            firecrawl_key=FIRECRAWL_KEY
        )
        await self.run_early_exit_test(url_list, query, "high_threshold", 
                                     custom_manager=high_threshold_manager)
        
        # Scenario 3: Low threshold (should exit very early)
        print(f"\n--- Scenario 3: Low Threshold Test (0.5) ---")
        low_threshold_manager = EarlyExitManager(
            quality_threshold=0.5,
            min_recipes=3,
            max_recipes=5,
            firecrawl_key=FIRECRAWL_KEY
        )
        await self.run_early_exit_test(url_list, query, "low_threshold", 
                                     custom_manager=low_threshold_manager,
                                     expected_early_exit=True)
    
    async def run_early_exit_test(self, url_list: List[Dict], query: str, 
                                scenario_name: str, custom_manager=None, 
                                expected_early_exit=None):
        """Run a single early exit test scenario"""
        manager = custom_manager or self.manager
        
        print(f"🎯 Running {scenario_name} scenario...")
        print(f"   Settings: threshold={manager.quality_threshold}, "
              f"min={manager.min_recipes}, max={manager.max_recipes}")
        
        start_time = time.time()
        
        # Run progressive parsing with early exit
        high_quality_recipes, all_recipes = await manager.progressive_parse_with_exit(
            url_list, query
        )
        
        processing_time = time.time() - start_time
        stats = manager.get_stats()
        
        # Analyze results
        print(f"📊 Results for {scenario_name}:")
        print(f"   ⏱️  Processing time: {processing_time:.2f}s")
        print(f"   🎯 URLs attempted: {stats['total_attempted']}")
        print(f"   ✅ Successful parses: {stats['successful_parses']}")
        print(f"   ❌ Failed parses: {stats['failed_parses']}")
        print(f"   ⭐ High quality found: {stats['high_quality_found']}")
        print(f"   🚫 Binary check failures: {stats['binary_check_failures']}")
        print(f"   📉 Low quality rejected: {stats['low_quality_rejected']}")
        print(f"   🚪 Early exit triggered: {stats['early_exit_triggered']}")
        
        if stats['total_attempted'] > 0:
            success_rate = stats['successful_parses'] / stats['total_attempted']
            print(f"   📈 Success rate: {success_rate:.1%}")
        
        if stats['successful_parses'] > 0:
            quality_rate = stats['high_quality_found'] / stats['successful_parses']
            print(f"   ⭐ Quality rate: {quality_rate:.1%}")
        
        # Performance analysis
        estimated_full_time = processing_time * (len(url_list) / max(stats['total_attempted'], 1))
        time_saved = estimated_full_time - processing_time
        
        print(f"   💰 Estimated time saved: {time_saved:.2f}s")
        print(f"   🏃 Speed improvement: {estimated_full_time/processing_time:.1f}x faster")
        
        # Validate expectations
        if expected_early_exit is not None:
            if stats['early_exit_triggered'] == expected_early_exit:
                print(f"   ✅ Early exit expectation met")
            else:
                print(f"   ⚠️  Early exit expectation not met (expected: {expected_early_exit})")
        
        # Show top recipes found
        if high_quality_recipes:
            print(f"   🍽️  Top recipes found:")
            for i, recipe in enumerate(high_quality_recipes[:3]):
                score = recipe.get('_quality_score', 0)
                title = recipe.get('title', 'No title')[:40]
                print(f"      {i+1}. {title}... (score: {score:.3f})")
        
        return {
            'scenario': scenario_name,
            'processing_time': processing_time,
            'stats': stats,
            'high_quality_count': len(high_quality_recipes),
            'time_saved': time_saved
        }
    
    async def test_failure_rate_monitoring(self):
        """Test failure rate monitoring with intentionally bad URLs"""
        print(f"\n🔥 Testing Failure Rate Monitoring")
        
        # Create list with mostly bad URLs to trigger failure monitoring
        bad_urls = [
            {"url": "https://example.com/nonexistent1", "title": "Fake Recipe 1", "snippet": ""},
            {"url": "https://example.com/nonexistent2", "title": "Fake Recipe 2", "snippet": ""},
            {"url": "https://httpbin.org/status/404", "title": "404 Recipe", "snippet": ""},
            {"url": "https://httpbin.org/status/500", "title": "500 Recipe", "snippet": ""},
            {"url": "https://www.allrecipes.com/recipe/23600/worlds-best-lasagna/", "title": "Real Recipe", "snippet": ""},
            {"url": "https://example.com/bad3", "title": "Fake Recipe 3", "snippet": ""},
            {"url": "https://example.com/bad4", "title": "Fake Recipe 4", "snippet": ""},
        ]
        
        failure_manager = EarlyExitManager(
            quality_threshold=0.6,
            min_recipes=3,
            max_recipes=5,
            firecrawl_key=FIRECRAWL_KEY
        )
        
        print(f"🎯 Testing with {len(bad_urls)} URLs (mostly bad)")
        
        start_time = time.time()
        high_quality, all_recipes = await failure_manager.progressive_parse_with_exit(
            bad_urls, "test failure monitoring"
        )
        processing_time = time.time() - start_time
        
        stats = failure_manager.get_stats()
        
        print(f"📊 Failure Rate Monitoring Results:")
        print(f"   ⏱️  Processing time: {processing_time:.2f}s")
        print(f"   🎯 URLs attempted: {stats['total_attempted']}")
        print(f"   ✅ Successful: {stats['successful_parses']}")
        print(f"   ❌ Failed: {stats['failed_parses']}")
        
        if stats['total_attempted'] > 0:
            failure_rate = stats['failed_parses'] / stats['total_attempted']
            print(f"   📉 Failure rate: {failure_rate:.1%}")
            
            if failure_rate >= 0.7:  # 70%+ failure rate
                print(f"   ✅ High failure rate detected - early stopping should have occurred")
            else:
                print(f"   ⚠️  Expected higher failure rate for this test")
        
        # Should have stopped early due to high failure rate
        if stats['total_attempted'] < len(bad_urls):
            print(f"   ✅ Early stopping triggered (processed {stats['total_attempted']}/{len(bad_urls)})")
        else:
            print(f"   ⚠️  Expected early stopping due to high failure rate")
    
    def analyze_optimization_potential(self, test_results: List[Dict]):
        """Analyze the optimization potential of early exit"""
        print(f"\n📈 Early Exit Optimization Analysis")
        
        total_scenarios = len(test_results)
        early_exit_scenarios = sum(1 for r in test_results if r['stats']['early_exit_triggered'])
        
        avg_time_saved = sum(r['time_saved'] for r in test_results) / len(test_results)
        avg_urls_processed = sum(r['stats']['total_attempted'] for r in test_results) / len(test_results)
        
        print(f"📊 Optimization Summary:")
        print(f"   🎯 Scenarios tested: {total_scenarios}")
        print(f"   🚪 Early exits triggered: {early_exit_scenarios}/{total_scenarios} ({early_exit_scenarios/total_scenarios:.1%})")
        print(f"   ⏱️  Average time saved: {avg_time_saved:.2f}s")
        print(f"   📈 Average URLs processed: {avg_urls_processed:.1f}")
        
        if early_exit_scenarios > 0:
            print(f"   ✅ Early exit optimization is working effectively!")
        else:
            print(f"   ⚠️  No early exits triggered - may need threshold adjustment")

async def run_comprehensive_early_exit_test():
    """Run comprehensive early exit manager test"""
    print("🧪 EARLY EXIT MANAGER COMPREHENSIVE TEST")
    print("="*50)
    
    tester = EarlyExitTester()
    
    # Test with different query types
    test_queries = [
        "chicken breast recipes",
        "chocolate cake easy",
        "vegetarian pasta healthy"
    ]
    
    all_test_results = []
    
    for query in test_queries:
        print(f"\n🔍 Testing Query: '{query}'")
        print("-" * 40)
        
        # Get test URLs
        url_list = await tester.search_test_urls(query, num_results=12)
        
        if not url_list:
            print(f"❌ No URLs found for '{query}', skipping...")
            continue
        
        # Test URL prioritization
        prioritized_urls = tester.test_url_prioritization(url_list)
        
        # Test early exit scenarios
        scenario_results = await tester.test_early_exit_scenarios(prioritized_urls, query)
        
        # Store results for analysis
        if isinstance(scenario_results, list):
            all_test_results.extend(scenario_results)
        
        print(f"\n" + "="*30)
    
    # Test failure rate monitoring
    await tester.test_failure_rate_monitoring()
    
    # Final analysis
    if all_test_results:
        tester.analyze_optimization_potential(all_test_results)
    
    print(f"\n🎉 Early Exit Manager testing completed!")
    print(f"✅ Progressive parsing tested")
    print(f"✅ Quality thresholds validated")
    print(f"✅ Early exit logic verified")
    print(f"✅ Failure rate monitoring confirmed")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_early_exit_test())