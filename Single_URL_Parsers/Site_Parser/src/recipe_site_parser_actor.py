"""
Recipe Site Parser Actor - Production MVP with LLM processing
Single-URL recipe parsing using Apify actor + LLM formatting + regex ingredient parsing.
"""

import asyncio
import httpx
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

# Add parent directory to path to import site_recipe_processor
sys.path.append(str(Path(__file__).parent.parent))
from site_recipe_processor import SiteRecipeProcessor

# Load environment variables
load_dotenv()


class RecipeSiteParser:
    """Production recipe parser using Apify actor with LLM processing."""
    
    def __init__(self):
        """Initialize with API credentials and processor."""
        self.apify_token = os.getenv("APIFY_API_KEY")
        
        if not self.apify_token:
            raise ValueError("Missing required API key: APIFY_API_KEY")
        
        # Initialize the recipe processor for LLM + regex processing
        self.processor = SiteRecipeProcessor()
    
    async def parse_recipe_url(self, recipe_url: str) -> dict:
        """
        Parse a single recipe URL with complete processing pipeline.
        
        Args:
            recipe_url: URL of the recipe to parse
            
        Returns:
            Dictionary with raw response and processed JSON
        """
        print("=" * 80)
        print("🎭 RECIPE SITE PARSER (APIFY + GEMINI + REGEX)")
        print("=" * 80)
        print(f"🔗 Recipe URL: {recipe_url}")
        print("-" * 80)
        
        start_time = time.time()
        
        try:
            # STEP 1: Get raw data from Apify actor
            print("🎭 Step 1: Extracting recipe with Apify actor...")
            step_start = time.time()
            
            apify_response = await self._call_apify_actor(recipe_url)
            apify_elapsed = time.time() - step_start
            
            if not apify_response.get("success"):
                return apify_response  # Return error if Apify failed
            
            print(f"   ✅ Apify extraction completed in {apify_elapsed:.1f}s")
            raw_data = apify_response["raw_response"]
            
            # STEP 2: Process with LLM + regex
            print("📦 Step 2: Processing with LLM + regex...")
            step_start = time.time()
            
            processed_json = self.processor.process_apify_response(raw_data)
            
            process_elapsed = time.time() - step_start
            print(f"   ✅ Processing completed in {process_elapsed:.1f}s")
            
            total_elapsed = time.time() - start_time
            
            return {
                "success": True,
                "recipe_url": recipe_url,
                "total_elapsed_seconds": round(total_elapsed, 1),
                "timing": {
                    "apify_extraction": round(apify_elapsed, 1),
                    "llm_processing": round(process_elapsed, 1)
                },
                "raw_apify_response": raw_data,
                "processed_json": processed_json
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "success": False,
                "error": str(e),
                "recipe_url": recipe_url,
                "total_elapsed_seconds": round(elapsed, 1),
                "raw_apify_response": None,
                "processed_json": None
            }
    
    async def _call_apify_actor(self, recipe_url: str) -> Dict:
        """Call Apify recipe scraper actor (extracted from original logic)."""
        
        actor_input = {
            "start_urls": [recipe_url]  # Working format
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                endpoint_url = f"https://api.apify.com/v2/acts/web.harvester~recipes-scraper/run-sync-get-dataset-items?token={self.apify_token}"
                
                response = await client.post(
                    endpoint_url,
                    json=actor_input,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                raw_results = response.json()
                
                if not raw_results or len(raw_results) == 0:
                    return {
                        "success": False,
                        "error": "No data returned from Apify actor",
                        "raw_response": None
                    }
                
                # Get first result
                recipe_data = raw_results[0]
                
                # Basic validation
                has_title = bool(recipe_data.get("title"))
                has_ingredients = bool(recipe_data.get("ingredients"))
                has_instructions = bool(recipe_data.get("instructions"))
                
                return {
                    "success": has_title and has_ingredients and has_instructions,
                    "raw_response": recipe_data,
                    "validation": {
                        "has_title": has_title,
                        "has_ingredients": has_ingredients,
                        "has_instructions": has_instructions
                    }
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Apify actor failed: {str(e)}",
                    "raw_response": None
                }


# Standalone function for API use
async def parse_single_recipe_url(recipe_url: str) -> Dict:
    """
    Standalone function for API integration.
    
    Args:
        recipe_url: URL of the recipe to parse
        
    Returns:
        Dictionary with success status and processed JSON string
    """
    parser = RecipeSiteParser()
    return await parser.parse_recipe_url(recipe_url)


# Simple test function (for basic verification)
async def test_single_url(url: str = "https://www.abeautifulplate.com/sheet-pan-cauliflower-curry/"):
    """Quick test function for API validation."""
    result = await parse_single_recipe_url(url)
    
    if result["success"]:
        print("✅ Parse successful!")
        print(f"⏱️  Time: {result['total_elapsed_seconds']}s")
        print("📦 JSON ready for API response")
        return result["processed_json"]
    else:
        print(f"❌ Parse failed: {result.get('error')}")
        return None


if __name__ == "__main__":
    # Simple test when run directly
    asyncio.run(test_single_url())