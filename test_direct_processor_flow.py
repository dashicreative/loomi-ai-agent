#!/usr/bin/env python3
"""
Test the direct processor flow to see where the week query goes wrong
"""

import asyncio
from dotenv import load_dotenv
load_dotenv()

from models.ai_models import ChatMessage
from ai_agents.meal_scheduling_agent.core.llm_intent_processor import LLMIntentProcessor
from ai_agents.meal_scheduling_agent.processors.direct_processor import DirectProcessor
from storage.local_storage import LocalStorage


async def test_direct_flow():
    """Test the flow through direct processor"""
    
    # Setup
    storage = LocalStorage()
    processor = LLMIntentProcessor()
    direct = DirectProcessor(storage)
    
    # First understand the request
    print("=== Step 1: LLM Intent Understanding ===")
    context = await processor.understand_request(
        "What's my current meal schedule look like for the week?",
        ["Chicken Parmesan", "Lasagna", "Steak Dinner"]
    )
    
    print(f"Intent: {context.intent_type}")
    print(f"Entities: {context.entities}")
    print(f"Temporal refs: {context.entities.get('temporal_references', [])}")
    print()
    
    # Now trace through the direct processor
    print("=== Step 2: Direct Processor Handling ===")
    
    # Check which code path it takes
    temporal_refs = context.entities.get("temporal_references", [])
    print(f"Temporal refs check: {temporal_refs}")
    print(f"Has 'week' in refs: {any('week' in ref.lower() for ref in temporal_refs)}")
    print(f"Has 'month' in refs: {any('month' in ref.lower() for ref in temporal_refs)}")
    
    # Process the message
    msg = ChatMessage(
        content="What's my current meal schedule look like for the week?",
        user_context={"user_id": "test_user"}
    )
    
    try:
        response = await direct.process(
            msg, 
            ["Chicken Parmesan", "Lasagna", "Steak Dinner"],
            user_id="test_user"
        )
        print(f"\nResponse: {response.conversational_response}")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_direct_flow())