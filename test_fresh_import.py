#!/usr/bin/env python3
"""
Test with fresh imports to avoid caching issues
"""

import sys
import asyncio
from datetime import date
from dotenv import load_dotenv
load_dotenv()

# Clear any cached modules
modules_to_clear = [m for m in sys.modules.keys() if 'ai_agents' in m or 'direct_processor' in m]
for module in modules_to_clear:
    del sys.modules[module]

# Now import fresh
from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent.agent import EnhancedMealAgent


async def test_fresh():
    """Test with fresh imports"""
    
    agent = EnhancedMealAgent()
    
    print("=== Testing with Fresh Imports ===")
    print()
    
    # Test the week view query
    print('User: "What\'s my current meal schedule look like for the week?"')
    
    msg = ChatMessage(
        content="What's my current meal schedule look like for the week?",
        user_context={"user_id": "test_user"}
    )
    
    response = await agent.process(msg)
    print(f"Agent: {response.conversational_response}")


if __name__ == "__main__":
    asyncio.run(test_fresh())