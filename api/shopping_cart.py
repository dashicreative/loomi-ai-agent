from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from uuid import UUID

from models.shopping_cart import ShoppingCart, CartMeal, CartItem, CartMealCreate, CartItemCreate
from storage.local_storage import LocalStorage

router = APIRouter()

# Initialize storage
storage = LocalStorage()

@router.get("/", response_model=ShoppingCart)
async def get_shopping_cart():
    """Get the current shopping cart"""
    try:
        cart = storage.load_shopping_cart()
        return cart
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load shopping cart: {str(e)}"
        )

@router.post("/meals", response_model=ShoppingCart, status_code=status.HTTP_201_CREATED)
async def add_meal_to_cart(meal_data: CartMealCreate):
    """Add a meal to the shopping cart"""
    try:
        # Verify that the meal exists
        meal = storage.get_meal_by_id(str(meal_data.meal_id))
        if not meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Meal with ID {meal_data.meal_id} not found"
            )
        
        # Create CartMeal from the data
        cart_meal = CartMeal(**meal_data.model_dump())
        
        # Add to cart
        updated_cart = storage.add_meal_to_cart(cart_meal)
        return updated_cart
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add meal to cart: {str(e)}"
        )

@router.post("/items", response_model=ShoppingCart, status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(item_data: CartItemCreate):
    """Add an item to the shopping cart"""
    try:
        # Create CartItem from the data
        cart_item = CartItem(**item_data.model_dump())
        
        # Add to cart
        updated_cart = storage.add_item_to_cart(cart_item)
        return updated_cart
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add item to cart: {str(e)}"
        )

@router.delete("/meals/{cart_meal_id}")
async def remove_meal_from_cart(cart_meal_id: str):
    """Remove a meal from the shopping cart"""
    try:
        cart = storage.load_shopping_cart()
        original_count = len(cart.meals)
        
        # Filter out the meal with the specified ID
        cart.meals = [meal for meal in cart.meals if str(meal.id) != cart_meal_id]
        
        if len(cart.meals) == original_count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart meal with ID {cart_meal_id} not found"
            )
        
        # Save updated cart
        storage.save_shopping_cart(cart)
        return {"message": f"Meal {cart_meal_id} removed from cart successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove meal from cart: {str(e)}"
        )

@router.delete("/items/{cart_item_id}")
async def remove_item_from_cart(cart_item_id: str):
    """Remove an item from the shopping cart"""
    try:
        cart = storage.load_shopping_cart()
        original_count = len(cart.items)
        
        # Filter out the item with the specified ID
        cart.items = [item for item in cart.items if str(item.id) != cart_item_id]
        
        if len(cart.items) == original_count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart item with ID {cart_item_id} not found"
            )
        
        # Save updated cart
        storage.save_shopping_cart(cart)
        return {"message": f"Item {cart_item_id} removed from cart successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove item from cart: {str(e)}"
        )

@router.put("/items/{cart_item_id}/toggle-completed")
async def toggle_item_completed(cart_item_id: str):
    """Toggle the completed status of a cart item"""
    try:
        cart = storage.load_shopping_cart()
        
        # Find and toggle the item
        item_found = False
        for item in cart.items:
            if str(item.id) == cart_item_id:
                item.is_completed = not item.is_completed
                item_found = True
                break
        
        if not item_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart item with ID {cart_item_id} not found"
            )
        
        # Save updated cart
        storage.save_shopping_cart(cart)
        return {"message": f"Item {cart_item_id} completion status toggled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle item completion: {str(e)}"
        )

@router.delete("/clear")
async def clear_shopping_cart():
    """Clear all items from the shopping cart"""
    try:
        storage.clear_shopping_cart()
        return {"message": "Shopping cart cleared successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear shopping cart: {str(e)}"
        )

@router.get("/summary")
async def get_cart_summary():
    """Get a summary of the shopping cart contents"""
    try:
        cart = storage.load_shopping_cart()
        
        # Calculate summary statistics
        total_meals = len(cart.meals)
        total_items = len(cart.items)
        completed_items = len([item for item in cart.items if item.is_completed])
        pending_items = total_items - completed_items
        
        # Get total servings
        total_servings = sum(meal.servings for meal in cart.meals)
        
        return {
            "total_meals": total_meals,
            "total_items": total_items,
            "completed_items": completed_items,
            "pending_items": pending_items,
            "total_servings": total_servings,
            "completion_percentage": (completed_items / total_items * 100) if total_items > 0 else 0
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cart summary: {str(e)}"
        )