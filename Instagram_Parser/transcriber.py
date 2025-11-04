import os
import shutil
import tempfile
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import yt_dlp
from openai import OpenAI
import google.generativeai as genai
from dotenv import load_dotenv
from recipe_json_structuring import RecipeStructurer

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class InstagramTranscriber:
    """
    A class to extract and transcribe audio from Instagram videos.
    
    Handles the complete pipeline:
    1. Extract video from Instagram URL using yt-dlp
    2. Extract audio from video and convert to WAV
    3. Transcribe audio using OpenAI Whisper API
    4. Clean up temporary files
    """
    
    def __init__(self, openai_api_key: Optional[str] = None, google_api_key: Optional[str] = None):
        """
        Initialize the transcriber with OpenAI for transcription and Google Gemini for LLM parsing.
        
        Args:
            openai_api_key: OpenAI API key for Whisper transcription. If None, will use OPENAI_API_KEY env var.
            google_api_key: Google API key for Gemini LLM parsing. If None, will use GOOGLE_GEMINI_KEY env var.
        """
        # Initialize OpenAI client for Whisper transcription
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Initialize Google Gemini client for LLM parsing
        google_key = google_api_key or os.getenv('GOOGLE_GEMINI_KEY')
        if google_key:
            genai.configure(api_key=google_key)
            self.google_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            raise ValueError("Google Gemini API key is required. Please add GOOGLE_GEMINI_KEY to your .env file.")
        
        self.temp_dir = tempfile.mkdtemp(prefix="instagram_transcriber_")
        self.temp_files = []  # Track files for cleanup
        self.recipe_structurer = RecipeStructurer()  # Initialize JSON structurer
    
    def call_llm(self, prompt: str, provider: str = "openai", max_tokens: int = 500) -> str:
        """
        Unified LLM call method that can use OpenAI, Claude, Google Gemini, or XAI Grok.
        
        Args:
            prompt: The prompt to send to the LLM
            provider: "openai", "claude", "google", or "xai"
            max_tokens: Maximum tokens for the response
            
        Returns:
            LLM response text
        """
        provider = provider.lower()
        
        if provider == "openai":
            # Using GPT-4o (flagship model)
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
            
        elif provider == "claude":
            # Using Claude Sonnet 4 (latest flagship model)
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
            
        elif provider == "google":
            # Using Gemini 2.0 Flash Experimental (latest available model)
            if not self.google_model:
                raise ValueError("Google Gemini API key not configured. Please add GOOGLE_GEMINI_KEY to your .env file.")
            
            try:
                response = self.google_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=max_tokens
                    ),
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    ]
                )
                
                # Better response handling
                if hasattr(response, 'text') and response.text:
                    return response.text.strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content.parts:
                        return candidate.content.parts[0].text.strip()
                    else:
                        raise Exception(f"Gemini response blocked. Finish reason: {candidate.finish_reason}")
                else:
                    raise Exception("Gemini returned empty response")
                    
            except Exception as e:
                if "finish_reason" in str(e):
                    raise Exception(f"Gemini safety filter triggered: {str(e)}")
                else:
                    raise Exception(f"Gemini API error: {str(e)}")
        
        elif provider == "xai":
            # Using Grok Beta (current available model)
            if not self.xai_client:
                raise ValueError("XAI API key not configured. Please add X_AI_APY_KEY to your .env file.")
            response = self.xai_client.chat.completions.create(
                model="grok-4-fast-reasoning",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
            
        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'openai', 'claude', 'google', or 'xai'.")
    
    def extract_audio_directly(self, instagram_url: str) -> str:
        """
        Extract audio directly from Instagram URL using yt-dlp.
        Optimized to download audio-only format and convert to MP3 in single operation.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Path to downloaded MP3 audio file
            
        Raises:
            Exception: For private videos, deleted videos, or other extraction errors
        """
        # Generate output path for MP3 audio file
        audio_path = os.path.join(self.temp_dir, 'instagram_audio.mp3')
        
        # Configure yt-dlp options for direct audio extraction to MP3
        ydl_opts = {
            'format': 'bestaudio/best',  # Download best audio quality available
            'proxy': 'http://smart-ri5uzd2za4ec:Dw2OpGt3cD4ES8cj@proxy.smartproxy.net:3120',  # Smartproxy to bypass rate limits
            'outtmpl': audio_path.replace('.mp3', '.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',  # 64kbps for faster processing, sufficient for transcription
            }],
            'quiet': True,  # Suppress verbose output
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get info first to check accessibility (no download yet)
                info = ydl.extract_info(instagram_url, download=False)
                
                # Download and convert audio in single operation
                ydl.download([instagram_url])
                
                # Track audio file for cleanup
                self.temp_files.append(audio_path)
                
                # Verify the audio file was created
                if not os.path.exists(audio_path):
                    raise Exception(f"Audio extraction failed - MP3 file not created: {audio_path}")
                
                return audio_path
                
        except yt_dlp.DownloadError as e:
            error_msg = str(e).lower()
            
            # Handle specific error cases with user-friendly messages
            if 'private' in error_msg or 'login' in error_msg:
                raise Exception(
                    "Unfortunately, this video is a private video and we cannot parse it. "
                    "We can't use our Loomi magic to turn it into a recipe."
                )
            elif 'not available' in error_msg or 'removed' in error_msg or 'deleted' in error_msg:
                raise Exception(
                    "Ah shucks, this video has been deleted. "
                    "Maybe you could find another one on Instagram for us to try?"
                )
            else:
                # Generic error for other cases
                raise Exception(f"Unable to extract audio from Instagram URL: {str(e)}")
                
        except Exception as e:
            raise Exception(f"Unexpected error during audio extraction: {str(e)}")
    
    def extract_instagram_metadata(self, instagram_url: str) -> Dict[str, Any]:
        """
        Extract Instagram post metadata (title, description, etc.) using yt-dlp.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Dictionary containing post metadata
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(instagram_url, download=False)
                
                return {
                    'title': info.get('title', ''),
                    'description': info.get('description', ''),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'duration': info.get('duration', 0),
                    'view_count': info.get('view_count', 0)
                }
                
        except Exception as e:
            # Return empty metadata if extraction fails
            return {
                'title': '',
                'description': '',
                'uploader': '',
                'upload_date': '',
                'duration': 0,
                'view_count': 0
            }
    
    def combine_content_for_parsing(self, transcript: str, metadata: Dict[str, Any]) -> str:
        """
        Combine transcript and Instagram metadata into clean text for LLM parsing.
        
        Args:
            transcript: Transcribed audio text
            metadata: Instagram post metadata
            
        Returns:
            Combined text optimized for recipe extraction
        """
        # Clean description by removing hashtags, emojis, and extra whitespace
        description = metadata.get('description', '').strip()
        
        # Remove hashtags (anything starting with #)
        import re
        description = re.sub(r'#\w+', '', description).strip()
        
        # Remove common emoji patterns and extra whitespace
        description = re.sub(r'[^\w\s\-:.,!?()]', ' ', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Build combined content
        combined_parts = []
        
        if description:
            combined_parts.append(f"POST DESCRIPTION: {description}")
        
        if transcript:
            combined_parts.append(f"VIDEO TRANSCRIPT: {transcript}")
        
        # Join with clear separators
        combined_content = "\n\n".join(combined_parts)
        
        return combined_content
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio file using OpenAI Whisper API.
        Supports MP3, WAV, and other audio formats.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            
        Returns:
            Transcribed text from the audio
        """
        try:
            # Verify audio file exists before attempting transcription
            if not os.path.exists(audio_path):
                raise Exception(f"Audio file not found: {audio_path}")
            
            # Open and transcribe the audio file using Whisper
            with open(audio_path, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            # Return the transcribed text
            return transcript.strip() if transcript else ""
            
        except Exception as e:
            raise Exception(f"Failed to transcribe audio: {str(e)}")
    
    def extract_ingredients(self, combined_content: str) -> str:
        """
        Extract ingredients from combined transcript and description using Google Gemini.
        Only includes quantities and units when explicitly stated.
        
        Args:
            combined_content: Combined transcript and description text
            
        Returns:
            Simple list of ingredients (one per line)
        """
        import time
        start_time = time.time()
        
        # Load prompt from external file
        prompt_file_path = Path(__file__).parent / "Ingredients_LLM_Parsing_Prompt.txt"
        
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            # Replace placeholder with actual content
            prompt = prompt_template.format(combined_content=combined_content)
            
        except FileNotFoundError:
            raise Exception(f"Ingredients prompt file not found: {prompt_file_path}")
        except Exception as e:
            raise Exception(f"Error loading ingredients prompt: {str(e)}")

        try:
            # Use Google Gemini for ingredient extraction
            response = self.google_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=500
                ),
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            )
            
            # Extract response text
            if hasattr(response, 'text') and response.text:
                result = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content.parts:
                    result = candidate.content.parts[0].text.strip()
                else:
                    raise Exception(f"Gemini response blocked. Finish reason: {candidate.finish_reason}")
            else:
                raise Exception("Gemini returned empty response")
            
            elapsed = time.time() - start_time
            print(f"      🍅 Ingredients LLM (GEMINI): {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            if "finish_reason" in str(e):
                raise Exception(f"Failed to extract ingredients - Gemini safety filter: {str(e)}")
            else:
                raise Exception(f"Failed to extract ingredients: {str(e)}")
    
    def extract_title_and_directions(self, combined_content: str) -> str:
        """
        Extract recipe title and directions from combined transcript and description using Google Gemini.
        Combines information from both sources intelligently.
        
        Args:
            combined_content: Combined transcript and description text
            
        Returns:
            Simple list with title first, then directions (one per line)
        """
        import time
        start_time = time.time()
        
        # Load prompt from external file
        prompt_file_path = Path(__file__).parent / "Directions_LLM_Parsing_Prompt.txt"
        
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            # Replace placeholder with actual content
            prompt = prompt_template.format(combined_content=combined_content)
            
        except FileNotFoundError:
            raise Exception(f"Directions prompt file not found: {prompt_file_path}")
        except Exception as e:
            raise Exception(f"Error loading directions prompt: {str(e)}")

        try:
            # Use Google Gemini for directions extraction
            response = self.google_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=800
                ),
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            )
            
            # Extract response text
            if hasattr(response, 'text') and response.text:
                result = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content.parts:
                    result = candidate.content.parts[0].text.strip()
                else:
                    raise Exception(f"Gemini response blocked. Finish reason: {candidate.finish_reason}")
            else:
                raise Exception("Gemini returned empty response")
            
            elapsed = time.time() - start_time
            print(f"      📝 Directions LLM (GEMINI): {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            if "finish_reason" in str(e):
                raise Exception(f"Failed to extract title and directions - Gemini safety filter: {str(e)}")
            else:
                raise Exception(f"Failed to extract title and directions: {str(e)}")
    
    def parse_recipe_parallel(self, combined_content: str) -> Tuple[str, str]:
        """
        Run both ingredient and direction extraction in parallel using Google Gemini.
        
        Args:
            combined_content: Combined transcript and description text
            
        Returns:
            Tuple of (ingredients_output, title_directions_output)
        """
        import time
        
        # Use ThreadPoolExecutor to run both API calls in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            print("   🍅 Starting ingredients extraction (GEMINI)...")
            print("   📝 Starting directions extraction (GEMINI)...")
            
            parallel_start = time.time()
            
            # Submit both tasks using Gemini
            ingredients_future = executor.submit(self.extract_ingredients, combined_content)
            directions_future = executor.submit(self.extract_title_and_directions, combined_content)
            
            # Wait for both to complete and track individual times
            ingredients_result = ingredients_future.result()
            directions_result = directions_future.result()
            
            parallel_total = time.time() - parallel_start
            
            print(f"   ✅ Parallel LLM calls completed in {parallel_total:.2f}s")
            
            return ingredients_result, directions_result
    
    def cleanup_files(self):
        """
        Clean up all temporary files created during the transcription process.
        """
        # Remove individual tracked files
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                # Silently ignore file removal errors (file might already be deleted)
                pass
        
        # Clear the tracked files list
        self.temp_files.clear()
        
        # Remove the entire temporary directory
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception:
            # Silently ignore directory removal errors
            pass
    
    def transcribe_instagram_video(self, instagram_url: str) -> str:
        """
        Main method to transcribe an Instagram video from URL to text.
        
        Optimized pipeline:
        1. Extract audio directly from Instagram URL (MP3 format, single operation)
        2. Transcribe audio using Whisper API
        3. Clean up temporary files
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Transcribed text from the video
            
        Raises:
            Exception: With user-friendly error messages for various failure cases
        """
        try:
            # Extract audio directly from Instagram URL (optimized single operation)
            audio_path = self.extract_audio_directly(instagram_url)
            
            # Transcribe audio using Whisper
            transcript = self.transcribe_audio(audio_path)
            
            return transcript
            
        finally:
            # Always clean up temp files, even if an error occurs
            self.cleanup_files()
    
    def parse_instagram_recipe(self, instagram_url: str) -> Tuple[str, str, str]:
        """
        Complete pipeline: transcribe Instagram video and parse into recipe components.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Tuple of (transcript, ingredients_output, title_directions_output)
        """
        try:
            # Step 1: Extract audio and transcribe
            audio_path = self.extract_audio_directly(instagram_url)
            transcript = self.transcribe_audio(audio_path)
            
            # Step 2: Extract Instagram metadata  
            metadata = self.extract_instagram_metadata(instagram_url)
            
            # Step 3: Combine content for LLM parsing
            combined_content = self.combine_content_for_parsing(transcript, metadata)
            
            # Step 4: Run parallel recipe extraction
            ingredients_output, directions_output = self.parse_recipe_parallel(combined_content)
            
            return transcript, ingredients_output, directions_output
            
        finally:
            # Always clean up temp files, even if an error occurs
            self.cleanup_files()
    
    def parse_instagram_recipe_to_json(self, instagram_url: str) -> str:
        """
        Complete pipeline: transcribe Instagram video and return structured recipe JSON.
        Uses OpenAI Whisper for transcription and Google Gemini for recipe parsing.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Structured recipe JSON string with title, ingredients, directions, and source URL
        """
        import time
        
        total_start = time.time()
        timings = {}
        
        try:
            # Step 1: Extract audio 
            print("🔽 Step 1: Extracting audio from Instagram...")
            step_start = time.time()
            audio_path = self.extract_audio_directly(instagram_url)
            timings['audio_extraction'] = time.time() - step_start
            print(f"   ✅ Audio extracted ({timings['audio_extraction']:.2f}s)")
            
            # Step 2: Transcribe audio
            print("🎤 Step 2: Transcribing audio with Whisper...")
            step_start = time.time()
            transcript = self.transcribe_audio(audio_path)
            timings['transcription'] = time.time() - step_start
            print(f"   ✅ Transcription complete ({timings['transcription']:.2f}s)")
            
            # Step 3: Extract Instagram metadata  
            print("📋 Step 3: Extracting Instagram metadata...")
            step_start = time.time()
            metadata = self.extract_instagram_metadata(instagram_url)
            timings['metadata_extraction'] = time.time() - step_start
            print(f"   ✅ Metadata extracted ({timings['metadata_extraction']:.2f}s)")
            
            # Step 4: Combine content for LLM parsing
            print("🔗 Step 4: Combining content...")
            step_start = time.time()
            combined_content = self.combine_content_for_parsing(transcript, metadata)
            timings['content_combination'] = time.time() - step_start
            print(f"   ✅ Content combined ({timings['content_combination']:.2f}s)")
            
            # Step 5: Run parallel recipe extraction
            print("🤖 Step 5: Running parallel LLM recipe extraction (GEMINI)...")
            step_start = time.time()
            ingredients_output, directions_output = self.parse_recipe_parallel(combined_content)
            timings['llm_parsing'] = time.time() - step_start
            print(f"   ✅ LLM parsing complete ({timings['llm_parsing']:.2f}s)")
            
            # Step 6: Structure into JSON format
            print("📦 Step 6: Structuring into JSON...")
            step_start = time.time()
            recipe_json = self.recipe_structurer.process_llm_outputs(
                ingredients_output, 
                directions_output, 
                instagram_url
            )
            timings['json_structuring'] = time.time() - step_start
            print(f"   ✅ JSON structuring complete ({timings['json_structuring']:.2f}s)")
            
            # Calculate total time
            timings['total_time'] = time.time() - total_start
            
            # Display detailed timing breakdown
            print("\n" + "=" * 50)
            print("⏱️  DETAILED TIMING BREAKDOWN")
            print("=" * 50)
            print(f"🔽 Audio Extraction:     {timings['audio_extraction']:.2f}s ({timings['audio_extraction']/timings['total_time']*100:.1f}%)")
            print(f"🎤 Audio Transcription:  {timings['transcription']:.2f}s ({timings['transcription']/timings['total_time']*100:.1f}%)")
            print(f"📋 Metadata Extraction:  {timings['metadata_extraction']:.2f}s ({timings['metadata_extraction']/timings['total_time']*100:.1f}%)")
            print(f"🔗 Content Combination:  {timings['content_combination']:.2f}s ({timings['content_combination']/timings['total_time']*100:.1f}%)")
            print(f"🤖 LLM Recipe Parsing:   {timings['llm_parsing']:.2f}s ({timings['llm_parsing']/timings['total_time']*100:.1f}%)")
            print(f"📦 JSON Structuring:     {timings['json_structuring']:.2f}s ({timings['json_structuring']/timings['total_time']*100:.1f}%)")
            print(f"{'─' * 50}")
            print(f"🎯 TOTAL PROCESSING:     {timings['total_time']:.2f}s (100.0%)")
            print("=" * 50)
            
            return recipe_json
            
        finally:
            # Always clean up temp files, even if an error occurs
            self.cleanup_files()