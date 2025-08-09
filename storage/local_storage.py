import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta

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
    
    def clear_schedule(self, date_range: Optional[str] = None, start_date: Optional[date] = None, end_date: Optional[date] = None) -> int:
        """Clear scheduled meals based on date range
        
        Args:
            date_range: 'all', 'week', 'month', or None
            start_date: Specific start date for custom range
            end_date: Specific end date for custom range
        
        Returns:
            Number of meals removed
        """
        scheduled_meals = self.load_scheduled_meals()
        original_count = len(scheduled_meals)
        
        if date_range == "all":
            # Clear all scheduled meals
            self.save_scheduled_meals([])
            return original_count
        
        elif date_range == "week":
            # Clear meals for current week (Monday to Sunday)
            today = date.today()
            days_since_monday = today.weekday()  # Monday is 0
            start_of_week = today - timedelta(days=days_since_monday)
            end_of_week = start_of_week + timedelta(days=6)
            
            filtered_meals = [sm for sm in scheduled_meals if not (start_of_week <= sm.date <= end_of_week)]
            self.save_scheduled_meals(filtered_meals)
            return original_count - len(filtered_meals)
        
        elif date_range == "month":
            # Clear meals for current month
            today = date.today()
            start_of_month = today.replace(day=1)
            # Get last day of month
            if today.month == 12:
                end_of_month = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_of_month = date(today.year, today.month + 1, 1) - timedelta(days=1)
            
            filtered_meals = [sm for sm in scheduled_meals if not (start_of_month <= sm.date <= end_of_month)]
            self.save_scheduled_meals(filtered_meals)
            return original_count - len(filtered_meals)
        
        elif start_date and end_date:
            # Clear meals within custom date range
            filtered_meals = [sm for sm in scheduled_meals if not (start_date <= sm.date <= end_date)]
            self.save_scheduled_meals(filtered_meals)
            return original_count - len(filtered_meals)
        
        return 0
    
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
    
    def get_meal_preferences(self, days: int = 60) -> Dict[str, Dict[str, Any]]:
        """Get meal scheduling preferences based on historical data
        
        Args:
            days: Number of days to look back for preference analysis
            
        Returns:
            Dictionary with meal preferences including frequency and recency data
        """
        from datetime import timedelta
        
        # Load all scheduled meals
        scheduled_meals = self.load_scheduled_meals()
        
        # Filter to last N days
        cutoff_date = date.today() - timedelta(days=days)
        recent_meals = [sm for sm in scheduled_meals if hasattr(sm, 'created_at') and sm.created_at.date() >= cutoff_date]
        
        # If no created_at timestamps, fall back to scheduled date
        if not recent_meals:
            recent_meals = [sm for sm in scheduled_meals if sm.date >= cutoff_date]
        
        # Load meals for name mapping
        meals = self.load_meals()
        meal_lookup = {meal.id: meal.name for meal in meals}
        
        # Calculate preferences
        preferences = {}
        for sm in recent_meals:
            meal_name = meal_lookup.get(sm.meal_id, "Unknown Meal")
            
            if meal_name not in preferences:
                preferences[meal_name] = {
                    "frequency": 0,
                    "last_scheduled": None,
                    "occasions": {},
                    "meal_id": sm.meal_id
                }
            
            preferences[meal_name]["frequency"] += 1
            
            # Track most recent scheduling
            schedule_date = sm.created_at.date() if hasattr(sm, 'created_at') else sm.date
            if not preferences[meal_name]["last_scheduled"] or schedule_date > preferences[meal_name]["last_scheduled"]:
                preferences[meal_name]["last_scheduled"] = schedule_date
            
            # Track occasion preferences
            occasion = sm.occasion.value if hasattr(sm.occasion, 'value') else str(sm.occasion)
            preferences[meal_name]["occasions"][occasion] = preferences[meal_name]["occasions"].get(occasion, 0) + 1
        
        return preferences
    
    def get_recommended_meals(self, occasion: str = "dinner", count: int = 3) -> List[str]:
        """Get meal recommendations based on user preferences
        
        Args:
            occasion: Meal occasion (breakfast, lunch, dinner, snack)
            count: Number of recommendations to return
            
        Returns:
            List of recommended meal names
        """
        import random
        
        preferences = self.get_meal_preferences()
        meals = self.load_meals()
        
        if not preferences:
            # New user - return random meals
            return [meal.name for meal in random.sample(meals, min(count, len(meals)))]
        
        # Score meals based on frequency and recency
        scored_meals = []
        for meal_name, pref_data in preferences.items():
            # Base score from frequency
            frequency_score = pref_data["frequency"]
            
            # Bonus for occasion preference
            occasion_score = pref_data["occasions"].get(occasion, 0) * 2
            
            # Recency penalty (prefer meals not scheduled recently)
            recency_penalty = 0
            if pref_data["last_scheduled"]:
                days_since = (date.today() - pref_data["last_scheduled"]).days
                if days_since < 7:
                    recency_penalty = max(0, 7 - days_since) * 0.5
            
            total_score = frequency_score + occasion_score - recency_penalty
            scored_meals.append((meal_name, total_score))
        
        # Sort by score and return top recommendations
        scored_meals.sort(key=lambda x: x[1], reverse=True)
        recommended = [meal[0] for meal in scored_meals[:count]]
        
        # Fill remaining slots with random meals if needed
        if len(recommended) < count:
            all_meal_names = [meal.name for meal in meals]
            remaining_meals = [name for name in all_meal_names if name not in recommended]
            additional = random.sample(remaining_meals, min(count - len(recommended), len(remaining_meals)))
            recommended.extend(additional)
        
        return recommended[:count]
    
    def file_exists(self, filename: str) -> bool:
        """Check if a data file exists"""
        return (self.data_directory / filename).exists()
    
    def get_file_size(self, filename: str) -> int:
        """Get the size of a data file in bytes"""
        file_path = self.data_directory / filename
        return file_path.stat().st_size if file_path.exists() else 0