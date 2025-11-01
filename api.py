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

# Import new hybrid agent
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "Lumi_pydantic_agent"))

from agents.hybrid_recipe_agent import hybrid_agent, HybridAgentDeps
from Custom_Ingredient_LLM.Custom_Ingredient_LLM import process_ingredient
from Custom_Ingredient_LLM.Custom_Ingredient_LLM_Batch import process_ingredients_with_fallback

# Simple session context for new agent (replaces old SessionContext)
class SimpleSessionContext:
    """Lightweight session context for hybrid agent"""
    def __init__(self):
        import uuid
        self.session_id = str(uuid.uuid4())
        self.search_history = []
        self.current_batch_recipes = []
        self.saved_meals = []
        
    def get_saved_nutrition_totals(self):
        """Calculate nutrition totals from saved meals"""
        totals = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
        for meal in self.saved_meals:
            nutrition = meal.get("nutrition", {})
            for key in totals:
                totals[key] += nutrition.get(key, 0)
        return totals

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

# Pydantic models for Ingredient endpoint
class IngredientRequest(BaseModel):
    ingredient_name: str

class IngredientResponse(BaseModel):
    success: bool
    ingredient_name: str
    nutrition: Optional[Dict] = None
    category: Optional[str] = None
    category_image_url: Optional[str] = None
    spoonacular_image_hit: Optional[bool] = None
    image_url: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

# Pydantic models for Batch Ingredient endpoint
class IngredientBatchRequest(BaseModel):
    ingredient_names: List[str]

class IngredientBatchResponse(BaseModel):
    total_count: int
    successful_count: int
    failed_count: int
    results: List[IngredientResponse]

