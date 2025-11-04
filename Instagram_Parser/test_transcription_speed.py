#!/usr/bin/env python3
"""
Transcription Speed Benchmark Test

Compares GPT-4o vs Whisper transcription speeds on the same audio file.
This helps determine which provider is actually faster for recipe transcription.
"""

import time
import tempfile
import os
from transcriber import InstagramTranscriber

def test_transcription_speeds():
    """Benchmark transcription speeds: GPT-4o vs Whisper."""
    print("🚀 TRANSCRIPTION SPEED BENCHMARK")
    print("=" * 50)
    
    # Get Instagram URL from user
    instagram_url = input("\nEnter Instagram URL to test transcription speeds: ").strip()
    
    if not instagram_url:
        print("❌ No URL provided. Exiting.")
        return
    
    if "instagram.com" not in instagram_url:
        print("❌ Please provide a valid Instagram URL.")
        return
    
    try:
        print("\n🏗️  Setting up transcriber...")
        transcriber = InstagramTranscriber()
        
        print(f"\n📹 Extracting audio from: {instagram_url}")
        print("-" * 50)
        
        # Extract audio once to test both transcription methods
        print("🚀 Step 1: Extracting Instagram data with Apify...")
        apify_data = transcriber.extract_with_apify(instagram_url)
        print(f"   ✅ Video URL: {apify_data['video_url'][:50]}...")
        print(f"   👤 Creator: @{apify_data['creator_username']}")
        print(f"   ⏱️  Duration: {apify_data['duration']:.1f}s")
        
        print("\n🔽 Step 2: Downloading audio...")
        audio_path = transcriber.download_audio_from_url(apify_data['video_url'])
        print(f"   ✅ Audio saved to: {audio_path}")
        
        # Get audio file size for context
        audio_size = os.path.getsize(audio_path) / 1024  # KB
        print(f"   📦 Audio file size: {audio_size:.1f} KB")
        
        print("\n" + "=" * 50)
        print("🏁 TRANSCRIPTION SPEED RACE (3-WAY BATTLE)")
        print("=" * 50)
        
        results = {}
        
        # Test 1: GPT-4o Transcription
        print("\n🎯 Test 1: GPT-4o Transcription")
        print("-" * 30)
        start_time = time.time()
        try:
            gpt4o_transcript = transcriber.transcribe_audio_gpt4o(audio_path)
            gpt4o_time = time.time() - start_time
            gpt4o_success = True
            print(f"✅ GPT-4o completed: {gpt4o_time:.2f}s")
            print(f"📝 Transcript length: {len(gpt4o_transcript)} characters")
            print(f"🗣️  Sample: \"{gpt4o_transcript[:100]}...\"")
            results['gpt4o'] = {
                'time': gpt4o_time,
                'success': True,
                'transcript': gpt4o_transcript,
                'length': len(gpt4o_transcript)
            }
        except Exception as e:
            gpt4o_time = time.time() - start_time
            gpt4o_success = False
            print(f"❌ GPT-4o failed after {gpt4o_time:.2f}s: {str(e)}")
            results['gpt4o'] = {
                'time': gpt4o_time,
                'success': False,
                'error': str(e),
                'length': 0
            }
        
        # Test 2: Deepgram Transcription
        print("\n🎯 Test 2: Deepgram Transcription (Nova-2)")
        print("-" * 30)
        start_time = time.time()
        try:
            deepgram_transcript = transcriber.transcribe_audio_deepgram(audio_path)
            deepgram_time = time.time() - start_time
            print(f"✅ Deepgram completed: {deepgram_time:.2f}s")
            print(f"📝 Transcript length: {len(deepgram_transcript)} characters")
            print(f"🗣️  Sample: \"{deepgram_transcript[:100]}...\"")
            results['deepgram'] = {
                'time': deepgram_time,
                'success': True,
                'transcript': deepgram_transcript,
                'length': len(deepgram_transcript)
            }
        except Exception as e:
            deepgram_time = time.time() - start_time
            print(f"❌ Deepgram failed after {deepgram_time:.2f}s: {str(e)}")
            results['deepgram'] = {
                'time': deepgram_time,
                'success': False,
                'error': str(e),
                'length': 0
            }
        
        # Test 3: Whisper Transcription
        print("\n🎯 Test 3: Whisper Transcription")
        print("-" * 30)
        start_time = time.time()
        try:
            whisper_transcript = transcriber.transcribe_audio_whisper(audio_path)
            whisper_time = time.time() - start_time
            whisper_success = True
            print(f"✅ Whisper completed: {whisper_time:.2f}s")
            print(f"📝 Transcript length: {len(whisper_transcript)} characters")
            print(f"🗣️  Sample: \"{whisper_transcript[:100]}...\"")
            results['whisper'] = {
                'time': whisper_time,
                'success': True,
                'transcript': whisper_transcript,
                'length': len(whisper_transcript)
            }
        except Exception as e:
            whisper_time = time.time() - start_time
            whisper_success = False
            print(f"❌ Whisper failed after {whisper_time:.2f}s: {str(e)}")
            results['whisper'] = {
                'time': whisper_time,
                'success': False,
                'error': str(e),
                'length': 0
            }
        
        # Results Analysis
        print("\n" + "=" * 50)
        print("📊 TRANSCRIPTION BENCHMARK RESULTS")
        print("=" * 50)
        
        print(f"\n📹 Video Info:")
        print(f"   Duration: {apify_data['duration']:.1f}s")
        print(f"   Audio Size: {audio_size:.1f} KB")
        print(f"   Creator: @{apify_data['creator_username']}")
        
        print(f"\n⏱️  Speed Results:")
        if results['gpt4o']['success']:
            print(f"   🎯 GPT-4o:     {results['gpt4o']['time']:.2f}s")
        else:
            print(f"   🎯 GPT-4o:     FAILED ({results['gpt4o']['time']:.2f}s)")
            
        if results['deepgram']['success']:
            print(f"   🚀 Deepgram:   {results['deepgram']['time']:.2f}s")
        else:
            print(f"   🚀 Deepgram:   FAILED ({results['deepgram']['time']:.2f}s)")
            
        if results['whisper']['success']:
            print(f"   🥇 Whisper:    {results['whisper']['time']:.2f}s")
        else:
            print(f"   🥇 Whisper:    FAILED ({results['whisper']['time']:.2f}s)")
        
        # Find the fastest successful provider
        successful_providers = {name: data for name, data in results.items() if data['success']}
        
        if len(successful_providers) >= 2:
            # Sort by speed (fastest first)
            sorted_providers = sorted(successful_providers.items(), key=lambda x: x[1]['time'])
            fastest_name, fastest_data = sorted_providers[0]
            second_name, second_data = sorted_providers[1]
            
            speedup = second_data['time'] / fastest_data['time']
            print(f"\n🏆 WINNER: {fastest_name.upper()} ({fastest_data['time']:.2f}s)")
            print(f"   📈 {speedup:.1f}x faster than {second_name}")
            
            # Quality comparison
            print(f"\n📝 Transcript Quality Comparison:")
            for name, data in sorted_providers:
                if data['success']:
                    print(f"   {name.capitalize():10}: {data['length']:,} chars")
            
            # Show speed ranking
            print(f"\n🏅 SPEED RANKING:")
            medals = ["🥇", "🥈", "🥉"]
            for i, (name, data) in enumerate(sorted_providers):
                medal = medals[min(i, 2)]
                print(f"   {medal} {i+1}. {name.capitalize():10}: {data['time']:6.2f}s")
            
            # Recommendation
            print(f"\n💡 RECOMMENDATION:")
            if fastest_data['time'] < 5:  # Very fast
                print(f"   ⚡ Use {fastest_name.upper()} - excellent speed at {fastest_data['time']:.2f}s!")
            elif speedup > 2:  # Significant improvement
                print(f"   🚀 Use {fastest_name.upper()} - {speedup:.1f}x speed improvement!")
            else:
                print(f"   🤷 Results are close - any provider works well")
                
        else:
            print(f"\n⚠️  Not enough successful transcriptions for comparison")
            print(f"   Check API keys: OPENAI_API_KEY, DEEPGRAM_WISPER_API")
        
        print("=" * 50)
        
        # Cleanup
        transcriber.cleanup_files()
        
    except Exception as e:
        print(f"\n❌ Benchmark failed: {str(e)}")
        print("Make sure you have all required API keys in .env file:")
        print("   - OPENAI_API_KEY")
        print("   - DEEPGRAM_WISPER_API") 
        print("   - APIFY_API_KEY")
        print("   - pip install deepgram-sdk")

if __name__ == "__main__":
    test_transcription_speeds()