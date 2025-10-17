from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import asyncio
from Custom_Ingredient_LLM import process_ingredient

app = FastAPI(title="Custom Ingredient LLM API")

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

@app.post("/process-ingredient", response_model=IngredientResponse)
async def create_custom_ingredient(request: IngredientRequest):
    """Process a custom ingredient and return nutrition data, category, and image"""
    
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

@app.get("/")
async def root():
    return {"message": "Custom Ingredient LLM API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)