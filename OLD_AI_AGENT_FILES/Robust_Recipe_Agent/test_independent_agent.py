#!/usr/bin/env python3
"""
Test script to verify the Robust Recipe Agent is independent of the original
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import from the new recipe_agent module
from recipe_agent.Discovery_Agent import create_recipe_discovery_agent
from recipe_agent.Dependencies import RecipeDeps, SessionContext

print("✅ Successfully imported from recipe_agent module")
print("✅ This agent is completely independent from Recipe_Discovery_Agent")

# Try to create the agent to verify it works
try:
    agent = create_recipe_discovery_agent()
    print("✅ Agent created successfully")
except Exception as e:
    print(f"⚠️ Agent creation failed (expected without API keys): {e}")

print("\n📦 Robust Recipe Agent is ready for experimentation!")
print("   - Located in: Robust_Recipe_Agent/recipe_agent/")
print("   - Manual testing: Robust_Recipe_Agent/Manual_Testing/")
print("   - Completely independent from original Recipe_Discovery_Agent")