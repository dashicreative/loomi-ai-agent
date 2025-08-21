"""
Comprehensive test for Recipe Quality Scorer with real recipe data from SerpAPI.
Tests scoring accuracy, binary requirements, and early exit decision making.
"""
import asyncio
import sys
import os
import httpx
import time
from typing import List, Dict

# Add parent directory to path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Tools.quality_scorer import RecipeQualityScorer, QualityScore
from Tools.Detailed_Recipe_Parsers.Parsers import parse_recipe

# SerpAPI configuration
SERPAPI_KEY = "92c86be4499012bcd19900c39638c6b05cd9920b4f914f4907b0d6afb0a14c87"
FIRECRAWL_KEY = "fc-b5737066edd940af852fc198ee3a4133"  # For recipe parsing

class QualityScorerTester:
    """Comprehensive tester for Recipe Quality Scorer using real data"""
    
    def __init__(self):
        self.scorer = RecipeQualityScorer()
        self.test_results = {
            'total_tested': 0,
            'passed_binary_check': 0,
            'failed_binary_check': 0,
            'high_quality_recipes': 0,
            'low_quality_recipes': 0,
            'priority_site_bonuses': 0,
            'nutrition_data_found': 0
        }
    
    async def search_recipes_serpapi(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search for recipes using SerpAPI"""
        print(f"🔍 Searching SerpAPI for: '{query}'")
        
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
                for result in organic_results:
                    url = result.get("link", "")
                    if url:
                        formatted_results.append({
                            "title": result.get("title", ""),
                            "url": url,
                            "snippet": result.get("snippet", ""),
                            "source": "serpapi"
                        })
                
                print(f"✅ Found {len(formatted_results)} recipe URLs")
                return formatted_results
                
            except Exception as e:
                print(f"❌ SerpAPI search failed: {e}")
                return []
    
    async def parse_and_score_recipes(self, search_results: List[Dict], query: str) -> List[Dict]:
        """Parse recipes and score them for quality"""
        print(f"\n📊 Parsing and scoring {len(search_results)} recipes...")
        
        scored_recipes = []
        
        for i, result in enumerate(search_results[:8]):  # Test first 8 for reasonable runtime
            url = result['url']
            print(f"\n--- Recipe {i+1}/8: {result['title'][:60]}... ---")
            print(f"URL: {url}")
            
            # Parse the recipe
            recipe_data = await parse_recipe(url, FIRECRAWL_KEY)
            
            if recipe_data.get("error"):
                print(f"❌ Parsing failed: {recipe_data.get('error')}")
                continue
            
            # Add URL to recipe data for priority site scoring
            recipe_data['source_url'] = url
            
            # Score the recipe
            score = self.scorer.score_recipe(recipe_data, query)
            
            # Update test statistics
            self.test_results['total_tested'] += 1
            
            if score.has_required_data:
                self.test_results['passed_binary_check'] += 1
                print(f"✅ PASSED binary check (has all required fields)")
            else:
                self.test_results['failed_binary_check'] += 1
                print(f"❌ FAILED binary check - missing required fields")
                print(f"   Rejection reason: {score.details.get('rejected', 'Unknown')}")
                continue
            
            if score.total_score >= 0.7:
                self.test_results['high_quality_recipes'] += 1
                print(f"⭐ HIGH QUALITY recipe (score: {score.total_score:.3f})")
            else:
                self.test_results['low_quality_recipes'] += 1
                print(f"📊 Standard quality recipe (score: {score.total_score:.3f})")
            
            # Check scoring components
            print(f"   📈 Score Breakdown:")
            print(f"      • Relevance (70%): {score.relevance_score:.3f}")
            print(f"      • Data Quality (15%): {score.data_quality_score:.3f}")
            
            if score.details.get('priority_site', 0) > 0:
                self.test_results['priority_site_bonuses'] += 1
                site_name = score.details.get('priority_site_name', 'unknown')
                print(f"      • Priority Site Bonus: {site_name} ⭐")
            
            if score.details.get('nutrition_present', 0) > 0:
                self.test_results['nutrition_data_found'] += 1
                nutrition_score = score.details.get('nutrition_present', 0)
                print(f"      • Nutrition Data: {nutrition_score:.1%} complete")
            
            # Store complete result
            scored_recipes.append({
                'recipe_data': recipe_data,
                'score': score,
                'search_result': result
            })
        
        return scored_recipes
    
    def test_early_exit_decision(self, scored_recipes: List[Dict], quality_threshold: float = 0.7) -> Dict:
        """Test early exit decision making"""
        print(f"\n🚪 Testing Early Exit Decision (threshold: {quality_threshold})")
        
        high_quality_count = 0
        recipes_processed = 0
        
        for recipe_info in scored_recipes:
            recipes_processed += 1
            score = recipe_info['score']
            
            if score.has_required_data and score.total_score >= quality_threshold:
                high_quality_count += 1
                print(f"   Recipe {recipes_processed}: ✅ High quality (score: {score.total_score:.3f})")
                
                # Early exit condition: 5 high-quality recipes
                if high_quality_count >= 5:
                    print(f"🎯 EARLY EXIT TRIGGERED! Found 5 high-quality recipes after processing {recipes_processed}")
                    break
            else:
                reason = "missing required fields" if not score.has_required_data else f"low score ({score.total_score:.3f})"
                print(f"   Recipe {recipes_processed}: ❌ Rejected ({reason})")
        
        return {
            'total_processed': recipes_processed,
            'high_quality_found': high_quality_count,
            'early_exit_triggered': high_quality_count >= 5,
            'processing_saved': max(0, len(scored_recipes) - recipes_processed)
        }
    
    def analyze_scoring_accuracy(self, scored_recipes: List[Dict], query: str):
        """Analyze scoring accuracy and component effectiveness"""
        print(f"\n🔬 Analyzing Scoring Accuracy for Query: '{query}'")
        
        if not scored_recipes:
            print("❌ No recipes to analyze")
            return
        
        # Sort by quality score
        sorted_recipes = sorted(scored_recipes, key=lambda x: x['score'].total_score, reverse=True)
        
        print(f"\n📊 Top 3 Scoring Recipes:")
        for i, recipe_info in enumerate(sorted_recipes[:3]):
            recipe = recipe_info['recipe_data']
            score = recipe_info['score']
            
            print(f"\n{i+1}. {recipe.get('title', 'No title')[:50]}...")
            print(f"   Total Score: {score.total_score:.3f}")
            print(f"   Relevance: {score.relevance_score:.3f}")
            print(f"   Has Image: {'✅' if recipe.get('image_url') else '❌'}")
            print(f"   Ingredients: {len(recipe.get('ingredients', []))} items")
            print(f"   Instructions: {'✅' if recipe.get('instructions') else '❌'}")
            
            # Check query relevance manually
            title_lower = recipe.get('title', '').lower()
            query_words = query.lower().split()
            matches = sum(1 for word in query_words if word in title_lower)
            print(f"   Title Relevance: {matches}/{len(query_words)} query words matched")
    
    def print_final_report(self):
        """Print comprehensive test report"""
        print(f"\n" + "="*60)
        print(f"📋 QUALITY SCORER TEST REPORT")
        print(f"="*60)
        
        stats = self.test_results
        
        print(f"🎯 Recipe Processing:")
        print(f"   Total Tested: {stats['total_tested']}")
        print(f"   Passed Binary Check: {stats['passed_binary_check']}")
        print(f"   Failed Binary Check: {stats['failed_binary_check']}")
        
        if stats['total_tested'] > 0:
            pass_rate = (stats['passed_binary_check'] / stats['total_tested']) * 100
            print(f"   Binary Pass Rate: {pass_rate:.1f}%")
        
        print(f"\n⭐ Quality Distribution:")
        print(f"   High Quality (≥0.7): {stats['high_quality_recipes']}")
        print(f"   Standard Quality (<0.7): {stats['low_quality_recipes']}")
        
        print(f"\n🎁 Bonus Features:")
        print(f"   Priority Site Bonuses: {stats['priority_site_bonuses']}")
        print(f"   Recipes with Nutrition Data: {stats['nutrition_data_found']}")
        
        # Scoring system validation
        print(f"\n✅ Scoring System Validation:")
        print(f"   Binary requirements enforced: {'✅' if stats['failed_binary_check'] > 0 else '⚠️  No failures to test'}")
        print(f"   Priority site detection: {'✅' if stats['priority_site_bonuses'] > 0 else '⚠️  No priority sites found'}")
        print(f"   Nutrition scoring: {'✅' if stats['nutrition_data_found'] > 0 else '⚠️  No nutrition data found'}")

async def run_comprehensive_test():
    """Run comprehensive quality scorer test"""
    print("🧪 RECIPE QUALITY SCORER COMPREHENSIVE TEST")
    print("="*50)
    
    tester = QualityScorerTester()
    
    # Test queries with different complexity
    test_queries = [
        "chicken breast high protein",
        "chocolate cake",
        "vegetarian pasta"
    ]
    
    all_scored_recipes = []
    
    for query in test_queries:
        print(f"\n🔍 Testing Query: '{query}'")
        print("-" * 40)
        
        # Search for recipes
        search_results = await tester.search_recipes_serpapi(query, num_results=6)
        
        if not search_results:
            print(f"❌ No search results for '{query}', skipping...")
            continue
        
        # Parse and score recipes  
        scored_recipes = await tester.parse_and_score_recipes(search_results, query)
        all_scored_recipes.extend(scored_recipes)
        
        # Test early exit logic
        early_exit_result = tester.test_early_exit_decision(scored_recipes)
        
        print(f"\n📊 Early Exit Results for '{query}':")
        print(f"   Processed: {early_exit_result['total_processed']}")
        print(f"   High Quality Found: {early_exit_result['high_quality_found']}")
        print(f"   Early Exit: {'✅' if early_exit_result['early_exit_triggered'] else '❌'}")
        print(f"   Processing Saved: {early_exit_result['processing_saved']} recipes")
        
        # Analyze scoring accuracy
        tester.analyze_scoring_accuracy(scored_recipes, query)
    
    # Final comprehensive report
    tester.print_final_report()
    
    print(f"\n🎉 Test completed! Processed {len(all_scored_recipes)} total recipes.")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())