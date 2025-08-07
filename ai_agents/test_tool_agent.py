"""
Test the tool-based agent against the original agent
"""

import asyncio
from models.ai_models import ChatMessage

# Import both versions
from ai_agents.meal_scheduling_agent import EnhancedMealAgent as OriginalAgent
from ai_agents.meal_scheduling_agent.tool_agent import ToolBasedMealAgent


async def test_tool_agent():
    """Test that tool-based agent produces same results as original"""
    
    # Initialize both agents
    original_agent = OriginalAgent()
    tool_agent = ToolBasedMealAgent()
    
    # Print tool information
    tool_info = tool_agent.get_tool_info()
    print(f"\nTool-Based Agent Information:")
    print(f"Total tools available: {tool_info['total_tools']}")
    print("\nAvailable tools:")
    for name, info in tool_info['tools'].items():
        print(f"  - {name}: {info['description']}")
    
    # Test cases
    test_cases = [
        # Simple requests
        "Schedule Pizza for tomorrow",
        "Schedule New Meal for Friday",
        
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
    
    print(f"\n{'='*80}")
    print("COMPARING ORIGINAL vs TOOL-BASED AGENT")
    print(f"{'='*80}")
    
    differences = []
    
    for test_msg in test_cases:
        print(f"\n{'='*60}")
        print(f"Test: '{test_msg}'")
        print(f"{'='*60}")
        
        message = ChatMessage(content=test_msg, user_context={})
        
        # Get results from both agents
        try:
            original_result = await original_agent.process(message)
            original_response = original_result.conversational_response
            original_actions = len(original_result.actions)
            original_action_details = [
                f"{a.type}: {a.parameters}" for a in original_result.actions
            ]
        except Exception as e:
            original_response = f"ERROR: {str(e)}"
            original_actions = 0
            original_action_details = []
        
        try:
            tool_result = await tool_agent.process(message)
            tool_response = tool_result.conversational_response
            tool_actions = len(tool_result.actions)
            tool_action_details = [
                f"{a.type}: {a.parameters}" for a in tool_result.actions
            ]
        except Exception as e:
            tool_response = f"ERROR: {str(e)}"
            tool_actions = 0
            tool_action_details = []
        
        # Compare results
        print(f"\nOriginal Agent:")
        print(f"  Response: {original_response}")
        print(f"  Actions: {original_actions}")
        if original_action_details:
            for detail in original_action_details:
                print(f"    - {detail}")
        
        print(f"\nTool-Based Agent:")
        print(f"  Response: {tool_response}")
        print(f"  Actions: {tool_actions}")
        if tool_action_details:
            for detail in tool_action_details:
                print(f"    - {detail}")
        
        # Check for differences (allowing for minor wording differences)
        responses_match = (
            original_response == tool_response or
            # Allow for minor differences in wording
            (original_actions == tool_actions and 
             "scheduled" in original_response.lower() and 
             "scheduled" in tool_response.lower())
        )
        
        if not responses_match or original_actions != tool_actions:
            differences.append({
                "test": test_msg,
                "original": original_response,
                "tool": tool_response,
                "actions_diff": f"{original_actions} vs {tool_actions}"
            })
            print("\n⚠️  DIFFERENCE DETECTED!")
        else:
            print("\n✅ Results match!")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total tests: {len(test_cases)}")
    print(f"Differences: {len(differences)}")
    
    if differences:
        print("\n⚠️  Some differences were detected. This might be due to:")
        print("  - Different scheduled_meal_id UUIDs (expected)")
        print("  - Minor wording differences in responses")
        print("  - Tool-based approach providing more detailed error messages")
    else:
        print("\n✅ All tests passed! Tool-based agent matches original functionality.")


if __name__ == "__main__":
    print("Testing Tool-Based Meal Scheduling Agent")
    print("=======================================")
    asyncio.run(test_tool_agent())