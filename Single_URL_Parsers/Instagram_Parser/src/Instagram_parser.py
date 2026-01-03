import os
import shutil
import tempfile
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import yt_dlp
import requests
import time
from openai import OpenAI
import google.generativeai as genai
from dotenv import load_dotenv
from instagram_json_structuring import RecipeStructurer

# Load environment variables from .env file  
env_path = Path(__file__).parent.parent.parent.parent / ".env"  # Go up to loomi_ai_agent directory
load_dotenv(dotenv_path=env_path)

# Add paths for shared modules
import sys
sys.path.append(str(Path(__file__).parent.parent.parent / "Step_Ingredient_Matching"))
sys.path.append(str(Path(__file__).parent.parent.parent / "Meta_Step_Extraction"))
sys.path.append(str(Path(__file__).parent.parent.parent / "Recipe_Quality_Control"))

# Import shared modules
from step_ingredient_matcher import StepIngredientMatcher
from meta_step_extractor import MetaStepExtractor
from recipe_quality_controller import RecipeQualityController

# Import enhanced JSON model
sys.path.append(str(Path(__file__).parent.parent.parent))
from json_recipe_model import create_enhanced_recipe_json

# Set up Deepgram environment variable if available (before importing)
deepgram_key = os.getenv('DEEPGRAM_WISPER_API')
if deepgram_key:
    os.environ['DEEPGRAM_API_KEY'] = deepgram_key

# Optional Deepgram import
try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False


