#!/usr/bin/env python3
"""
Instagram Overlay Text Processor

Extracts on-screen text from Instagram videos using frame sampling and Google Vision OCR.
Designed for videos where recipe information appears as text overlays rather than in transcript/description.
"""

import os
import cv2
import tempfile
import shutil
import base64
import requests
import asyncio
import aiohttp
from pathlib import Path
from typing import List, Dict, Any
import yt_dlp
from dotenv import load_dotenv

# Load environment variables  
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class OverlayTextProcessor:
    """
    Processes Instagram videos to extract text overlays using OCR.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the overlay text processor.
        
        Args:
            api_key: Google Cloud Vision API key. If None, uses GOOGLE_CLOUD_VISION env var.
        """
        # Set up Google Vision API key
        self.api_key = api_key or os.getenv('GOOGLE_CLOUD_VISION')
        if not self.api_key:
            raise Exception("Google Cloud Vision API key not found. Set GOOGLE_CLOUD_VISION environment variable.")
        
        # Vision API endpoint
        self.vision_api_url = f"https://vision.googleapis.com/v1/images:annotate?key={self.api_key}"
        
        print(f"✅ Google Vision API configured with key: {self.api_key[:10]}...")
        print(f"🔍 Full API URL: {self.vision_api_url[:50]}...")
        
        # Test if the API key format is correct
        if not self.api_key.startswith('AIzaSy'):
            print(f"⚠️  Warning: API key doesn't start with 'AIzaSy' - got: {self.api_key[:6]}...")
            print("   Make sure this is a Google Cloud API key, not a service account email")
        
        # Create temp directory for video and frames
        self.temp_dir = tempfile.mkdtemp(prefix="overlay_text_processor_")
        self.temp_files = []
    
    def download_video(self, instagram_url: str) -> str:
        """
        Download Instagram video using yt-dlp.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Path to downloaded video file
        """
        # Configure yt-dlp for video download
        video_path = os.path.join(self.temp_dir, 'instagram_video.mp4')
        
        ydl_opts = {
            'outtmpl': video_path.replace('.mp4', '.%(ext)s'),
            'format': 'best[ext=mp4]',  # Prefer mp4 for OpenCV compatibility
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([instagram_url])
                
                # Track for cleanup
                self.temp_files.append(video_path)
                
                # Verify file exists
                if not os.path.exists(video_path):
                    raise Exception(f"Video download failed - file not created: {video_path}")
                
                return video_path
                
        except yt_dlp.DownloadError as e:
            error_msg = str(e).lower()
            
            if 'private' in error_msg or 'login' in error_msg:
                raise Exception("Private video - cannot access for text extraction.")
            elif 'not available' in error_msg or 'removed' in error_msg:
                raise Exception("Video has been deleted or is no longer available.")
            else:
                raise Exception(f"Unable to download video: {str(e)}")
                
        except Exception as e:
            raise Exception(f"Unexpected error during video download: {str(e)}")
    
    def extract_frames(self, video_path: str, interval_seconds: float = 0.6) -> List[str]:
        """
        Extract frames from video at specified intervals.
        
        Args:
            video_path: Path to video file
            interval_seconds: Time interval between frames (default 0.6 seconds)
            
        Returns:
            List of paths to extracted frame images
        """
        frame_paths = []
        
        try:
            # Open video with OpenCV
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                raise Exception(f"Cannot open video file: {video_path}")
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            
            print(f"📹 Video info: {duration:.1f}s duration, {fps:.1f} fps, {total_frames} total frames")
            
            # Calculate frame interval
            frames_per_interval = int(fps * interval_seconds)
            print(f"🎬 Extracting frames every {interval_seconds}s ({frames_per_interval} frames)")
            
            frame_count = 0
            extracted_count = 0
            
            while True:
                ret, frame = cap.read()
                
                if not ret:
                    break
                
                # Extract frame at intervals
                if frame_count % frames_per_interval == 0:
                    # Generate frame filename
                    timestamp = frame_count / fps
                    frame_filename = f"frame_{extracted_count:04d}_t{timestamp:.1f}s.jpg"
                    frame_path = os.path.join(self.temp_dir, frame_filename)
                    
                    # Save frame
                    success = cv2.imwrite(frame_path, frame)
                    
                    if success:
                        frame_paths.append(frame_path)
                        self.temp_files.append(frame_path)
                        extracted_count += 1
                    else:
                        print(f"⚠️  Failed to save frame at {timestamp:.1f}s")
                
                frame_count += 1
            
            cap.release()
            
            print(f"✅ Extracted {len(frame_paths)} frames")
            return frame_paths
            
        except Exception as e:
            if 'cap' in locals():
                cap.release()
            raise Exception(f"Frame extraction failed: {str(e)}")
    
    async def extract_text_from_batch(self, frame_batch: List[str]) -> List[Dict[str, Any]]:
        """
        Extract text from a batch of frames using Google Vision API (up to 16 images per request).
        
        Args:
            frame_batch: List of frame file paths (max 16)
            
        Returns:
            List of results with extracted text for each frame
        """
        if len(frame_batch) > 16:
            raise ValueError("Batch size cannot exceed 16 images per Google Vision API limits")
        
        # Prepare batch request payload
        requests_payload = []
        
        for frame_path in frame_batch:
            try:
                # Read and encode image to base64
                with open(frame_path, 'rb') as image_file:
                    image_content = image_file.read()
                    image_base64 = base64.b64encode(image_content).decode('utf-8')
                
                # Add to batch payload
                requests_payload.append({
                    "image": {"content": image_base64},
                    "features": [{"type": "TEXT_DETECTION", "maxResults": 50}]
                })
                
            except Exception as e:
                print(f"⚠️  Error reading {os.path.basename(frame_path)}: {e}")
                # Add empty request to maintain order
                requests_payload.append(None)
        
        # Create batch API request
        batch_payload = {"requests": [req for req in requests_payload if req is not None]}
        
        if not batch_payload["requests"]:
            return []
        
        try:
            # Make async API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.vision_api_url,
                    json=batch_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"⚠️  Batch API error {response.status}: {error_text}")
                        return []
                    
                    result = await response.json()
                    
                    # Process batch results
                    batch_results = []
                    responses = result.get('responses', [])
                    
                    for i, frame_path in enumerate(frame_batch):
                        frame_name = os.path.basename(frame_path)
                        
                        # Get corresponding response (accounting for skipped frames)
                        if i < len(responses):
                            response_data = responses[i]
                            
                            # Extract text from response
                            text_annotations = response_data.get('textAnnotations', [])
                            
                            if text_annotations:
                                extracted_text = text_annotations[0].get('description', '').strip()
                                has_text = bool(extracted_text)
                            else:
                                extracted_text = ""
                                has_text = False
                        else:
                            extracted_text = ""
                            has_text = False
                        
                        batch_results.append({
                            'frame_path': frame_path,
                            'frame_name': frame_name,
                            'extracted_text': extracted_text,
                            'has_text': has_text
                        })
                    
                    return batch_results
                    
        except Exception as e:
            print(f"⚠️  Batch processing error: {e}")
            return []

    async def process_frames_in_parallel(self, frame_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Process all frames in parallel batches for maximum speed.
        
        Args:
            frame_paths: List of all frame file paths
            
        Returns:
            List of results with extracted text for each frame
        """
        # Group frames into batches of 16 (Google Vision API limit)
        batches = []
        for i in range(0, len(frame_paths), 16):
            batch = frame_paths[i:i+16]
            batches.append(batch)
        
        print(f"🚀 Processing {len(frame_paths)} frames in {len(batches)} parallel batches of up to 16 images")
        
        # Create async tasks for all batches
        tasks = []
        for batch_idx, batch in enumerate(batches):
            task = self.extract_text_from_batch(batch)
            tasks.append(task)
        
        # Execute all batches in parallel
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results from all batches
        all_results = []
        for batch_idx, batch_result in enumerate(batch_results):
            if isinstance(batch_result, Exception):
                print(f"⚠️  Batch {batch_idx + 1} failed: {batch_result}")
                # Add empty results for failed batch
                batch_size = len(batches[batch_idx])
                for i in range(batch_size):
                    frame_path = batches[batch_idx][i]
                    all_results.append({
                        'frame_number': len(all_results),
                        'frame_path': frame_path,
                        'frame_name': os.path.basename(frame_path),
                        'extracted_text': "",
                        'has_text': False
                    })
            else:
                # Add frame numbers to results
                for result in batch_result:
                    result['frame_number'] = len(all_results)
                    all_results.append(result)
        
        return all_results
    
    def process_instagram_video(self, instagram_url: str, interval_seconds: float = 0.6) -> List[Dict[str, Any]]:
        """
        Complete pipeline: download video, extract frames, and perform OCR.
        
        Args:
            instagram_url: Instagram post/reel URL
            interval_seconds: Frame sampling interval
            
        Returns:
            List of dictionaries with frame info and extracted text
        """
        results = []
        
        try:
            print(f"🔄 Processing: {instagram_url}")
            
            # Step 1: Download video
            print("📥 Downloading video...")
            video_path = self.download_video(instagram_url)
            
            # Step 2: Extract frames
            print("🎬 Extracting frames...")
            frame_paths = self.extract_frames(video_path, interval_seconds)
            
            if not frame_paths:
                print("❌ No frames extracted")
                return results
            
            # Step 3: OCR all frames in parallel batches
            print("🔍 Performing batch OCR on frames...")
            
            # Use async batch processing
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self.process_frames_in_parallel(frame_paths))
            finally:
                loop.close()
            
            # Print summary of results
            frames_with_text = [r for r in results if r['has_text']]
            print(f"✅ Batch processing complete!")
            print(f"   📊 Frames processed: {len(results)}")
            print(f"   📝 Frames with text: {len(frames_with_text)}")
            print(f"   🎯 Text detection rate: {len(frames_with_text)/len(results)*100:.1f}%" if results else "0%")
            
            return results
            
        finally:
            # Clean up temp files
            self.cleanup_files()
    
    def create_deduplicated_transcript(self, results: List[Dict[str, Any]]) -> str:
        """
        Create a deduplicated transcript from all extracted text.
        
        Args:
            results: List of frame results with extracted text
            
        Returns:
            Clean, deduplicated transcript combining all overlay text
        """
        # Get all text fragments that have content
        text_fragments = []
        
        for result in results:
            if result['has_text']:
                text = result['extracted_text'].strip()
                if text:
                    text_fragments.append(text)
        
        if not text_fragments:
            return "No overlay text found in video"
        
        # Advanced deduplication with better text cleaning
        seen_texts = set()
        unique_fragments = []
        
        for text in text_fragments:
            # Clean and normalize text for better comparison
            cleaned_text = self._clean_text(text)
            
            # Skip very short or meaningless text
            if len(cleaned_text) < 2:
                continue
            
            # Normalize for comparison (lowercase, remove extra whitespace)
            normalized = ' '.join(cleaned_text.lower().split())
            
            # Skip if we've seen this text before
            if normalized in seen_texts:
                continue
            
            # Check for substring duplicates (e.g., "butter" vs "butter chicken")
            is_substring = False
            for existing in seen_texts:
                if normalized in existing or existing in normalized:
                    # Keep the longer, more descriptive version
                    if len(normalized) > len(existing):
                        # Remove the shorter version and add the longer one
                        seen_texts.discard(existing)
                        # Find and remove the shorter version from unique_fragments
                        unique_fragments = [f for f in unique_fragments if ' '.join(self._clean_text(f).lower().split()) != existing]
                        break
                    else:
                        is_substring = True
                        break
            
            if not is_substring:
                seen_texts.add(normalized)
                unique_fragments.append(cleaned_text)
        
        # Join unique fragments into a coherent transcript
        deduplicated_transcript = '\n'.join(unique_fragments)
        
        return deduplicated_transcript
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by removing OCR artifacts and normalizing.
        
        Args:
            text: Raw OCR text
            
        Returns:
            Cleaned text
        """
        import re
        
        # Remove common OCR artifacts
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip single character lines (common OCR noise)
            if len(line) == 1:
                continue
                
            # Skip very short lines that are likely OCR artifacts
            if len(line) <= 3:
                # Allow only meaningful short words
                meaningful_short_words = {'oil', 'mix', 'the', 'and', 'add', 'put', 'hot', 'pan', 'egg', 'cup', 'tsp', 'tbsp'}
                if line.lower() not in meaningful_short_words:
                    continue
            
            # Skip lines with only numbers, symbols, or non-English characters
            if re.match(r'^[^a-zA-Z\s]*$', line):
                continue
                
            # Skip lines that are mostly numbers/symbols (less than 50% letters)
            letter_count = sum(1 for c in line if c.isalpha())
            total_count = len(line.replace(' ', ''))
            if total_count > 0 and letter_count / total_count < 0.5:
                continue
            
            # Skip common OCR artifacts patterns
            ocr_artifacts = {
                'od', 'oo', '00', '000', '090', 'dd', 'do', 'b.', 'c', 'd', 'a', 
                'eavy', 'の', '201', '21', '12', '20', '10', '9', '3'
            }
            if line.lower() in ocr_artifacts:
                continue
            
            # Skip Hebrew or other non-Latin script artifacts
            if re.search(r'[^\x00-\x7F]', line) and not re.search(r'[a-zA-Z]', line):
                continue
            
            cleaned_lines.append(line)
        
        # Join cleaned lines
        cleaned_text = '\n'.join(cleaned_lines)
        
        # Additional cleaning
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)  # Normalize whitespace
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text
    
    def cleanup_files(self):
        """
        Clean up temporary files and directory.
        """
        # Remove tracked files
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
        
        # Remove temp directory
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass


