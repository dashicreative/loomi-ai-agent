from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from datetime import date, datetime
from uuid import UUID

from models.scheduled_meal import ScheduledMeal, ScheduledMealCreate, ScheduledMealUpdate, ScheduledMealWithMeal
from storage.local_storage import LocalStorage

router = APIRouter()

# Initialize storage
storage = LocalStorage()

@router.get("/", response_model=List[ScheduledMeal])
async def get_scheduled_meals():
    """Get all scheduled meals from storage"""
    try:
        scheduled_meals = storage.load_scheduled_meals()
        return scheduled_meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load scheduled meals: {str(e)}"
        )

@router.get("/{scheduled_meal_id}", response_model=ScheduledMeal)
async def get_scheduled_meal(scheduled_meal_id: str):
    """Get a specific scheduled meal by ID"""
    try:
        scheduled_meals = storage.load_scheduled_meals()
        scheduled_meal = next(
            (sm for sm in scheduled_meals if str(sm.id) == scheduled_meal_id), 
            None
        )
        
        if not scheduled_meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled meal with ID {scheduled_meal_id} not found"
            )
        return scheduled_meal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduled meal: {str(e)}"
        )

@router.post("/", response_model=ScheduledMeal, status_code=status.HTTP_201_CREATED)
async def create_scheduled_meal(scheduled_meal_data: ScheduledMealCreate):
    """Create a new scheduled meal"""
    try:
        # Verify that the meal exists
        meal = storage.get_meal_by_id(str(scheduled_meal_data.meal_id))
        if not meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal with ID {scheduled_meal_data.meal_id} not found"
            )
        
        # Convert ScheduledMealCreate to ScheduledMeal (this will generate a new UUID)
        scheduled_meal = ScheduledMeal(**scheduled_meal_data.model_dump())
        
        # Add to storage
        created_scheduled_meal = storage.add_scheduled_meal(scheduled_meal)
        return created_scheduled_meal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scheduled meal: {str(e)}"
        )

@router.put("/{scheduled_meal_id}", response_model=ScheduledMeal)
async def update_scheduled_meal(scheduled_meal_id: str, scheduled_meal_update: ScheduledMealUpdate):
    """Update an existing scheduled meal"""
    try:
        # Get existing scheduled meal
        scheduled_meals = storage.load_scheduled_meals()
        existing_scheduled_meal = next(
            (sm for sm in scheduled_meals if str(sm.id) == scheduled_meal_id),
            None
        )
        
        if not existing_scheduled_meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled meal with ID {scheduled_meal_id} not found"
            )
        
        # If meal_id is being updated, verify the new meal exists
        update_data = scheduled_meal_update.model_dump(exclude_unset=True)
        if 'meal_id' in update_data:
            meal = storage.get_meal_by_id(str(update_data['meal_id']))
            if not meal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Meal with ID {update_data['meal_id']} not found"
                )
        
        # Update only provided fields
        updated_data = existing_scheduled_meal.model_dump()
        updated_data.update(update_data)
        updated_scheduled_meal = ScheduledMeal(**updated_data)
        
        # Replace in storage
        scheduled_meals = [
            updated_scheduled_meal if str(sm.id) == scheduled_meal_id else sm 
            for sm in scheduled_meals
        ]
        storage.save_scheduled_meals(scheduled_meals)
        
        return updated_scheduled_meal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update scheduled meal: {str(e)}"
        )

@router.delete("/{scheduled_meal_id}")
async def delete_scheduled_meal(scheduled_meal_id: str):
    """Delete a scheduled meal from storage"""
    try:
        success = storage.delete_scheduled_meal(scheduled_meal_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled meal with ID {scheduled_meal_id} not found"
            )
        
        return {"message": f"Scheduled meal {scheduled_meal_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete scheduled meal: {str(e)}"
        )

@router.get("/by-date/{target_date}")
async def get_scheduled_meals_by_date(target_date: date):
    """Get all scheduled meals for a specific date"""
    try:
        scheduled_meals = storage.get_scheduled_meals_by_date(target_date)
        return scheduled_meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduled meals for date: {str(e)}"
        )

@router.get("/with-details/", response_model=List[ScheduledMealWithMeal])
async def get_scheduled_meals_with_details():
    """Get scheduled meals with embedded meal details for UI display"""
    try:
        scheduled_meals = storage.load_scheduled_meals()
        meals = storage.load_meals()
        
        # Create a lookup dict for meals
        meals_dict = {str(meal.id): meal for meal in meals}
        
        result = []
        for scheduled_meal in scheduled_meals:
            meal = meals_dict.get(str(scheduled_meal.meal_id))
            if meal:
                scheduled_with_meal = ScheduledMealWithMeal(
                    **scheduled_meal.model_dump(),
                    meal_name=meal.name,
                    meal_prep_time=meal.prep_time
                )
                result.append(scheduled_with_meal)
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduled meals with details: {str(e)}"
        )

@router.get("/by-date-range/{start_date}/{end_date}")
async def get_scheduled_meals_by_date_range(start_date: date, end_date: date):
    """Get scheduled meals within a date range"""
    try:
        scheduled_meals = storage.load_scheduled_meals()
        filtered_meals = [
            sm for sm in scheduled_meals 
            if start_date <= sm.date <= end_date
        ]
        return filtered_meals
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduled meals by date range: {str(e)}"
        )