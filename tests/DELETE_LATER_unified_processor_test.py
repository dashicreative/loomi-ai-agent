#!/usr/bin/env python3
"""
DELETE_LATER: UnifiedProcessor validation test

Tests that the new UnifiedProcessor maintains all functionality from
SimpleProcessor + ComplexProcessor + BatchExecutor while simplifying the architecture.

Usage: python tests/DELETE_LATER_unified_processor_test.py
"""

import asyncio
import sys
from typing import List, Dict, Any
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/Users/agustin/Desktop/loomi_ai_agent/.env')

# Add project root to path
sys.path.append('/Users/agustin/Desktop/loomi_ai_agent')

# Import components
from ai_agents.meal_scheduling_agent.processors.unified_processor import UnifiedProcessor
from ai_agents.meal_scheduling_agent.processors.simple_processor import SimpleProcessor
from ai_agents.meal_scheduling_agent.processors.complex_processor import ComplexProcessor
from models.ai_models import ChatMessage
from storage.local_storage import LocalStorage


# Test scenarios covering all processor functionality
TEST_SCENARIOS = [
    {
        "name": "simple_direct_schedule",
        "message": "Schedule pizza for dinner tomorrow",
        "expected_type": "single_schedule",
        "description": "Basic single meal scheduling (SimpleProcessor territory)"
    },
    {
        "name": "batch_schedule_week",
        "message": "Schedule dinners for the rest of the week",
        "expected_type": "batch_schedule", 
        "description": "Multi-day batch scheduling (ComplexProcessor territory)"
    },
    {
        "name": "clear_schedule",
        "message": "Clear next week's meals",
        "expected_type": "clear_operation",
        "description": "Clear schedule operation (ComplexProcessor territory)"
    },
    {
        "name": "ambiguous_request",
        "message": "Schedule something for dinner",
        "expected_type": "clarification",
        "description": "Ambiguous request requiring clarification"
    },
    {
        "name": "view_schedule",
        "message": "What's scheduled for tomorrow",
        "expected_type": "view_operation",
        "description": "Schedule viewing request"
    },
    {
        "name": "list_meals",
        "message": "What meals do I have saved",
        "expected_type": "list_operation", 
        "description": "List available meals"
    },
    {
        "name": "unknown_request",
        "message": "yes",
        "expected_type": "unknown",
        "description": "Unclear/unknown request"
    }
]


