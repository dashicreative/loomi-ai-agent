#!/usr/bin/env python3
"""
DELETE_LATER: LLM Intent Processor validation test

Quick validation script to test the new LLMIntentProcessor against
the baseline scenarios from the existing components.

Usage: python tests/DELETE_LATER_llm_processor_test.py
"""

import asyncio
import os
import sys
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/Users/agustin/Desktop/loomi_ai_agent/.env')

# Add project root to path
sys.path.append('/Users/agustin/Desktop/loomi_ai_agent')

# Import the new LLM processor
from ai_agents.meal_scheduling_agent.core.llm_intent_processor import (
    LLMIntentProcessor, 
    LLMIntentProcessorTester,
    LLMRequestContext
)

# Import existing components for comparison
from ai_agents.meal_scheduling_agent.core.intent_classifier import IntentType


class MockLLMIntentProcessor:
    """Mock processor that uses fallback logic only"""
    
    def __init__(self):
        self.processor = LLMIntentProcessor()
    
    async def understand_request(self, request: str, available_meals: List[str]) -> LLMRequestContext:
        """Use fallback analysis only"""
        return self.processor._fallback_analysis(request, available_meals)

# Test scenarios from baseline tests
TEST_SCENARIOS = [
    {
        "name": "direct_schedule",
        "request": "Schedule pizza for dinner tomorrow", 
        "expected_intent": "direct_schedule",
        "expected_complexity": "simple",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    },
    {
        "name": "batch_schedule",
        "request": "Schedule dinners for the rest of the week",
        "expected_intent": "batch_schedule", 
        "expected_complexity": "complex",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    },
    {
        "name": "clear_schedule",
        "request": "Clear next week's meals",
        "expected_intent": "clear_schedule",
        "expected_complexity": "complex",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    },
    {
        "name": "view_schedule", 
        "request": "What's scheduled for tomorrow",
        "expected_intent": "view_schedule",
        "expected_complexity": "simple",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    },
    {
        "name": "ambiguous_meal",
        "request": "Schedule something for dinner",
        "expected_intent": "ambiguous_schedule",
        "expected_complexity": "complex",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    },
    {
        "name": "minimal_input",
        "request": "yes",
        "expected_intent": "unknown",
        "expected_complexity": "complex",
        "available_meals": ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    }
]


class LLMProcessorValidator:
    """Validate LLM processor against baseline expectations"""
    
    def __init__(self):
        self.processor = None
        self.results = {
            "passed": 0,
            "failed": 0, 
            "errors": 0,
            "details": []
        }
    
    async def setup(self):
        """Initialize the LLM processor"""
        try:
            # Check if we have OpenAI API key
            if not os.getenv("OPENAI_API_KEY"):
                print("⚠️  Warning: No OPENAI_API_KEY found in environment")
                print("   Testing fallback behavior only...")
                self.fallback_mode = True
            else:
                print("✅ OpenAI API key found - testing full LLM functionality")
                self.fallback_mode = False
                
            self.processor = LLMIntentProcessor()
            print("✅ LLM Intent Processor initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize LLM processor: {e}")
            # Try fallback mode
            try:
                self.processor = MockLLMIntentProcessor()
                self.fallback_mode = True
                print("✅ Using fallback processor for testing")
                return True
            except:
                return False
    
    async def run_validation_tests(self) -> Dict[str, Any]:
        """Run all validation tests"""
        if not await self.setup():
            return {"error": "Setup failed"}
        
        print(f"\n🔍 Running {len(TEST_SCENARIOS)} validation scenarios...")
        print("=" * 60)
        
        for i, scenario in enumerate(TEST_SCENARIOS, 1):
            print(f"\n[{i}/{len(TEST_SCENARIOS)}] Testing: {scenario['name']}")
            await self._test_scenario(scenario)
        
        return self.results
    
    async def _test_scenario(self, scenario: Dict[str, Any]):
        """Test a single scenario"""
        try:
            # Call LLM processor
            context = await self.processor.understand_request(
                scenario["request"],
                scenario["available_meals"]
            )
            
            # Check intent classification (compare enum values)
            expected_intent_value = scenario["expected_intent"].lower() if isinstance(scenario["expected_intent"], str) else scenario["expected_intent"]
            intent_match = context.intent_type.value == expected_intent_value
            complexity_match = context.complexity == scenario["expected_complexity"]
            
            # Overall pass/fail
            passed = intent_match and complexity_match
            
            # Record results
            if passed:
                self.results["passed"] += 1
                print(f"   ✅ PASSED")
            else:
                self.results["failed"] += 1
                print(f"   ❌ FAILED")
            
            # Log details
            print(f"      Intent: {context.intent_type.value} (expected: {scenario['expected_intent']}) {'✅' if intent_match else '❌'}")
            print(f"      Complexity: {context.complexity} (expected: {scenario['expected_complexity']}) {'✅' if complexity_match else '❌'}")
            print(f"      Confidence: {context.confidence:.2f}")
            
            if context.needs_clarification:
                print(f"      Clarification: {context.clarification_question}")
            
            if context.entities:
                print(f"      Entities: {context.entities}")
            
            # Store detailed results
            self.results["details"].append({
                "scenario": scenario["name"],
                "request": scenario["request"],
                "expected_intent": scenario["expected_intent"],
                "actual_intent": context.intent_type.value,
                "expected_complexity": scenario["expected_complexity"],
                "actual_complexity": context.complexity,
                "confidence": context.confidence,
                "needs_clarification": context.needs_clarification,
                "entities": context.entities,
                "passed": passed,
                "reasoning": context.reasoning
            })
            
        except Exception as e:
            self.results["errors"] += 1
            print(f"   💥 ERROR: {str(e)}")
            
            self.results["details"].append({
                "scenario": scenario["name"],
                "request": scenario["request"],
                "error": str(e),
                "passed": False
            })
    
    def print_summary(self):
        """Print test summary"""
        total = self.results["passed"] + self.results["failed"] + self.results["errors"]
        
        print("\n" + "=" * 60)
        print("🔍 VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Total scenarios: {total}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"💥 Errors: {self.results['errors']}")
        
        if total > 0:
            success_rate = (self.results["passed"] / total) * 100
            print(f"📊 Success rate: {success_rate:.1f}%")
        
        if self.results["failed"] > 0 or self.results["errors"] > 0:
            print("\n⚠️  ISSUES FOUND:")
            for detail in self.results["details"]:
                if not detail.get("passed", True):
                    print(f"   - {detail['scenario']}: {detail.get('error', 'Failed expectations')}")
        
        # Migration readiness assessment
        if self.results["errors"] == 0 and self.results["failed"] == 0:
            print("\n🎉 ALL TESTS PASSED - Migration ready!")
        elif self.results["errors"] == 0 and self.results["failed"] <= 2:
            print("\n⚠️  Minor issues found - Review before migration")
        else:
            print("\n🛑 Significant issues found - Fix before migration")


async def main():
    """Main test execution"""
    print("🚀 LLM Intent Processor Validation Test")
    print("=====================================")
    print("Testing new LLM processor against baseline expectations...")
    
    validator = LLMProcessorValidator()
    
    try:
        results = await validator.run_validation_tests()
        validator.print_summary()
        
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