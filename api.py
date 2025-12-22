"""
Recipe Parser API - Instagram & Site Recipe Parsing with Silent Push
FastAPI service for URL parsing with background processing and APNs integration.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os
import sys
import json
import asyncio
import time
import socket
import uuid
import ssl
import httpx
import random
from pathlib import Path
from urllib.parse import urlparse
from aioapns import APNs, NotificationRequest, PushType
import firebase_admin
from firebase_admin import credentials, firestore
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parser directories to path
sys.path.append(str(Path(__file__).parent / "Single_URL_Parsers" / "Instagram_Parser" / "src"))
sys.path.append(str(Path(__file__).parent / "Single_URL_Parsers" / "Site_Parser" / "src"))

# Import parsers
from Instagram_parser import InstagramTranscriber
from recipe_site_parser_actor import parse_single_recipe_url

# Pydantic models
class URLRequest(BaseModel):
    url: str
    userId: str

class SupportMessageRequest(BaseModel):
    message: str
    userEmail: str = None  # Optional - user's email if they want a response
    userId: str = None     # Optional - for tracking

class ParseResponse(BaseModel):
    success: bool
    recipe_json: str = None
    error: str = None
    elapsed_seconds: float = None
    debug_info: dict = None

class SilentPushRequest(BaseModel):
    url: str
    deviceToken: str
    userId: str
    timestamp: float = None
    source: str = "share_extension"

class SilentPushResponse(BaseModel):
    success: bool
    message: str
    jobId: str

class IngredientRequestModel(BaseModel):
    ingredientName: str
    userEmail: str = None
    userId: str = None

class LearnAliasRequest(BaseModel):
    alias_text: str
    ingredient_id: int
    confidence: float

# Create FastAPI app
app = FastAPI(
    title="Recipe Parser API",
    description="Parse Instagram videos and recipe sites into structured JSON. Includes silent push processing for background recipe parsing.",
    version="2.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for your iOS app in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Instagram parser (once at startup)
instagram_parser = InstagramTranscriber()

# APNs configuration (for per-task client creation)
apns_config = {
    "key": os.getenv("APNS_P8_KEY"),
    "key_id": os.getenv("APNS_KEY_ID"),
    "team_id": os.getenv("APNS_TEAM_ID"),
    "topic": os.getenv("APNS_TOPIC"),
    "use_sandbox": bool(os.getenv("APNS_USE_SANDBOX", "false").lower() == "true")
}

# Check if APNs is configured (exclude boolean flag)
apns_configured = all([
    apns_config["key"],
    apns_config["key_id"],
    apns_config["team_id"],
    apns_config["topic"]
])

if apns_configured:
    print("✅ APNs configuration loaded successfully - will create clients per background task")
else:
    print("⚠️  APNs not configured - missing environment variables")
    print("   Silent push notifications will be disabled until APNs credentials are provided")

# Initialize Firebase Admin
firebase_db = None
try:
    # Load service account from environment variable
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        # Parse JSON string into dict
        service_account_info = json.loads(service_account_json)
        
        # Initialize Firebase Admin SDK
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'projectId': 'loomi-cec3e'
        })
        
        # Get Firestore client
        firebase_db = firestore.client()
        print("✅ Firebase Admin initialized successfully for project: loomi-cec3e")
    else:
        print("⚠️  Firebase not configured - missing FIREBASE_SERVICE_ACCOUNT_JSON")
        print("   Recipe storage will be disabled until Firebase credentials are provided")
        
except Exception as e:
    print(f"❌ Failed to initialize Firebase: {str(e)}")
    print("   Recipe storage will be disabled")
    firebase_db = None

# DNS validation function
async def is_valid_domain(url: str) -> bool:
    """Quick DNS check to validate domain exists without HTTP overhead"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
            
        # Quick DNS lookup
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, socket.error, ValueError):
        return False

