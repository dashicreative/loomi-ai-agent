from fastapi import APIRouter, HTTPException, status
from typing import Optional

from models.ai_models import ChatMessage, ChatResponse, AIAction
from services.llm_service import llm_service

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Process a chat message from the iOS app.
    For now, returns echo responses for testing.
    """
    try:
        # Echo response for testing Step 5
        echo_response = ChatResponse(
            conversational_response=f"Echo: {message.content}",
            actions=[],
            model_used="echo"
        )
        
        return echo_response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(e)}"
        )


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