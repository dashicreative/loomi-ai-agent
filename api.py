"""
Recipe Parser API - Instagram & Site Recipe Parsing with Silent Push
FastAPI service for URL parsing with background processing and APNs integration.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import sys
import json
import asyncio
import time
import socket
import uuid
import ssl
import httpx
from pathlib import Path
from urllib.parse import urlparse
from aioapns import APNs, NotificationRequest

# Add parser directories to path
sys.path.append(str(Path(__file__).parent / "Single_URL_Parsers" / "Instagram_Parser" / "src"))
sys.path.append(str(Path(__file__).parent / "Single_URL_Parsers" / "Site_Parser" / "src"))

# Import parsers
from Instagram_parser import InstagramTranscriber
from recipe_site_parser_actor import parse_single_recipe_url

# Pydantic models
class URLRequest(BaseModel):
    url: str

class ParseResponse(BaseModel):
    success: bool
    recipe_json: str = None
    error: str = None
    elapsed_seconds: float = None
    debug_info: dict = None

class SilentPushRequest(BaseModel):
    url: str
    deviceToken: str
    timestamp: float = None
    source: str = "share_extension"

class SilentPushResponse(BaseModel):
    success: bool
    message: str
    jobId: str

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

# APNs configuration (initialize per request to avoid event loop conflicts)
apns_config = {
    "key": os.getenv("APNS_P8_KEY"),
    "key_id": os.getenv("APNS_KEY_ID"), 
    "team_id": os.getenv("APNS_TEAM_ID"),
    "topic": os.getenv("APNS_TOPIC"),
    "use_sandbox": bool(os.getenv("APNS_USE_SANDBOX", "false").lower() == "true")
}

# Check if APNs is configured (exclude boolean use_sandbox flag)
apns_configured = all([
    apns_config["key"],
    apns_config["key_id"], 
    apns_config["team_id"],
    apns_config["topic"]
])
if apns_configured:
    print("✅ APNs configuration loaded successfully")
else:
    print("⚠️  APNs not configured - missing environment variables")
    print("   Silent push notifications will be disabled until APNs credentials are provided")

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
    """Send silent push notification via APNs using fresh client per request"""
    try:
        if not apns_configured:
            print("❌ APNs not configured - silent push skipped")
            return False
        
        # Create fresh APNs client for this request (no async context manager)
        apns_client = APNs(
            key=apns_config["key"],
            key_id=apns_config["key_id"],
            team_id=apns_config["team_id"],
            topic=apns_config["topic"],
            use_sandbox=apns_config["use_sandbox"]
        )
        
        # Create notification request
        request = NotificationRequest(
            device_token=device_token,
            message=payload
        )
        
        # Send notification
        await apns_client.send_notification(request)
        print(f"✅ Silent push sent successfully to {device_token[:8]}...")
        return True
        
    except Exception as e:
        print(f"❌ Silent push failed: {str(e)}")
        return False

def determine_parser_type(url: str) -> str:
    """Determine if URL should use Instagram or Site parser"""
    if "instagram.com" in url.lower():
        return "instagram"
    else:
        return "site"

async def process_recipe_background(url: str, device_token: str, job_id: str):
    """Background task to parse recipe and send silent push with proper async context"""
    try:
        print(f"🚀 Starting background processing for job {job_id}")
        start_time = time.time()
        
        # Determine parser type
        parser_type = determine_parser_type(url)
        print(f"📱 Using {parser_type} parser for {url}")
        
        # Parse recipe using existing logic - handle different return formats
        if parser_type == "instagram":
            # Instagram parser is sync, so run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            recipe_json = await loop.run_in_executor(
                None, 
                instagram_parser.parse_instagram_recipe_to_json, 
                url
            )
            # Instagram parser returns JSON string directly
            recipe_data = json.loads(recipe_json)
            parser_method = "Instagram"
        else:
            # Site parser is already async - returns dict with success status
            result = await parse_single_recipe_url(url)
            
            if result["success"]:
                # Extract JSON string from site parser response
                recipe_json = result["processed_json"]
                recipe_data = json.loads(recipe_json)
                parser_method = "RecipeSite"
            else:
                raise Exception(f"Site parser failed: {result.get('error', 'Unknown parsing error')}")
        
        
        # Create silent push payload
        push_payload = {
            "aps": {
                "content-available": 1
            },
            "recipe": recipe_data
        }
        
        # Send silent push with proper async context
        push_success = await send_silent_push(device_token, push_payload)
        
        elapsed = time.time() - start_time
        print(f"✅ Background processing complete for job {job_id} in {elapsed:.2f}s")
        
        if not push_success:
            print(f"⚠️  Recipe parsed but push notification failed for job {job_id}")
            
    except Exception as e:
        print(f"❌ Background processing failed for job {job_id}: {str(e)}")
        
        # Send error push with proper async context
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
            await send_silent_push(device_token, error_payload)
        except Exception as push_error:
            print(f"❌ Error push also failed for job {job_id}: {str(push_error)}")

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

@app.post("/queue-recipe-silent-push", response_model=SilentPushResponse)
async def queue_recipe_silent_push(request: SilentPushRequest, background_tasks: BackgroundTasks):
    """
    Queue recipe parsing and send result via silent push notification.
    Returns immediately while processing happens in background.
    """
    try:
        # Validate URL format
        if not request.url.strip():
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Add https if missing
        if not request.url.startswith(('http://', 'https://')):
            request.url = f"https://{request.url}"
        
        # Validate device token
        if not request.deviceToken.strip():
            raise HTTPException(status_code=400, detail="Device token is required")
        
        # DNS validation
        if not await is_valid_domain(request.url):
            raise HTTPException(status_code=400, detail="Invalid or unreachable URL domain")
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        print(f"📋 Queuing recipe processing job {job_id}")
        print(f"   📱 URL: {request.url}")
        print(f"   🔔 Device: {request.deviceToken[:8]}...")
        print(f"   📦 Source: {request.source}")
        
        # Add background task
        background_tasks.add_task(
            process_recipe_background,
            request.url,
            request.deviceToken,
            job_id
        )
        
        return SilentPushResponse(
            success=True,
            message="Recipe queued for background processing",
            jobId=job_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        print(f"❌ Silent Push Queue Error: {error_message}")
        raise HTTPException(status_code=500, detail=error_message)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)