async def send_silent_push(device_token: str, payload: dict) -> bool:
    """Send silent push notification via APNs using per-task client creation (event loop safe)"""
    print(f"🔔 [DEBUG] send_silent_push called")
    print(f"   [DEBUG] APNs configured: {apns_configured}")
    print(f"   [DEBUG] Device token: {device_token[:8]}...")
    print(f"   [DEBUG] Payload size: {len(json.dumps(payload))} chars")
    print(f"   [DEBUG] Running in event loop: {id(asyncio.get_event_loop())}")
    
    if not apns_configured:
        print("❌ [DEBUG] APNs not configured - silent push skipped")
        return False
    
    apns_client = None
    try:
        print(f"🔧 [DEBUG] Creating fresh APNs client...")
        print(f"   [DEBUG] Use sandbox: {apns_config['use_sandbox']}")
        print(f"   [DEBUG] Topic: {apns_config['topic']}")
        print(f"   [DEBUG] Key ID: {apns_config['key_id']}")
        
        # Create fresh APNs client inside background task (binds to current event loop)
        apns_client = APNs(
            key=apns_config["key"],
            key_id=apns_config["key_id"],
            team_id=apns_config["team_id"],
            topic=apns_config["topic"],
            use_sandbox=apns_config["use_sandbox"]
        )
        print(f"   [DEBUG] APNs client created successfully")
        
        # Create notification request with proper APNs format
        print(f"📝 [DEBUG] Creating notification request...")
        request = NotificationRequest(
            device_token=device_token,
            message=payload,
            push_type=PushType.BACKGROUND
        )
        print(f"   [DEBUG] Notification request created")
        
        # Send notification
        print(f"📤 [DEBUG] Sending notification to APNs servers...")
        response = await apns_client.send_notification(request)
        print(f"✅ [DEBUG] APNs response received: {response}")
        print(f"✅ Silent push sent successfully to {device_token[:8]}...")
        return True
        
    except Exception as e:
        print(f"❌ [DEBUG] Silent push exception occurred")
        print(f"   [DEBUG] Exception type: {type(e).__name__}")
        print(f"   [DEBUG] Exception message: {str(e)}")
        return False
        
    finally:
        # APNs client automatically cleans up - no manual close() method needed
        if apns_client:
            print(f"🧹 [DEBUG] APNs client cleanup complete (automatic)")

def determine_parser_type(url: str) -> str:
    """Determine if URL should use Instagram or Site parser"""
    if "instagram.com" in url.lower():
        return "instagram"
    else:
        return "site"

def generate_recipe_id() -> str:
    """Generate unique recipe ID with timestamp and random component"""
    timestamp = int(time.time())
    random_part = random.randint(1000, 9999)
    return f"recipe_{timestamp}_{random_part}"

async def save_recipe_to_firebase(user_id: str, recipe_id: str, recipe_data: dict) -> bool:
    """Save complete recipe to Firebase user collection"""
    try:
        print(f"\n{'='*60}")
        print(f"💾 [FIREBASE] SAVE ATTEMPT STARTED")
        print(f"{'='*60}")

        # Log user_id immediately (critical for debugging)
        print(f"👤 [FIREBASE] User ID: '{user_id}'")
        print(f"   [FIREBASE] User ID type: {type(user_id)}")
        print(f"   [FIREBASE] User ID length: {len(user_id) if user_id else 0}")
        print(f"   [FIREBASE] User ID is empty: {not user_id or user_id.strip() == ''}")

        # Check Firebase initialization
        if not firebase_db:
            print("❌ [FIREBASE] Firebase client not initialized!")
            print("   [FIREBASE] Check FIREBASE_SERVICE_ACCOUNT_JSON env var")
            print("   [FIREBASE] Recipe save ABORTED")
            return False

        print(f"✅ [FIREBASE] Firebase client initialized")

        # Log recipe details
        print(f"🆔 [FIREBASE] Recipe ID: '{recipe_id}'")
        print(f"📝 [FIREBASE] Recipe title: '{recipe_data.get('title', 'Unknown')}'")
        print(f"🥕 [FIREBASE] Ingredients count: {len(recipe_data.get('ingredients', []))}")
        print(f"📋 [FIREBASE] Directions count: {len(recipe_data.get('directions', []))}")
        print(f"📊 [FIREBASE] Recipe data keys: {list(recipe_data.keys())}")

        # Construct Firebase path
        firebase_path = f"users/{user_id}/recipes/{recipe_id}"
        print(f"🔗 [FIREBASE] Full document path: {firebase_path}")

        # Validate user_id is not empty
        if not user_id or user_id.strip() == '':
            print(f"❌ [FIREBASE] User ID is EMPTY or whitespace!")
            print(f"   [FIREBASE] Cannot save recipe without valid user_id")
            return False

        # Create document reference
        print(f"📍 [FIREBASE] Creating document reference...")
        doc_ref = firebase_db.collection('users').document(user_id).collection('recipes').document(recipe_id)
        print(f"   [FIREBASE] Document reference created: {doc_ref.path}")

        # Perform the write
        print(f"💾 [FIREBASE] Writing recipe data to Firestore...")
        doc_ref.set(recipe_data)
        print(f"✅ [FIREBASE] Write operation completed")

        # Verify the write was successful by reading it back
        print(f"🔍 [FIREBASE] Verifying save by reading document back...")
        saved_doc = doc_ref.get()

        if saved_doc.exists:
            saved_data = saved_doc.to_dict()
            print(f"✅ [FIREBASE] VERIFICATION SUCCESSFUL - Document exists in Firestore")
            print(f"   [FIREBASE] Verified title: '{saved_data.get('title', 'N/A')}'")
            print(f"   [FIREBASE] Verified ingredients: {len(saved_data.get('ingredients', []))}")
            print(f"   [FIREBASE] Verified directions: {len(saved_data.get('directions', []))}")
        else:
            print(f"⚠️  [FIREBASE] WARNING - Document write succeeded but verification read found no document!")
            print(f"   [FIREBASE] Path checked: {firebase_path}")
            print(f"   [FIREBASE] This may indicate a permission or timing issue")
            return False

        print(f"{'='*60}")
        print(f"✅ [FIREBASE] SAVE COMPLETE - Recipe successfully saved and verified")
        print(f"{'='*60}\n")
        return True

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ [FIREBASE] SAVE FAILED - Exception occurred")
        print(f"{'='*60}")
        print(f"   [FIREBASE] Exception type: {type(e).__name__}")
        print(f"   [FIREBASE] Exception message: {str(e)}")
        print(f"   [FIREBASE] User ID at time of error: '{user_id}'")
        print(f"   [FIREBASE] Recipe ID at time of error: '{recipe_id}'")

        # Print full traceback for debugging
        import traceback
        print(f"   [FIREBASE] Full traceback:")
        print(traceback.format_exc())
        print(f"{'='*60}\n")
        return False

