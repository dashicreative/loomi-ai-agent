#!/usr/bin/env python3
"""
Test week view with a clean schedule
"""

import asyncio
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent.agent import EnhancedMealAgent
from storage.local_storage import LocalStorage


async def test_week_view_clean():
    """Test week view with a fresh schedule"""
    
    # Clear any existing schedule first
    storage = LocalStorage()
    storage.clear_schedule(date_range="month")
    
    agent = EnhancedMealAgent()
    
    print("=== Testing Week View with Fresh Data ===")
    print()
    
    # Schedule some meals throughout the week
    print("Setting up test data for the week...")
    
    # Schedule for today (Sunday)
    msg1 = ChatMessage(
        content="Schedule chicken parmesan for dinner today",
        user_context={"user_id": "test_user"}
    )
    response1 = await agent.process(msg1)
    print(f"✓ {response1.conversational_response.split('.')[0]}")
    
    # Schedule for tomorrow (Monday)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%A")
    msg2 = ChatMessage(
        content=f"Schedule lasagna for lunch {tomorrow}",
        user_context={"user_id": "test_user"}
    )
    response2 = await agent.process(msg2)
    print(f"✓ {response2.conversational_response.split('!')[0]}!")
    
    # Schedule for Wednesday
    msg3 = ChatMessage(
        content="Schedule steak dinner for Wednesday dinner",
        user_context={"user_id": "test_user"}
    )
    response3 = await agent.process(msg3)
    print(f"✓ {response3.conversational_response.split('!')[0]}!")
    
    print("\n" + "="*50 + "\n")
    
    # Now test the week view
    print("Testing week view query:")
    print('User: "What\'s my current meal schedule look like for the week?"')
    print()
    
    msg = ChatMessage(
        content="What's my current meal schedule look like for the week?",
        user_context={"user_id": "test_user"}
    )
    
    response = await agent.process(msg)
    print(f"Agent: {response.conversational_response}")


if __name__ == "__main__":
    asyncio.run(test_week_view_clean())