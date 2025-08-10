#!/usr/bin/env python3
"""
Test what attributes ScheduledMeal objects actually have
"""

from datetime import date
from storage.local_storage import LocalStorage

storage = LocalStorage()

# Get scheduled meals for today
scheduled_meals = storage.get_scheduled_meals_by_date(date.today())

if scheduled_meals:
    meal = scheduled_meals[0]
    print(f"ScheduledMeal attributes: {dir(meal)}")
    print(f"\nScheduledMeal type: {type(meal)}")
    print(f"Has 'occasion': {'occasion' in dir(meal)}")
    print(f"Has 'meal_occasion': {'meal_occasion' in dir(meal)}")
    print(f"Has 'meal_name': {'meal_name' in dir(meal)}")
    print(f"Has 'meal_id': {'meal_id' in dir(meal)}")
    
    print(f"\nActual values:")
    print(f"meal.occasion: {meal.occasion}")
    print(f"meal.meal_id: {meal.meal_id}")
    print(f"meal.date: {meal.date}")
else:
    print("No scheduled meals found for today")