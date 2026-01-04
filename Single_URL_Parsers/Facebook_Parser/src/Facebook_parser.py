"""
Facebook Recipe Parser

Extracts and processes recipes from Facebook videos using:
1. Apify Facebook Audio Downloader (for audio extraction)
2. Deepgram Nova-2 (for transcription)
3. Shared VerticalVideoProcessor (for recipe parsing steps 5-10)

Complete pipeline: Facebook URL → Audio → Transcript → Recipe JSON
"""

import os
import shutil
import tempfile
import time
import requests
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add paths for shared modules
import sys
sys.path.append(str(Path(__file__).parent.parent.parent / "Vertical_Video_Recipes"))

# Import shared vertical video processor
from vertical_video_processor import VerticalVideoProcessor

# Set up Deepgram environment variable (before importing)
deepgram_key = os.getenv('DEEPGRAM_WISPER_API')
if deepgram_key:
    os.environ['DEEPGRAM_API_KEY'] = deepgram_key

# Import Deepgram
try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False

# Import Google Gemini for LLM
import google.generativeai as genai


class FacebookTranscriber:
    """
    Extract and process recipes from Facebook videos.

    Pipeline:
    1. Extract Facebook data using Apify Facebook Audio Downloader
    2. Download audio from Facebook CDN
    3. Transcribe audio using Deepgram Nova-2
    4. Process recipe using shared VerticalVideoProcessor (steps 5-10)
    """

    def __init__(self, google_api_key: str = None):
        """
        Initialize Facebook transcriber.

        Args:
            google_api_key: Google Gemini API key (optional, will use env var if not provided)
        """
        # Initialize Google Gemini for LLM processing
        google_key = google_api_key or os.getenv('GOOGLE_GEMINI_KEY')
        if google_key:
            genai.configure(api_key=google_key)
            self.google_model = genai.GenerativeModel('gemini-2.5-flash-lite')
        else:
            raise ValueError("Google Gemini API key is required. Set GOOGLE_GEMINI_KEY in .env")

        # Initialize Apify client
        self.apify_token = os.getenv("APIFY_API_KEY")
        if not self.apify_token:
            raise ValueError("APIFY_API_KEY not found in .env file")

        # Initialize Deepgram client
        self.deepgram_client = None
        if DEEPGRAM_AVAILABLE and deepgram_key:
            try:
                self.deepgram_client = DeepgramClient()
            except Exception as e:
                print(f"⚠️  Failed to initialize Deepgram client: {str(e)}")
                self.deepgram_client = None

        # Initialize shared vertical video processor (handles steps 5-10)
        self.vertical_video_processor = VerticalVideoProcessor(self.google_model)

        # Temp directory for audio files
        self.temp_dir = tempfile.mkdtemp(prefix="facebook_transcriber_")
        self.temp_files = []

    def extract_with_apify(self, facebook_url: str) -> Dict[str, Any]:
        """
        Extract Facebook audio data using Apify's Facebook Audio Downloader.

        Args:
            facebook_url: Facebook video or reel URL

        Returns:
            Dictionary with audio_download_url, description, and metadata
        """
        actor_id = "alpha-scraper~facebook-audio-downloader"
        endpoint = f"https://api.apify.com/v2/acts/{actor_id}/runs"

        payload = {
            "startUrls": [
                {
                    "url": facebook_url
                }
            ]
        }

        headers = {"Content-Type": "application/json"}
        params = {"token": self.apify_token}

        try:
            print(f"🚀 Step 1: Extracting Facebook data with Apify...")
            start_time = time.time()

            # Start actor run
            response = requests.post(endpoint, json=payload, headers=headers, params=params, timeout=10)

            if response.status_code in [200, 201]:
                run_data = response.json()
                run_id = run_data.get("data", {}).get("id")

                # Wait for run to complete
                run_status_url = f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}"
                status_params = {"token": self.apify_token}

                max_wait = 120
                poll_interval = 2
                elapsed = 0

                while elapsed < max_wait:
                    time.sleep(poll_interval)
                    elapsed += poll_interval

                    status_response = requests.get(run_status_url, params=status_params, timeout=10)

                    if status_response.status_code == 200:
                        run_info = status_response.json()
                        status = run_info.get("data", {}).get("status")

                        if status == "SUCCEEDED":
                            # Get dataset
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
                                            "audio_url": item.get("audio_download_url"),
                                            "video_url": item.get("url", ""),
                                            "caption": item.get("description", ""),
                                            "title": item.get("title", ""),
                                            "uploader": item.get("uploader", ""),
                                            "upload_date": item.get("upload_date", ""),
                                            "duration": item.get("duration", ""),
                                            "view_count": "",  # Facebook doesn't provide this consistently
                                            "like_count": "",
                                            "comment_count": "",
                                            "thumbnail_url": ""  # Facebook doesn't provide thumbnail
                                        }

                raise Exception("Actor did not complete successfully or returned no items")

            else:
                raise Exception(f"Apify API error: HTTP {response.status_code}")

        except Exception as e:
            raise Exception(f"Failed to extract Facebook data: {str(e)}")

    def download_audio_from_url(self, audio_url: str) -> str:
        """
        Download audio from Facebook CDN URL.

        Args:
            audio_url: Direct audio URL from Apify

        Returns:
            Path to downloaded audio file
        """
        print(f"🔽 Step 2: Downloading audio from Facebook CDN...")

        audio_path = os.path.join(self.temp_dir, "facebook_audio.m4a")

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
            'Referer': 'https://www.facebook.com/',
            'Accept': 'audio/mpeg,audio/*;q=0.9,*/*;q=0.8',
        }

        try:
            start_time = time.time()
            response = requests.get(audio_url, headers=headers, stream=True, timeout=30)

            if response.status_code == 200:
                total_size = 0
                with open(audio_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)

                file_size_mb = total_size / (1024 * 1024)
                download_time = time.time() - start_time

                print(f"   ✅ Audio downloaded in {download_time:.2f}s ({file_size_mb:.2f} MB)")

                self.temp_files.append(audio_path)
                return audio_path

            else:
                raise Exception(f"Download failed: HTTP {response.status_code}")

        except Exception as e:
            raise Exception(f"Failed to download audio: {str(e)}")

    def transcribe_audio_deepgram(self, audio_path: str) -> str:
        """
        Transcribe audio using Deepgram Nova-2.

        Args:
            audio_path: Path to audio file

        Returns:
            Transcribed text
        """
        print(f"🎤 Step 3: Transcribing audio with Deepgram Nova-2...")

        if not self.deepgram_client:
            raise Exception("Deepgram client not initialized")

        if not os.path.exists(audio_path):
            raise Exception(f"Audio file not found: {audio_path}")

        try:
            start_time = time.time()

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

                return transcript
            else:
                raise Exception("No transcript found in Deepgram response")

        except Exception as e:
            raise Exception(f"Deepgram transcription failed: {str(e)}")

    def format_apify_metadata(self, apify_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Apify data into standardized metadata format for VerticalVideoProcessor.

        Args:
            apify_data: Raw Apify response data

        Returns:
            Standardized metadata dictionary
        """
        return {
            'caption': apify_data.get('caption', ''),
            'creator_username': apify_data.get('uploader', ''),
            'creator_id': '',  # TikTok doesn't provide this
            'likes_count': apify_data.get('like_count', ''),
            'view_count': apify_data.get('view_count', ''),
            'comment_count': apify_data.get('comment_count', ''),
            'upload_date': apify_data.get('upload_date', ''),
            'image_url': apify_data.get('thumbnail_url', ''),  # Cover photo/thumbnail
            'duration': apify_data.get('duration', '')
        }

    def parse_facebook_recipe_to_json(self, facebook_url: str) -> str:
        """
        Complete pipeline: Extract Facebook video and return structured recipe JSON.

        Args:
            facebook_url: Facebook video or reel URL

        Returns:
            Structured recipe JSON string
        """
        total_start = time.time()
        timings = {}

        try:
            # Step 1: Extract Facebook data with Apify
            step_start = time.time()
            apify_data = self.extract_with_apify(facebook_url)
            timings['apify_extraction'] = time.time() - step_start

            if not apify_data.get("audio_url"):
                raise Exception("No audio URL returned from Apify")

            # Step 2: Download audio
            step_start = time.time()
            audio_path = self.download_audio_from_url(apify_data["audio_url"])
            timings['audio_download'] = time.time() - step_start

            # Step 3: Transcribe with Deepgram
            step_start = time.time()
            transcript = self.transcribe_audio_deepgram(audio_path)
            timings['transcription'] = time.time() - step_start

            # Step 4: Format metadata
            print("📋 Step 4: Formatting metadata...")
            step_start = time.time()
            metadata = self.format_apify_metadata(apify_data)
            timings['metadata_formatting'] = time.time() - step_start
            print(f"   ✅ Metadata formatted ({timings['metadata_formatting']:.2f}s)")

            # Steps 5-10: Use shared VerticalVideoProcessor
            print("\n🎬 Steps 5-10: Processing with shared Vertical Video Processor...")
            step_start = time.time()

            recipe_json = self.vertical_video_processor.process_recipe(
                transcript=transcript,
                metadata=metadata,
                source_url=facebook_url,
                parser_method="Facebook"
            )

            timings['vertical_video_processing'] = time.time() - step_start
            print(f"   ✅ Vertical video processing complete ({timings['vertical_video_processing']:.2f}s)")

            # Calculate total time
            timings['total_time'] = time.time() - total_start

            # Display timing breakdown
            print("\n" + "=" * 50)
            print("⏱️  DETAILED TIMING BREAKDOWN")
            print("=" * 50)
            print(f"🚀 Apify Data Extraction:  {timings['apify_extraction']:.2f}s ({timings['apify_extraction']/timings['total_time']*100:.1f}%)")
            print(f"🔽 Audio Download:         {timings['audio_download']:.2f}s ({timings['audio_download']/timings['total_time']*100:.1f}%)")
            print(f"🎤 Deepgram Transcription: {timings['transcription']:.2f}s ({timings['transcription']/timings['total_time']*100:.1f}%)")
            print(f"📋 Metadata Formatting:    {timings['metadata_formatting']:.2f}s ({timings['metadata_formatting']/timings['total_time']*100:.1f}%)")
            print(f"🎬 Recipe Processing:      {timings['vertical_video_processing']:.2f}s ({timings['vertical_video_processing']/timings['total_time']*100:.1f}%)")
            print(f"   (LLM parsing, quality control, JSON structuring)")
            print(f"{'─' * 50}")
            print(f"🎯 TOTAL PROCESSING:       {timings['total_time']:.2f}s (100.0%)")
            print("=" * 50)

            return recipe_json

        finally:
            # Always clean up temp files
            self.cleanup_files()

    def cleanup_files(self):
        """Remove temporary files and directory."""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

        self.temp_files.clear()

        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass
