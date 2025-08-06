import asyncio
from ai_agents.enhanced_meal_agent import EnhancedMealAgent
from models.ai_models import ChatMessage

async def test_conversation_flow():
    agent = EnhancedMealAgent()
    
    # Test the exact problematic request
    test_request = "how about you pick a meal and schedule it for me"
    print(f"🧪 Testing: '{test_request}'")
    
    # Debug what the ambiguity detection sees
    available_meals = ["Pizza", "Egg Tacos", "New Meal", "Storage Test Meal", "Potato salad"]
    ambiguity_info = agent._detect_ambiguity(test_request, available_meals)
    
    print(f"Ambiguity Analysis:")
    print(f"  Is ambiguous: {ambiguity_info['is_ambiguous']}")
    print(f"  Has specific quantity: {ambiguity_info['has_specific_quantity']}")
    print(f"  Has vague quantity: {ambiguity_info['has_vague_quantity']}")
    print(f"  Has timeframe: {ambiguity_info['has_timeframe']}")
    print(f"  Missing elements: {ambiguity_info['missing']}")
    
    if ambiguity_info['is_ambiguous']:
        clarification = agent._generate_clarification_response(ambiguity_info, test_request)
        print(f"  Should ask: '{clarification}'")
    
    # Test actual response
    print(f"\nActual Agent Response:")
    message = ChatMessage(content=test_request, user_context={})
    result = await agent.process(message)
    print(f"  Response: '{result.conversational_response}'")
    print(f"  Actions: {len(result.actions)}")

if __name__ == "__main__":
    asyncio.run(test_conversation_flow())