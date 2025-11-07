"""
Agents - Main recipe discovery agent with intent detection
"""

from .hybrid_recipe_agent import hybrid_agent, find_recipes_with_hybrid_agent, HybridAgentDeps

__all__ = [
    'hybrid_agent',
    'find_recipes_with_hybrid_agent', 
    'HybridAgentDeps'
]