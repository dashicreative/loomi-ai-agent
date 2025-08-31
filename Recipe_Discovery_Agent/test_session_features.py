"""
Test Script for Session Features

This script simulates user interactions to test:
1. Session context tracking
2. Find more functionality (URL exclusion)
3. Saved meals tracking
4. Nutritional analysis
5. Goal calculations
"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from Tools.session_context import get_or_create_session
from Tools.session_tools import save_meal_to_session, analyze_saved_meals, get_session_status
from Tools.saved_meals_analyzer import analyze_saved_meals_tool


async def test_session_features():
    """Test all session management features."""
    
    print("\n" + "="*60)
    print("🧪 TESTING SESSION FEATURES")
    print("="*60)
    
    # 1. Create a session
    print("\n1️⃣ Creating test session...")
    session = get_or_create_session("test-session-001")
    print(f"   Session ID: {session.session_id}")
    
    # 2. Simulate recipes from a search (mock data)
    print("\n2️⃣ Simulating recipe search results...")
    mock_recipes = [
        {
            "id": 1,
            "title": "Grilled Chicken Breast",
            "sourceUrl": "https://example.com/chicken",
            "nutrition": [
                {"name": "Calories", "value": "165"},
                {"name": "Protein", "value": "31g"},
                {"name": "Fat", "value": "3.6g"},
                {"name": "Carbs", "value": "0g"}
            ]
        },
        {
            "id": 2,
            "title": "Quinoa Salad Bowl",
            "sourceUrl": "https://example.com/quinoa",
            "nutrition": [
                {"name": "Calories", "value": "222"},
                {"name": "Protein", "value": "8g"},
                {"name": "Fat", "value": "4g"},
                {"name": "Carbs", "value": "39g"}
            ]
        },
        {
            "id": 3,
            "title": "Salmon with Vegetables",
            "sourceUrl": "https://example.com/salmon",
            "nutrition": [
                {"name": "Calories", "value": "367"},
                {"name": "Protein", "value": "34g"},
                {"name": "Fat", "value": "22g"},
                {"name": "Carbs", "value": "8g"}
            ]
        },
        {
            "id": 4,
            "title": "Greek Yogurt Parfait",
            "sourceUrl": "https://example.com/yogurt",
            "nutrition": [
                {"name": "Calories", "value": "149"},
                {"name": "Protein", "value": "20g"},
                {"name": "Fat", "value": "2g"},
                {"name": "Carbs", "value": "15g"}
            ]
        },
        {
            "id": 5,
            "title": "Beef Stir Fry",
            "sourceUrl": "https://example.com/beef",
            "nutrition": [
                {"name": "Calories", "value": "454"},
                {"name": "Protein", "value": "35g"},
                {"name": "Fat", "value": "28g"},
                {"name": "Carbs", "value": "12g"}
            ]
        }
    ]
    
    # Update session with current batch
    session.update_current_batch(mock_recipes)
    print(f"   Added {len(mock_recipes)} recipes to current batch")
    print(f"   Shown URLs tracked: {len(session.shown_recipe_urls)}")
    
    # 3. Test saving meals
    print("\n3️⃣ Testing meal saving...")
    
    # Save recipe #1 (Grilled Chicken)
    result = await save_meal_to_session("test-session-001", 1)
    print(f"   Save meal #1: {result['message']}")
    
    # Save recipe #3 (Salmon)
    result = await save_meal_to_session("test-session-001", 3)
    print(f"   Save meal #3: {result['message']}")
    
    # Save recipe #4 (Greek Yogurt)
    result = await save_meal_to_session("test-session-001", 4)
    print(f"   Save meal #4: {result['message']}")
    
    # Try to save duplicate
    result = await save_meal_to_session("test-session-001", 1)
    print(f"   Try duplicate save: {result['message']}")
    
    # 4. Test nutritional analysis
    print("\n4️⃣ Testing nutritional analysis...")
    
    # Total calories
    result = await analyze_saved_meals("test-session-001", "What's the total calories?")
    print(f"\n   Query: 'Total calories?'")
    print(f"   Result: {result['message']}")
    
    # Total protein
    result = await analyze_saved_meals("test-session-001", "How much protein in total?")
    print(f"\n   Query: 'Total protein?'")
    print(f"   Result: {result['message']}")
    
    # All totals
    result = await analyze_saved_meals("test-session-001", "Show me all nutrition totals")
    print(f"\n   Query: 'All nutrition totals'")
    print(f"   Result: {result['message']}")
    if 'breakdown' in result:
        for nutrient, value in result['breakdown'].items():
            print(f"      - {nutrient}: {value}")
    
    # 5. Test goal calculations
    print("\n5️⃣ Testing goal-based queries...")
    
    # Protein goal
    result = await analyze_saved_meals("test-session-001", "I have a 100g protein goal, how much more do I need?")
    print(f"\n   Query: '100g protein goal, how much more?'")
    print(f"   Result: {result['message']}")
    
    # 6. Test averages
    print("\n6️⃣ Testing average calculations...")
    result = await analyze_saved_meals("test-session-001", "What's the average calories per meal?")
    print(f"\n   Query: 'Average calories per meal?'")
    print(f"   Result: {result['message']}")
    if 'breakdown' in result:
        for nutrient, value in result['breakdown'].items():
            print(f"      - Average {nutrient}: {value}")
    
    # 7. Test session status
    print("\n7️⃣ Testing session status...")
    status = await get_session_status("test-session-001")
    print(f"   Session ID: {status['session_id']}")
    print(f"   Saved meals: {status['saved_meals_count']}")
    print(f"   Total shown URLs: {status['total_shown_urls']}")
    print(f"   Saved meal titles:")
    for meal in status['saved_meals']:
        print(f"      - {meal['title']} (originally #{meal['original_number']})")
    
    # 8. Test URL exclusion for "find more"
    print("\n8️⃣ Testing URL exclusion for 'find more'...")
    print(f"   URLs to exclude in next search: {session.shown_recipe_urls}")
    print(f"   This prevents these {len(session.shown_recipe_urls)} recipes from appearing again")
    
    # 9. Simulate second search with exclusion
    print("\n9️⃣ Simulating 'find more' with new recipes...")
    new_mock_recipes = [
        {
            "id": 6,
            "title": "Turkey Sandwich",
            "sourceUrl": "https://example.com/turkey",
            "nutrition": [
                {"name": "Calories", "value": "324"},
                {"name": "Protein", "value": "24g"},
                {"name": "Fat", "value": "11g"},
                {"name": "Carbs", "value": "33g"}
            ]
        }
    ]
    
    # Check if URL would be excluded
    for recipe in new_mock_recipes:
        url = recipe['sourceUrl']
        if url in session.shown_recipe_urls:
            print(f"   ❌ Would exclude: {recipe['title']} (already shown)")
        else:
            print(f"   ✅ Would include: {recipe['title']} (new recipe)")
    
    print("\n" + "="*60)
    print("✅ SESSION FEATURE TESTS COMPLETE")
    print("="*60)
    

async def test_edge_cases():
    """Test edge cases and error handling."""
    
    print("\n" + "="*60)
    print("🧪 TESTING EDGE CASES")
    print("="*60)
    
    # Test with no saved meals
    print("\n1️⃣ Testing with no saved meals...")
    empty_session = get_or_create_session("empty-session")
    result = await analyze_saved_meals("empty-session", "total calories?")
    print(f"   Result: {result['message']}")
    
    # Test invalid meal number
    print("\n2️⃣ Testing invalid meal number...")
    result = await save_meal_to_session("empty-session", 10)
    print(f"   Result: {result['message']}")
    
    # Test without current batch
    print("\n3️⃣ Testing save without current batch...")
    result = await save_meal_to_session("no-batch-session", 1)
    print(f"   Result: {result['message']}")
    
    print("\n" + "="*60)
    print("✅ EDGE CASE TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    print("\n🚀 Starting Session Feature Tests...")
    
    # Run main tests
    asyncio.run(test_session_features())
    
    # Run edge case tests
    asyncio.run(test_edge_cases())
    
    print("\n✨ All tests completed!")