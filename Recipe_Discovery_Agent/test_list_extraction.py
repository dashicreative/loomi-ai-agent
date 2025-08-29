"""
Test file for list URL to recipe URL extraction functionality.
Tests the ListParser class and recipe extraction pipeline.
"""

import asyncio
import os
from dotenv import load_dotenv
from Tools.Detailed_Recipe_Parsers.list_parser import ListParser
from Tools.Recipe_Search_Stages.stage_4_recipe_parsing import parse_recipe

# Load environment variables
load_dotenv()

async def test_list_extraction():
    """Test list URL extraction with the 21 list URLs from our actual test run."""
    
    # The 20 backlog URLs from the latest test run
    test_list_urls = [
        "https://www.eatingwell.com/gallery/8026150/high-protein-breakfasts-without-eggs/",
        "https://www.foodnetwork.com/recipes/photos/high-protein-breakfast-recipes",
        "https://www.bbcgoodfood.com/recipes/collection/high-protein-breakfast-recipes",
        "https://joytothefood.com/breakfast-recipes-with-over-30g-of-protein-without-protein-powder/",
        "https://engagement.source.colostate.edu/want-to-stop-craving-snacks-and-sweets-a-high-protein-breakfast-could-help/",
        "https://blog.myfitnesspal.com/30-grams-protein-breakfast/",
        "https://www.womenshealthmag.com/food/g65519760/high-protein-breakfast-meal-prep-how-to/",
        "https://bewellbykelly.com/blogs/blog/easy-breakfasts-with-30-grams-of-protein-or-more?srsltid=AfmBOoo_9t67Hui8csTz1IupxsfDM6CbGbQjUFmzPneh1wyCR2CzLAC1",
        "https://www.health.com/25-high-protein-breakfast-ideas-to-keep-you-full-7566320",
        "https://reallifenutritionist.com/easy-high-protein-breakfast-recipes/",
        "https://sofreshnsogreen.com/recipes/30g-protein-breakfast-recipes/",
        "https://therealfooddietitians.com/high-protein-breakfast-ideas/",
        "https://www.prevention.com/food-nutrition/healthy-eating/g23709836/high-protein-breakfasts/",
        "https://kimabbagehart.com/30-grams-of-protein-breakfast-ideas-5-easy-recipes/",
        "https://www.womenshealthmag.com/weight-loss/a19993913/protein-breakfast-ideas/",
        "https://experiencelife.lifetime.life/article/4-breakfast-recipes-with-30-grams-of-protein/",
        "https://www.snackinginsneakers.com/breakfasts-30-grams-protein/",
        "https://www.dietlicious.com.au/blog/high-protein-breafast-ideas/",
        "https://moderatelymessyrd.com/30-breakfasts-with-30-grams-of-protein/?srsltid=AfmBOooLCAhkhZ-GS91VXU5n1UrmniZBlaT8W6D0LlKFnLZD48Sq7_32",
        "https://www.quora.com/What-are-six-tasty-ways-to-consume-30g-of-protein-for-breakfast"
    ]
    
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("❌ OpenAI API key not found")
        return
    
    print(f"🧪 Testing list extraction on {len(test_list_urls)} backlog URLs from latest test run")
    print("=" * 80)
    
    # Track results
    successful_extractions = 0
    failed_extractions = 0
    total_recipe_urls_extracted = 0
    successful_parses = 0
    failed_parses = 0
    
    results_report = []
    
    # Test each list URL
    for i, test_url in enumerate(test_list_urls, 1):
        print(f"\n📋 LIST URL {i}/{len(test_list_urls)}: {test_url}")
        
        try:
            # Fetch the list page content
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(test_url, follow_redirects=True)
                response.raise_for_status()
                html_content = response.text
            
            # Initialize ListParser and extract URLs
            list_parser = ListParser(openai_key)
            extracted_urls = await list_parser.extract_recipe_urls(
                test_url, 
                html_content, 
                max_urls=3  # Limit to 3 per list for testing
            )
            
            if extracted_urls:
                successful_extractions += 1
                total_recipe_urls_extracted += len(extracted_urls)
                
                print(f"   ✅ Extracted {len(extracted_urls)} recipe URLs")
                
                # Test parsing one of the extracted URLs
                test_recipe_url = extracted_urls[0].get('url')
                if test_recipe_url:
                    parsed_recipe = await parse_recipe(test_recipe_url, openai_key)
                    
                    if parsed_recipe.get('error'):
                        failed_parses += 1
                        print(f"   ❌ Recipe parse failed: {parsed_recipe['error']}")
                        
                        results_report.append({
                            "list_url": test_url,
                            "extraction": "success",
                            "extracted_count": len(extracted_urls),
                            "parse_test": "failed",
                            "parse_error": parsed_recipe['error']
                        })
                    else:
                        successful_parses += 1
                        print(f"   ✅ Recipe parse succeeded: {parsed_recipe.get('title', 'No title')}")
                        
                        results_report.append({
                            "list_url": test_url,
                            "extraction": "success", 
                            "extracted_count": len(extracted_urls),
                            "parse_test": "success",
                            "recipe_title": parsed_recipe.get('title', 'No title')
                        })
            else:
                failed_extractions += 1
                print(f"   ❌ No recipe URLs extracted")
                
                results_report.append({
                    "list_url": test_url,
                    "extraction": "failed",
                    "extracted_count": 0,
                    "parse_test": "N/A"
                })
                
        except Exception as e:
            failed_extractions += 1
            print(f"   ❌ Extraction failed: {str(e)}")
            
            results_report.append({
                "list_url": test_url,
                "extraction": "failed",
                "error": str(e),
                "parse_test": "N/A"
            })
    
    # Final report
    print("\n" + "=" * 80)
    print("📊 FINAL EXTRACTION EFFECTIVENESS REPORT")
    print("=" * 80)
    print(f"List URLs tested: {len(test_list_urls)}")
    print(f"Successful extractions: {successful_extractions}")
    print(f"Failed extractions: {failed_extractions}")
    print(f"Total recipe URLs extracted: {total_recipe_urls_extracted}")
    print(f"Successful recipe parses: {successful_parses}")
    print(f"Failed recipe parses: {failed_parses}")
    print(f"")
    print(f"Extraction success rate: {(successful_extractions/len(test_list_urls)*100):.1f}%")
    if total_recipe_urls_extracted > 0:
        print(f"Parse success rate: {(successful_parses/(successful_parses+failed_parses)*100):.1f}%")
    
    print(f"\n📋 DETAILED RESULTS:")
    for i, result in enumerate(results_report, 1):
        status = "✅" if result["extraction"] == "success" else "❌"
        print(f"{i:2}. {status} {result['list_url']}")
        if result["extraction"] == "success":
            print(f"      Extracted: {result['extracted_count']} URLs")
            if result["parse_test"] == "success":
                print(f"      Parse: ✅ {result.get('recipe_title', 'No title')}")
            elif result["parse_test"] == "failed":
                print(f"      Parse: ❌ {result.get('parse_error', 'Unknown error')}")
        else:
            print(f"      Error: {result.get('error', 'Unknown error')}")
        print()

if __name__ == "__main__":
    asyncio.run(test_list_extraction())