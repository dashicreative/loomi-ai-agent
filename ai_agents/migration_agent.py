"""
Migration agent for gradual transition from monolithic to LangChain architecture
"""

import os
from typing import Optional
from models.ai_models import ChatMessage, AIResponse
from .enhanced_meal_agent import EnhancedMealAgent
from .langchain_meal_agent import LangChainMealAgent


class MigrationAgent:
    """
    Wrapper agent that allows gradual migration from old to new implementation
    with feature flags and fallback support
    """
    
    def __init__(self):
        # Initialize both agents
        self.old_agent = EnhancedMealAgent()
        self.new_agent = LangChainMealAgent()
        
        # Feature flags - can be controlled via environment variables
        self.use_new_agent = os.getenv("USE_LANGCHAIN_AGENT", "false").lower() == "true"
        self.fallback_enabled = os.getenv("ENABLE_FALLBACK", "true").lower() == "true"
        
        # Track which agent is being used
        self.last_used_agent = None
    
    async def process(self, message: ChatMessage) -> AIResponse:
        """
        Process message with migration logic
        """
        if self.use_new_agent:
            try:
                # Try new agent first
                print("🔄 Using LangChain agent...")
                result = await self.new_agent.process(message)
                self.last_used_agent = "langchain"
                return result
                
            except Exception as e:
                print(f"❌ LangChain agent failed: {e}")
                
                if self.fallback_enabled:
                    print("🔄 Falling back to enhanced agent...")
                    result = await self.old_agent.process(message)
                    self.last_used_agent = "enhanced"
                    # Mark that we used fallback
                    result.model_used = "enhanced_fallback"
                    return result
                else:
                    # No fallback, return error
                    return AIResponse(
                        conversational_response=f"I encountered an error: {str(e)}",
                        actions=[],
                        model_used="langchain_error"
                    )
        else:
            # Use old agent
            print("🔄 Using enhanced agent (default)...")
            result = await self.old_agent.process(message)
            self.last_used_agent = "enhanced"
            return result
    
    def get_agent_status(self) -> dict:
        """Get current migration status"""
        return {
            "new_agent_enabled": self.use_new_agent,
            "fallback_enabled": self.fallback_enabled,
            "last_used_agent": self.last_used_agent
        }
    
    def enable_new_agent(self, enable: bool = True):
        """Enable or disable new agent"""
        self.use_new_agent = enable
        print(f"✅ LangChain agent {'enabled' if enable else 'disabled'}")
    
    def enable_fallback(self, enable: bool = True):
        """Enable or disable fallback"""
        self.fallback_enabled = enable
        print(f"✅ Fallback {'enabled' if enable else 'disabled'}")


# Singleton instance for easy access
migration_agent = MigrationAgent()


# Test function
async def test_migration():
    """Test migration between agents"""
    from models.ai_models import ChatMessage
    
    test_message = ChatMessage(
        content="Schedule pizza for tomorrow",
        user_context={}
    )
    
    # Test with old agent
    print("\n=== Testing with enhanced agent ===")
    migration_agent.enable_new_agent(False)
    result1 = await migration_agent.process(test_message)
    print(f"Response: {result1.conversational_response}")
    print(f"Used: {result1.model_used}")
    
    # Test with new agent
    print("\n=== Testing with LangChain agent ===")
    migration_agent.enable_new_agent(True)
    result2 = await migration_agent.process(test_message)
    print(f"Response: {result2.conversational_response}")
    print(f"Used: {result2.model_used}")
    
    print(f"\nStatus: {migration_agent.get_agent_status()}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_migration())