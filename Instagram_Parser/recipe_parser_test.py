#!/usr/bin/env python3
"""
Test CLI for the complete Instagram recipe parsing pipeline.

Tests transcription + parallel recipe extraction (ingredients and directions).
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from transcriber import InstagramTranscriber

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def main():
    """
    Test the complete Instagram recipe parsing pipeline.
    """
    print("🍳 Instagram Recipe Parser Test")
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
    print("⏱️  This includes: audio extraction → transcription → parallel recipe parsing\n")
    
    # Record start time
    start_time = time.time()
    
    try:
        # Create transcriber instance
        transcriber = InstagramTranscriber()
        
        # Run complete pipeline
        transcript, ingredients, directions = transcriber.parse_instagram_recipe(instagram_url)
        
        # Record end time
        end_time = time.time()
        duration = end_time - start_time
        
        # Display results
        print("=" * 50)
        print("✅ RECIPE PARSING COMPLETE")
        print("=" * 50)
        print(f"⏱️  Total processing time: {duration:.2f} seconds")
        
        print(f"\n📝 RAW TRANSCRIPT:")
        print("-" * 30)
        print(transcript)
        
        print(f"\n🥕 EXTRACTED INGREDIENTS:")
        print("-" * 30)
        print(ingredients)
        
        print(f"\n📋 TITLE + DIRECTIONS:")
        print("-" * 30)
        print(directions)
        
        print("-" * 50)
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n❌ Error after {duration:.2f} seconds: {str(e)}")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()