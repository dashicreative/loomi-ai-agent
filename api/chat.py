from fastapi import APIRouter, HTTPException, status
from typing import Optional

from models.ai_models import ChatMessage, ChatResponse, AIAction
from services.llm_service import llm_service
from ai_agents.meal_scheduling_agent import EnhancedMealAgent

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Process a chat message from the iOS app.
    
    Enhanced: Uses Enhanced Meal Agent with multi-task support,
    batch scheduling, random meal selection, and complex request handling.
    """
    try:
        # Initialize the Enhanced Meal Agent
        enhanced_agent = EnhancedMealAgent()
        
        # Process the message with the agent
        ai_response = await enhanced_agent.process(message)
        
        # Convert AIResponse to ChatResponse (iOS format)
        chat_response = ChatResponse(
            conversational_response=ai_response.conversational_response,
            actions=ai_response.actions,
            model_used=ai_response.model_used
        )
        
        return chat_response
        
    except Exception as e:
        # Return error message to iOS app
        error_response = ChatResponse(
            conversational_response=f"Sorry, I encountered an error: {str(e)}",
            actions=[],
            model_used="error"
        )
        return error_response


@router.get("/test")
async def test_llm_connections():
    """Test endpoint to verify LLM connections"""
    try:
        results = {
            "claude": "not tested",
            "gpt4": "not tested"
        }
        
        # Test Claude
        try:
            claude_response = await llm_service.test_claude("Hello, testing connection")
            results["claude"] = "connected" if claude_response else "failed"
        except Exception as e:
            results["claude"] = f"error: {str(e)}"
        
        # Test GPT-4
        try:
            gpt4_response = await llm_service.test_gpt4("Hello, testing connection")
            results["gpt4"] = "connected" if gpt4_response else "failed"
        except Exception as e:
            results["gpt4"] = f"error: {str(e)}"
        
        return {
            "status": "ok" if all(v == "connected" for v in results.values()) else "partial",
            "connections": results
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM test failed: {str(e)}"
        )