async def get_recipe_from_firebase(user_id: str, recipe_id: str) -> dict:
    """Retrieve recipe from Firebase (for future download endpoint)"""
    try:
        if not firebase_db:
            raise Exception("Firebase not available")
        
        doc_ref = firebase_db.collection('users').document(user_id).collection('recipes').document(recipe_id)
        doc = doc_ref.get()
        
        if doc.exists:
            return doc.to_dict()
        else:
            raise Exception(f"Recipe {recipe_id} not found for user {user_id}")
            
    except Exception as e:
        print(f"❌ Firebase retrieve failed: {str(e)}")
        raise

async def process_recipe_background(url: str, device_token: str, user_id: str, job_id: str):
    """Background task to parse recipe and send silent push with Firebase storage"""
    print(f"\n{'='*60}")
    print(f"🚀 [BACKGROUND] TASK STARTED for job {job_id}")
    print(f"{'='*60}")
    print(f"⏱️  [BACKGROUND] Task running in event loop: {id(asyncio.get_event_loop())}")

    # Log user_id immediately at the start of background task
    print(f"👤 [BACKGROUND] User ID received in background task: '{user_id}'")
    print(f"   [BACKGROUND] User ID type: {type(user_id)}")
    print(f"   [BACKGROUND] User ID length: {len(user_id) if user_id else 0}")
    print(f"   [BACKGROUND] User ID valid: {bool(user_id and user_id.strip())}")

    print(f"📋 [BACKGROUND] URL: {url}")
    print(f"📱 [BACKGROUND] Device token: {device_token[:8]}...")

    try:
        start_time = time.time()

        # Determine parser type
        parser_type = determine_parser_type(url)
        print(f"\n📱 [BACKGROUND] Parser type determined: {parser_type}")

        # Parse recipe using existing logic - handle different return formats
        print(f"🔄 [BACKGROUND] Starting recipe parsing with {parser_type} parser...")

        if parser_type == "instagram":
            print(f"   [BACKGROUND] Instagram parser: Running in thread pool executor...")
            # Instagram parser is sync, so run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            print(f"   [BACKGROUND] Got event loop: {id(loop)}")

            recipe_json = await loop.run_in_executor(
                None,
                instagram_parser.parse_instagram_recipe_to_json,
                url
            )
            print(f"   [BACKGROUND] Instagram parser completed, JSON length: {len(recipe_json)} chars")

            # Instagram parser returns JSON string directly
            recipe_data = json.loads(recipe_json)
            print(f"   [BACKGROUND] Instagram JSON parsed successfully, recipe title: {recipe_data.get('title', 'Unknown')}")
            parser_method = "Instagram"

        else:
            print(f"   [BACKGROUND] Site parser: Calling async parse_single_recipe_url...")
            # Site parser is already async - returns dict with success status
            result = await parse_single_recipe_url(url)
            print(f"   [BACKGROUND] Site parser completed, success: {result.get('success', False)}")

            if result["success"]:
                # Extract JSON string from site parser response
                recipe_json = result["processed_json"]
                print(f"   [BACKGROUND] Site parser JSON extracted, length: {len(recipe_json)} chars")

                recipe_data = json.loads(recipe_json)
                print(f"   [BACKGROUND] Site parser JSON parsed successfully, recipe title: {recipe_data.get('title', 'Unknown')}")
                parser_method = "RecipeSite"
            else:
                error_msg = result.get('error', 'Unknown parsing error')
                print(f"   [BACKGROUND] Site parser failed with error: {error_msg}")
                raise Exception(f"Site parser failed: {error_msg}")

        print(f"\n✅ [BACKGROUND] Recipe parsing completed successfully")
        print(f"   [BACKGROUND] Recipe title: '{recipe_data.get('title', 'Unknown')}'")
        print(f"   [BACKGROUND] Recipe has {len(recipe_data.get('ingredients', []))} ingredients")
        print(f"   [BACKGROUND] Recipe has {len(recipe_data.get('directions', []))} steps")

        # Generate unique recipe ID
        recipe_id = generate_recipe_id()
        print(f"\n🆔 [BACKGROUND] Generated recipe ID: {recipe_id}")

        # Save complete recipe to Firebase
        print(f"\n💾 [BACKGROUND] About to call save_recipe_to_firebase()...")
        print(f"   [BACKGROUND] Passing user_id: '{user_id}'")
        print(f"   [BACKGROUND] Passing recipe_id: '{recipe_id}'")
        print(f"   [BACKGROUND] Recipe data has {len(recipe_data)} keys")

        firebase_success = await save_recipe_to_firebase(user_id, recipe_id, recipe_data)

        print(f"\n📊 [BACKGROUND] Firebase save result: {firebase_success}")

        if firebase_success:
            # Create minimal silent push payload (no full recipe data)
            print(f"\n🔔 [BACKGROUND] Firebase save succeeded, creating push notification...")
            push_payload = {
                "aps": {
                    "content-available": 1
                },
                "recipeAdded": {
                    "recipeId": recipe_id,
                    "title": recipe_data.get("title", "Unknown Recipe"),
                    "action": "refresh_collection"
                }
            }
            print(f"   [BACKGROUND] Push payload created, size: {len(json.dumps(push_payload))} chars")

            # Send minimal silent push
            print(f"📤 [BACKGROUND] Sending silent push notification...")
            push_success = await send_silent_push(device_token, push_payload)
            print(f"   [BACKGROUND] Silent push result: {push_success}")
        else:
            print(f"\n❌ [BACKGROUND] Firebase save FAILED - skipping push notification")
            print(f"   [BACKGROUND] User will NOT be notified of this recipe")
            push_success = False

        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"✅ [BACKGROUND] Processing complete for job {job_id} in {elapsed:.2f}s")

        if not push_success:
            print(f"⚠️  [BACKGROUND] Recipe parsed successfully but push notification failed")
        else:
            print(f"🎉 [BACKGROUND] Complete success! Recipe parsed AND push sent")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ [BACKGROUND] PROCESSING FAILED for job {job_id}")
        print(f"{'='*60}")
        print(f"   [BACKGROUND] Exception type: {type(e).__name__}")
        print(f"   [BACKGROUND] Exception message: {str(e)}")
        print(f"   [BACKGROUND] User ID at time of error: '{user_id}'")

        # Print full traceback
        import traceback
        print(f"   [BACKGROUND] Full traceback:")
        print(traceback.format_exc())

        # Send error push with proper async context
        print(f"\n🔔 [BACKGROUND] Attempting to send error push notification...")
        error_payload = {
            "aps": {
                "content-available": 1
            },
            "error": {
                "message": "Failed to parse recipe",
                "code": "PARSE_FAILED",
                "details": str(e)
            }
        }

        try:
            error_push_success = await send_silent_push(device_token, error_payload)
            print(f"   [BACKGROUND] Error push result: {error_push_success}")
        except Exception as push_error:
            print(f"❌ [BACKGROUND] Error push ALSO failed: {str(push_error)}")

        print(f"{'='*60}\n")

    print(f"🏁 [BACKGROUND] Task FINISHED for job {job_id}\n")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Recipe Parser API",
        "status": "healthy", 
        "version": "2.0.0",
        "endpoints": [
            "POST /parse-instagram-recipe",
            "POST /parse-site-recipe"
        ]
    }

