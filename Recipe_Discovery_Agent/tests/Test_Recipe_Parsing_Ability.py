#!/usr/bin/env python3
"""
Test Recipe Parsing Performance Analyzer

This script tests the exact recipe parsing logic used in production,
allowing us to measure success rates, timing, and identify failure patterns
for different recipe websites.
"""

import asyncio
import time
import json
from typing import List, Dict, Optional
from datetime import datetime
import statistics
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Tools.Detailed_Recipe_Parsers.Parsers import parse_recipe
from Tools.Detailed_Recipe_Parsers.ingredient_parser import parse_ingredients_list
from Tools.Detailed_Recipe_Parsers.nutrition_parser import parse_nutrition_list
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test URLs from various recipe sites
TEST_URLS = {
    "Currently Failing URLs": [
        "https://www.delish.com/cooking/recipe-ideas/a21566115/how-to-cook-steak-in-the-oven/",
        "https://www.delish.com/cooking/recipe-ideas/a25658914/pepper-steak-recipe/",
        "https://www.seriouseats.com/butter-basted-pan-seared-steaks-recipe",
        "https://www.thepioneerwoman.com/food-cooking/recipes/a61827998/steak-diane-recipe/"
    ]
}

class RecipeParsingTester:
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
        self.results = {
            "total_tests": 0,
            "successful_parses": 0,
            "failed_parses": 0,
            "partial_parses": 0,
            "timing_data": [],
            "failures_by_site": {},
            "success_by_site": {},
            "detailed_results": []
        }
    
    async def test_single_url(self, url: str, category: str) -> Dict:
        """Test parsing a single URL and collect metrics."""
        print(f"\n{'='*60}")
        print(f"Testing: {url}")
        print(f"Category: {category}")
        print(f"{'='*60}")
        
        start_time = time.time()
        result = {
            "url": url,
            "category": category,
            "success": False,
            "partial_success": False,
            "parse_time": 0,
            "error": None,
            "data_completeness": {},
            "parsed_data": None
        }
        
        try:
            # Call the exact same parse_recipe function used in production
            parsed_data = await parse_recipe(url, self.openai_key)
            parse_time = time.time() - start_time
            result["parse_time"] = parse_time
            
            if isinstance(parsed_data, dict) and not parsed_data.get("error"):
                result["success"] = True
                result["parsed_data"] = parsed_data
                
                # Check data completeness
                completeness = self.check_data_completeness(parsed_data)
                result["data_completeness"] = completeness
                
                # Determine if it's a partial success
                if completeness["completeness_score"] < 100:
                    result["partial_success"] = True
                
                # Parse ingredients and nutrition for testing
                if parsed_data.get("ingredients"):
                    structured_ingredients = parse_ingredients_list(parsed_data["ingredients"])
                    result["ingredient_parse_success"] = len(structured_ingredients) > 0
                    result["ingredient_count"] = len(structured_ingredients)
                
                if parsed_data.get("nutrition"):
                    structured_nutrition = parse_nutrition_list(parsed_data["nutrition"])
                    result["nutrition_parse_success"] = len(structured_nutrition) > 0
                    result["nutrition_count"] = len(structured_nutrition)
                
                print(f"✅ SUCCESS in {parse_time:.2f}s")
                print(f"   - Title: {parsed_data.get('title', 'N/A')}")
                print(f"   - Ingredients: {len(parsed_data.get('ingredients', []))}")
                print(f"   - Instructions: {len(parsed_data.get('instructions', []))}")
                print(f"   - Nutrition: {len(parsed_data.get('nutrition', []))}")
                print(f"   - Image URL: {'Yes' if parsed_data.get('image_url') else 'No'}")
                print(f"   - Servings: {parsed_data.get('servings', 'N/A')}")
                print(f"   - Cook Time: {parsed_data.get('cook_time', 'N/A')}")
                print(f"   - Completeness: {completeness['completeness_score']:.1f}%")
                
            else:
                result["error"] = parsed_data.get("error", "Unknown error") if parsed_data else "No data returned"
                print(f"❌ FAILED: {result['error']}")
                # If it's a partial failure, show what we DID get
                if parsed_data and isinstance(parsed_data, dict):
                    print(f"   Partial data received:")
                    if parsed_data.get('title'):
                        print(f"      - Title: {parsed_data.get('title')}")
                    if parsed_data.get('ingredients'):
                        print(f"      - Ingredients: {len(parsed_data.get('ingredients', []))}")
                    if parsed_data.get('instructions'):
                        print(f"      - Instructions: {len(parsed_data.get('instructions', []))}")
                
        except Exception as e:
            parse_time = time.time() - start_time
            result["parse_time"] = parse_time
            result["error"] = str(e)
            print(f"❌ EXCEPTION: {str(e)}")
        
        return result
    
    def check_data_completeness(self, parsed_data: Dict) -> Dict:
        """Check how complete the parsed recipe data is."""
        required_fields = {
            "title": 20,
            "ingredients": 30,
            "instructions": 30,
            "image_url": 10,
            "servings": 5,
            "cook_time": 5
        }
        
        completeness = {
            "has_title": bool(parsed_data.get("title")),
            "has_ingredients": bool(parsed_data.get("ingredients")),
            "has_instructions": bool(parsed_data.get("instructions")),
            "has_image_url": bool(parsed_data.get("image_url")),
            "has_servings": bool(parsed_data.get("servings")),
            "has_cook_time": bool(parsed_data.get("cook_time")),
            "has_nutrition": bool(parsed_data.get("nutrition")),
            "ingredient_count": len(parsed_data.get("ingredients", [])),
            "instruction_count": len(parsed_data.get("instructions", [])),
            "nutrition_count": len(parsed_data.get("nutrition", [])),
            "completeness_score": 0
        }
        
        # Calculate completeness score
        total_weight = sum(required_fields.values())
        earned_weight = 0
        
        for field, weight in required_fields.items():
            if field == "ingredients" and completeness["has_ingredients"]:
                # Give partial credit based on ingredient count
                if completeness["ingredient_count"] >= 5:
                    earned_weight += weight
                elif completeness["ingredient_count"] > 0:
                    earned_weight += weight * (completeness["ingredient_count"] / 5)
            elif field == "instructions" and completeness["has_instructions"]:
                # Give partial credit based on instruction count
                if completeness["instruction_count"] >= 3:
                    earned_weight += weight
                elif completeness["instruction_count"] > 0:
                    earned_weight += weight * (completeness["instruction_count"] / 3)
            elif field == "image_url" and completeness["has_image_url"]:
                earned_weight += weight
            elif field != "image_url" and completeness.get(f"has_{field}"):
                earned_weight += weight
        
        completeness["completeness_score"] = (earned_weight / total_weight) * 100
        
        return completeness
    
    async def test_url_batch(self, urls: List[str], category: str) -> List[Dict]:
        """Test a batch of URLs in parallel."""
        print(f"\n{'#'*60}")
        print(f"# Testing {category} - {len(urls)} URLs")
        print(f"{'#'*60}")
        
        tasks = [self.test_single_url(url, category) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "url": urls[i],
                    "category": category,
                    "success": False,
                    "error": str(result),
                    "parse_time": 0
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def run_all_tests(self) -> None:
        """Run tests on all URL categories."""
        print("\n" + "="*60)
        print("RECIPE PARSING PERFORMANCE TEST")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        overall_start = time.time()
        
        for category, urls in TEST_URLS.items():
            batch_results = await self.test_url_batch(urls, category)
            
            # Update statistics
            for result in batch_results:
                self.results["total_tests"] += 1
                self.results["detailed_results"].append(result)
                
                # Extract domain for site-specific stats
                from urllib.parse import urlparse
                domain = urlparse(result["url"]).netloc
                
                if result["success"]:
                    self.results["successful_parses"] += 1
                    self.results["success_by_site"][domain] = self.results["success_by_site"].get(domain, 0) + 1
                    if result.get("partial_success"):
                        self.results["partial_parses"] += 1
                else:
                    self.results["failed_parses"] += 1
                    self.results["failures_by_site"][domain] = self.results["failures_by_site"].get(domain, 0) + 1
                
                if result["parse_time"] > 0:
                    self.results["timing_data"].append(result["parse_time"])
        
        overall_time = time.time() - overall_start
        self.print_summary(overall_time)
    
    def print_summary(self, overall_time: float) -> None:
        """Print comprehensive test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        # Overall statistics
        success_rate = (self.results["successful_parses"] / self.results["total_tests"]) * 100 if self.results["total_tests"] > 0 else 0
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   Total Tests: {self.results['total_tests']}")
        print(f"   Successful: {self.results['successful_parses']} ({success_rate:.1f}%)")
        print(f"   Failed: {self.results['failed_parses']}")
        print(f"   Partial Success: {self.results['partial_parses']}")
        print(f"   Total Time: {overall_time:.2f}s")
        
        # Timing statistics
        if self.results["timing_data"]:
            print(f"\n⏱️  TIMING STATISTICS:")
            print(f"   Average Parse Time: {statistics.mean(self.results['timing_data']):.2f}s")
            print(f"   Median Parse Time: {statistics.median(self.results['timing_data']):.2f}s")
            print(f"   Min Parse Time: {min(self.results['timing_data']):.2f}s")
            print(f"   Max Parse Time: {max(self.results['timing_data']):.2f}s")
            if len(self.results["timing_data"]) > 1:
                print(f"   Std Dev: {statistics.stdev(self.results['timing_data']):.2f}s")
        
        # Success by site
        print(f"\n✅ SUCCESS BY SITE:")
        for site, count in sorted(self.results["success_by_site"].items(), key=lambda x: x[1], reverse=True):
            print(f"   {site}: {count}")
        
        # Failures by site
        if self.results["failures_by_site"]:
            print(f"\n❌ FAILURES BY SITE:")
            for site, count in sorted(self.results["failures_by_site"].items(), key=lambda x: x[1], reverse=True):
                print(f"   {site}: {count}")
        
        # Data completeness analysis
        print(f"\n📈 DATA COMPLETENESS ANALYSIS:")
        completeness_scores = []
        field_availability = {
            "title": 0,
            "ingredients": 0,
            "instructions": 0,
            "image_url": 0,
            "servings": 0,
            "cook_time": 0,
            "nutrition": 0
        }
        
        for result in self.results["detailed_results"]:
            if result["success"] and "data_completeness" in result:
                completeness = result["data_completeness"]
                if "completeness_score" in completeness:
                    completeness_scores.append(completeness["completeness_score"])
                    
                    for field in field_availability:
                        if completeness.get(f"has_{field}"):
                            field_availability[field] += 1
        
        if completeness_scores:
            print(f"   Average Completeness: {statistics.mean(completeness_scores):.1f}%")
            print(f"   Field Availability (out of {len(completeness_scores)} successful parses):")
            for field, count in field_availability.items():
                percentage = (count / len(completeness_scores)) * 100
                print(f"      - {field}: {count} ({percentage:.1f}%)")
        
        # Common failure patterns
        print(f"\n⚠️  COMMON FAILURE PATTERNS:")
        error_patterns = {}
        error_details = {}
        for result in self.results["detailed_results"]:
            if not result["success"] and result.get("error"):
                error_type = self.categorize_error(result["error"])
                error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
                # Store detailed error messages
                if error_type not in error_details:
                    error_details[error_type] = []
                error_details[error_type].append({
                    "url": result["url"],
                    "error": result["error"]
                })
        
        for pattern, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True):
            print(f"   {pattern}: {count}")
            # Print detailed error messages for each pattern
            if pattern in error_details:
                for detail in error_details[pattern][:3]:  # Show up to 3 examples
                    print(f"      - URL: {detail['url']}")
                    print(f"        Error: {detail['error'][:200]}")
        
        # Save detailed results to file
        self.save_results_to_file()
    
    def categorize_error(self, error_msg: str) -> str:
        """Categorize error messages into common patterns."""
        error_lower = str(error_msg).lower()
        
        if "timeout" in error_lower:
            return "Timeout errors"
        elif "403" in error_lower or "forbidden" in error_lower:
            return "403 Forbidden"
        elif "404" in error_lower:
            return "404 Not Found"
        elif "robots" in error_lower:
            return "Robots.txt blocked"
        elif "ssl" in error_lower or "certificate" in error_lower:
            return "SSL/Certificate errors"
        elif "connection" in error_lower:
            return "Connection errors"
        elif "json" in error_lower or "parse" in error_lower:
            return "Parsing errors"
        elif "rate" in error_lower or "limit" in error_lower:
            return "Rate limiting"
        else:
            return "Other errors"
    
    def save_results_to_file(self) -> None:
        """Save detailed results to JSON file for further analysis."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recipe_parsing_test_results_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n💾 Detailed results saved to: {filename}")


async def main():
    """Main test execution."""
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("❌ ERROR: OPENAI_API_KEY not found in environment variables")
        return
    
    tester = RecipeParsingTester(openai_key)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())