from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from uuid import UUID

from models.meal import Meal, MealCreate, MealUpdate
from storage.local_storage import LocalStorage

router = APIRouter()

# Initialize storage
storage = LocalStorage()

@router.get("/", response_model=List[Meal])
async def get_meals():
    """Get all meals from storage"""
    try:
        meals = storage.load_meals()
        return meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load meals: {str(e)}"
        )

@router.get("/{meal_id}", response_model=Meal)
async def get_meal(meal_id: str):
    """Get a specific meal by ID"""
    try:
        meal = storage.get_meal_by_id(meal_id)
        if not meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal with ID {meal_id} not found"
            )
        return meal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get meal: {str(e)}"
        )

@router.post("/", response_model=Meal, status_code=status.HTTP_201_CREATED)
async def create_meal(meal_data: MealCreate):
    """Create a new meal"""
    try:
        # Convert MealCreate to Meal (this will generate a new UUID)
        meal = Meal(**meal_data.model_dump())
        
        # Add to storage
        created_meal = storage.add_meal(meal)
        return created_meal
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create meal: {str(e)}"
        )

@router.put("/{meal_id}", response_model=Meal)
async def update_meal(meal_id: str, meal_update: MealUpdate):
    """Update an existing meal"""
    try:
        # Get existing meal
        existing_meal = storage.get_meal_by_id(meal_id)
        if not existing_meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal with ID {meal_id} not found"
            )
        
        # Update only provided fields
        update_data = meal_update.model_dump(exclude_unset=True)
        updated_meal_data = existing_meal.model_dump()
        updated_meal_data.update(update_data)
        
        # Create updated meal
        updated_meal = Meal(**updated_meal_data)
        
        # Replace in storage
        meals = storage.load_meals()
        meals = [updated_meal if str(m.id) == meal_id else m for m in meals]
        storage.save_meals(meals)
        
        return updated_meal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update meal: {str(e)}"
        )

@router.delete("/{meal_id}")
async def delete_meal(meal_id: str):
    """Delete a meal from storage"""
    try:
        success = storage.delete_meal(meal_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal with ID {meal_id} not found"
            )
        
        return {"message": f"Meal {meal_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete meal: {str(e)}"
        )

@router.get("/search/by-occasion/{occasion}")
async def get_meals_by_occasion(occasion: str):
    """Get meals filtered by occasion"""
    try:
        meals = storage.load_meals()
        filtered_meals = [meal for meal in meals if meal.occasion.value == occasion]
        return filtered_meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search meals: {str(e)}"
        )

@router.get("/search/favorites")
async def get_favorite_meals():
    """Get all favorite meals"""
    try:
        meals = storage.load_meals()
        favorite_meals = [meal for meal in meals if meal.is_favorite]
        return favorite_meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get favorite meals: {str(e)}"
        )