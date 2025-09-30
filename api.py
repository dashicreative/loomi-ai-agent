"""
FastAPI service for Recipe Discovery Agent
Provides HTTP endpoints for iOS app integration
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
import asyncio
from contextlib import asynccontextmanager

from Recipe_Discovery_Agent.Discovery_Agent import create_recipe_discovery_agent
from Recipe_Discovery_Agent.Dependencies import RecipeDeps, SessionContext

# Pydantic models for API requests/responses
class SearchRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    
class SaveMealRequest(BaseModel):
    meal_number: int
    session_id: str
    
class AnalyzeMealsRequest(BaseModel):
    query: str
    session_id: str
    daily_goals: Optional[Dict] = None

class SessionResponse(BaseModel):
    session_id: str
    current_recipes: List[Dict]
    saved_meals: List[Dict]
    nutrition_totals: Dict
    search_history: List[str]

class SearchResponse(BaseModel):
    session_id: str
    recipes: List[Dict]
    agent_response: str
    total_results: int
    search_query: str

# Global storage for sessions (in production, use Redis/database)
sessions: Dict[str, SessionContext] = {}
agent = None
deps_template = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent and dependencies on startup"""
    global agent, deps_template
    
    # Validate required environment variables
    required_vars = {
        'OPENAI_API_KEY': os.getenv("OPENAI_API_KEY"),
        'SERPAPI_KEY': os.getenv("SERPAPI_KEY"), 
        'FIRECRAWL_API_KEY': os.getenv("FIRECRAWL_API_KEY")
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Create agent and dependencies template
    agent = create_recipe_discovery_agent()
    deps_template = RecipeDeps(
        serpapi_key=required_vars['SERPAPI_KEY'],
        firecrawl_key=required_vars['FIRECRAWL_API_KEY'],
        openai_key=required_vars['OPENAI_API_KEY'],
        google_search_key=os.getenv("GOOGLE_SEARCH_KEY"),
        google_search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
        session=None  # Will be set per request
    )
    
    print("✅ Recipe Discovery Agent API initialized successfully")
    yield
    print("🔄 Shutting down Recipe Discovery Agent API")

# Create FastAPI app
app = FastAPI(
    title="Recipe Discovery Agent API",
    description="HTTP API for Recipe Discovery Agent - iOS App Integration",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for your iOS app in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_or_create_session(session_id: Optional[str] = None) -> SessionContext:
    """Get existing session or create new one"""
    if session_id and session_id in sessions:
        return sessions[session_id]
    
    # Create new session
    new_session = SessionContext()
    sessions[new_session.session_id] = new_session
    return new_session

def create_deps_with_session(session: SessionContext) -> RecipeDeps:
    """Create RecipeDeps with the specified session"""
    return RecipeDeps(
        serpapi_key=deps_template.serpapi_key,
        firecrawl_key=deps_template.firecrawl_key,
        openai_key=deps_template.openai_key,
        google_search_key=deps_template.google_search_key,
        google_search_engine_id=deps_template.google_search_engine_id,
        session=session
    )

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Recipe Discovery Agent API",
        "status": "healthy",
        "version": "1.0.0",
        "active_sessions": len(sessions)
    }

@app.post("/search", response_model=SearchResponse)
async def search_recipes(request: SearchRequest):
    """Search for recipes and return structured results"""
    try:
        # Debug: Log exactly what query we received from iOS app
        print(f"🔍 DEBUG: API RECEIVED QUERY: '{request.query}'")
        print(f"🔍 DEBUG: API RECEIVED SESSION_ID: '{request.session_id}'")
        
        # Get or create session
        session = get_or_create_session(request.session_id)
        deps = create_deps_with_session(session)
        
        # Debug: Confirm what we're sending to agent
        print(f"🔍 DEBUG: SENDING TO AGENT: '{request.query}'")
        
        # Run agent with search query
        result = await agent.run(request.query, deps=deps)
        
        # Debug: Log the actual agent response structure
        print(f"🔍 DEBUG: Agent result type: {type(result)}")
        print(f"🔍 DEBUG: Agent result data: {getattr(result, 'data', 'No data attr')}")
        print(f"🔍 DEBUG: Agent result messages count: {len(result.all_messages())}")
        
        # Extract structured data from agent response
        all_recipes = []
        search_query = request.query
        
        # Debug: Let's examine the entire result structure
        print(f"🔍 DEBUG: Examining all messages for recipes...")
        
        for i, message in enumerate(result.all_messages()):
            print(f"🔍 DEBUG: Message {i} type: {type(message)}")
            
            # Check for tool call responses
            if hasattr(message, 'parts'):
                for part in message.parts:
                    if hasattr(part, 'tool_name'):
                        print(f"🔍 DEBUG: Found tool call: {part.tool_name}")
                    if hasattr(part, 'tool_result'):
                        tool_result = part.tool_result
                        print(f"🔍 DEBUG: Tool result type: {type(tool_result)}")
                        if isinstance(tool_result, dict):
                            print(f"🔍 DEBUG: Tool result keys: {list(tool_result.keys())[:10]}")  # First 10 keys
                            if 'full_recipes' in tool_result:
                                batch_recipes = tool_result.get('full_recipes', [])
                                print(f"🔍 DEBUG: Found {len(batch_recipes)} recipes via parts.tool_result")
                                all_recipes.extend(batch_recipes)
                                search_query = tool_result.get('searchQuery', search_query)
            
            # Original extraction logic as fallback
            if hasattr(message, 'content'):
                content = message.content
                if isinstance(content, list):
                    for j, item in enumerate(content):
                        print(f"🔍 DEBUG: Message {i}, Item {j} type: {type(item)}")
                        if hasattr(item, 'output'):
                            output = item.output
                            print(f"🔍 DEBUG: Tool output keys: {list(output.keys()) if isinstance(output, dict) else 'Not dict'}")
                            if isinstance(output, dict) and 'full_recipes' in output:
                                batch_recipes = output.get('full_recipes', [])
                                print(f"🔍 DEBUG: Found {len(batch_recipes)} recipes via content.output")
                                all_recipes.extend(batch_recipes)
                                search_query = output.get('searchQuery', search_query)
        
        # Also check if session has recipes (agent might have updated it directly)
        if not all_recipes and session.current_batch_recipes:
            print(f"🔍 DEBUG: No recipes in tool outputs, but session has {len(session.current_batch_recipes)} recipes")
            all_recipes = session.current_batch_recipes
        
        print(f"🔍 DEBUG: Final recipe count: {len(all_recipes)}")
        
        # Update session with new recipes
        session.current_batch_recipes = all_recipes
        
        # Clean agent response text
        agent_response = str(result.data) if hasattr(result, 'data') else str(result)
        if 'AgentRunResult' in agent_response:
            # Extract clean text from AgentRunResult
            if 'output=' in agent_response:
                start = agent_response.find("output='") + 8
                end = agent_response.find("')", start)
                if start > 7 and end > start:
                    agent_response = agent_response[start:end]
        
        return SearchResponse(
            session_id=session.session_id,
            recipes=all_recipes,
            agent_response=agent_response,
            total_results=len(all_recipes),
            search_query=search_query
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/save-meal")
async def save_meal(request: SaveMealRequest):
    """Save a meal from current batch to saved meals"""
    try:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = sessions[request.session_id]
        deps = create_deps_with_session(session)
        
        # Use agent's save_meal tool
        result = await agent.run(
            f"save meal #{request.meal_number}",
            deps=deps
        )
        
        return {
            "success": True,
            "message": f"Meal #{request.meal_number} saved successfully",
            "session_id": session.session_id,
            "saved_meals_count": len(session.saved_meals)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save meal failed: {str(e)}")

@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get current session state"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    return SessionResponse(
        session_id=session.session_id,
        current_recipes=session.current_batch_recipes,
        saved_meals=session.saved_meals,
        nutrition_totals=session.get_saved_nutrition_totals(),
        search_history=session.search_history
    )

@app.get("/saved-meals/{session_id}")
async def get_saved_meals(session_id: str):
    """Get all saved meals for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    return {
        "session_id": session_id,
        "saved_meals": session.saved_meals,
        "nutrition_totals": session.get_saved_nutrition_totals(),
        "total_count": len(session.saved_meals)
    }

@app.post("/analyze-meals")
async def analyze_meals(request: AnalyzeMealsRequest):
    """Analyze saved meals based on user query"""
    try:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = sessions[request.session_id]
        deps = create_deps_with_session(session)
        
        # Use agent's analyze tool
        result = await agent.run(
            f"analyze my saved meals: {request.query}",
            deps=deps
        )
        
        return {
            "session_id": request.session_id,
            "analysis": str(result.data) if hasattr(result, 'data') else str(result),
            "saved_meals_count": len(session.saved_meals),
            "nutrition_totals": session.get_saved_nutrition_totals()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del sessions[session_id]
    
    return {
        "success": True,
        "message": f"Session {session_id} deleted",
        "active_sessions": len(sessions)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)