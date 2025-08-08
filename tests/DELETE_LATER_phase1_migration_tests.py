"""
DELETE_LATER: Temporary test suite for Phase 1 migration
==================================================

This test suite ensures no functionality is lost during the architecture
simplification in Phase 1. DELETE after migration is complete.

Tests current behavior of:
- IntentClassifier
- ComplexityDetector  
- AmbiguityDetector
- Response building

Will be used to verify LLM replacements maintain identical functionality.
"""

import pytest
import asyncio
from datetime import date, timedelta
from typing import List, Dict, Any

# Import current system components
from ai_agents.meal_scheduling_agent.core.intent_classifier import IntentClassifier, IntentType
from ai_agents.meal_scheduling_agent.core.complexity_detector import ComplexityDetector
from ai_agents.meal_scheduling_agent.core.ambiguity_detector import AmbiguityDetector
from ai_agents.meal_scheduling_agent.utils.response_utils import ResponseBuilder
from models.ai_models import ChatMessage, AIResponse


class TestCurrentIntentClassification:
    """DELETE_LATER: Test current intent classification behavior"""
    
    @pytest.fixture
    def intent_classifier(self):
        return IntentClassifier()
    
    @pytest.fixture
    def available_meals(self):
        return ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos", "Storage Test Meal"]
    
    @pytest.mark.asyncio
    async def test_direct_schedule_intent(self, intent_classifier, available_meals):
        """Test detection of direct scheduling requests"""
        request = "Schedule pizza for dinner tomorrow"
        intent = await intent_classifier.classify(request, available_meals)
        
        assert intent.type == IntentType.DIRECT_SCHEDULE
        assert intent.confidence >= 0.8
        assert "meal_name" in intent.entities
        assert intent.entities["meal_name"] == "Pizza"
        
    @pytest.mark.asyncio
    async def test_batch_schedule_intent(self, intent_classifier, available_meals):
        """Test detection of batch scheduling requests"""
        request = "Schedule dinners for the rest of the week"
        intent = await intent_classifier.classify(request, available_meals)
        
        assert intent.type == IntentType.BATCH_SCHEDULE
        assert intent.confidence >= 0.7
        
    @pytest.mark.asyncio
    async def test_clear_schedule_intent(self, intent_classifier, available_meals):
        """Test detection of clear schedule requests"""
        request = "Clear next week's meals"
        intent = await intent_classifier.classify(request, available_meals)
        
        assert intent.type == IntentType.CLEAR_SCHEDULE
        assert intent.confidence >= 0.8
        
    @pytest.mark.asyncio
    async def test_ambiguous_intent(self, intent_classifier, available_meals):
        """Test detection of ambiguous requests"""
        request = "yes"
        intent = await intent_classifier.classify(request, available_meals)
        
        assert intent.type in [IntentType.AMBIGUOUS_SCHEDULE, IntentType.UNKNOWN]
        assert intent.confidence < 0.5


class TestCurrentComplexityDetection:
    """DELETE_LATER: Test current complexity detection behavior"""
    
    @pytest.fixture
    def complexity_detector(self):
        return ComplexityDetector()
    
    @pytest.fixture
    def available_meals(self):
        return ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    
    @pytest.mark.asyncio
    async def test_simple_request_detection(self, complexity_detector, available_meals):
        """Test simple request classification"""
        request = "Schedule pizza for dinner tomorrow"
        complexity = await complexity_detector.detect(request, available_meals)
        
        assert complexity == "simple"
        
    @pytest.mark.asyncio
    async def test_complex_request_detection(self, complexity_detector, available_meals):
        """Test complex request classification"""
        request = "Schedule dinners for the rest of the week"
        complexity = await complexity_detector.detect(request, available_meals)
        
        assert complexity == "complex"
        
    @pytest.mark.asyncio
    async def test_clear_request_complexity(self, complexity_detector, available_meals):
        """Test clear requests are marked as complex"""
        request = "Clear next week's schedule"
        complexity = await complexity_detector.detect(request, available_meals)
        
        assert complexity == "complex"


class TestCurrentAmbiguityDetection:
    """DELETE_LATER: Test current ambiguity detection behavior"""
    
    @pytest.fixture
    def ambiguity_detector(self):
        return AmbiguityDetector()
    
    @pytest.fixture
    def available_meals(self):
        return ["Pizza", "Chicken Parmesan", "Potato salad"]
    
    def test_unambiguous_request(self, ambiguity_detector, available_meals):
        """Test clear, unambiguous request"""
        request = "Schedule pizza for dinner tomorrow"
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        
        assert not ambiguity_info["is_ambiguous"]
        assert ambiguity_info["confidence"] >= 0.8
        
    def test_ambiguous_meal_request(self, ambiguity_detector, available_meals):
        """Test request with unclear meal reference"""
        request = "Schedule something for dinner"
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        
        assert ambiguity_info["is_ambiguous"]
        assert "meal" in ambiguity_info["missing_info"]
        
    def test_ambiguous_date_request(self, ambiguity_detector, available_meals):
        """Test request with unclear date reference"""
        request = "Schedule pizza sometime"
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        
        assert ambiguity_info["is_ambiguous"]
        assert "date" in ambiguity_info["missing_info"]
        
    def test_clarification_generation(self, ambiguity_detector, available_meals):
        """Test clarification message generation"""
        request = "Schedule something"
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        clarification = ambiguity_detector.generate_clarification_response(ambiguity_info, request)
        
        assert isinstance(clarification, str)
        assert len(clarification) > 0
        assert "?" in clarification  # Should be asking a question


