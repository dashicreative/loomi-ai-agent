"""
Lean Recipe Parser API - Instagram & Site Recipe Parsing
Minimal FastAPI service with just 2 endpoints for URL parsing.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import sys
from pathlib import Path

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

# Create FastAPI app
app = FastAPI(
    title="Recipe Parser API",
    description="Parse Instagram videos and recipe sites into structured JSON",
    version="2.0.0"
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)