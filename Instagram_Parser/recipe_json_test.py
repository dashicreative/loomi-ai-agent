#!/usr/bin/env python3
"""
Test CLI for Instagram recipe parsing with structured JSON output.

Tests the complete pipeline and outputs structured recipe JSON.
"""

import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from transcriber import InstagramTranscriber

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def main():
    """
    Test the complete Instagram recipe parsing pipeline with JSON output.
    """
    print("🍳 Instagram Recipe JSON Parser Test")
    print("=" * 50)
    
    # Get Instagram URL from user
    instagram_url = input("\nEnter Instagram URL: ").strip()
    
    if not instagram_url:
        print("❌ No URL provided. Exiting.")
        return
    
    # Validate URL format
    if "instagram.com" not in instagram_url:
        print("❌ Please provide a valid Instagram URL.")
        return
    
    print(f"\n🔄 Processing: {instagram_url}")
    print("Running complete recipe parsing pipeline...")
    print("⏱️  This includes: audio extraction → transcription → parallel recipe parsing → JSON structuring\n")
    
    # Record start time
    start_time = time.time()
    
    try:
        # Create transcriber instance
        transcriber = InstagramTranscriber()
        
        # Run complete pipeline and get structured JSON (Whisper + Gemini)
        recipe_json = transcriber.parse_instagram_recipe_to_json(instagram_url)
        
        # Record end time
        end_time = time.time()
        duration = end_time - start_time
        
        # Display results
        print("=" * 50)
        print("✅ RECIPE JSON PARSING COMPLETE")
        print("=" * 50)
        print(f"⏱️  Total processing time: {duration:.2f} seconds")
        
        print(f"\n📋 STRUCTURED RECIPE JSON:")
        print("-" * 30)
        
        # Pretty print the JSON
        try:
            # Parse and re-format for better display
            recipe_dict = json.loads(recipe_json)
            formatted_json = json.dumps(recipe_dict, indent=2, ensure_ascii=False)
            print(formatted_json)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            print(recipe_json)
        
        print("-" * 50)
        
        # Show summary stats
        try:
            recipe_dict = json.loads(recipe_json)
            print(f"\n📊 Recipe Summary:")
            print(f"   📝 Title: {recipe_dict.get('title', 'N/A')}")
            print(f"   🥕 Ingredients: {len(recipe_dict.get('ingredients', []))}")
            print(f"   📋 Directions: {len(recipe_dict.get('directions', []))}")
            print(f"   🔗 Source: {recipe_dict.get('source_url', 'N/A')}")
        except:
            pass
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n❌ Error after {duration:.2f} seconds: {str(e)}")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()