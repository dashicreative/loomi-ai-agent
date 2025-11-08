"""
Lean Recipe Parser API - Instagram & Site Recipe Parsing
Minimal FastAPI service with just 2 endpoints for URL parsing.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import sys
import json
import asyncio
import time
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
            "POST /parse-site-recipe",
            "POST /parse-instagram-recipe-stream (SSE)",
            "POST /parse-site-recipe-stream (SSE)"
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

# =============================================================================
# SERVER-SENT EVENTS (SSE) STREAMING ENDPOINTS
# =============================================================================

def sse_format(data: dict) -> str:
    """Format data as Server-Sent Events message"""
    return f"data: {json.dumps(data)}\n\n"

async def stream_instagram_parsing(url: str):
    """
    Stream Instagram recipe parsing with real-time progress updates
    """
    try:
        # Stage 1: Finding your recipe (0-40%)
        yield sse_format({"stage": "Finding your recipe...", "progress": 10})
        
        # Validate Instagram URL
        if "instagram.com" not in url.lower():
            yield sse_format({
                "stage": "Error", 
                "progress": 0, 
                "success": False,
                "error": "URL must be an Instagram post or reel"
            })
            return
            
        yield sse_format({"stage": "Finding your recipe...", "progress": 20})
        
        # Check environment variables
        required_env_vars = ["APIFY_API_KEY", "GOOGLE_GEMINI_KEY", "DEEPGRAM_WISPER_API"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            yield sse_format({
                "stage": "Error",
                "progress": 0,
                "success": False,
                "error": f"Server configuration error: Missing environment variables"
            })
            return
            
        yield sse_format({"stage": "Finding your recipe...", "progress": 40})
        
        # Stage 2: Reading your recipe (40-70%)
        yield sse_format({"stage": "Reading your recipe...", "progress": 50})
        
        # Parse Instagram recipe in a thread to avoid blocking
        import concurrent.futures
        import threading
        
        # Create a lock and progress tracker for threaded operations
        progress_lock = threading.Lock()
        current_progress = {"value": 50}
        
        def update_progress(stage: str, progress: int):
            with progress_lock:
                current_progress["value"] = progress
        
        # Run the parsing in a thread pool
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Start the parsing
            future = executor.submit(instagram_parser.parse_instagram_recipe_to_json, url)
            
            # Monitor progress while parsing runs
            llm_start_time = time.time()
            llm_shown = False
            
            while not future.done():
                await asyncio.sleep(0.5)  # Check every 500ms
                
                # Show "Preparing your recipe..." if LLM takes longer than 3 seconds
                if not llm_shown and (time.time() - llm_start_time) > 3:
                    yield sse_format({"stage": "Preparing your recipe...", "progress": 80})
                    llm_shown = True
                
                # Update reading progress gradually
                if current_progress["value"] < 70:
                    current_progress["value"] = min(70, current_progress["value"] + 2)
                    yield sse_format({"stage": "Reading your recipe...", "progress": current_progress["value"]})
            
            # Get the result
            recipe_json = future.result()
        
        # Stage 4: Recipe Ready! (100%)
        yield sse_format({
            "stage": "Your recipe is ready!", 
            "progress": 100,
            "success": True,
            "recipe_json": recipe_json
        })
        
    except Exception as e:
        # Handle any errors during streaming
        import traceback
        print(f"❌ SSE Instagram Parse Error: {str(e)}")
        print("📍 Full traceback:")
        print(traceback.format_exc())
        
        yield sse_format({
            "stage": "Error",
            "progress": 0,
            "success": False,
            "error": str(e)
        })

async def stream_site_parsing(url: str):
    """
    Stream site recipe parsing with real-time progress updates
    """
    try:
        # Stage 1: Finding your recipe (0-40%)
        yield sse_format({"stage": "Finding your recipe...", "progress": 20})
        
        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
            
        yield sse_format({"stage": "Finding your recipe...", "progress": 40})
        
        # Stage 2: Reading your recipe (40-70%)
        yield sse_format({"stage": "Reading your recipe...", "progress": 60})
        
        # Parse recipe site
        llm_start_time = time.time()
        result = await parse_single_recipe_url(url)
        llm_duration = time.time() - llm_start_time
        
        # Stage 3: Preparing your recipe (only if LLM took > 3 seconds)
        if llm_duration > 3:
            yield sse_format({"stage": "Preparing your recipe...", "progress": 90})
            await asyncio.sleep(0.5)  # Brief pause to show the stage
        
        if result["success"]:
            # Stage 4: Recipe Ready!
            yield sse_format({
                "stage": "Your recipe is ready!",
                "progress": 100,
                "success": True,
                "recipe_json": result["processed_json"],
                "elapsed_seconds": result["total_elapsed_seconds"]
            })
        else:
            yield sse_format({
                "stage": "Error",
                "progress": 0,
                "success": False,
                "error": result.get("error", "Failed to parse recipe")
            })
            
    except Exception as e:
        print(f"❌ SSE Site Parse Error: {str(e)}")
        yield sse_format({
            "stage": "Error",
            "progress": 0,
            "success": False,
            "error": str(e)
        })

@app.post("/parse-instagram-recipe-stream")
async def parse_instagram_recipe_stream(request: URLRequest):
    """
    Parse Instagram video/reel with real-time progress updates via Server-Sent Events.
    
    Returns a stream of progress updates followed by the final recipe JSON.
    
    Input: {"url": "https://www.instagram.com/p/ABC123/"}
    Output: SSE stream with progress updates + final result
    """
    return StreamingResponse(
        stream_instagram_parsing(request.url),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*"
        }
    )

@app.post("/parse-site-recipe-stream")
async def parse_site_recipe_stream(request: URLRequest):
    """
    Parse recipe website with real-time progress updates via Server-Sent Events.
    
    Returns a stream of progress updates followed by the final recipe JSON.
    
    Input: {"url": "https://www.allrecipes.com/recipe/..."}
    Output: SSE stream with progress updates + final result
    """
    return StreamingResponse(
        stream_site_parsing(request.url),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*"
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)