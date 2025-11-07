"""
Test CLI for Recipe Site Parser
Interactive testing interface for the recipe parser.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent.parent / "src"))
from recipe_site_parser_actor import parse_single_recipe_url


async def main():
    """Interactive CLI for testing recipe URL parsing."""
    print("🎭 Recipe Site Parser Test CLI")
    print("Enter recipe URLs to parse. Press Ctrl+C to exit.\n")
    
    while True:
        try:
            # Get URL from user
            recipe_url = input("🔗 Enter recipe URL: ").strip()
            
            if not recipe_url:
                print("❌ Please enter a valid URL")
                continue
            
            if not recipe_url.startswith(('http://', 'https://')):
                recipe_url = f"https://{recipe_url}"
            
            print()
            
            # Parse the recipe using standalone function
            result = await parse_single_recipe_url(recipe_url)
            
            # Show results
            if result["success"]:
                print("🎉 RECIPE PARSING SUCCESSFUL!")
                print("=" * 80)
                print(f"⏱️  Total Time: {result['total_elapsed_seconds']}s")
                print(f"   🎭 Apify: {result['timing']['apify_extraction']}s")
                print(f"   🧠 LLM: {result['timing']['llm_processing']}s")
                print()
                
                print("📋 RAW APIFY RESPONSE:")
                print("-" * 40)
                print(json.dumps(result["raw_apify_response"], indent=2))
                print()
                
                print("📦 FINAL JSON (FOR MOBILE APP):")
                print("-" * 40)
                print(result["processed_json"])
                print()
                
            else:
                print("❌ RECIPE PARSING FAILED!")
                print(f"Error: {result.get('error', 'Unknown error')}")
                if result.get("raw_apify_response"):
                    print("\n📋 RAW APIFY RESPONSE:")
                    print("-" * 40)
                    print(json.dumps(result["raw_apify_response"], indent=2))
            
            print()
            
            # Ask for another URL
            another = input("Parse another URL? (y/n): ").strip().lower()
            if another not in ['y', 'yes']:
                break
            print()
            
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            print()


if __name__ == "__main__":
    asyncio.run(main())