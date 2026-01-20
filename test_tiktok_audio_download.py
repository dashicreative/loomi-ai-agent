#!/usr/bin/env python3
"""
Test if TikTok audio URLs from Apify work (must be fresh URLs).
"""

import requests
import sys
from pathlib import Path

def test_tiktok_audio_download(audio_url: str):
    """
    Test downloading audio from TikTok CDN URL.

    Args:
        audio_url: Fresh TikTok audio CDN URL from Apify
    """
    print("=" * 80)
    print("🎵 TESTING TIKTOK AUDIO DOWNLOAD")
    print("=" * 80)
    print(f"\n📍 Audio URL: {audio_url[:100]}...")

    # Extract URL parameters to check freshness
    if "mime_type=audio_mpeg" in audio_url:
        print("✅ URL format: MP3 audio (good!)")
    elif "mime_type=video_mp4" in audio_url:
        print("⚠️  URL format: MP4 video (will need audio extraction)")

    # Check expiration timestamp if present
    if "l=" in audio_url:
        try:
            timestamp_part = audio_url.split("l=")[1].split("&")[0]
            print(f"📅 URL timestamp: {timestamp_part}")
        except:
            pass

    # Test download with proper headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Referer': 'https://www.tiktok.com/',
        'Accept': 'audio/mpeg,audio/*;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    output_path = Path("/tmp/tiktok_test_audio.mp3")

    print("\n🔄 Attempting download...")

    try:
        response = requests.get(
            audio_url,
            headers=headers,
            stream=True,
            timeout=30
        )

        print(f"   Status Code: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"   Content-Length: {response.headers.get('Content-Length', 'N/A')} bytes")

        if response.status_code == 200:
            # Download file
            total_size = 0
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            file_size_mb = total_size / (1024 * 1024)
            print(f"\n✅ SUCCESS! Audio downloaded")
            print(f"   File size: {file_size_mb:.2f} MB")
            print(f"   Path: {output_path}")

            # Cleanup
            output_path.unlink()
            print(f"   Cleaned up test file")

            print("\n" + "=" * 80)
            print("✅ VERDICT: TikTok audio CDN URLs work!")
            print("=" * 80)
            print("\n💡 Implementation Notes:")
            print("   1. URLs expire quickly (likely 5-15 minutes)")
            print("   2. MUST download immediately after Apify returns URL")
            print("   3. Use proper headers (User-Agent, Referer)")
            print("   4. Same flow as Instagram parser:")
            print("      - Apify returns audio URL")
            print("      - Download immediately")
            print("      - Upload to Deepgram for transcription")
            print("      - Process with shared LLM pipeline")

            return True

        elif response.status_code == 403:
            print(f"\n❌ FAILED: 403 Forbidden - Anti-bot blocking")
            print("   This means TikTok is blocking the request")
            return False

        elif response.status_code == 404:
            print(f"\n❌ FAILED: 404 Not Found - URL expired or invalid")
            print("   URL likely expired. Get fresh URL from Apify.")
            return False

        elif response.status_code == 504:
            print(f"\n❌ FAILED: 504 Gateway Timeout - URL expired")
            print("   URL definitely expired. Get fresh URL from Apify.")
            return False

        else:
            print(f"\n❌ FAILED: Unexpected status code {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        print(f"\n❌ FAILED: Request timeout")
        print("   URL might be expired or network issue")
        return False

    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_tiktok_audio_download.py <audio_url>")
        print("\nGet a FRESH audio URL from your Apify TikTok actor and test immediately!")
        sys.exit(1)

    audio_url = sys.argv[1]
    success = test_tiktok_audio_download(audio_url)
    sys.exit(0 if success else 1)
