import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date

from models.meal import Meal
from models.scheduled_meal import ScheduledMeal
from models.shopping_cart import ShoppingCart, CartMeal, CartItem

class LocalStorage:
    """Local JSON file storage service that matches iOS expectations"""
    
    def __init__(self, data_directory: str = "storage/data"):
        self.data_directory = Path(data_directory)
        self.data_directory.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.meals_file = self.data_directory / "meals.json"
        self.scheduled_meals_file = self.data_directory / "scheduled_meals.json" 
        self.shopping_cart_file = self.data_directory / "shopping_cart.json"
    
    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime, date, and UUID objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        elif hasattr(obj, 'hex'):  # UUID objects
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _load_json_file(self, file_path: Path, default_value=None):
        """Load JSON data from file with error handling"""
        if not file_path.exists():
            return default_value or []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default_value or []
    
    def _save_json_file(self, file_path: Path, data):
        """Save data to JSON file with proper formatting"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=self._json_serializer)
    
    # Meals Storage
    def save_meals(self, meals: List[Meal]) -> None:
        """Save meals to JSON file"""
        meals_data = [meal.model_dump(by_alias=True) for meal in meals]
        self._save_json_file(self.meals_file, meals_data)
    
    def load_meals(self) -> List[Meal]:
        """Load meals from JSON file"""
        meals_data = self._load_json_file(self.meals_file, [])
        return [Meal(**meal_data) for meal_data in meals_data]
    
    def add_meal(self, meal: Meal) -> Meal:
        """Add a single meal to storage"""
        meals = self.load_meals()
        meals.append(meal)
        self.save_meals(meals)
        return meal
    
    def get_meal_by_id(self, meal_id: str) -> Optional[Meal]:
        """Get a specific meal by ID"""
        meals = self.load_meals()
        for meal in meals:
            if str(meal.id) == meal_id:
                return meal
        return None
    
    def delete_meal(self, meal_id: str) -> bool:
        """Delete a meal from storage"""
        meals = self.load_meals()
        original_count = len(meals)
        meals = [meal for meal in meals if str(meal.id) != meal_id]
        if len(meals) < original_count:
            self.save_meals(meals)
            return True
        return False
    
    # Scheduled Meals Storage
    def save_scheduled_meals(self, scheduled_meals: List[ScheduledMeal]) -> None:
        """Save scheduled meals to JSON file"""
        scheduled_data = [scheduled.model_dump(by_alias=True) for scheduled in scheduled_meals]
        self._save_json_file(self.scheduled_meals_file, scheduled_data)
    
    def load_scheduled_meals(self) -> List[ScheduledMeal]:
        """Load scheduled meals from JSON file"""
        scheduled_data = self._load_json_file(self.scheduled_meals_file, [])
        return [ScheduledMeal(**scheduled) for scheduled in scheduled_data]
    
    def add_scheduled_meal(self, scheduled_meal: ScheduledMeal) -> ScheduledMeal:
        """Add a single scheduled meal to storage"""
        scheduled_meals = self.load_scheduled_meals()
        scheduled_meals.append(scheduled_meal)
        self.save_scheduled_meals(scheduled_meals)
        return scheduled_meal
    
    def get_scheduled_meals_by_date(self, target_date: date) -> List[ScheduledMeal]:
        """Get all scheduled meals for a specific date"""
        scheduled_meals = self.load_scheduled_meals()
        return [sm for sm in scheduled_meals if sm.date == target_date]
    
    def delete_scheduled_meal(self, scheduled_meal_id: str) -> bool:
        """Delete a scheduled meal from storage"""
        scheduled_meals = self.load_scheduled_meals()
        original_count = len(scheduled_meals)
        scheduled_meals = [sm for sm in scheduled_meals if str(sm.id) != scheduled_meal_id]
        if len(scheduled_meals) < original_count:
            self.save_scheduled_meals(scheduled_meals)
            return True
        return False
    
    # Shopping Cart Storage
    def save_shopping_cart(self, shopping_cart: ShoppingCart) -> None:
        """Save shopping cart to JSON file"""
        cart_data = shopping_cart.model_dump(by_alias=True)
        self._save_json_file(self.shopping_cart_file, cart_data)
    
    def load_shopping_cart(self) -> ShoppingCart:
        """Load shopping cart from JSON file"""
        cart_data = self._load_json_file(self.shopping_cart_file, {"meals": [], "items": []})
        return ShoppingCart(**cart_data)
    
    def add_meal_to_cart(self, cart_meal: CartMeal) -> ShoppingCart:
        """Add a meal to the shopping cart"""
        cart = self.load_shopping_cart()
        cart.meals.append(cart_meal)
        self.save_shopping_cart(cart)
        return cart
    
    def add_item_to_cart(self, cart_item: CartItem) -> ShoppingCart:
        """Add an item to the shopping cart"""
        cart = self.load_shopping_cart()
        cart.items.append(cart_item)
        self.save_shopping_cart(cart)
        return cart
    
    def clear_shopping_cart(self) -> None:
        """Clear all items from shopping cart"""
        empty_cart = ShoppingCart(meals=[], items=[])
        self.save_shopping_cart(empty_cart)
    
    # Utility methods
    def get_data_directory(self) -> Path:
        """Get the data directory path"""
        return self.data_directory
    
    def file_exists(self, filename: str) -> bool:
        """Check if a data file exists"""
        return (self.data_directory / filename).exists()
    
    def get_file_size(self, filename: str) -> int:
        """Get the size of a data file in bytes"""
        file_path = self.data_directory / filename
        return file_path.stat().st_size if file_path.exists() else 0