@app.post("/parse-instagram-recipe", response_model=ParseResponse)
async def parse_instagram_recipe(request: URLRequest):
    """
    Parse Instagram video/reel into structured recipe JSON.
    
    Input: {"url": "https://www.instagram.com/p/ABC123/"}
    Output: {"success": true, "recipe_json": "...", "elapsed_seconds": 15.2}
    """
    import traceback
    import time
    
    start_time = time.time()
    
    try:
        print(f"🎬 Instagram Parse Request: {request.url}")
        
        # Validate Instagram URL
        if "instagram.com" not in request.url.lower():
            raise HTTPException(status_code=400, detail="URL must be an Instagram post or reel")
        
        # DNS validation to check if domain exists
        if not await is_valid_domain(request.url):
            raise HTTPException(status_code=400, detail="Invalid or unreachable URL domain")
        
        print("✅ URL validation passed")
        
        # Check environment variables
        required_env_vars = ["APIFY_API_KEY", "GOOGLE_GEMINI_KEY", "DEEPGRAM_WISPER_API"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"Missing environment variables: {', '.join(missing_vars)}"
            print(f"❌ Environment error: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        print("✅ Environment variables check passed")
        
        # Parse Instagram recipe (not async - runs in thread pool automatically)
        print("🚀 Starting Instagram parser...")
        recipe_json = instagram_parser.parse_instagram_recipe_to_json(request.url)
        
        elapsed_seconds = time.time() - start_time
        print(f"✅ Instagram parsing completed successfully in {elapsed_seconds:.2f}s")
        
        return ParseResponse(
            success=True,
            recipe_json=recipe_json,
            elapsed_seconds=elapsed_seconds
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        elapsed_seconds = time.time() - start_time
        error_message = str(e)
        
        # Log full traceback for debugging
        print(f"❌ Instagram Parse Error after {elapsed_seconds:.2f}s: {error_message}")
        print("📍 Full traceback:")
        print(traceback.format_exc())
        
        # Create detailed error response
        detailed_error = {
            "original_error": error_message,
            "error_type": type(e).__name__,
            "elapsed_seconds": elapsed_seconds,
            "url": request.url
        }
        
        # Handle specific error cases with better status codes
        if "private video" in error_message.lower() or "private account" in error_message.lower():
            status_code = 403
            user_message = "This Instagram video is private or from a private account"
        elif "deleted" in error_message.lower() or "not available" in error_message.lower() or "not found" in error_message.lower():
            status_code = 404
            user_message = "Instagram video not found or has been deleted"
        elif "rate limit" in error_message.lower() or "too many requests" in error_message.lower():
            status_code = 429
            user_message = "Rate limit exceeded, please try again later"
        elif "timeout" in error_message.lower():
            status_code = 504
            user_message = "Request timed out, please try again"
        elif "api key" in error_message.lower() or "authentication" in error_message.lower():
            status_code = 500
            user_message = "Server configuration error"
        else:
            status_code = 500
            user_message = f"Server error: {error_message}"
            
        raise HTTPException(
            status_code=status_code, 
            detail={
                "message": user_message,
                "debug_info": detailed_error
            }
        )

@app.post("/parse-site-recipe", response_model=ParseResponse)
async def parse_site_recipe(request: URLRequest):
    print(f"🔍 [PARSE-SITE] Received request: url={request.url}, userId={request.userId}")
    print(f"🔍 [PARSE-SITE] Request type: {type(request)}")
    """
    Parse recipe website into structured recipe JSON.
    
    Input: {"url": "https://www.allrecipes.com/recipe/..."}
    Output: {"success": true, "recipe_json": "...", "elapsed_seconds": 12.4}
    """
    try:
        print(f"🌐 Site Parse Request: {request.url}")
        
        # Validate URL format
        if not request.url.startswith(('http://', 'https://')):
            request.url = f"https://{request.url}"
        
        # DNS validation to check if domain exists
        if not await is_valid_domain(request.url):
            raise HTTPException(status_code=400, detail="Invalid or unreachable URL domain")
        
        print("✅ URL domain validation passed")
        
        # Parse recipe site
        result = await parse_single_recipe_url(request.url)
        
        if result["success"]:
            return ParseResponse(
                success=True,
                recipe_json=result["processed_json"],
                elapsed_seconds=result["total_elapsed_seconds"]
            )
        else:
            raise HTTPException(status_code=422, detail=result.get("error", "Failed to parse recipe"))
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        print(f"❌ Site Parse Error: {error_message}")
        
        # Handle specific error cases
        if "403" in error_message or "forbidden" in error_message.lower():
            status_code = 403
        elif "timeout" in error_message.lower():
            status_code = 504
        else:
            status_code = 500
            
        raise HTTPException(status_code=status_code, detail=error_message)

@app.post("/api/support/send-message")
async def send_support_message(request: SupportMessageRequest):
      """
      Send support message to Loomi care team via email.
      
      Input: {"message": "User's support message", "userEmail": "user@example.com"}
      Output: {"success": true, "message": "Support message sent successfully"}
      """
      try:
          print(f"📧 Support Message Request")
          print(f"   Message length: {len(request.message)} chars")
          print(f"   User email: {request.userEmail or 'Not provided'}")

          # Get SendGrid API key from environment
          sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
          if not sendgrid_api_key:
              raise HTTPException(status_code=500, detail="Email service not configured")

          # Create email content
          email_subject = "Customer Message from Loomi App"
          # Build email body with user info
          email_body = f"""
  New support message from Loomi app:

  MESSAGE:
  {request.message}

  ---
  User Email: {request.userEmail or 'Not provided'}
  User ID: {request.userId or 'Not provided'}
  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
          """

          # Create SendGrid email
          message = Mail(
              from_email='careteam@liveloomi.com',  # Must be verified in SendGrid
              to_emails='careteam@liveloomi.com',
              subject=email_subject,
              plain_text_content=email_body
          )

          # Send email
          sg = SendGridAPIClient(sendgrid_api_key)
          response = sg.send(message)

          print(f"✅ Support email sent successfully (Status: {response.status_code})")

          return {
              "success": True,
              "message": "Support message sent successfully"
          }

      except Exception as e:
          error_message = str(e)
          print(f"❌ Support Email Error: {error_message}")
          raise HTTPException(status_code=500, detail=f"Failed to send support message: {error_message}")


@app.post("/api/ingredients/missing-ingredient")
async def send_support_message(request: SupportMessageRequest):
      """
      Send email to loomi care team regarding a missing ingredient
     
      """
      try:
          print(f"Missing Ingredient Catch")
          print(f"   Message length: {len(request.message)} chars")
          print(f"   User email: {request.userEmail or 'Not provided'}")

          # Get SendGrid API key from environment
          sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
          if not sendgrid_api_key:
              raise HTTPException(status_code=500, detail="Email service not configured")

          # Create email content
          email_subject = "Missed Ingredient Match."
          # Build email body with user info
          email_body = f"""
  Ingredient(s) missed during ingredient enrichmentment. 
  {request.message}
  /Users/agustin/Library/Mobile Documents/com~apple~CloudDocs/Loomi
  ---
  User Email: {request.userEmail or 'Not provided'}
  User ID: {request.userId or 'Not provided'}
  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
          """

          # Create SendGrid email
          message = Mail(
              from_email='careteam@liveloomi.com',  # Must be verified in SendGrid
              to_emails='careteam@liveloomi.com',
              subject=email_subject,
              plain_text_content=email_body
          )

          # Send email
          sg = SendGridAPIClient(sendgrid_api_key)
          response = sg.send(message)

          print(f"✅ missing ingredient sent successfully (Status: {response.status_code})")

          return {
              "success": True,
              "message": "Missing ingredient sent successfully"
          }

      except Exception as e:
          error_message = str(e)
          print(f"❌ Support Email Error: {error_message}")
          raise HTTPException(status_code=500, detail=f"Failed to send support message: {error_message}")


@app.post("/api/ingredients/submit-request")
async def submit_ingredient_request(request: IngredientRequestModel):
      """
      Submit ingredient photo request via email.
      
      Input: {"ingredientName": "Turmeric", "userEmail": "user@example.com", "userId": "abc123"}
      Output: {"success": true, "message": "Ingredient request submitted successfully"}
      """
      try:
          print(f"🥕 Ingredient Request")
          print(f"   Ingredient: {request.ingredientName}")
          print(f"   User email: {request.userEmail or 'Not provided'}")

          # Get SendGrid API key
          sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
          if not sendgrid_api_key:
              raise HTTPException(status_code=500, detail="Email service not configured")

          # Create email subject
          email_subject = f"Ingredient Photo Request: {request.ingredientName}"

          # Build email body
          email_body = f"""
  New ingredient photo request from Loomi app:

  INGREDIENT REQUESTED:
  {request.ingredientName}

  ---
  User Email: {request.userEmail or 'Not provided'}
  User ID: {request.userId or 'Not provided'}
  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
          """

          # Create SendGrid email
          message = Mail(
              from_email='careteam@liveloomi.com',
              to_emails='careteam@liveloomi.com',
              subject=email_subject,
              plain_text_content=email_body
          )

          # Send email
          sg = SendGridAPIClient(sendgrid_api_key)
          response = sg.send(message)

          print(f"✅ Ingredient request email sent successfully (Status: {response.status_code})")

          return {
              "success": True,
              "message": "Ingredient request submitted successfully"
          }

      except Exception as e:
          error_message = str(e)
          print(f"❌ Ingredient Request Error: {error_message}")
          raise HTTPException(status_code=500, detail=f"Failed to submit ingredient request: {error_message}")



@app.post("/queue-recipe-silent-push", response_model=SilentPushResponse)
async def queue_recipe_silent_push(request: SilentPushRequest, background_tasks: BackgroundTasks):
    """
    Queue recipe parsing and send result via silent push notification.
    Returns immediately while processing happens in background.
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 [SILENT-PUSH] NEW REQUEST RECEIVED")
        print(f"{'='*60}")

        # Log user_id FIRST (critical for debugging)
        print(f"👤 [SILENT-PUSH] User ID from request: '{request.userId}'")
        print(f"   [SILENT-PUSH] User ID type: {type(request.userId)}")
        print(f"   [SILENT-PUSH] User ID length: {len(request.userId) if request.userId else 0}")

        # Validate URL format
        if not request.url.strip():
            raise HTTPException(status_code=400, detail="URL is required")

        # Add https if missing
        if not request.url.startswith(('http://', 'https://')):
            request.url = f"https://{request.url}"

        # Validate device token
        if not request.deviceToken.strip():
            raise HTTPException(status_code=400, detail="Device token is required")

        # Validate user ID
        if not request.userId or request.userId.strip() == '':
            print(f"❌ [SILENT-PUSH] User ID is EMPTY or missing!")
            raise HTTPException(status_code=400, detail="User ID is required")

        # DNS validation
        if not await is_valid_domain(request.url):
            raise HTTPException(status_code=400, detail="Invalid or unreachable URL domain")

        # Generate job ID
        job_id = str(uuid.uuid4())

        print(f"📋 [SILENT-PUSH] Queuing recipe processing job {job_id}")
        print(f"   [SILENT-PUSH] URL: {request.url}")
        print(f"   [SILENT-PUSH] Device: {request.deviceToken[:8]}...")
        print(f"   [SILENT-PUSH] User ID being passed: '{request.userId}'")
        print(f"   [SILENT-PUSH] Source: {request.source}")
        print(f"   [SILENT-PUSH] Main event loop: {id(asyncio.get_event_loop())}")

        # Add background task with user ID
        print(f"🔄 [SILENT-PUSH] Adding background task to FastAPI...")
        background_tasks.add_task(
            process_recipe_background,
            request.url,
            request.deviceToken,
            request.userId,
            job_id
        )
        print(f"✅ [SILENT-PUSH] Background task added successfully")
        print(f"{'='*60}\n")

        return SilentPushResponse(
            success=True,
            message="Recipe queued for background processing",
            jobId=job_id
        )

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        print(f"❌ [SILENT-PUSH] Queue Error: {error_message}")
        raise HTTPException(status_code=500, detail=error_message)

# ============================================================================
# LEARNED ALIASES ENDPOINTS
# ============================================================================

def get_db():
    """Get PostgreSQL database connection for learned aliases"""
    print("🔌 [DB] Attempting database connection...")
    print(f"   [DB] Host: {os.getenv('PGHOST')}")
    print(f"   [DB] Database: {os.getenv('PGDATABASE')}")
    print(f"   [DB] User: {os.getenv('PGUSER')}")
    print(f"   [DB] Port: {os.getenv('PGPORT', '5432')}")

    try:
        conn = psycopg2.connect(
            host=os.getenv("PGHOST"),
            database=os.getenv("PGDATABASE"),
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD"),
            port=os.getenv("PGPORT", "5432"),
            cursor_factory=RealDictCursor
        )
        print("✅ [DB] Database connection successful")
        return conn
    except Exception as e:
        print(f"❌ [DB] Database connection failed: {type(e).__name__}: {str(e)}")
        raise

@app.post("/api/learned-aliases/learn")
async def learn_alias(request: LearnAliasRequest):
    """Learn a new ingredient alias from LLM matching."""
    print(f"📝 [LEARN] Received request to learn alias")
    print(f"   [LEARN] Alias text: '{request.alias_text}'")
    print(f"   [LEARN] Ingredient ID: {request.ingredient_id}")
    print(f"   [LEARN] Confidence: {request.confidence}")

    try:
        print(f"   [LEARN] Getting database connection...")
        conn = get_db()
        cursor = conn.cursor()
        print(f"   [LEARN] Database cursor created")

        print(f"   [LEARN] Checking if alias already exists...")
        cursor.execute(
            "SELECT id, usage_count FROM learned_ingredient_aliases WHERE alias_text = %s",
            (request.alias_text.lower(),)
        )

        existing = cursor.fetchone()

        if existing:
            print(f"   [LEARN] Alias exists (ID: {existing['id']}), incrementing usage count...")
            # Already exists - increment usage
            cursor.execute(
                "UPDATE learned_ingredient_aliases SET usage_count = usage_count + 1, last_used = NOW() WHERE id = %s RETURNING usage_count",
                (existing['id'],)
            )
            result = cursor.fetchone()
            conn.commit()
            print(f"✅ [LEARN] Alias updated successfully, new usage count: {result['usage_count']}")
            return {
                "status": "updated",
                "usage_count": result['usage_count'],
                "message": f"Alias '{request.alias_text}' usage count updated"
            }
        else:
            print(f"   [LEARN] Alias is new, inserting into database...")
            # New alias - insert
            cursor.execute(
                "INSERT INTO learned_ingredient_aliases (alias_text, ingredient_id, confidence) VALUES (%s, %s, %s) RETURNING id",
                (request.alias_text.lower(), request.ingredient_id, request.confidence)
            )
            result = cursor.fetchone()
            conn.commit()
            print(f"✅ [LEARN] New alias created successfully with ID: {result['id']}")
            return {
                "status": "created",
                "alias_id": result['id'],
                "message": "New alias learned successfully"
            }

    except psycopg2.Error as db_error:
        print(f"❌ [LEARN] Database error: {type(db_error).__name__}: {str(db_error)}")
        if 'conn' in locals():
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {type(db_error).__name__}: {str(db_error)}")
    except Exception as e:
        print(f"❌ [LEARN] Unexpected error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"   [LEARN] Traceback: {traceback.format_exc()}")
        if 'conn' in locals():
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {type(e).__name__}: {str(e)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        print(f"   [LEARN] Database connection closed")


@app.get("/api/learned-aliases/lookup/{alias_text}")
async def lookup_alias(alias_text: str):
    """Check if alias exists. Returns matched ingredient if found."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Join with ingredients table to get full data
        cursor.execute("""
            SELECT
                a.ingredient_id,
                i.name as ingredient_name,
                i.category_name,
                i.primary_image_url as image_url,
                a.confidence,
                a.usage_count
            FROM learned_ingredient_aliases a
            JOIN ingredients i ON a.ingredient_id = i.id
            WHERE a.alias_text = %s AND a.status = 'active'
        """, (alias_text.lower(),))

        result = cursor.fetchone()

        if result:
            # Update usage
            cursor.execute(
                "UPDATE learned_ingredient_aliases SET usage_count = usage_count + 1, last_used = NOW() WHERE alias_text = %s",
                (alias_text.lower(),)
            )
            conn.commit()
            return {"found": True, **result}
        else:
            return {"found": False}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/learned-aliases/sync")
async def sync_aliases(since: Optional[str] = None):
    """Get all active aliases for app cache sync."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT a.*, i.name as ingredient_name, i.category_name, i.primary_image_url as image_url
            FROM learned_ingredient_aliases a
            JOIN ingredients i ON a.ingredient_id = i.id
            WHERE a.status = 'active'
        """)

        aliases = cursor.fetchall()
        return {
            "aliases": aliases,
            "total_count": len(aliases),
            "last_sync": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/learned-aliases/analytics")
async def get_alias_analytics():
    """Analytics for admin - shows ingredient gaps."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Top ingredients by alias count (these have the most variations/gaps)
        cursor.execute("""
            SELECT
                i.name as ingredient_name,
                i.category_name,
                COUNT(a.id) as alias_count,
                AVG(a.confidence) as avg_confidence,
                SUM(a.usage_count) as total_usage
            FROM ingredients i
            JOIN learned_ingredient_aliases a ON i.id = a.ingredient_id
            WHERE a.status = 'active'
            GROUP BY i.id, i.name, i.category_name
            ORDER BY alias_count DESC
            LIMIT 20
        """)
        top_ingredients = cursor.fetchall()

        # Recent learnings
        cursor.execute("""
            SELECT a.*, i.name as ingredient_name
            FROM learned_ingredient_aliases a
            JOIN ingredients i ON a.ingredient_id = i.id
            ORDER BY a.learned_date DESC
            LIMIT 50
        """)
        recent = cursor.fetchall()

        return {
            "top_ingredients": top_ingredients,
            "recent_learnings": recent
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/learned-aliases/health")
async def learned_aliases_health():
    """Health check endpoint specifically for learned aliases feature."""
    print("🏥 [HEALTH] Learned aliases health check requested")

    health_status = {
        "service": "learned_aliases",
        "status": "healthy",
        "endpoints_registered": True,
        "database_configured": False,
        "database_connection": "not_tested"
    }

    # Check if DB env vars are set
    required_env_vars = ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        print(f"⚠️  [HEALTH] Missing environment variables: {missing_vars}")
        health_status["database_configured"] = False
        health_status["missing_env_vars"] = missing_vars
    else:
        print(f"✅ [HEALTH] All environment variables configured")
        health_status["database_configured"] = True

        # Try to connect to database
        try:
            print(f"   [HEALTH] Testing database connection...")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            print(f"✅ [HEALTH] Database connection successful")
            health_status["database_connection"] = "successful"
        except Exception as e:
            print(f"❌ [HEALTH] Database connection failed: {type(e).__name__}: {str(e)}")
            health_status["database_connection"] = "failed"
            health_status["database_error"] = f"{type(e).__name__}: {str(e)}"

    return health_status

# Startup event to confirm endpoints are registered
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*80)
    print("🚀 LEARNED ALIASES ENDPOINTS REGISTERED")
    print("="*80)
    print("📍 POST   /api/learned-aliases/learn")
    print("📍 GET    /api/learned-aliases/lookup/{alias_text}")
    print("📍 GET    /api/learned-aliases/sync")
    print("📍 GET    /api/learned-aliases/analytics")
    print("📍 GET    /api/learned-aliases/health")
    print("="*80 + "\n")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)