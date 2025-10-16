"""
Two-Endpoint Recipe Agent System
Endpoint 1: Fast agent decisions + recipe IDs
Endpoint 2: Rich recipe data retrieval by IDs
"""

import asyncio
import os
import sys
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import the hybrid agent system we just built
from hybrid_recipe_agent import (
    hybrid_agent, 
    HybridAgentDeps, 
    UserIntent,
    find_recipes_with_hybrid_agent
)


class RecipeAgentAPI:
    """
    API interface for the two-endpoint system.
    Separates conversational decisions from data delivery.
    """
    
    def __init__(self, serpapi_key: str = None, openai_key: str = None, google_key: str = None, google_cx: str = None):
        self.sessions = {}  # session_id -> HybridAgentDeps
        
        # Default API keys
        self.default_keys = {
            'serpapi': serpapi_key or os.getenv("SERPAPI_KEY"),
            'openai': openai_key or os.getenv("OPENAI_API_KEY"),
            'google': google_key or os.getenv("GOOGLE_SEARCH_KEY"),
            'google_cx': google_cx or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        }
    
    # ===============================================
    # ENDPOINT 1: Agent Decision Service (Fast)
    # ===============================================
    
    async def find_recipes_decision(
        self, 
        query: str, 
        target_count: int = 4, 
        session_id: str = None
    ) -> Dict:
        """
        ENDPOINT 1: Get agent conversational response + recipe ID selections.
        Ultra-fast response for immediate user feedback.
        
        Returns: {"response": "...", "selected_recipe_ids": [...], "metadata": {...}}
        """
        print(f"🚀 [ENDPOINT 1] Fast agent decision for: '{query}'")
        
        # Get or create session
        if not session_id:
            session_id = f"session_{int(time.time())}"
        
        deps = self._get_or_create_session(session_id)
        
        # Use hybrid agent to make decision
        start_time = time.time()
        
        result = await hybrid_agent.run(
            f"Find {target_count} recipes for: {query}",
            deps=deps
        )
        
        decision_time = time.time() - start_time
        
        # Parse agent response to extract response and IDs
        agent_output = result.data if hasattr(result, 'data') else str(result)
        
        # Handle AgentRunResult wrapper if present
        if 'AgentRunResult(output=' in str(agent_output):
            # Extract content from AgentRunResult wrapper
            import re
            match = re.search(r"AgentRunResult\(output='(.*?)'\)", str(agent_output), re.DOTALL)
            if match:
                agent_output = match.group(1)
        
        print(f"🔍 [PARSE] Extracted agent content: {agent_output[:200]}...")
        
        # Simple parsing of agent output format (RESPONSE: ... SELECTED_IDS: ...)
        response_text, selected_ids = self._parse_agent_output(agent_output)
        
        decision_result = {
            "response": response_text,
            "selected_recipe_ids": selected_ids,
            "session_id": session_id,
            "metadata": {
                "decision_time": round(decision_time, 2),
                "total_recipes_in_memory": len(deps.recipe_memory),
                "query_enhanced": deps.user_intent.enhanced_query if deps.user_intent else query,
                "constraints_detected": self._summarize_constraints(deps.user_intent) if deps.user_intent else [],
                "follow_up_available": len(deps.recipe_memory) > target_count
            }
        }
        
        print(f"✅ [ENDPOINT 1] Decision completed in {decision_time:.2f}s: {len(selected_ids)} IDs selected")
        return decision_result
    
    # ===============================================  
    # ENDPOINT 2: Recipe Data Service (Rich Content)
    # ===============================================
    
    async def get_recipes_by_ids(
        self, 
        recipe_ids: List[str], 
        session_id: str,
        fields_requested: Optional[List[str]] = None
    ) -> Dict:
        """
        ENDPOINT 2: Get complete recipe data by IDs.
        Fast data lookup from session memory.
        
        Returns: {"recipes": [...], "metadata": {...}}
        """
        print(f"📊 [ENDPOINT 2] Fetching {len(recipe_ids)} recipes for session {session_id}")
        
        if session_id not in self.sessions:
            return {
                "error": "Session not found",
                "recipes": [],
                "suggestion": "Please start a new recipe search"
            }
        
        deps = self.sessions[session_id]
        start_time = time.time()
        
        # Retrieve recipes from memory
        retrieved_recipes = []
        missing_ids = []
        
        for recipe_id in recipe_ids:
            if recipe_id in deps.recipe_memory:
                full_recipe = deps.recipe_memory[recipe_id].copy()
                
                # Optional field filtering for bandwidth optimization
                if fields_requested:
                    filtered_recipe = {"id": recipe_id}
                    for field in fields_requested:
                        if field in full_recipe:
                            filtered_recipe[field] = full_recipe[field]
                    retrieved_recipes.append(filtered_recipe)
                else:
                    full_recipe["id"] = recipe_id
                    retrieved_recipes.append(full_recipe)
            else:
                missing_ids.append(recipe_id)
        
        lookup_time = time.time() - start_time
        
        result = {
            "recipes": retrieved_recipes,
            "metadata": {
                "lookup_time": round(lookup_time, 3),
                "retrieved_count": len(retrieved_recipes),
                "missing_ids": missing_ids,
                "session_memory_size": len(deps.recipe_memory)
            }
        }
        
        if missing_ids:
            result["warning"] = f"Could not find {len(missing_ids)} recipes in session memory"
        
        print(f"✅ [ENDPOINT 2] Data retrieval completed in {lookup_time:.3f}s: {len(retrieved_recipes)} recipes")
        return result
    
    # ===============================================
    # HELPER METHODS
    # ===============================================
    
    def _get_or_create_session(self, session_id: str) -> HybridAgentDeps:
        """Get existing session or create new one."""
        if session_id not in self.sessions:
            print(f"🆕 [SESSION] Creating new session: {session_id}")
            self.sessions[session_id] = HybridAgentDeps(
                serpapi_key=self.default_keys['serpapi'],
                openai_key=self.default_keys['openai'], 
                google_key=self.default_keys['google'],
                google_cx=self.default_keys['google_cx']
            )
        else:
            print(f"🔄 [SESSION] Using existing session: {session_id} ({len(self.sessions[session_id].recipe_memory)} recipes in memory)")
        
        return self.sessions[session_id]
    
    def _parse_agent_output(self, agent_output: str) -> tuple[str, List[str]]:
        """Parse agent output to extract response and recipe IDs."""
        try:
            # Debug: Print what we received
            print(f"🔍 [PARSE] Agent output received: {agent_output[:200]}...")
            
            # Look for RESPONSE: and SELECTED_IDS: format
            if 'RESPONSE:' in agent_output and 'SELECTED_IDS:' in agent_output:
                import re
                
                # Extract response text
                response_match = re.search(r'RESPONSE:\s*(.*?)(?=\nSELECTED_IDS:|$)', agent_output, re.DOTALL)
                response_text = response_match.group(1).strip() if response_match else "Found recipes for you!"
                
                # Extract selected IDs  
                ids_match = re.search(r'SELECTED_IDS:\s*\[(.*?)\]', agent_output, re.DOTALL)
                if ids_match:
                    ids_text = ids_match.group(1)
                    # Extract all session_recipe_XXX patterns
                    id_matches = re.findall(r'session_recipe_\d+', ids_text)
                    selected_ids = id_matches
                else:
                    selected_ids = []
                
                print(f"✅ [PARSE] Extracted response: '{response_text[:50]}...', IDs: {selected_ids}")
                return response_text, selected_ids
            
            # Fallback: Extract IDs from any format
            import re
            id_matches = re.findall(r'session_recipe_\d+', agent_output)
            
            if id_matches:
                response_text = "Found some great recipes for you!"
                return response_text, id_matches
            else:
                # Last resort: Use agent's raw response as-is
                return str(agent_output), []
            
        except Exception as e:
            print(f"⚠️ [PARSE] Failed to parse agent output: {e}")
            return "Found some recipes for you!", []
    
    def _summarize_constraints(self, user_intent: UserIntent) -> List[str]:
        """Summarize user constraints for metadata."""
        constraints = []
        
        if user_intent.ingredient_constraints:
            constraints.extend(user_intent.ingredient_constraints)
        if user_intent.allergy_constraints:
            constraints.extend([f"no_{allergy}" for allergy in user_intent.allergy_constraints])
        if user_intent.nutritional_constraints:
            constraints.extend(user_intent.nutritional_constraints)
        if user_intent.time_constraints:
            constraints.append(user_intent.time_constraints)
        
        return constraints
    
    def get_session_info(self, session_id: str) -> Dict:
        """Get session information for debugging/monitoring."""
        if session_id not in self.sessions:
            return {"error": "Session not found"}
        
        deps = self.sessions[session_id]
        
        return {
            "session_id": session_id,
            "recipes_in_memory": len(deps.recipe_memory),
            "urls_shown": len(deps.session_shown_urls),
            "user_intent": {
                "original_query": deps.user_intent.original_query if deps.user_intent else None,
                "subject": deps.user_intent.subject if deps.user_intent else None,
                "constraints": self._summarize_constraints(deps.user_intent) if deps.user_intent else []
            }
        }
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Clean up old sessions to prevent memory leaks."""
        # Implementation would check session timestamps and remove old ones
        pass


# ===============================================
# USAGE EXAMPLES FOR RAILWAY INTEGRATION  
# ===============================================

async def example_ios_workflow():
    """Example of how iOS app would use the two-endpoint system."""
    
    api = RecipeAgentAPI()
    
    print("📱 EXAMPLE: iOS App Recipe Search Workflow")
    print("=" * 60)
    
    # Step 1: User types query
    user_query = "gluten-free chocolate cake"
    
    # Step 2: Get instant agent decision  
    print(f"\n1️⃣ INSTANT FEEDBACK (Endpoint 1)")
    decision = await api.find_recipes_decision(user_query, target_count=3)
    
    print(f"   Agent Response: {decision['response']}")
    print(f"   Recipe IDs: {decision['selected_recipe_ids']}")
    print(f"   Decision Time: {decision['metadata']['decision_time']}s")
    
    # Step 3: Get rich recipe data
    print(f"\n2️⃣ RICH CONTENT (Endpoint 2)")  
    recipes = await api.get_recipes_by_ids(
        decision['selected_recipe_ids'],
        decision['session_id']
    )
    
    print(f"   Retrieved: {recipes['metadata']['retrieved_count']} complete recipes")
    print(f"   Lookup Time: {recipes['metadata']['lookup_time']}s")
    
    # Step 4: Show what iOS would display
    print(f"\n📱 iOS APP WOULD DISPLAY:")
    print(f"   Conversational: '{decision['response']}'")
    print(f"   Recipe Cards: {len(recipes['recipes'])} beautiful native UI cards")
    
    return decision, recipes


if __name__ == "__main__":
    print("🤖 Two-Endpoint Recipe Agent System")
    print("Run example_ios_workflow() to see integration pattern")
    
    # Uncomment to test:
    # asyncio.run(example_ios_workflow())