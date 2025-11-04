"""
Apify Recipe Scraper Actor Test
Test the web.harvester~recipes-scraper actor performance against Google search results.
"""

import asyncio
import httpx
import json
import os
import time
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class ApifyActorTester:
    """Test Apify recipe scraper actor with Google search results."""
    
    def __init__(self):
        """Initialize with API credentials."""
        self.google_key = os.getenv("GOOGLE_SEARCH_KEY")
        self.google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID") 
        self.apify_token = os.getenv("APIFY_API_KEY")
        
        if not all([self.google_key, self.google_cx, self.apify_token]):
            raise ValueError("Missing required API keys: GOOGLE_SEARCH_KEY, GOOGLE_SEARCH_ENGINE_ID, APIFY_API_KEY")
    
    async def test_actor_performance(self, query: str = "cheesecake recipes", url_count: int = 50) -> Dict:
        """
        Test Apify actor performance with Google search results.
        
        Args:
            query: Search query for recipes
            url_count: Number of URLs to test
            
        Returns:
            Performance analysis and detailed results
        """
        print("=" * 80)
        print("🧪 APIFY RECIPE SCRAPER ACTOR TEST")
        print("=" * 80)
        print(f"📝 Query: '{query}'")
        print(f"🎯 Testing: {url_count} recipe URLs")
        print("-" * 80)
        
        start_time = time.time()
        
        # STEP 1: Get recipe URLs from Google search
        print("🔍 STEP 1: Fetching recipe URLs from Google Custom Search...")
        search_start = time.time()
        
        recipe_urls = await self._get_recipe_urls_from_search(query, url_count)
        search_elapsed = time.time() - search_start
        
        if not recipe_urls:
            return {"error": "No URLs found from search"}
        
        print(f"   ✅ Found {len(recipe_urls)} recipe URLs in {search_elapsed:.1f}s")
        print()
        
        # STEP 2: Test URLs with Apify recipe scraper actor
        print("🎭 STEP 2: Testing URLs with Apify recipe scraper actor...")
        actor_start = time.time()
        
        actor_results = await self._test_urls_with_apify_actor(recipe_urls)
        actor_elapsed = time.time() - actor_start
        
        print(f"   ✅ Actor processing completed in {actor_elapsed:.1f}s")
        print()
        
        # STEP 3: Analyze results and generate report
        print("📊 STEP 3: Analyzing success vs failure metrics...")
        analysis = self._analyze_actor_results(actor_results, recipe_urls)
        
        total_elapsed = time.time() - start_time
        
        # Print comprehensive report
        self._print_performance_report(analysis, total_elapsed, search_elapsed, actor_elapsed)
        
        return {
            "analysis": analysis,
            "timing": {
                "total_seconds": round(total_elapsed, 1),
                "search_seconds": round(search_elapsed, 1), 
                "actor_seconds": round(actor_elapsed, 1)
            },
            "actor_results": actor_results
        }
    
    async def _get_recipe_urls_from_search(self, query: str, count: int) -> List[Dict]:
        """Get recipe URLs using Google Custom Search API (same as agent)."""
        
        # Auto-append "recipes" if not present
        if "recipe" not in query.lower():
            query = f"{query} recipes"
        
        print(f"   📝 Search Query: '{query}'")
        print(f"   🔍 Using Custom Search Engine: {self.google_cx}")
        
        all_results = []
        results_per_page = 10
        total_pages = min((count + results_per_page - 1) // results_per_page, 5)  # Max 5 pages (50 results)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create parallel pagination tasks (same as agent)
            search_tasks = []
            for page in range(total_pages):
                start_position = (page * 10) + 1  # Google pagination: 1, 11, 21, 31, 41
                
                task = self._google_search_single_page(
                    client, query, start_position
                )
                search_tasks.append(task)
                print(f"      📄 Page {page + 1}: Results {start_position}-{start_position + 9}")
            
            # Execute all pages in parallel
            page_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Combine results
            for page_num, results in enumerate(page_results, 1):
                if isinstance(results, Exception):
                    print(f"      ⚠️ Page {page_num} failed: {results}")
                    continue
                    
                valid_results = [r for r in results if r.get('url')]
                all_results.extend(valid_results)
                print(f"      ✅ Page {page_num}: {len(valid_results)} URLs")
        
        # Remove duplicates
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        print(f"   🎯 Total unique URLs: {len(unique_results)}")
        return unique_results[:count]  # Ensure we don't exceed requested count
    
    async def _google_search_single_page(self, client: httpx.AsyncClient, query: str, start_position: int) -> List[Dict]:
        """Execute single Google CSE API call for one page."""
        params = {
            "key": self.google_key,
            "cx": self.google_cx,
            "q": query,
            "num": 10,
            "start": start_position,
            "gl": "us",
            "hl": "en",
            "safe": "active"
        }
        
        try:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("items", []):
                results.append({
                    "url": item.get("link"),
                    "title": item.get("title"),
                    "snippet": item.get("snippet", "")
                })
            
            return results
            
        except Exception as e:
            print(f"      ❌ Search page {start_position} failed: {e}")
            return []
    
    async def _test_urls_with_apify_actor(self, urls: List[Dict]) -> Dict:
        """Send URLs to Apify recipe scraper actor for batch processing."""
        
        # Extract just the URLs for actor input
        url_list = [url_data.get("url") for url_data in urls if url_data.get("url")]
        
        print(f"   📋 Sending {len(url_list)} URLs to Apify actor...")
        
        # Apify actor input format - try minimal first
        actor_input = {
            "startUrls": url_list[:5]  # Test with just 5 URLs first to debug
        }
        
        print(f"   🔍 DEBUG: Actor input sample: {json.dumps(actor_input, indent=2)[:200]}...")
        print(f"   🔍 DEBUG: API endpoint: web.harvester~recipes-scraper")
        
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5min timeout for batch processing
            try:
                # Try different endpoint format - maybe the actor ID needs forward slash
                endpoint_url = f"https://api.apify.com/v2/acts/web.harvester/recipes-scraper/run-sync-get-dataset-items?token={self.apify_token}"
                print(f"   🔍 DEBUG: Full endpoint URL: {endpoint_url}")
                
                response = await client.post(
                    endpoint_url,
                    json=actor_input,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                # Response should be array of scraped recipe data
                results = response.json()
                
                print(f"   ✅ Actor returned {len(results) if isinstance(results, list) else 'unknown'} results")
                return {
                    "success": True,
                    "results": results,
                    "total_results": len(results) if isinstance(results, list) else 0
                }
                
            except Exception as e:
                print(f"   ❌ Apify actor failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "results": [],
                    "total_results": 0
                }
    
    def _analyze_actor_results(self, actor_results: Dict, original_urls: List[Dict]) -> Dict:
        """Analyze actor performance and create detailed metrics."""
        
        if not actor_results.get("success"):
            return {
                "total_urls_tested": len(original_urls),
                "successful_extractions": 0,
                "failed_extractions": len(original_urls),
                "success_rate": 0.0,
                "error": actor_results.get("error", "Unknown actor error")
            }
        
        actor_data = actor_results.get("results", [])
        
        # Create URL mapping for analysis
        original_url_set = {url_data.get("url") for url_data in original_urls}
        
        # Analyze successful extractions
        successful_urls = set()
        failed_urls = set()
        
        if isinstance(actor_data, list):
            for result in actor_data:
                if isinstance(result, dict):
                    source_url = result.get("url") or result.get("source_url") or result.get("sourceUrl")
                    if source_url and source_url in original_url_set:
                        # Check if result has required recipe data
                        if self._has_required_recipe_data(result):
                            successful_urls.add(source_url)
                        else:
                            failed_urls.add(source_url)
        
        # Any URLs not in results are failures
        unprocessed_urls = original_url_set - successful_urls - failed_urls
        failed_urls.update(unprocessed_urls)
        
        success_rate = len(successful_urls) / len(original_urls) * 100
        
        return {
            "total_urls_tested": len(original_urls),
            "successful_extractions": len(successful_urls),
            "failed_extractions": len(failed_urls),
            "success_rate": round(success_rate, 1),
            "successful_urls": list(successful_urls),
            "failed_urls": list(failed_urls),
            "successful_domains": [self._extract_domain(url) for url in successful_urls],
            "failed_domains": [self._extract_domain(url) for url in failed_urls]
        }
    
    def _has_required_recipe_data(self, result: Dict) -> bool:
        """Check if actor result has minimum required recipe data."""
        # Basic check - actor should return title and ingredients at minimum
        title = result.get("title") or result.get("name")
        ingredients = result.get("ingredients") or result.get("recipeIngredient")
        
        return bool(title and ingredients)
    
    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"
    
    def _print_performance_report(self, analysis: Dict, total_time: float, search_time: float, actor_time: float):
        """Print comprehensive performance report."""
        
        print("=" * 80)
        print("📊 APIFY ACTOR PERFORMANCE REPORT")
        print("=" * 80)
        
        # High-level metrics
        print(f"🎯 Success Rate: {analysis['success_rate']}% ({analysis['successful_extractions']}/{analysis['total_urls_tested']} URLs)")
        print(f"⏱️  Total Time: {total_time:.1f}s")
        print(f"   🔍 Search Time: {search_time:.1f}s")
        print(f"   🎭 Actor Time: {actor_time:.1f}s")
        print()
        
        # Success analysis
        if analysis['successful_extractions'] > 0:
            print(f"✅ SUCCESSFUL SITES ({analysis['successful_extractions']} sites):")
            for domain in analysis.get('successful_domains', [])[:10]:  # Show first 10
                print(f"   • {domain}")
            if len(analysis.get('successful_domains', [])) > 10:
                print(f"   • ... and {len(analysis.get('successful_domains', [])) - 10} more")
            print()
        
        # Failure analysis
        if analysis['failed_extractions'] > 0:
            print(f"❌ FAILED SITES ({analysis['failed_extractions']} sites):")
            for domain in analysis.get('failed_domains', [])[:15]:  # Show first 15
                print(f"   • {domain}")
            if len(analysis.get('failed_domains', [])) > 15:
                print(f"   • ... and {len(analysis.get('failed_domains', [])) - 15} more")
            print()
        
        # Performance assessment
        if analysis['success_rate'] >= 80:
            assessment = "🎉 EXCELLENT"
        elif analysis['success_rate'] >= 60:
            assessment = "✅ GOOD"
        elif analysis['success_rate'] >= 40:
            assessment = "⚠️ ACCEPTABLE"
        else:
            assessment = "❌ POOR"
        
        print(f"📈 Performance Assessment: {assessment}")
        print(f"💰 Cost Efficiency: {analysis['successful_extractions']} recipes extracted per actor run")
        
        # Recommendation
        if analysis['success_rate'] >= 60:
            print("🎯 Recommendation: Apify actor is viable for production use")
        else:
            print("🎯 Recommendation: Consider building custom parser or hybrid approach")
        
        print("=" * 80)


async def main():
    """Interactive CLI for testing Apify actor."""
    print("🧪 Apify Recipe Scraper Actor Tester")
    print("Press Ctrl+C to exit\n")
    
    tester = ApifyActorTester()
    
    while True:
        try:
            # Get user input
            query = input("Enter search query (default: 'cheesecake recipes'): ").strip()
            if not query:
                query = "cheesecake recipes"
            
            url_count_input = input("Enter number of URLs to test (default: 50): ").strip()
            try:
                url_count = int(url_count_input) if url_count_input else 50
                url_count = min(max(url_count, 1), 100)  # Clamp between 1-100
            except ValueError:
                url_count = 50
            
            # Run test
            result = await tester.test_actor_performance(query, url_count)
            
            # Ask for another test
            print()
            another = input("Test another query? (y/n): ").strip().lower()
            if another not in ['y', 'yes']:
                break
            print()
            
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            break


if __name__ == "__main__":
    asyncio.run(main())