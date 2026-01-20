#!/usr/bin/env python3
"""
Test script to verify if yt-dlp can extract audio from TikTok URLs
without requiring authentication/scraping like Instagram does.
"""

import subprocess
import sys
import json
from pathlib import Path

def test_ytdlp_tiktok_audio(tiktok_url: str):
    """
    Test yt-dlp audio extraction from TikTok URL.

    Args:
        tiktok_url: TikTok video URL (e.g., https://www.tiktok.com/@user/video/123)
    """

    print("=" * 80)
    print("🧪 TESTING YT-DLP WITH TIKTOK")
    print("=" * 80)
    print(f"\n📍 Testing URL: {tiktok_url}\n")

    # Test 1: Check if yt-dlp is installed
    print("✅ Test 1: Checking yt-dlp installation...")
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"   yt-dlp version: {result.stdout.strip()}")
    except FileNotFoundError:
        print("   ❌ yt-dlp not installed!")
        print("   Install with: pip install yt-dlp")
        return False
    except Exception as e:
        print(f"   ❌ Error checking yt-dlp: {e}")
        return False

    # Test 2: Extract video metadata (no download)
    print("\n✅ Test 2: Extracting video metadata (no auth required)...")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",  # Get metadata only
                "--no-warnings",
                tiktok_url
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            metadata = json.loads(result.stdout)
            print(f"   ✅ Title: {metadata.get('title', 'N/A')}")
            print(f"   ✅ Uploader: {metadata.get('uploader', 'N/A')}")
            print(f"   ✅ Duration: {metadata.get('duration', 'N/A')}s")
            print(f"   ✅ Description: {metadata.get('description', 'N/A')[:100]}...")

            # Check available formats
            formats = metadata.get('formats', [])
            audio_formats = [f for f in formats if f.get('acodec') != 'none']
            print(f"   ✅ Audio formats available: {len(audio_formats)}")
        else:
            print(f"   ❌ Metadata extraction failed!")
            print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("   ❌ Timeout - TikTok might be blocking requests")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    # Test 3: Download audio-only
    print("\n✅ Test 3: Downloading audio-only (testing actual download)...")
    output_file = Path("/tmp/tiktok_test_audio.m4a")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestaudio",  # Audio only, best quality
                "-o", str(output_file),
                "--no-warnings",
                tiktok_url
            ],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0 and output_file.exists():
            file_size = output_file.stat().st_size / (1024 * 1024)  # MB
            print(f"   ✅ Audio downloaded successfully!")
            print(f"   ✅ File size: {file_size:.2f} MB")
            print(f"   ✅ File path: {output_file}")

            # Cleanup
            output_file.unlink()
            print(f"   ✅ Test file cleaned up")
            return True
        else:
            print(f"   ❌ Audio download failed!")
            print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("   ❌ Timeout - Download took too long or blocked")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def analyze_tiktok_vs_instagram():
    """
    Print analysis of TikTok vs Instagram scraping requirements.
    """
    print("\n" + "=" * 80)
    print("📊 TIKTOK VS INSTAGRAM SCRAPING ANALYSIS")
    print("=" * 80)

    analysis = """

🔍 INSTAGRAM (Current Approach):
   ❌ Direct video URLs require authentication
   ❌ Anti-bot systems block unauthenticated requests
   ❌ Need to scrape to get actual MP4 CDN URL
   ✅ Solution: Use Apify actor to handle auth/scraping
   ✅ Apify provides direct video URL that works

🔍 TIKTOK (Potential Approach):
   ✅ yt-dlp handles authentication automatically
   ✅ No manual scraping/auth required
   ✅ Can extract audio directly from public TikTok URL
   ✅ TikTok's anti-bot is less aggressive than Instagram
   ⚠️  Public videos work, private videos don't

💡 KEY DIFFERENCES:
   1. TikTok allows more public access than Instagram
   2. TikTok's CDN URLs are more accessible (with proper headers)
   3. yt-dlp has built-in TikTok extractors that handle auth
   4. Instagram requires more complex scraping infrastructure

📈 SCALABILITY CONCERNS:

   Option A: Pure yt-dlp
   ✅ Pros:
      - Free (no Apify costs)
      - Simple integration
      - Handles auth automatically
   ❌ Cons:
      - Rate limiting from your server IP
      - TikTok could block your IPs at scale
      - Single point of failure

   Option B: Apify TikTok Actor
   ✅ Pros:
      - Distributed IPs (harder to block)
      - Professional scraping infrastructure
      - Better for high volume (100k+ users)
      - SLA/reliability guarantees
   ❌ Cons:
      - Costs money per scrape
      - Additional API dependency

   Option C: Hybrid (yt-dlp with fallback to Apify)
   ✅ Pros:
      - Try free yt-dlp first
      - Fallback to Apify if blocked
      - Cost-effective at scale
   ❌ Cons:
      - More complex implementation

🎯 RECOMMENDATION FOR YOUR SCALE (100k+ users):

   Start with: Pure yt-dlp
   Monitor for: Rate limiting, IP blocks, failures
   Migrate to: Apify if you hit >10% failure rate

   Why: TikTok is more permissive than Instagram, yt-dlp should
         handle moderate scale. Add Apify later if needed.
    """

    print(analysis)

if __name__ == "__main__":
    print("\n" + "🎬" * 40)
    print("TIKTOK YT-DLP AUDIO EXTRACTION TEST")
    print("🎬" * 40 + "\n")

    # Check if URL provided
    if len(sys.argv) > 1:
        tiktok_url = sys.argv[1]
    else:
        print("⚠️  No TikTok URL provided as argument")
        print("Usage: python test_tiktok_ytdlp.py <tiktok_url>")
        print("\nExample TikTok URL to test:")
        print("  https://www.tiktok.com/@gordonramsayofficial/video/7011062878162357509")
        print("\nRunning analysis only...\n")
        analyze_tiktok_vs_instagram()
        sys.exit(0)

    # Run tests
    success = test_ytdlp_tiktok_audio(tiktok_url)

    # Print analysis
    analyze_tiktok_vs_instagram()

    # Final verdict
    print("\n" + "=" * 80)
    if success:
        print("✅ VERDICT: yt-dlp can extract TikTok audio without Apify!")
        print("=" * 80)
        print("\n💡 Next Steps:")
        print("   1. Test with multiple TikTok URLs to verify consistency")
        print("   2. Test with private TikTok accounts (will likely fail)")
        print("   3. Implement retry logic for rate limiting")
        print("   4. Monitor failure rates in production")
        print("   5. Consider Apify as fallback if failures > 10%")
    else:
        print("❌ VERDICT: yt-dlp failed - may need Apify for TikTok")
        print("=" * 80)
        print("\n💡 Next Steps:")
        print("   1. Check if yt-dlp is properly installed")
        print("   2. Try with a different TikTok URL")
        print("   3. Investigate error messages above")
        print("   4. Consider using Apify TikTok actor instead")