class InstagramTranscriber:
    """
    A class to extract and transcribe audio from Instagram videos.
    
    Handles the complete pipeline:
    1. Extract video data using Apify Instagram scraper (fast)
    2. Download audio from direct video URL and convert to MP3
    3. Transcribe audio using Deepgram Nova-2 (fast & accurate)
    4. Parse recipe content using Google Gemini LLM
    5. Clean up temporary files
    """
    
    def __init__(self, openai_api_key: Optional[str] = None, google_api_key: Optional[str] = None):
        """
        Initialize the transcriber with Deepgram for transcription and Google Gemini for LLM parsing.
        
        Args:
            openai_api_key: Not used anymore (kept for compatibility).
            google_api_key: Google API key for Gemini LLM parsing. If None, will use GOOGLE_GEMINI_KEY env var.
        """
        # Initialize OpenAI client (kept for compatibility, not used for transcription)
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Initialize Google Gemini client for LLM parsing
        google_key = google_api_key or os.getenv('GOOGLE_GEMINI_KEY')
        if google_key:
            genai.configure(api_key=google_key)
            self.google_model = genai.GenerativeModel('gemini-2.5-flash-lite')
        else:
            raise ValueError("Google Gemini API key is required. Please add GOOGLE_GEMINI_KEY to your .env file.")
        
        # Initialize Apify client for Instagram scraping
        self.apify_token = os.getenv("APIFY_API_KEY")
        if not self.apify_token:
            raise ValueError("APIFY_API_KEY not found in .env file. Please add it.")
        # Use general Instagram scraper
        self.apify_base_url = "https://api.apify.com/v2/acts/apify~instagram-scraper"
        
        # Initialize Deepgram client (optional)
        self.deepgram_client = None
        if DEEPGRAM_AVAILABLE and deepgram_key:
            try:
                self.deepgram_client = DeepgramClient()
            except Exception as e:
                print(f"⚠️  Failed to initialize Deepgram client: {str(e)}")
                self.deepgram_client = None
        
        self.temp_dir = tempfile.mkdtemp(prefix="instagram_transcriber_")
        self.temp_files = []  # Track files for cleanup
        self.recipe_structurer = RecipeStructurer()  # Initialize JSON structurer

        # Initialize shared recipe analysis modules
        self.step_ingredient_matcher = StepIngredientMatcher(self.google_model)
        self.meta_step_extractor = MetaStepExtractor(self.google_model)
        self.quality_controller = RecipeQualityController(self.google_model)
    
    def call_llm(self, prompt: str, provider: str = "openai", max_tokens: int = 1200) -> str:
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
    
    def extract_with_apify(self, instagram_url: str) -> Dict[str, Any]:
        """
        Extract Instagram post data using Apify's Instagram scraper.
        Uses the general scraper with Apify's built-in retry mechanism.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Dictionary containing video URL, metadata, and creator info
            
        Raises:
            Exception: For private videos, deleted videos, or other extraction errors
        """
        endpoint = f"{self.apify_base_url}/run-sync-get-dataset-items"
        
        payload = {
            "directUrls": [instagram_url],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False
        }
        
        headers = {"Content-Type": "application/json"}
        params = {"token": self.apify_token, "timeout": 120}
        
        try:
            print(f"🚀 Extracting Instagram data with Apify...")
            start_time = time.time()
            
            response = requests.post(endpoint, json=payload, headers=headers, params=params, timeout=120)
            
            # Accept both 200 and 201 as success
            if response.status_code in [200, 201]:
                result = response.json()
                
                if not result or len(result) == 0:
                    raise Exception("No data returned from Apify scraper")
                
                post_data = result[0]
                
                # Extract essential data only
                extracted_data = {
                    "video_url": post_data.get("videoUrl"),
                    "duration": post_data.get("videoDuration", 0),
                    "caption": post_data.get("caption", ""),
                    "creator_username": post_data.get("ownerUsername", ""),
                    "creator_id": post_data.get("ownerId", ""),
                    "likes_count": post_data.get("likesCount", 0),
                    "post_type": post_data.get("type", ""),
                    "image_url": post_data.get("displayUrl", "")
                }
                
                if not extracted_data["video_url"]:
                    raise Exception("No video URL found in Instagram post")
                
                extraction_time = time.time() - start_time
                print(f"✅ Apify extraction completed in {extraction_time:.2f}s")
                
                return extracted_data
                
            else:
                raise Exception(f"Apify API error: HTTP {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise Exception("Apify request timed out - Instagram might be blocking or post unavailable")
        except Exception as e:
            error_msg = str(e).lower()
            if 'private' in error_msg or 'login' in error_msg:
                raise Exception(
                    "Unfortunately, this video is a private video and we cannot parse it. "
                    "We can't use our Loomi magic to turn it into a recipe."
                )
            else:
                raise Exception(f"Failed to extract Instagram data: {str(e)}")
    
    def download_audio_from_url(self, video_url: str) -> str:
        """
        Download audio directly from video URL without proxy.
        
        Args:
            video_url: Direct video URL from Apify
            
        Returns:
            Path to downloaded MP3 audio file
        """
        audio_path = os.path.join(self.temp_dir, 'instagram_audio.mp3')
        
        ydl_opts = {
            'format': 'bestaudio/best',
            # Proxy commented out for Apify testing
            # 'proxy': 'http://smart-ri5uzd2za4ec:Dw2OpGt3cD4ES8cj@proxy.smartproxy.net:3120',
            'outtmpl': audio_path.replace('.mp3', '.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
                
                self.temp_files.append(audio_path)
                
                if not os.path.exists(audio_path):
                    raise Exception(f"Audio extraction failed - MP3 file not created: {audio_path}")
                
                return audio_path
                
        except Exception as e:
            raise Exception(f"Failed to download audio from video URL: {str(e)}")
    
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
            'proxy': 'http://smart-ri5uzd2za4ec:Dw2OpGt3cD4ES8cj@proxy.smartproxy.net:3120',  # Smartproxy to bypass rate limits (trades speed for scalability)
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
    
    def format_apify_metadata(self, apify_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Apify data to match expected metadata format.
        
        Args:
            apify_data: Data extracted from Apify
            
        Returns:
            Dictionary containing formatted metadata
        """
        return {
            'title': f"Recipe by @{apify_data.get('creator_username', 'unknown')}",
            'description': apify_data.get('caption', ''),
            'uploader': apify_data.get('creator_username', ''),
            'upload_date': '',  # Not needed for our use case
            'duration': apify_data.get('duration', 0),
            'view_count': apify_data.get('likes_count', 0)  # Use likes as proxy for popularity
        }
    
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
    
    def transcribe_audio_whisper(self, audio_path: str) -> str:
        """
        Transcribe audio file using OpenAI Whisper API.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            
        Returns:
            Transcribed text from the audio
        """
        try:
            if not os.path.exists(audio_path):
                raise Exception(f"Audio file not found: {audio_path}")
            
            with open(audio_path, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            return transcript.strip() if transcript else ""
            
        except Exception as e:
            raise Exception(f"Failed to transcribe audio with Whisper: {str(e)}")
    
    def transcribe_audio_gpt4o(self, audio_path: str) -> str:
        """
        Transcribe audio using GPT-4o with proper audio configuration.
        This should be faster than Whisper for transcription tasks.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            
        Returns:
            Transcribed text from the audio
        """
        import base64
        
        try:
            if not os.path.exists(audio_path):
                raise Exception(f"Audio file not found: {audio_path}")
            
            # Read and encode the audio file
            with open(audio_path, "rb") as audio_file:
                audio_data = base64.b64encode(audio_file.read()).decode('utf-8')
            
            # Use GPT-4o with proper audio configuration
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-audio-preview",
                modalities=["text"],  # Only text output needed
                audio={"voice": "alloy", "format": "mp3"},  # Audio output config (required even if not used)
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Please transcribe this audio file accurately. Focus on cooking instructions, ingredients, and recipe details. Return only the transcribed text without any additional commentary."
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_data,
                                    "format": "mp3"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1
            )
            
            return response.choices[0].message.content.strip() if response.choices[0].message.content else ""
            
        except Exception as e:
            # Fallback to Whisper if GPT-4o fails
            print(f"⚠️  GPT-4o transcription failed: {str(e)}")
            print("🔄 Falling back to Whisper...")
            return self.transcribe_audio_whisper(audio_path)
    
    def transcribe_audio_deepgram(self, audio_path: str) -> str:
        """
        Transcribe audio using Deepgram's Nova-3 model.
        Should be faster than Whisper and competitive with GPT-4o.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            
        Returns:
            Transcribed text from the audio
        """
        try:
            if not self.deepgram_client:
                if not DEEPGRAM_AVAILABLE:
                    raise Exception("Deepgram SDK not installed. Install with: pip install deepgram-sdk")
                else:
                    raise Exception("Deepgram client not initialized - check DEEPGRAM_WISPER_API key")
            
            if not os.path.exists(audio_path):
                raise Exception(f"Audio file not found: {audio_path}")
            
            # Read audio file and transcribe using Nova-2 model
            with open(audio_path, "rb") as audio_file:
                response = self.deepgram_client.listen.v1.media.transcribe_file(
                    request=audio_file.read(),
                    model="nova-2"
                )
            
            # Extract transcript from response
            if (response.results and 
                response.results.channels and 
                len(response.results.channels) > 0 and
                response.results.channels[0].alternatives and
                len(response.results.channels[0].alternatives) > 0):
                
                transcript = response.results.channels[0].alternatives[0].transcript
                return transcript.strip() if transcript else ""
            else:
                raise Exception("No transcript found in Deepgram response")
                
        except Exception as e:
            raise Exception(f"Failed to transcribe audio with Deepgram: {str(e)}")
    
    def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio file using Deepgram.
        
        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            
        Returns:
            Transcribed text from the audio
        """
        start_time = time.time()
        
        try:
            transcript = self.transcribe_audio_deepgram(audio_path)
            duration = time.time() - start_time
            print(f"   ✅ Deepgram transcription: {duration:.2f}s")
            return transcript
            
        except Exception as e:
            duration = time.time() - start_time
            print(f"   ❌ Transcription failed after {duration:.2f}s: {str(e)}")
            raise
    
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
        prompt_file_path = Path(__file__).parent / "llm_prompts" / "Ingredients_LLM_Parsing_Prompt.txt"
        
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
                    max_output_tokens=1200
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
        prompt_file_path = Path(__file__).parent / "llm_prompts" / "Directions_LLM_Parsing_Prompt.txt"
        
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
                    max_output_tokens=1200
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
    
    def extract_meal_occasion(self, combined_content: str) -> str:
        """
        Extract meal occasion from combined transcript and description using Google Gemini.
        Returns one of: Breakfast, Lunch, Dinner, Dessert, Snack, Other
        
        Args:
            combined_content: Combined transcript and description text
            
        Returns:
            Meal occasion string (one of the six categories)
        """
        import time
        start_time = time.time()
        
        # Load prompt from external file
        prompt_file_path = Path(__file__).parent / "llm_prompts" / "Meal_Occasion_LLM_Parsing_Prompt.txt"
        
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            
            # Replace placeholder with actual content
            prompt = prompt_template.format(combined_content=combined_content)
            
        except FileNotFoundError:
            raise Exception(f"Meal occasion prompt file not found: {prompt_file_path}")
        except Exception as e:
            raise Exception(f"Error loading meal occasion prompt: {str(e)}")

        try:
            # Use Google Gemini for meal occasion extraction
            response = self.google_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1200  # Increased for Gemini 2.5 compatibility
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
            
            # Validate that the result is one of the expected categories
            valid_categories = ["Breakfast", "Lunch", "Dinner", "Dessert", "Snack", "Other"]
            if result in valid_categories:
                meal_occasion = result
            else:
                # If LLM returns something unexpected, default to "Other" 
                meal_occasion = "Other"
            
            elapsed = time.time() - start_time
            print(f"      🍽️  Meal Occasion LLM (GEMINI): {elapsed:.2f}s")
            
            return meal_occasion
            
        except Exception as e:
            if "finish_reason" in str(e):
                raise Exception(f"Failed to extract meal occasion - Gemini safety filter: {str(e)}")
            else:
                raise Exception(f"Failed to extract meal occasion: {str(e)}")
    
    def parse_recipe_parallel(self, combined_content: str) -> Tuple[str, str, str]:
        """
        Run ingredient, direction, and meal occasion extraction in parallel using Google Gemini.
        
        Args:
            combined_content: Combined transcript and description text
            
        Returns:
            Tuple of (ingredients_output, title_directions_output, meal_occasion_output)
        """
        import time
        
        # Use ThreadPoolExecutor to run all three API calls in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            print("   🍅 Starting ingredients extraction (GEMINI)...")
            print("   📝 Starting directions extraction (GEMINI)...")
            print("   🍽️  Starting meal occasion extraction (GEMINI)...")
            
            parallel_start = time.time()
            
            # Submit all three tasks using Gemini
            ingredients_future = executor.submit(self.extract_ingredients, combined_content)
            directions_future = executor.submit(self.extract_title_and_directions, combined_content)
            meal_occasion_future = executor.submit(self.extract_meal_occasion, combined_content)
            
            # Wait for all three to complete and track individual times
            ingredients_result = ingredients_future.result()
            directions_result = directions_future.result()
            meal_occasion_result = meal_occasion_future.result()
            
            parallel_total = time.time() - parallel_start
            
            print(f"   ✅ Parallel LLM calls completed in {parallel_total:.2f}s")
            
            return ingredients_result, directions_result, meal_occasion_result
    
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
            # Extract Instagram data with Apify (NEW - replaces yt-dlp + proxy)
            apify_data = self.extract_with_apify(instagram_url)
            
            # Download audio from direct video URL (no proxy needed)
            audio_path = self.download_audio_from_url(apify_data['video_url'])
            
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
            # Step 1: Extract Instagram data with Apify
            apify_data = self.extract_with_apify(instagram_url)
            
            # Step 2: Download audio from video URL
            audio_path = self.download_audio_from_url(apify_data['video_url'])
            
            # Step 3: Transcribe audio with GPT-4o
            transcript = self.transcribe_audio(audio_path, provider="gpt4o")
            
            # Step 4: Format metadata from Apify data
            metadata = self.format_apify_metadata(apify_data)
            
            # Step 5: Combine content for LLM parsing
            combined_content = self.combine_content_for_parsing(transcript, metadata)
            
            # Step 6: Run parallel recipe extraction
            ingredients_output, directions_output, meal_occasion_output = self.parse_recipe_parallel(combined_content)
            
            return transcript, ingredients_output, directions_output, meal_occasion_output
            
        finally:
            # Always clean up temp files, even if an error occurs
            self.cleanup_files()
    
    def parse_instagram_recipe_to_json(self, instagram_url: str) -> str:
        """
        Complete pipeline: transcribe Instagram video and return structured recipe JSON.
        Uses Deepgram for fast transcription and Google Gemini for recipe parsing.
        
        Args:
            instagram_url: Instagram post/reel URL
            
        Returns:
            Structured recipe JSON string with title, ingredients, directions, and source URL
        """
        import time
        
        total_start = time.time()
        timings = {}
        
        try:
            # Step 1: Extract Instagram data with Apify (NEW - replaces yt-dlp + proxy)
            print("🚀 Step 1: Extracting Instagram data with Apify...")
            step_start = time.time()
            apify_data = self.extract_with_apify(instagram_url)
            timings['apify_extraction'] = time.time() - step_start
            print(f"   ✅ Instagram data extracted ({timings['apify_extraction']:.2f}s)")
            print(f"   📹 Video URL found: {apify_data['video_url'][:50]}...")
            print(f"   👤 Creator: @{apify_data['creator_username']}")
            
            # Step 2: Download audio from direct video URL (no proxy needed)
            print("🔽 Step 2: Downloading audio from video URL...")
            step_start = time.time()
            audio_path = self.download_audio_from_url(apify_data['video_url'])
            timings['audio_download'] = time.time() - step_start
            print(f"   ✅ Audio downloaded ({timings['audio_download']:.2f}s)")
            
            # Step 3: Transcribe audio with Deepgram
            print("🎤 Step 3: Transcribing audio with Deepgram...")
            step_start = time.time()
            transcript = self.transcribe_audio(audio_path)
            timings['transcription'] = time.time() - step_start
            print(f"   ✅ Transcription complete ({timings['transcription']:.2f}s)")
            
            # Step 4: Format metadata from Apify data
            print("📋 Step 4: Formatting metadata...")
            step_start = time.time()
            metadata = self.format_apify_metadata(apify_data)
            timings['metadata_formatting'] = time.time() - step_start
            print(f"   ✅ Metadata formatted ({timings['metadata_formatting']:.2f}s)")
            
            # Step 5: Combine content for LLM parsing
            print("🔗 Step 5: Combining content...")
            step_start = time.time()
            combined_content = self.combine_content_for_parsing(transcript, metadata)
            timings['content_combination'] = time.time() - step_start
            print(f"   ✅ Content combined ({timings['content_combination']:.2f}s)")
            
            # Step 6: Run parallel recipe extraction
            print("🤖 Step 6: Running parallel LLM recipe extraction (GEMINI)...")
            step_start = time.time()
            ingredients_output, directions_output, meal_occasion_output = self.parse_recipe_parallel(combined_content)
            timings['llm_parsing'] = time.time() - step_start
            print(f"   ✅ LLM parsing complete ({timings['llm_parsing']:.2f}s)")
            
            # Step 6.5: Parse LLM outputs into structured format
            print("📋 Step 6.5: Parsing LLM outputs...")
            step_start = time.time()

            # Parse LLM outputs into structured format for analysis
            parsed_ingredients = self.recipe_structurer.parse_ingredients(ingredients_output)
            title, parsed_directions = self.recipe_structurer.parse_directions(directions_output)

            # Convert ParsedIngredient objects to dict format for quality control
            ingredients_for_quality_control = [
                {
                    "name": ing.name,
                    "quantity": ing.quantity,
                    "unit": ing.unit
                }
                for ing in parsed_ingredients
            ]

            timings['parsing'] = time.time() - step_start
            print(f"   ✅ Parsing complete ({timings['parsing']:.2f}s)")

            # Step 7: PARALLEL BATCH 2 - Quality Control (clean ingredients + paraphrase directions)
            print("🧹 Step 7: Running quality control (GEMINI)...")
            step_start = time.time()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both quality control tasks
                clean_ingredients_future = executor.submit(
                    self.quality_controller.clean_ingredients_with_llm,
                    ingredients_for_quality_control
                )
                paraphrase_directions_future = executor.submit(
                    self.quality_controller.paraphrase_directions_with_llm,
                    parsed_directions
                )

                # Get results
                cleaned_ingredients = clean_ingredients_future.result()
                paraphrased_directions = paraphrase_directions_future.result()

            timings['quality_control'] = time.time() - step_start
            print(f"   ✅ Quality control complete ({timings['quality_control']:.2f}s)")

            # Step 8: PARALLEL BATCH 3 - Rescue + Meta Steps
            print("🔧 Step 8: Running rescue + meta step analysis (GEMINI)...")
            step_start = time.time()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit rescue and meta step tasks
                rescue_future = executor.submit(
                    self.quality_controller.rescue_failed_ingredient_parses,
                    cleaned_ingredients
                )
                meta_step_future = executor.submit(
                    self.meta_step_extractor.extract_meta_steps,
                    cleaned_ingredients,  # Use cleaned ingredients for context
                    paraphrased_directions,  # Use paraphrased directions (Option B!)
                    title
                )

                # Get results
                rescued_ingredients = rescue_future.result()
                meta_step_result = meta_step_future.result()  # Already has paraphrased text!

            timings['rescue_and_meta'] = time.time() - step_start
            print(f"   ✅ Rescue + meta step analysis complete ({timings['rescue_and_meta']:.2f}s)")

            # Step 9: SEQUENTIAL - Step-Ingredient Matching (uses rescued ingredients)
            print("🔗 Step 9: Matching ingredients to steps (GEMINI)...")
            step_start = time.time()

            step_ingredient_result = self.step_ingredient_matcher.match_steps_with_ingredients(
                rescued_ingredients,  # Use final rescued ingredients
                paraphrased_directions  # Use paraphrased directions
            )

            timings['step_matching'] = time.time() - step_start
            print(f"   ✅ Step-ingredient matching complete ({timings['step_matching']:.2f}s)")

            # Step 10: Structure into enhanced JSON format
            print("📦 Step 10: Structuring into enhanced JSON...")
            step_start = time.time()
            
            # Create enhanced recipe JSON with step-ingredient matching and meta steps
            recipe_dict = create_enhanced_recipe_json(
                title=title,
                parser_method="Instagram",
                source_url=instagram_url,
                step_ingredient_result=step_ingredient_result,
                meta_step_result=meta_step_result,
                image=apify_data.get("image_url", ""),
                meal_occasion=meal_occasion_output,
                servings=0  # Instagram videos rarely specify servings
            )
            
            # Format to JSON string
            import json
            recipe_json = json.dumps(recipe_dict, indent=2, ensure_ascii=False)
            timings['json_structuring'] = time.time() - step_start
            print(f"   ✅ JSON structuring complete ({timings['json_structuring']:.2f}s)")
            
            # Calculate total time
            timings['total_time'] = time.time() - total_start
            
            # Display detailed timing breakdown
            print("\n" + "=" * 50)
            print("⏱️  DETAILED TIMING BREAKDOWN (WITH QUALITY CONTROL)")
            print("=" * 50)
            print(f"🚀 Apify Data Extraction:  {timings['apify_extraction']:.2f}s ({timings['apify_extraction']/timings['total_time']*100:.1f}%)")
            print(f"🔽 Audio Download:         {timings['audio_download']:.2f}s ({timings['audio_download']/timings['total_time']*100:.1f}%)")
            print(f"🎤 Deepgram Transcription: {timings['transcription']:.2f}s ({timings['transcription']/timings['total_time']*100:.1f}%)")
            print(f"📋 Metadata Formatting:    {timings['metadata_formatting']:.2f}s ({timings['metadata_formatting']/timings['total_time']*100:.1f}%)")
            print(f"🔗 Content Combination:    {timings['content_combination']:.2f}s ({timings['content_combination']/timings['total_time']*100:.1f}%)")
            print(f"🤖 LLM Recipe Parsing:     {timings['llm_parsing']:.2f}s ({timings['llm_parsing']/timings['total_time']*100:.1f}%)")
            print(f"📋 Output Parsing:         {timings['parsing']:.2f}s ({timings['parsing']/timings['total_time']*100:.1f}%)")
            print(f"🧹 Quality Control:        {timings['quality_control']:.2f}s ({timings['quality_control']/timings['total_time']*100:.1f}%)")
            print(f"🔧 Rescue + Meta Steps:    {timings['rescue_and_meta']:.2f}s ({timings['rescue_and_meta']/timings['total_time']*100:.1f}%)")
            print(f"🔗 Step-Ingredient Match:  {timings['step_matching']:.2f}s ({timings['step_matching']/timings['total_time']*100:.1f}%)")
            print(f"📦 JSON Structuring:       {timings['json_structuring']:.2f}s ({timings['json_structuring']/timings['total_time']*100:.1f}%)")
            print(f"{'─' * 50}")
            print(f"🎯 TOTAL PROCESSING:       {timings['total_time']:.2f}s (100.0%)")
            
            # Show comparison vs proxy approach
            proxy_time_estimate = 150  # Conservative estimate for proxy approach
            if timings['total_time'] > 0:
                speedup = proxy_time_estimate / timings['total_time']
                print(f"\n🚀 SPEED COMPARISON:")
                print(f"   Proxy approach (est):  ~{proxy_time_estimate}s")
                print(f"   Apify approach:        {timings['total_time']:.2f}s")
                print(f"   Speed improvement:     {speedup:.1f}x faster")
            print("=" * 50)
            
            return recipe_json
            
        finally:
            # Always clean up temp files, even if an error occurs
            self.cleanup_files()