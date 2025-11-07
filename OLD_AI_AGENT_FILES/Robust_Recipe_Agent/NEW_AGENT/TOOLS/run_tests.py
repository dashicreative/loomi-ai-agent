"""
Test Runner for All Tools
Runs all individual tool tests from the test/ directory.
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def run_test_file(test_file: Path):
    """Run a single test file and capture output."""
    print(f"\n{'='*80}")
    print(f"🧪 Running {test_file.name}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            cwd=test_file.parent
        )
        
        # Print stdout
        if result.stdout:
            print(result.stdout)
        
        # Print stderr if there are errors
        if result.stderr:
            print(f"❌ STDERR:\n{result.stderr}")
        
        if result.returncode == 0:
            print(f"✅ {test_file.name} completed successfully")
        else:
            print(f"❌ {test_file.name} failed with return code {result.returncode}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run {test_file.name}: {e}")
        return False


def main():
    """Run all tests in the test directory."""
    print("\n" + "="*80)
    print("🚀 RECIPE DISCOVERY AGENT - ALL TOOL TESTS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Find all test files
    test_dir = Path(__file__).parent / "test"
    test_files = list(test_dir.glob("test_*.py"))
    
    if not test_files:
        print("⚠️ No test files found in test/ directory")
        return
    
    print(f"Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    
    # Run each test
    results = []
    for test_file in test_files:
        success = run_test_file(test_file)
        results.append((test_file.name, success))
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed. Check output above for details.")


if __name__ == "__main__":
    main()