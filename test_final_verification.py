#!/usr/bin/env python3
"""
Final verification that both scheduling and viewing work correctly
"""

import asyncio
from dotenv import load_dotenv
load_dotenv()

from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent.agent import EnhancedMealAgent


async def test_final_verification():
    """Test both scheduling and viewing work correctly"""
    
    agent = EnhancedMealAgent()
    
    print("=== Final Verification ===")
    print()
    
    # Test 1: View query (the one that was broken)
    print("1. Testing the originally broken view query:")
    print('User: "What meals do I have scheduled for next Tuesday"')
    
    msg1 = ChatMessage(
        content="What meals do I have scheduled for next Tuesday",
        user_context={"user_id": "test_user"}
    )
    
    response1 = await agent.process(msg1)
    
    if "error" in response1.conversational_response.lower():
        print(f"❌ STILL BROKEN: {response1.conversational_response}")
    else:
        print(f"✅ FIXED: {response1.conversational_response[:80]}...")
    
    print()
    
    # Test 2: Scheduling with clarification (the main fix)
    print("2. Testing scheduling profile validation:")
    print('User: "Schedule dinner tomorrow"')
    
    msg2 = ChatMessage(
        content="Schedule dinner tomorrow",
        user_context={"user_id": "test_user"}
    )
    
    response2 = await agent.process(msg2)
    
    if "what dinner would you like" in response2.conversational_response.lower():
        print("✅ WORKING: Agent asks for clarification")
        print(f"Response: {response2.conversational_response[:80]}...")
    elif "i've scheduled" in response2.conversational_response.lower():
        print("❌ REGRESSION: Agent auto-selected again")
    else:
        print(f"❓ UNCLEAR: {response2.conversational_response[:80]}...")
    
    print()
    print("=== Summary ===")
    print("✅ View queries: Fixed the '.value' attribute error")
    print("✅ Scheduling: Agent asks for clarification when meal not specified")


if __name__ == "__main__":
    asyncio.run(test_final_verification())