#!/usr/bin/env python3
"""
Test CLI for TikTok audio extraction and transcription (Steps 1-4 only).

Tests:
1. Receive TikTok URL
2. Call Apify TikTok Audio Downloader actor
3. Download audio as MP3
4. Upload to Deepgram for transcription
5. Print transcript
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables FIRST
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Set up Deepgram environment variable if available (before importing)
deepgram_key = os.getenv('DEEPGRAM_WISPER_API')
if deepgram_key:
    os.environ['DEEPGRAM_API_KEY'] = deepgram_key

# Try to import Deepgram (after setting env var)
try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    print("⚠️  Deepgram SDK not installed. Install with: pip install deepgram-sdk")


class TikTokTranscriber:
    """
    TikTok audio extractor and transcriber (proof of concept).
    Steps 1-4 only: Apify → Audio Download → Deepgram Transcription
    """

    def __init__(self):
        """Initialize TikTok transcriber with API keys."""
        # API Keys
        self.apify_token = os.getenv("APIFY_API_KEY")
        self.deepgram_api_key = os.getenv("DEEPGRAM_WISPER_API")

        # Validate required keys
        if not self.apify_token:
            raise ValueError("APIFY_API_KEY not found in environment variables")

        # Initialize Deepgram client (environment variable already set at module level)
        self.deepgram_client = None
        if DEEPGRAM_AVAILABLE and deepgram_key:
            try:
                self.deepgram_client = DeepgramClient()
            except Exception as e:
                print(f"⚠️  Failed to initialize Deepgram client: {str(e)}")
                self.deepgram_client = None

        # Temp directory for audio files
        self.temp_dir = Path(__file__).parent / "temp"
        self.temp_dir.mkdir(exist_ok=True)

        print("✅ TikTok Transcriber initialized")
        print(f"   📁 Temp directory: {self.temp_dir}")

    def extract_with_apify(self, tiktok_url: str) -> dict:
        """
        Extract TikTok audio data using Apify's TikTok Audio Downloader actor.

        Args:
            tiktok_url: TikTok video URL

        Returns:
            Dictionary containing audioUrl, caption, metadata
        """
        # Apify TikTok Audio Downloader endpoint
        actor_id = "alpha-scraper~tiktok-audio-downloader"
        endpoint = f"https://api.apify.com/v2/acts/{actor_id}/runs"

        # Request payload matching Apify documentation
        payload = {
            "startUrls": [
                {
                    "url": tiktok_url,
                    "method": "GET"
                }
            ]
        }

        headers = {"Content-Type": "application/json"}
        params = {"token": self.apify_token}

        try:
            print(f"\n📱 Step 1: Calling Apify TikTok Audio Downloader...")
            print(f"   URL: {tiktok_url}")
            start_time = time.time()

            # Start the actor run
            response = requests.post(endpoint, json=payload, headers=headers, params=params, timeout=10)

            if response.status_code in [200, 201]:
                run_data = response.json()
                run_id = run_data.get("data", {}).get("id")

                print(f"   ✅ Actor run started: {run_id}")
                print(f"   ⏳ Waiting for actor to complete...")

                # First, wait for run to complete by checking status
                run_status_url = f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}"
                status_params = {"token": self.apify_token}

                # Poll for completion (max 2 minutes)
                max_wait = 120
                poll_interval = 2
                elapsed = 0

                while elapsed < max_wait:
                    time.sleep(poll_interval)
                    elapsed += poll_interval

                    # Check run status
                    status_response = requests.get(run_status_url, params=status_params, timeout=10)

                    if status_response.status_code == 200:
                        run_info = status_response.json()
                        status = run_info.get("data", {}).get("status")

                        if status == "SUCCEEDED":
                            # Run completed - now get the dataset
                            default_dataset_id = run_info.get("data", {}).get("defaultDatasetId")

                            if default_dataset_id:
                                dataset_url = f"https://api.apify.com/v2/datasets/{default_dataset_id}/items"
                                dataset_params = {"token": self.apify_token}

                                dataset_response = requests.get(dataset_url, params=dataset_params, timeout=10)

                                if dataset_response.status_code == 200:
                                    items = dataset_response.json()

                                    if items and len(items) > 0:
                                        item = items[0]
                                        extraction_time = time.time() - start_time
                                        print(f"   ✅ Apify extraction completed in {extraction_time:.2f}s")

                                        return {
                                            "audio_url": item.get("audioUrl"),
                                            "video_url": item.get("videoUrl"),
                                            "video_id": item.get("videoId"),
                                            "caption": item.get("caption", ""),
                                            "title": item.get("title", ""),
                                            "uploader": item.get("uploader", ""),
                                            "upload_date": item.get("uploadDate", ""),
                                            "duration": item.get("audioDuration", ""),
                                            "view_count": item.get("viewCount", ""),
                                            "like_count": item.get("likeCount", ""),
                                            "comment_count": item.get("commentCount", "")
                                        }
                                    else:
                                        raise Exception("Dataset is empty - no items returned")
                                else:
                                    raise Exception(f"Failed to fetch dataset: {dataset_response.status_code}")
                            else:
                                raise Exception("No dataset ID found in run info")

                        elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                            raise Exception(f"Actor run failed with status: {status}")

                        # Still running, continue polling
                        if elapsed % 6 == 0:  # Print every 6 seconds
                            print(f"   ⏳ Still waiting... ({elapsed}s elapsed, status: {status})")

                raise Exception(f"Actor did not complete within {max_wait} seconds")

            else:
                raise Exception(f"Apify API error: HTTP {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            raise Exception("Apify request timed out")
        except Exception as e:
            raise Exception(f"Failed to extract TikTok data: {str(e)}")

    def download_audio_from_url(self, audio_url: str) -> Path:
        """
        Download audio from TikTok CDN URL.

        Args:
            audio_url: Direct audio URL from Apify

        Returns:
            Path to downloaded MP3 file
        """
        print(f"\n🎵 Step 2: Downloading audio from TikTok CDN...")
        print(f"   URL: {audio_url[:80]}...")

        audio_path = self.temp_dir / "tiktok_audio.mp3"

        # Required headers for TikTok CDN
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.tiktok.com/',
            'Accept': 'audio/mpeg,audio/*;q=0.9,*/*;q=0.8',
        }

        try:
            start_time = time.time()
            response = requests.get(audio_url, headers=headers, stream=True, timeout=30)

            if response.status_code == 200:
                # Download file
                total_size = 0
                with open(audio_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)

                file_size_mb = total_size / (1024 * 1024)
                download_time = time.time() - start_time

                print(f"   ✅ Audio downloaded successfully in {download_time:.2f}s")
                print(f"   📦 File size: {file_size_mb:.2f} MB")
                print(f"   📁 Path: {audio_path}")

                return audio_path

            elif response.status_code == 404:
                raise Exception("Audio URL expired (404) - URL likely too old")
            elif response.status_code == 403:
                raise Exception("Access forbidden (403) - TikTok blocking request")
            else:
                raise Exception(f"Download failed: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            raise Exception("Audio download timed out")
        except Exception as e:
            raise Exception(f"Failed to download audio: {str(e)}")

    def transcribe_audio_deepgram(self, audio_path: Path) -> str:
        """
        Transcribe audio using Deepgram Nova-2 model.

        Args:
            audio_path: Path to audio file

        Returns:
            Transcribed text
        """
        print(f"\n🎙️  Step 3: Transcribing audio with Deepgram Nova-2...")

        if not self.deepgram_client:
            raise Exception("Deepgram client not initialized")

        if not audio_path.exists():
            raise Exception(f"Audio file not found: {audio_path}")

        try:
            start_time = time.time()

            # Read audio file and transcribe using Nova-2 model
            with open(audio_path, "rb") as audio_file:
                response = self.deepgram_client.listen.v1.media.transcribe_file(
                    request=audio_file.read(),
                    model="nova-2"
                )

            # Extract transcript
            if (response.results and
                response.results.channels and
                len(response.results.channels) > 0 and
                response.results.channels[0].alternatives and
                len(response.results.channels[0].alternatives) > 0):

                transcript = response.results.channels[0].alternatives[0].transcript
                transcription_time = time.time() - start_time

                print(f"   ✅ Transcription completed in {transcription_time:.2f}s")
                print(f"   📝 Transcript length: {len(transcript)} characters")

                return transcript
            else:
                raise Exception("No transcript found in Deepgram response")

        except Exception as e:
            raise Exception(f"Deepgram transcription failed: {str(e)}")

    def cleanup(self):
        """Remove temporary audio files."""
        for file in self.temp_dir.glob("*.mp3"):
            try:
                file.unlink()
                print(f"🗑️  Cleaned up: {file.name}")
            except Exception as e:
                print(f"⚠️  Could not delete {file.name}: {e}")


def main():
    """
    Test TikTok audio extraction and transcription (Steps 1-4).
    """
    print("=" * 70)
    print("🎵 TikTok Audio Transcription Test (Proof of Concept)")
    print("=" * 70)
    print("\n📋 This test covers steps 1-4:")
    print("   1. Receive TikTok URL")
    print("   2. Call Apify TikTok Audio Downloader")
    print("   3. Download audio as MP3")
    print("   4. Upload to Deepgram for transcription\n")

    # Get TikTok URL from user
    tiktok_url = input("Enter TikTok URL: ").strip()

    if not tiktok_url:
        print("❌ No URL provided. Exiting.")
        return

    # Validate URL
    if "tiktok.com" not in tiktok_url:
        print("❌ Please provide a valid TikTok URL.")
        return

    print(f"\n🔄 Processing: {tiktok_url}")

    # Record start time
    overall_start = time.time()

    try:
        # Initialize transcriber
        transcriber = TikTokTranscriber()

        # Step 1: Extract with Apify
        apify_data = transcriber.extract_with_apify(tiktok_url)

        # Verify we got an audio URL
        if not apify_data.get("audio_url"):
            raise Exception("No audio URL returned from Apify actor")

        # Step 2: Download audio
        audio_path = transcriber.download_audio_from_url(apify_data["audio_url"])

        # Step 3: Transcribe with Deepgram
        transcript = transcriber.transcribe_audio_deepgram(audio_path)

        # Calculate total time
        total_time = time.time() - overall_start

        # Display results
        print("\n" + "=" * 70)
        print("✅ TRANSCRIPTION COMPLETE")
        print("=" * 70)

        print(f"\n📊 METADATA:")
        print(f"   📝 Title: {apify_data.get('title', 'N/A')}")
        print(f"   👤 Uploader: {apify_data.get('uploader', 'N/A')}")
        print(f"   📅 Upload Date: {apify_data.get('upload_date', 'N/A')}")
        print(f"   ⏱️  Duration: {apify_data.get('duration', 'N/A')}")
        print(f"   👁️  Views: {apify_data.get('view_count', 'N/A')}")
        print(f"   ❤️  Likes: {apify_data.get('like_count', 'N/A')}")

        print(f"\n📝 CAPTION:")
        print("-" * 70)
        print(apify_data.get('caption', 'N/A'))

        print(f"\n🎙️  TRANSCRIPT:")
        print("-" * 70)
        print(transcript)
        print("-" * 70)

        print(f"\n⏱️  Total processing time: {total_time:.2f} seconds")

        # Cleanup
        print("\n🗑️  Cleaning up temporary files...")
        transcriber.cleanup()

    except Exception as e:
        total_time = time.time() - overall_start
        print(f"\n❌ Error after {total_time:.2f} seconds: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()
