"""
Test the fix for "Unknown" meal and performance optimization
"""

import asyncio
import time
from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent import EnhancedMealAgent


async def test_chicken_fix():
    """Test that chicken dish request works properly"""
    agent = EnhancedMealAgent()
    
    # Test case that was failing
    test_msg = "Schedule me a chicken dish tomorrow"
    
    print(f"Testing: '{test_msg}'")
    print("-" * 50)
    
    message = ChatMessage(content=test_msg, user_context={})
    
    # Time the response
    start_time = time.time()
    result = await agent.process(message)
    end_time = time.time()
    
    print(f"Response: {result.conversational_response}")
    print(f"Response time: {end_time - start_time:.2f} seconds")
    print(f"Actions: {len(result.actions)}")
    
    # Check that response doesn't contain "Unknown"
    if "Unknown" in result.conversational_response:
        print("❌ FAILED: Response still contains 'Unknown'")
    else:
        print("✅ PASSED: No 'Unknown' in response")
    
    # Check performance
    if end_time - start_time < 5:
        print(f"✅ PASSED: Response time under 5 seconds")
    else:
        print(f"⚠️  WARNING: Response time over 5 seconds")


if __name__ == "__main__":
    asyncio.run(test_chicken_fix())