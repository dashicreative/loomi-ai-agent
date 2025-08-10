#!/usr/bin/env python3
"""
Test the direct processor week view directly
"""

import asyncio
from datetime import date
from dotenv import load_dotenv
load_dotenv()

from models.ai_models import ChatMessage
from storage.local_storage import LocalStorage
from ai_agents.meal_scheduling_agent.processors.direct_processor import DirectProcessor
from ai_agents.meal_scheduling_agent.core.llm_intent_processor import IntentType, LLMRequestContext


async def test_direct_week_view():
    """Test week view directly"""
    
    storage = LocalStorage()
    processor = DirectProcessor(storage)
    
    # Create a mock context for week view
    context = LLMRequestContext(
        intent_type=IntentType.VIEW_SCHEDULE,
        confidence=0.9,
        complexity="simple",
        entities={
            "temporal_references": ["week"],
            "dates": [],
            "meal_names": [],
            "meal_types": []
        },
        needs_clarification=False
    )
    
    print("Testing _direct_view_schedule with week temporal reference...")
    
    try:
        result = await processor._direct_view_schedule(context)
        print(f"Success! Response:\n{result.conversational_response}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_direct_week_view())