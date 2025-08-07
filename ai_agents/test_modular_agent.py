"""
Test the modular meal scheduling agent
"""

import asyncio
from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent import EnhancedMealAgent


async def test_modular_agent():
    """Test the modular agent with various requests"""
    agent = EnhancedMealAgent()
    
    test_cases = [
        # Simple requests
        "Schedule Pizza for tomorrow",
        "Schedule chicken for Tuesday",
        
        # Complex requests
        "Schedule pizza and egg tacos for tomorrow",
        "Schedule breakfast for the next 5 days based on my saved meals",
        "Pick some meals at random to schedule for Friday",
        
        # Ambiguous requests
        "Can you just pick a meal for me",
        "Schedule some meals",
        
        # Error cases
        "Schedule sushi for tomorrow",  # Non-existent meal
    ]
    
    for test_msg in test_cases:
        print(f"\n{'='*60}")
        print(f"🧪 Test: '{test_msg}'")
        print(f"{'='*60}")
        
        message = ChatMessage(content=test_msg, user_context={})
        
        try:
            result = await agent.process(message)
            print(f"📝 Response: {result.conversational_response}")
            print(f"⚡ Actions: {len(result.actions)}")
            if result.actions:
                print(f"   Action details:")
                for i, action in enumerate(result.actions):
                    print(f"   {i+1}. {action.type}: {action.parameters}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    print("Testing Modular Meal Scheduling Agent")
    print("=====================================")
    asyncio.run(test_modular_agent())