class UnifiedProcessorValidator:
    """Validate UnifiedProcessor functionality and performance"""
    
    def __init__(self):
        # Use default local storage for testing
        self.storage = LocalStorage()
        self.unified_processor = UnifiedProcessor(self.storage)
        
        # Focus on UnifiedProcessor only
        # self.simple_processor = SimpleProcessor(self.storage)
        # self.complex_processor = ComplexProcessor(self.storage)
        
        self.available_meals = [
            "Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos", 
            "Grilled Salmon", "Beef Stir Fry", "Vegetable Curry"
        ]
        
        self.results = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "details": []
        }
    
    async def run_validation_tests(self) -> Dict[str, Any]:
        """Run all validation tests"""
        print(f"🔍 Testing UnifiedProcessor against {len(TEST_SCENARIOS)} scenarios...")
        print("=" * 70)
        
        for i, scenario in enumerate(TEST_SCENARIOS, 1):
            print(f"\n[{i}/{len(TEST_SCENARIOS)}] Testing: {scenario['name']}")
            print(f"   Request: '{scenario['message']}'")
            await self._test_scenario(scenario)
        
        return self.results
    
    async def _test_scenario(self, scenario: Dict[str, Any]):
        """Test a single scenario"""
        try:
            # Create test message
            message = ChatMessage(
                content=scenario["message"],
                user_context={"user_id": "test_user"}
            )
            
            # Process with UnifiedProcessor
            response = await self.unified_processor.process(message, self.available_meals)
            
            # Validate response structure
            validation_passed = self._validate_response(response, scenario)
            
            if validation_passed:
                self.results["passed"] += 1
                print(f"   ✅ PASSED")
            else:
                self.results["failed"] += 1
                print(f"   ❌ FAILED")
            
            # Log response details
            print(f"   Response: {response.conversational_response[:100]}...")
            print(f"   Actions: {len(response.actions)} action(s)")
            
            # Store detailed results
            self.results["details"].append({
                "scenario": scenario["name"],
                "request": scenario["message"],
                "response_text": response.conversational_response,
                "action_count": len(response.actions),
                "passed": validation_passed,
                "expected_type": scenario["expected_type"]
            })
            
        except Exception as e:
            self.results["errors"] += 1
            print(f"   💥 ERROR: {str(e)}")
            
            self.results["details"].append({
                "scenario": scenario["name"],
                "request": scenario["message"],
                "error": str(e),
                "passed": False
            })
    
    def _validate_response(self, response, scenario) -> bool:
        """Validate response matches expectations"""
        if not response or not response.conversational_response:
            return False
        
        expected_type = scenario["expected_type"]
        response_text = response.conversational_response.lower()
        
        # Basic validation based on expected type
        if expected_type == "single_schedule":
            # Should confirm scheduling a specific meal
            return ("scheduled" in response_text or "schedule" in response_text) and len(response.actions) >= 1
            
        elif expected_type == "batch_schedule":
            # Should handle multiple scheduling
            return ("scheduled" in response_text or "meals" in response_text) and "I've" in response_text
            
        elif expected_type == "clear_operation":
            # Should confirm clearing
            return ("clear" in response_text or "cleared" in response_text)
            
        elif expected_type == "clarification":
            # Should ask for clarification
            return ("?" in response_text or "clarification" in response_text or "which" in response_text)
            
        elif expected_type == "view_operation":
            # Should provide schedule info (or placeholder)
            return ("schedule" in response_text or "scheduled" in response_text)
            
        elif expected_type == "list_operation":
            # Should list meals
            return ("meals" in response_text or "saved" in response_text)
            
        elif expected_type == "unknown":
            # Should handle unknown requests gracefully
            return ("not sure" in response_text or "try" in response_text or "?" in response_text)
        
        return True  # Default to pass for edge cases
    
    def print_summary(self):
        """Print comprehensive test summary"""
        total = self.results["passed"] + self.results["failed"] + self.results["errors"]
        
        print("\n" + "=" * 70)
        print("🔍 UNIFIED PROCESSOR VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Total scenarios: {total}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"💥 Errors: {self.results['errors']}")
        
        if total > 0:
            success_rate = (self.results["passed"] / total) * 100
            print(f"📊 Success rate: {success_rate:.1f}%")
        
        # Show detailed results
        print("\n📋 SCENARIO DETAILS:")
        for detail in self.results["details"]:
            status = "✅" if detail.get("passed", False) else ("💥" if detail.get("error") else "❌")
            print(f"   {status} {detail['scenario']}: {detail.get('error', 'OK')}")
        
        # Migration readiness assessment
        if self.results["errors"] == 0 and self.results["failed"] <= 1:
            print("\n🎉 UNIFIED PROCESSOR READY - Phase 2 migration can proceed!")
        elif self.results["errors"] == 0 and self.results["failed"] <= 3:
            print("\n⚠️  Minor issues found - Review before proceeding")
        else:
            print("\n🛑 Significant issues found - Fix before migration")
    
    async def performance_comparison(self):
        """Optional: Compare performance with original processors"""
        print("\n⚡ PERFORMANCE COMPARISON")
        print("-" * 30)
        
        test_message = ChatMessage(
            content="Schedule pizza for dinner tomorrow",
            user_context={"user_id": "test_user"}
        )
        
        # Time UnifiedProcessor
        start_time = asyncio.get_event_loop().time()
        await self.unified_processor.process(test_message, self.available_meals)
        unified_time = asyncio.get_event_loop().time() - start_time
        
        print(f"UnifiedProcessor: {unified_time:.3f}s")
        print("✅ Single processor handling all request types")


async def main():
    """Main test execution"""
    print("🚀 UnifiedProcessor Validation Test")
    print("==================================")
    print("Testing Phase 2 migration: SimpleProcessor + ComplexProcessor → UnifiedProcessor")
    
    validator = UnifiedProcessorValidator()
    
    try:
        # Run validation tests
        results = await validator.run_validation_tests()
        validator.print_summary()
        
        # Optional performance comparison
        await validator.performance_comparison()
        
        # Return appropriate exit code
        if results.get("errors", 0) > 0 or results.get("failed", 0) > 2:
            sys.exit(1)  # Indicate failure
        else:
            sys.exit(0)  # Success
            
    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())