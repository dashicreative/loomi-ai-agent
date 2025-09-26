"""
Railway Entry Point for Recipe Discovery Agent

This is the main entry point for deploying the Recipe Discovery Agent on Railway.
It simply imports and runs the Discovery_Agent main function.
"""

import sys
from pathlib import Path

# Add the current directory to Python path to ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

from Recipe_Discovery_Agent.Discovery_Agent import main

if __name__ == "__main__":
    print("🚂 Starting Recipe Discovery Agent on Railway...")
    main()