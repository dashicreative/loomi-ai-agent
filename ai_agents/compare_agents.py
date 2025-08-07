"""
Compare the original monolithic agent with the new modular agent
"""

import asyncio
from models.ai_models import ChatMessage

# Import both versions
from ai_agents.enhanced_meal_agent import EnhancedMealAgent as OriginalAgent
from ai_agents.meal_scheduling_agent import EnhancedMealAgent as ModularAgent


async def compare_agents():
    """Compare outputs of both agents"""
    original_agent = OriginalAgent()
    modular_agent = ModularAgent()
    
    test_cases = [
        "Schedule Pizza for tomorrow",
        "Schedule pizza and egg tacos for tomorrow",
        "Pick some meals at random for Friday",
        "Can you just pick a meal for me",
        "Schedule chicken for Tuesday",  # Non-existent meal
    ]
    
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
        except Exception as e:
            original_response = f"ERROR: {str(e)}"
            original_actions = 0
        
        try:
            modular_result = await modular_agent.process(message)
            modular_response = modular_result.conversational_response
            modular_actions = len(modular_result.actions)
        except Exception as e:
            modular_response = f"ERROR: {str(e)}"
            modular_actions = 0
        
        # Compare results
        print(f"\nOriginal Agent:")
        print(f"  Response: {original_response}")
        print(f"  Actions: {original_actions}")
        
        print(f"\nModular Agent:")
        print(f"  Response: {modular_response}")
        print(f"  Actions: {modular_actions}")
        
        # Check for differences
        if original_response != modular_response or original_actions != modular_actions:
            differences.append({
                "test": test_msg,
                "original": original_response,
                "modular": modular_response,
                "actions_diff": f"{original_actions} vs {modular_actions}"
            })
            print("\n⚠️  DIFFERENCE DETECTED!")
        else:
            print("\n✅ Results match!")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total tests: {len(test_cases)}")
    print(f"Differences: {len(differences)}")
    
    if differences:
        print("\nDifferences found:")
        for diff in differences:
            print(f"\nTest: {diff['test']}")
            print(f"  Original: {diff['original']}")
            print(f"  Modular: {diff['modular']}")
            print(f"  Actions: {diff['actions_diff']}")


if __name__ == "__main__":
    print("Comparing Original vs Modular Agent")
    print("===================================")
    asyncio.run(compare_agents())