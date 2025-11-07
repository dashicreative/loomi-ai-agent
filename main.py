"""
Railway Entry Point for Recipe Parser API

This is the main entry point for deploying the Recipe Parser API as a 
FastAPI web service on Railway for iOS app integration.
Supports Instagram video parsing and recipe site parsing.
"""

import os
import sys
from pathlib import Path

# Add the current directory to Python path to ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("🚂 Starting Recipe Parser API on Railway...")
    
    import uvicorn
    from api import app
    
    # Get port from environment (Railway sets this automatically)
    port = int(os.getenv("PORT", 8000))
    
    # Run FastAPI server
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )