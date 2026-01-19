#!/usr/bin/env python3
"""
Quick test for meta-ingredient parsing logic.
Tests the parse_meta_ingredient_response method with sample LLM outputs.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from vertical_video_processor import VerticalVideoProcessor


def test_parsing():
    """Test parsing of various LLM response formats."""

    # Create mock processor (no model needed for parsing test)
    class MockModel:
        pass

    processor = VerticalVideoProcessor(MockModel())

    print("="*60)
    print("TEST: Meta-Ingredient Parsing")
    print("="*60)

    # Test Case 1: Basic deduplication
    print("\n1. Basic deduplication (multiple instances of same ingredient):")
    response1 = """META_1:I101,I102|baby cucumber
META_2:I103,I104|natural Greek yogurt
META_3:I105,I106|lemon juice"""

    result1 = processor.parse_meta_ingredient_response(response1)
    print(f"   Input: {response1}")
    print(f"   Parsed:")
    for meta in result1:
        print(f"      {meta['id']}: {meta['name']} → {meta['linked_raw_ids']}")

    assert len(result1) == 3
    assert result1[0]['id'] == 'META_1'
    assert result1[0]['name'] == 'baby cucumber'
    assert result1[0]['linked_raw_ids'] == ['I101', 'I102']
    print("   ✅ PASSED\n")

    # Test Case 2: Preserving product specificity
    print("2. Preserving product types (different products, not combined):")
    response2 = """META_1:I201|extra virgin olive oil
META_2:I202|olive oil
META_3:I203,I204|garlic
META_4:I205|sea salt
META_5:I206|salt"""

    result2 = processor.parse_meta_ingredient_response(response2)
    print(f"   Input: {response2}")
    print(f"   Parsed:")
    for meta in result2:
        print(f"      {meta['id']}: {meta['name']} → {meta['linked_raw_ids']}")

    assert len(result2) == 5
    assert result2[0]['name'] == 'extra virgin olive oil'  # Preserved
    assert result2[1]['name'] == 'olive oil'  # Kept separate
    assert result2[3]['name'] == 'sea salt'  # Preserved
    assert result2[4]['name'] == 'salt'  # Kept separate
    print("   ✅ PASSED\n")

    # Test Case 3: Single ingredient (no duplicates)
    print("3. Single ingredient (no grouping needed):")
    response3 = """META_1:I301|chicken breast
META_2:I302|lemon zest"""

    result3 = processor.parse_meta_ingredient_response(response3)
    print(f"   Input: {response3}")
    print(f"   Parsed:")
    for meta in result3:
        print(f"      {meta['id']}: {meta['name']} → {meta['linked_raw_ids']}")

    assert len(result3) == 2
    assert result3[0]['linked_raw_ids'] == ['I301']  # Single ID
    assert result3[1]['linked_raw_ids'] == ['I302']  # Single ID
    print("   ✅ PASSED\n")

    # Test Case 4: Malformed line (graceful handling)
    print("4. Malformed response (missing pipe delimiter):")
    response4 = """META_1:I401,I402
META_2:I403|garlic"""

    result4 = processor.parse_meta_ingredient_response(response4)
    print(f"   Input: {response4}")
    print(f"   Parsed:")
    for meta in result4:
        print(f"      {meta['id']}: {meta['name']} → {meta['linked_raw_ids']}")

    assert len(result4) == 1  # Only valid line parsed
    assert result4[0]['id'] == 'META_2'
    print("   ✅ PASSED (gracefully skipped malformed line)\n")

    print("="*60)
    print("ALL TESTS PASSED! ✅")
    print("="*60)
    print("\nMeta-ingredient parsing logic is working correctly.")
    print("Ready for end-to-end testing with real recipe data.")


if __name__ == "__main__":
    try:
        test_parsing()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