def main():
    """
    CLI interface for testing overlay text extraction.
    """
    print("📱 Instagram Overlay Text Processor")
    print("=" * 50)
    
    # Get Instagram URL from user
    instagram_url = input("\nEnter Instagram URL: ").strip()
    
    if not instagram_url:
        print("❌ No URL provided. Exiting.")
        return
    
    # Validate URL
    if "instagram.com" not in instagram_url:
        print("❌ Please provide a valid Instagram URL.")
        return
    
    # Get frame interval (optional)
    interval_input = input("\nFrame interval in seconds (default 0.6): ").strip()
    
    try:
        interval = float(interval_input) if interval_input else 0.6
    except ValueError:
        print("⚠️  Invalid interval, using default 0.6 seconds")
        interval = 0.6
    
    print(f"\n🔄 Starting overlay text extraction...")
    print(f"⏱️  Frame sampling interval: {interval} seconds")
    
    try:
        # Create processor
        processor = OverlayTextProcessor()
        
        # Process video
        results = processor.process_instagram_video(instagram_url, interval)
        
        # Display results
        print("\n" + "=" * 50)
        print("📊 OVERLAY TEXT EXTRACTION RESULTS")
        print("=" * 50)
        
        # Summary
        frames_with_text = [r for r in results if r['has_text']]
        print(f"\n📈 Summary:")
        print(f"   Total frames processed: {len(results)}")
        print(f"   Frames with text: {len(frames_with_text)}")
        print(f"   Text detection rate: {len(frames_with_text)/len(results)*100:.1f}%" if results else "0%")
        
        # Show individual frame results
        if frames_with_text:
            print(f"\n📝 Extracted Text by Frame:")
            print("-" * 30)
            
            for result in frames_with_text:
                print(f"\n🎬 {result['frame_name']}:")
                print(f"   {result['extracted_text']}")
        
        # Create and show deduplicated transcript
        if frames_with_text:
            deduplicated_transcript = processor.create_deduplicated_transcript(results)
            
            print(f"\n" + "=" * 50)
            print("📄 FINAL DEDUPLICATED OVERLAY TRANSCRIPT")
            print("=" * 50)
            print(f"\n{deduplicated_transcript}")
            print("\n" + "-" * 50)
        else:
            print("\n❌ No text found in any frames")
            print("💡 This video may not have text overlays, or the text may be too small/unclear for OCR")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    
    print("\n🎉 Processing complete!")


if __name__ == "__main__":
    main()