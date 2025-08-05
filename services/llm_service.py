from typing import Optional
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config.settings import settings


class LLMService:
    """Service for managing LLM connections and interactions"""
    
    def __init__(self):
        """Initialize LLM clients with API keys from settings"""
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Initialize Claude (Anthropic)
        self.claude = ChatAnthropic(
            anthropic_api_key=settings.anthropic_api_key,
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            max_tokens=1000
        )
        
        # Initialize GPT-4 (OpenAI)
        self.gpt4 = ChatOpenAI(
            openai_api_key=settings.openai_api_key,
            model="gpt-4-turbo-preview",
            temperature=0.7,
            max_tokens=1000
        )
    
    async def test_claude(self, message: str = "Hello") -> str:
        """Test Claude connection"""
        try:
            response = await self.claude.ainvoke([HumanMessage(content=message)])
            return response.content
        except Exception as e:
            raise Exception(f"Claude test failed: {str(e)}")
    
    async def test_gpt4(self, message: str = "Hello") -> str:
        """Test GPT-4 connection"""
        try:
            response = await self.gpt4.ainvoke([HumanMessage(content=message)])
            return response.content
        except Exception as e:
            raise Exception(f"GPT-4 test failed: {str(e)}")


# Create singleton instance
llm_service = LLMService()