# Global storage for sessions (in production, use Redis/database)
sessions: Dict[str, SimpleSessionContext] = {}
hybrid_deps = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize hybrid agent dependencies on startup"""
    global hybrid_deps
    
    # Validate required environment variables for new hybrid agent
    required_vars = {
        'OPENAI_API_KEY': os.getenv("OPENAI_API_KEY"),
        'SERPAPI_KEY': os.getenv("SERPAPI_KEY"), 
        'GOOGLE_SEARCH_KEY': os.getenv("GOOGLE_SEARCH_KEY"),
        'GOOGLE_SEARCH_ENGINE_ID': os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Create hybrid agent dependencies template
    hybrid_deps = HybridAgentDeps(
        serpapi_key=required_vars['SERPAPI_KEY'],
        openai_key=required_vars['OPENAI_API_KEY'],
        google_key=required_vars['GOOGLE_SEARCH_KEY'],
        google_cx=required_vars['GOOGLE_SEARCH_ENGINE_ID']
    )
    
    print("✅ Hybrid Recipe Agent API initialized successfully")
    print(f"🔧 Using new hybrid agent with discovery + selective modes")
    yield
    print("🔄 Shutting down Hybrid Recipe Agent API")

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

def get_or_create_session(session_id: Optional[str] = None) -> SimpleSessionContext:
    """Get existing session or create new one"""
    if session_id and session_id in sessions:
        return sessions[session_id]
    
    # Create new session
    new_session = SimpleSessionContext()
    sessions[new_session.session_id] = new_session
    return new_session

def create_hybrid_deps_for_request() -> HybridAgentDeps:
    """Create a fresh HybridAgentDeps instance for each request"""
    # Create a copy of the template with fresh session state
    return HybridAgentDeps(
        serpapi_key=hybrid_deps.serpapi_key,
        openai_key=hybrid_deps.openai_key,
        google_key=hybrid_deps.google_key,
        google_cx=hybrid_deps.google_cx
        # Note: HybridAgentDeps has built-in session management (recipe_memory, etc.)
    )

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Hybrid Recipe Agent API",
        "status": "healthy", 
        "version": "2.0.0",
        "agent_type": "hybrid_discovery_selective",
        "active_sessions": len(sessions),
        "features": [
            "discovery_mode_fast_exploration",
            "selective_mode_precise_constraints", 
            "structured_ingredients_nutrition_timing",
            "multi_image_gallery_support",
            "10_grocery_store_categories"
        ]
    }

@app.get("/test")
async def test_hybrid_agent():
    """Test endpoint to verify new hybrid agent is working"""
    try:
        # Create test dependencies
        test_deps = create_hybrid_deps_for_request()
        
        # Test with simple query
        result = await hybrid_agent.run("chocolate cake", deps=test_deps)
        
        # Get results
        agent_response = result.data if hasattr(result, 'data') else str(result)
        recipe_count = len(test_deps.recipe_memory)
        
        return {
            "success": True,
            "agent_response": agent_response[:200] + "..." if len(agent_response) > 200 else agent_response,
            "recipes_found": recipe_count,
            "sample_recipe_ids": list(test_deps.recipe_memory.keys())[:3],
            "message": "Hybrid agent is working correctly!"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Hybrid agent test failed"
        }

@app.post("/search", response_model=SearchResponse)
async def search_recipes(request: SearchRequest):
    """Search for recipes using new hybrid agent and return structured results"""
    try:
        # Debug: Log exactly what query we received from iOS app
        print(f"🔍 API RECEIVED: '{request.query}' (session: {request.session_id})")
        
        # Get or create session for tracking
        session = get_or_create_session(request.session_id)
        session.search_history.append(request.query)
        
        # Create hybrid agent dependencies for this request
        request_deps = create_hybrid_deps_for_request()
        
        # Run NEW hybrid agent
        print(f"🚀 CALLING HYBRID AGENT: '{request.query}'")
        result = await hybrid_agent.run(request.query, deps=request_deps)
        
        # Extract clean agent response text
        agent_response = result.data if hasattr(result, 'data') else str(result)
        print(f"🤖 AGENT RESPONSE: '{agent_response}'")
        
        # Get recipes from agent's session memory (where clean recipes are stored)
        recipe_memory = request_deps.recipe_memory
        recipe_count = len(recipe_memory)
        print(f"📊 FOUND: {recipe_count} clean recipes in session memory")
        
        # Extract clean app-ready recipes
        all_recipes = []
        for recipe_id, recipe_data in recipe_memory.items():
            # Remove internal fields that apps don't need
            clean_recipe = recipe_data.copy()
            
            # Remove session/debug fields for cleaner API response
            if '_metadata' in clean_recipe:
                # Keep metadata but remove some session fields for cleaner API
                metadata = clean_recipe['_metadata'].copy()
                if 'session' in metadata:
                    # Keep only essential session info
                    metadata['session'] = {
                        'recipe_id': metadata['session'].get('recipe_id'),
                        'user_position': metadata['session'].get('user_position')
                    }
                clean_recipe['_metadata'] = metadata
            
            all_recipes.append(clean_recipe)
        
        print(f"✅ RETURNING: {len(all_recipes)} clean app-ready recipes")
        
        # Update session with recipes for future reference
        session.current_batch_recipes = all_recipes
        
        return SearchResponse(
            session_id=session.session_id,
            recipes=all_recipes,
            agent_response=agent_response,
            total_results=len(all_recipes),
            search_query=request.query
        )
        
    except Exception as e:
        print(f"❌ API ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/save-meal")
async def save_meal(request: SaveMealRequest):
    """Save a meal from current batch to saved meals"""
    try:
        if request.session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = sessions[request.session_id]
        
        # Simple meal saving logic (no agent needed for this)
        if 0 <= request.meal_number < len(session.current_batch_recipes):
            recipe_to_save = session.current_batch_recipes[request.meal_number]
            session.saved_meals.append(recipe_to_save)
            
            return {
                "success": True,
                "message": f"Meal #{request.meal_number} saved successfully",
                "session_id": session.session_id,
                "saved_meals_count": len(session.saved_meals)
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid meal number")
        
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
        
        # For analysis, we can either use the hybrid agent or provide a simpler response
        # Since the main focus is recipe discovery, let's provide basic analysis
        saved_meals_count = len(session.saved_meals)
        nutrition_totals = session.get_saved_nutrition_totals()
        
        # Simple analysis based on saved meals
        analysis = f"You have {saved_meals_count} saved meals. "
        if nutrition_totals['calories'] > 0:
            analysis += f"Total nutrition: {nutrition_totals['calories']:.0f} calories, "
            analysis += f"{nutrition_totals['protein']:.0f}g protein, "
            analysis += f"{nutrition_totals['fat']:.0f}g fat, "
            analysis += f"{nutrition_totals['carbs']:.0f}g carbs."
        else:
            analysis += "Nutrition data will be available once you save some meals with nutrition information."
        
        return {
            "session_id": request.session_id,
            "analysis": analysis,
            "saved_meals_count": len(session.saved_meals),
            "nutrition_totals": nutrition_totals
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

# ========== CUSTOM INGREDIENT LLM ENDPOINTS ==========

@app.post("/process-ingredient", response_model=IngredientResponse)
async def create_custom_ingredient(request: IngredientRequest):
    """
    Process a custom ingredient and return nutrition data, category, and images.
    
    This endpoint:
    1. Validates if the input is actually a food item
    2. Returns nutritional information per 100g/100ml
    3. Categorizes the ingredient
    4. Fetches both ingredient and category images
    
    Returns 400 if the input is not a food item.
    """
    
    if not request.ingredient_name:
        raise HTTPException(status_code=400, detail="Ingredient name is required")
    
    try:
        result = await process_ingredient(request.ingredient_name)
        
        # If it's not a food item, return with 400 status
        if not result.get("success", False):
            raise HTTPException(
                status_code=400, 
                detail={
                    "error": result.get("error"),
                    "message": result.get("message"),
                    "ingredient_name": result.get("ingredient_name")
                }
            )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing ingredient: {str(e)}")

@app.post("/process-ingredients-batch", response_model=IngredientBatchResponse)
async def create_custom_ingredients_batch(request: IngredientBatchRequest):
    """
    Process multiple ingredients in parallel and return all results.
    
    This endpoint:
    1. Accepts a list of ingredient names (max 50)
    2. Processes them in parallel batches of 5 to respect rate limits
    3. Returns results for all ingredients in a single response
    4. Handles failures gracefully (failed ingredients don't stop others)
    
    Example request:
    {
        "ingredient_names": ["chicken", "rice", "olive oil", "tomato"]
    }
    
    Returns structured results with success/failure status for each ingredient.
    """
    
    if not request.ingredient_names:
        raise HTTPException(status_code=400, detail="At least one ingredient name is required")
    
    if len(request.ingredient_names) > 50:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum 50 ingredients allowed per request, received {len(request.ingredient_names)}"
        )
    
    try:
        result = await process_ingredients_with_fallback(request.ingredient_names)
        
        # Check if there was a validation error
        if "error" in result and result["error"] == "TOO_MANY_INGREDIENTS":
            raise HTTPException(status_code=400, detail=result)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing ingredients batch: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)