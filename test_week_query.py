#!/usr/bin/env python3
"""
Test the specific query that's returning "No meals scheduled for today"
"""

import asyncio
from dotenv import load_dotenv
load_dotenv()

from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent.agent import EnhancedMealAgent


async def test_week_query():
    """Test the exact query that's causing issues"""
    
    agent = EnhancedMealAgent()
    
    print("=== Testing Week View Query ===")
    print()
    
    # First, let's schedule some meals for testing
    print("Setting up test data...")
    
    # Schedule a meal for today
    msg1 = ChatMessage(
        content="Schedule chicken parmesan for dinner today",
        user_context={"user_id": "test_user"}
    )
    response1 = await agent.process(msg1)
    print(f"Setup: {response1.conversational_response}")
    print()
    
    # Now test the exact problematic query
    print("Testing the problematic query:")
    print('User: "What\'s my current meal schedule look like for the week?"')
    
    msg = ChatMessage(
        content="What's my current meal schedule look like for the week?",
        user_context={"user_id": "test_user"}
    )
    
    response = await agent.process(msg)
    print(f"Agent: {response.conversational_response}")
    print()
    
    # Let's also check what the LLM intent processor is understanding
    from ai_agents.meal_scheduling_agent.core.llm_intent_processor import LLMIntentProcessor
    
    processor = LLMIntentProcessor()
    
    print("\n=== Checking LLM Intent Understanding ===")
    context = await processor.understand_request(
        "What's my current meal schedule look like for the week?",
        ["Chicken Parmesan", "Lasagna", "Steak Dinner"]
    )
    
    print(f"Intent Type: {context.intent_type.value}")
    print(f"Entities: {context.entities}")
    print(f"Temporal References: {context.entities.get('temporal_references', [])}")
    print(f"Dates: {context.entities.get('dates', [])}")
    print(f"Needs Clarification: {context.needs_clarification}")
    print(f"Reasoning: {context.reasoning}")


if __name__ == "__main__":
    asyncio.run(test_week_query())