class TestCurrentResponseBuilding:
    """DELETE_LATER: Test current response building behavior"""
    
    @pytest.fixture
    def response_builder(self):
        return ResponseBuilder()
    
    def test_success_response(self, response_builder):
        """Test success response generation"""
        response = response_builder.success_response(
            meal_name="Pizza",
            target_date="2025-08-10", 
            meal_type="dinner"
        )
        
        assert isinstance(response, AIResponse)
        assert "Pizza" in response.conversational_response
        assert "dinner" in response.conversational_response
        assert len(response.actions) == 1
        assert response.actions[0].type.value == "schedule_meal"
        
    def test_error_response(self, response_builder):
        """Test error response generation"""
        error_msg = "Test error message"
        response = response_builder.error_response(error_msg)
        
        assert isinstance(response, AIResponse)
        assert error_msg in response.conversational_response
        assert len(response.actions) == 0
        
    def test_no_meals_error(self, response_builder):
        """Test no meals available error"""
        response = response_builder.no_meals_error()
        
        assert isinstance(response, AIResponse)
        assert "no saved meals" in response.conversational_response.lower()
        assert len(response.actions) == 0
        
    def test_clarification_response(self, response_builder):
        """Test clarification response generation"""
        clarification_msg = "What meal would you like to schedule?"
        response = response_builder.clarification_response(clarification_msg)
        
        assert isinstance(response, AIResponse)
        assert clarification_msg in response.conversational_response
        assert len(response.actions) == 0


class TestCurrentSystemIntegration:
    """DELETE_LATER: Test current system integration behavior"""
    
    @pytest.fixture
    def available_meals(self):
        return ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos"]
    
    @pytest.mark.asyncio
    async def test_simple_to_complex_flow(self, available_meals):
        """Test flow from complexity detection to intent classification"""
        complexity_detector = ComplexityDetector()
        intent_classifier = IntentClassifier()
        
        # Test simple request
        simple_request = "Schedule pizza for dinner tomorrow"
        complexity = await complexity_detector.detect(simple_request, available_meals)
        assert complexity == "simple"
        
        # Verify intent classification still works
        intent = await intent_classifier.classify(simple_request, available_meals)
        assert intent.type == IntentType.DIRECT_SCHEDULE
        
        # Test complex request  
        complex_request = "Schedule dinners for the rest of the week"
        complexity = await complexity_detector.detect(complex_request, available_meals)
        assert complexity == "complex"
        
        # Verify intent classification
        intent = await intent_classifier.classify(complex_request, available_meals)
        assert intent.type == IntentType.BATCH_SCHEDULE
        
    def test_ambiguity_to_response_flow(self, available_meals):
        """Test flow from ambiguity detection to response building"""
        ambiguity_detector = AmbiguityDetector()
        response_builder = ResponseBuilder()
        
        # Create ambiguous request
        request = "Schedule something"
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        assert ambiguity_info["is_ambiguous"]
        
        # Generate clarification
        clarification = ambiguity_detector.generate_clarification_response(ambiguity_info, request)
        
        # Build response
        response = response_builder.clarification_response(clarification)
        assert isinstance(response, AIResponse)
        assert clarification in response.conversational_response


# Test data for validation
TEST_SCENARIOS = [
    {
        "name": "direct_schedule",
        "request": "Schedule pizza for dinner tomorrow",
        "expected_complexity": "simple",
        "expected_intent": IntentType.DIRECT_SCHEDULE,
        "expected_ambiguous": False
    },
    {
        "name": "batch_schedule", 
        "request": "Schedule dinners for the rest of the week",
        "expected_complexity": "complex",
        "expected_intent": IntentType.BATCH_SCHEDULE,
        "expected_ambiguous": False
    },
    {
        "name": "clear_schedule",
        "request": "Clear next week's meals",
        "expected_complexity": "complex", 
        "expected_intent": IntentType.CLEAR_SCHEDULE,
        "expected_ambiguous": False
    },
    {
        "name": "ambiguous_meal",
        "request": "Schedule something for dinner",
        "expected_complexity": "complex",
        "expected_intent": IntentType.AMBIGUOUS_SCHEDULE,
        "expected_ambiguous": True
    },
    {
        "name": "view_schedule",
        "request": "What's scheduled for tomorrow",
        "expected_complexity": "simple",
        "expected_intent": IntentType.VIEW_SCHEDULE,
        "expected_ambiguous": False
    }
]


class TestCurrentSystemBehaviorBaseline:
    """DELETE_LATER: Comprehensive baseline tests for all scenarios"""
    
    @pytest.fixture
    def available_meals(self):
        return ["Pizza", "Chicken Parmesan", "Potato salad", "Egg Tacos", "Storage Test Meal"]
    
    @pytest.mark.parametrize("scenario", TEST_SCENARIOS)
    @pytest.mark.asyncio
    async def test_scenario_baseline(self, scenario, available_meals):
        """Test baseline behavior for all scenarios"""
        complexity_detector = ComplexityDetector()
        intent_classifier = IntentClassifier() 
        ambiguity_detector = AmbiguityDetector()
        
        request = scenario["request"]
        
        # Test complexity detection
        complexity = await complexity_detector.detect(request, available_meals)
        assert complexity == scenario["expected_complexity"], f"Complexity mismatch for {scenario['name']}"
        
        # Test intent classification
        intent = await intent_classifier.classify(request, available_meals)
        assert intent.type == scenario["expected_intent"], f"Intent mismatch for {scenario['name']}"
        
        # Test ambiguity detection
        ambiguity_info = ambiguity_detector.detect_ambiguity(request, available_meals)
        assert ambiguity_info["is_ambiguous"] == scenario["expected_ambiguous"], f"Ambiguity mismatch for {scenario['name']}"


if __name__ == "__main__":
    print("DELETE_LATER: Running baseline tests for Phase 1 migration...")
    pytest.main([__file__, "-v"])