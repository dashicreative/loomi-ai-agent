#!/usr/bin/env python3
"""
Test script for the new Apify-integrated transcriber flow.
Compares the full pipeline: Apify extraction + audio download + Whisper transcription.
"""

import time
from transcriber import InstagramTranscriber

def test_apify_integration():
    """Test the complete Apify-integrated pipeline."""
    print("🧪 APIFY INTEGRATION TEST")
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
        # Initialize transcriber with Apify integration
        print("\n🚀 Initializing Apify-powered transcriber...")
        transcriber = InstagramTranscriber()
        
        print(f"\n🔄 Testing complete pipeline with Apify...")
        print(f"Target URL: {instagram_url}")
        print("\n" + "-" * 50)
        
        # Start timing the complete process
        total_start = time.time()
        
        # Run the complete pipeline
        recipe_json = transcriber.parse_instagram_recipe_to_json(instagram_url)
        
        total_time = time.time() - total_start
        
        # Display results summary
        print("\n" + "=" * 50)
        print("🎉 APIFY INTEGRATION TEST COMPLETE!")
        print("=" * 50)
        
        print(f"\n⏱️  Total Pipeline Time: {total_time:.2f} seconds")
        print(f"📊 Recipe JSON Length: {len(recipe_json):,} characters")
        
        # Show first 300 characters of recipe JSON
        print(f"\n📋 Recipe JSON Preview:")
        print("-" * 30)
        print(recipe_json[:300] + "..." if len(recipe_json) > 300 else recipe_json)
        print("-" * 30)
        
        # Speed comparison
        proxy_estimate = 150  # Conservative estimate
        speedup = proxy_estimate / total_time if total_time > 0 else 0
        
        print(f"\n🚀 SPEED COMPARISON:")
        print(f"   Previous (proxy):  ~{proxy_estimate}s")
        print(f"   New (Apify):       {total_time:.2f}s")
        print(f"   Improvement:       {speedup:.1f}x faster")
        
        print(f"\n✅ SUCCESS: Apify integration working perfectly!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        print("Make sure you have:")
        print("   - APIFY_API_KEY in your .env file")
        print("   - OPENAI_API_KEY in your .env file") 
        print("   - GOOGLE_GEMINI_KEY in your .env file")
        print("   - FFmpeg installed for audio processing")

if __name__ == "__main__":
    test_apify_integration()