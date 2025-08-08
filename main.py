from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import API routers
from api import meals, scheduled_meals, shopping_cart, chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for FastAPI application"""
    # Startup
    print("🚀 Loomi AI Agent starting up...")
    print("📁 Storage directory: storage/data/")
    print("🔗 API available at: http://localhost:3000")
    yield
    # Shutdown
    print("🛑 Loomi AI Agent shutting down...")

# Create FastAPI application
app = FastAPI(
    title="Loomi AI Agent",
    description="AI-powered meal planning backend for Loomi iOS app",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS for iOS app communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Add iOS simulator origins
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        # Add any additional origins your iOS app might use
        "*"  # For development only - restrict in production
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint for health checks"""
    return {
        "message": "Loomi AI Agent is running!",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": {
            "meals": "/api/meals",
            "scheduled_meals": "/api/scheduled-meals", 
            "shopping_cart": "/api/shopping-cart",
            "chat": "/api/chat",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check endpoint"""
    from storage.local_storage import LocalStorage
    
    try:
        storage = LocalStorage()
        meals_count = len(storage.load_meals())
        scheduled_count = len(storage.load_scheduled_meals())
        cart = storage.load_shopping_cart()
        
        return {
            "status": "healthy",
            "storage": {
                "meals": meals_count,
                "scheduled_meals": scheduled_count,
                "cart_meals": len(cart.meals),
                "cart_items": len(cart.items)
            },
            "endpoints_available": [
                "/api/meals",
                "/api/scheduled-meals",
                "/api/shopping-cart",
                "/api/chat"
            ]
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

# Include API routers
app.include_router(meals.router, prefix="/api/meals", tags=["meals"])
app.include_router(scheduled_meals.router, prefix="/api/scheduled-meals", tags=["scheduled-meals"])
app.include_router(shopping_cart.router, prefix="/api/shopping-cart", tags=["shopping-cart"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",  # Use IPv4 only for iOS simulator compatibility
        port=3000,
        reload=True,
        log_level="info"
    )