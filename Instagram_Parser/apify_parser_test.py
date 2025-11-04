#!/usr/bin/env python3
"""
Apify Instagram Scraper Speed Test

This is a proof-of-concept to test the speed of Apify's Instagram scraper
vs our current yt-dlp + proxy approach for extracting video URLs.

We only test the scraping speed here - no transcription or recipe parsing.
"""

import time
import requests
import json
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class ApifyInstagramTest:
    """Simple test class for Apify Instagram scraper speed testing."""
    
    def __init__(self):
        """Initialize with Apify API token."""
        self.apify_token = os.getenv("APIFY_API_KEY")
        if not self.apify_token:
            raise ValueError("APIFY_API_KEY not found in .env file. Please add it.")
        
        # Apify Instagram scraper endpoint
        self.base_url = "https://api.apify.com/v2/acts/apify~instagram-scraper"
    
    def run_synchronous_scrape(self, instagram_url: str) -> dict:
        """
        Run Apify Instagram scraper synchronously and get results.
        
        Args:
            instagram_url: Instagram post/reel URL to scrape
            
        Returns:
            Dictionary containing scraper results
        """
        # Synchronous run endpoint that waits for completion
        endpoint = f"{self.base_url}/run-sync-get-dataset-items"
        
        # Input payload for the scraper
        payload = {
            "directUrls": [instagram_url],  # Single URL to scrape
            "resultsType": "posts",         # We want post/reel data
            "resultsLimit": 1,              # Only scrape this one URL
            "addParentData": False          # Don't need profile data
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        params = {
            "token": self.apify_token,
            "timeout": 120  # 2 minute timeout
        }
        
        print(f"🚀 Starting Apify scrape for: {instagram_url}")
        start_time = time.time()
        
        try:
            response = requests.post(
                endpoint, 
                json=payload, 
                headers=headers, 
                params=params,
                timeout=120
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Apify scrape completed in {duration:.2f} seconds")
                return {
                    "success": True,
                    "duration": duration,
                    "data": result,
                    "status_code": response.status_code
                }
            else:
                print(f"❌ Apify scrape failed: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "duration": duration,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }
                
        except requests.exceptions.Timeout:
            end_time = time.time()
            duration = end_time - start_time
            print(f"⏰ Apify scrape timed out after {duration:.2f} seconds")
            return {
                "success": False,
                "duration": duration,
                "error": "Request timed out",
                "status_code": None
            }
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            print(f"❌ Apify scrape error: {str(e)}")
            return {
                "success": False,
                "duration": duration,
                "error": str(e),
                "status_code": None
            }
    
    def extract_video_info(self, scrape_result: dict) -> dict:
        """
        Extract video information from Apify scraper results.
        
        Args:
            scrape_result: Result from run_synchronous_scrape()
            
        Returns:
            Dictionary with extracted video info
        """
        if not scrape_result["success"] or not scrape_result["data"]:
            return {"found_video": False, "error": "No data returned"}
        
        try:
            # Apify returns an array of results
            items = scrape_result["data"]
            if not items or len(items) == 0:
                return {"found_video": False, "error": "No items in response"}
            
            post_data = items[0]  # Get first (and should be only) result
            
            # Extract video URL and metadata
            video_info = {
                "found_video": False,
                "video_url": None,
                "post_type": post_data.get("type"),
                "caption": post_data.get("caption", ""),
                "timestamp": post_data.get("timestamp"),
                "likes": post_data.get("likesCount", 0),
                "duration": None
            }
            
            # Check for video URL in different possible fields
            video_fields = ["videoUrl", "video_url", "displayUrl", "url"]
            for field in video_fields:
                if field in post_data and post_data[field]:
                    video_info["video_url"] = post_data[field]
                    video_info["found_video"] = True
                    break
            
            # Get video duration if available
            if "videoDuration" in post_data:
                video_info["duration"] = post_data["videoDuration"]
            elif "duration" in post_data:
                video_info["duration"] = post_data["duration"]
            
            return video_info
            
        except Exception as e:
            return {"found_video": False, "error": f"Failed to parse results: {str(e)}"}


def main():
    """Main test function to compare Apify speed."""
    print("🧪 Apify Instagram Scraper Speed Test")
    print("=" * 50)
    
    # Get Instagram URL from user
    instagram_url = input("\nEnter Instagram URL to test: ").strip()
    
    if not instagram_url:
        print("❌ No URL provided. Exiting.")
        return
    
    if "instagram.com" not in instagram_url:
        print("❌ Please provide a valid Instagram URL.")
        return
    
    try:
        # Initialize Apify tester
        apify_test = ApifyInstagramTest()
        
        print(f"\n🔄 Testing Apify scraper speed...")
        print(f"Target URL: {instagram_url}")
        
        # Run the scrape test
        result = apify_test.run_synchronous_scrape(instagram_url)
        
        # Display results
        print("\n" + "=" * 50)
        print("📊 APIFY SCRAPER RESULTS")
        print("=" * 50)
        
        print(f"\n⏱️  Duration: {result['duration']:.2f} seconds")
        print(f"✅ Success: {'Yes' if result['success'] else 'No'}")
        
        if result["success"]:
            # Extract video information
            video_info = apify_test.extract_video_info(result)
            
            print(f"\n📹 Video Information:")
            print(f"   Found Video: {'Yes' if video_info['found_video'] else 'No'}")
            
            if video_info["found_video"]:
                print(f"   Video URL: {video_info['video_url'][:100]}..." if len(video_info['video_url']) > 100 else video_info['video_url'])
                print(f"   Post Type: {video_info['post_type']}")
                print(f"   Duration: {video_info['duration']} seconds" if video_info['duration'] else "Duration: Unknown")
                print(f"   Likes: {video_info['likes']:,}")
                print(f"   Caption: {video_info['caption'][:100]}..." if len(video_info['caption']) > 100 else video_info['caption'])
            else:
                print(f"   Error: {video_info.get('error', 'Unknown error')}")
            
            # Show raw data sample for debugging
            print(f"\n📋 Raw Data Sample (first 500 chars):")
            print("-" * 40)
            raw_str = json.dumps(result["data"], indent=2)
            print(raw_str[:500] + "..." if len(raw_str) > 500 else raw_str)
        else:
            print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
            print(f"   Status Code: {result.get('status_code', 'N/A')}")
        
        print("\n" + "=" * 50)
        print("🎯 SPEED COMPARISON REFERENCE:")
        print("   Current yt-dlp + proxy: ~120-180 seconds")
        print(f"   Apify scraper: {result['duration']:.2f} seconds")
        if result["success"] and result['duration'] > 0:
            speedup = 150 / result['duration']  # Using 150s as baseline proxy time
            print(f"   Potential speedup: {speedup:.1f}x faster")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        print("Make sure you have APIFY_API_KEY in your .env file")


if __name__ == "__main__":
    main()