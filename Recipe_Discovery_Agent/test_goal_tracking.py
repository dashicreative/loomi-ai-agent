"""
Test Goal Tracking and Context-Aware Search

This demonstrates:
1. Saving meals via chat command (temporary feature)
2. Calculating nutrition gaps
3. Using "meet my goal" to search with context
"""

import asyncio
from Tools.session_context import get_or_create_session
from Tools.temporary_save_handler import temporary_save_meal_tool
from Tools.saved_meals_analyzer import analyze_saved_meals_tool


async def test_goal_aware_search():
    """Test the complete flow of goal tracking and context-aware search."""
    
    print("\n" + "="*60)
    print("🎯 TESTING GOAL-AWARE SEARCH FLOW")
    print("="*60)
    
    session_id = "test-goal-session"
    session = get_or_create_session(session_id)
    
    # 1. Simulate initial search results
    print("\n1️⃣ Simulating initial recipe search...")
    mock_recipes = [
        {
            "id": 1,
            "title": "Grilled Chicken Breast",
            "sourceUrl": "https://example.com/chicken",
            "nutrition": [
                {"name": "Calories", "value": "165"},
                {"name": "Protein", "value": "31g"},
            ]
        },
        {
            "id": 2,
            "title": "Quinoa Salad",
            "sourceUrl": "https://example.com/quinoa",
            "nutrition": [
                {"name": "Calories", "value": "222"},
                {"name": "Protein", "value": "8g"},
            ]
        },
        {
            "id": 3,
            "title": "Greek Yogurt",
            "sourceUrl": "https://example.com/yogurt",
            "nutrition": [
                {"name": "Calories", "value": "100"},
                {"name": "Protein", "value": "17g"},
            ]
        }
    ]
    
    session.update_current_batch(mock_recipes)
    print(f"   Added {len(mock_recipes)} recipes to current batch")
    
    # 2. Test temporary save command
    print("\n2️⃣ Testing temporary save via chat command...")
    
    # Save meal #1 via chat
    result = await temporary_save_meal_tool(session_id, "save meal #1")
    print(f"   Command: 'save meal #1'")
    print(f"   Result: {result['message']}")
    print(f"   Is temporary: {result.get('_temporary_chat_save', False)}")
    
    # Save meal #3 via chat
    result = await temporary_save_meal_tool(session_id, "save the third one")
    print(f"   Command: 'save the third one'")
    print(f"   Result: {result['message']}")
    
    # 3. Calculate protein gap
    print("\n3️⃣ Calculating nutrition gap...")
    result = await analyze_saved_meals_tool(
        session,
        "I have a 100g protein goal, how much more do I need?",
        None
    )
    print(f"   Query: '100g protein goal'")
    print(f"   Result: {result['message']}")
    print(f"   Gap stored: {session.current_nutrition_gaps}")
    
    # 4. Simulate "meet my goal" request
    print("\n4️⃣ Simulating 'meet my goal' search...")
    print("   User says: 'Find me a healthy snack to meet my protein goal'")
    
    # Agent should extract from context
    protein_gap = session.current_nutrition_gaps.get('protein', 0)
    print(f"   Context retrieved: Need {protein_gap}g more protein")
    
    # Build requirements from context
    requirements = {
        "nutrition": {"protein": {"min": protein_gap}},
        "meal_type": "snack"
    }
    print(f"   Generated requirements: {requirements}")
    
    # This would be the search call
    print(f"   Would search with: query='healthy snack', requirements={requirements}")
    
    # 5. Test other temporary save formats
    print("\n5️⃣ Testing various save command formats...")
    test_commands = [
        "save recipe #2",
        "save #2",
        "save meal 2",
        "save the second one"
    ]
    
    for cmd in test_commands:
        # Check if command would be recognized
        import re
        patterns = [
            r'save\s+meal\s+#?(\d+)',
            r'save\s+recipe\s+#?(\d+)',
            r'save\s+#?(\d+)',
            r'save\s+the\s+(\w+)\s+one',
        ]
        
        matched = False
        for pattern in patterns:
            if re.search(pattern, cmd.lower()):
                matched = True
                break
        
        print(f"   '{cmd}': {'✅ Would work' if matched else '❌ Would not work'}")
    
    print("\n" + "="*60)
    print("✅ GOAL-AWARE SEARCH TEST COMPLETE")
    print("="*60)
    
    # Show final session state
    print("\n📊 Final Session State:")
    print(f"   Saved meals: {len(session.saved_meals)}")
    print(f"   Nutrition gaps: {session.current_nutrition_gaps}")
    print(f"   Can use 'meet my goal': {'protein' in session.current_nutrition_gaps}")


if __name__ == "__main__":
    print("\n🚀 Starting Goal Tracking Tests...")
    asyncio.run(test_goal_aware_search())
    
    print("\n💡 How this works in practice:")
    print("1. User searches and saves meals")
    print("2. User asks: 'I need 100g protein, how much more?'")
    print("3. System stores: gap = 52g protein")
    print("4. User says: 'Find snacks to meet my protein goal'")
    print("5. System searches with: requirements={nutrition: {protein: {min: 52}}}")
    print("\n✨ Context-aware search complete!")