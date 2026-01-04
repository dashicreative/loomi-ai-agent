#!/usr/bin/env python3
"""
Test CLI for complete YouTube recipe parsing (Steps 1-10).

Tests full pipeline:
1-4: YouTube-specific extraction
5-10: Shared vertical video processing
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from YouTube_parser import YouTubeTranscriber

# Load environment variables
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def main():
    """
    Test the complete YouTube recipe parsing pipeline.
    """
    print("=" * 70)
    print("🎬 YouTube Recipe JSON Parser Test (Complete Pipeline)")
    print("=" * 70)
    print("\n📋 This test covers ALL steps 1-10:")
    print("   1-3: Apify → Audio Download → Deepgram Transcription")
    print("   4: Format metadata")
    print("   5-10: Shared recipe processing (LLM, quality control, JSON)\n")

    # Get YouTube URL from user
    youtube_url = input("Enter YouTube URL: ").strip()

    if not youtube_url:
        print("❌ No URL provided. Exiting.")
        return

    # Validate URL
    if "youtube.com" not in youtube_url and "youtu.be" not in youtube_url:
        print("❌ Please provide a valid YouTube URL.")
        return

    print(f"\n🔄 Processing: {youtube_url}")
    print("Running complete recipe parsing pipeline...")

    # Record start time
    start_time = time.time()

    try:
        # Create transcriber instance
        transcriber = YouTubeTranscriber()

        print("\n🚀 Running YouTube recipe parsing pipeline...\n")

        # Parse YouTube recipe to JSON
        recipe_json = transcriber.parse_youtube_recipe_to_json(youtube_url)

        # Calculate total time
        end_time = time.time()
        duration = end_time - start_time

        # Display final JSON
        print("\n" + "=" * 70)
        print("📦 FINAL JSON (FOR MOBILE APP)")
        print("=" * 70)

        print(f"\n📋 RECIPE JSON:")
        print("-" * 70)

        # Pretty print the JSON
        try:
            recipe_dict = json.loads(recipe_json)
            formatted_json = json.dumps(recipe_dict, indent=2, ensure_ascii=False)
            print(formatted_json)
        except json.JSONDecodeError:
            print(recipe_json)

        print("-" * 70)

        # Enhanced analysis
        print(f"\n📊 RECIPE ANALYSIS")
        print("=" * 70)

        try:
            recipe_dict = json.loads(recipe_json)

            # Basic stats
            ingredients_count = len(recipe_dict.get('ingredients', []))
            directions_count = len(recipe_dict.get('directions', []))

            print(f"\n🍳 RECIPE OVERVIEW:")
            print(f"   📝 Title: {recipe_dict.get('title', 'N/A')}")
            print(f"   🥕 Ingredients: {ingredients_count} items with IDs")
            print(f"   📋 Directions: {directions_count} steps")
            print(f"   🍽️  Meal Occasion: {recipe_dict.get('meal_occasion', 'N/A')}")
            print(f"   🖼️  Thumbnail: {recipe_dict.get('image', 'N/A')[:60]}...")
            print(f"   🔗 Source URL: {recipe_dict.get('source_url', 'N/A')}")

            # Enhanced features analysis
            print(f"\n🔗 ENHANCED FEATURES:")

            # Step-ingredient matching
            steps_with_ingredients = 0
            total_ingredient_assignments = 0

            for direction in recipe_dict.get('directions', []):
                ingredient_ids = direction.get('ingredient_ids', [])
                if ingredient_ids:
                    steps_with_ingredients += 1
                    total_ingredient_assignments += len(ingredient_ids)

            print(f"   ✅ Step-Ingredient Matching:")
            print(f"      📋 {steps_with_ingredients}/{directions_count} steps have ingredient assignments")
            print(f"      🔗 {total_ingredient_assignments} total ingredient-step connections")

            # Meta step analysis
            meta_steps = [d for d in recipe_dict.get('directions', []) if d.get('type') == 'meta_step']
            regular_steps = [d for d in recipe_dict.get('directions', []) if d.get('type') == 'regular_step']
            steps_with_sections = [d for d in regular_steps if d.get('meta_step_section')]

            print(f"   ✅ Meta Step Organization:")
            print(f"      🏗️  {len(meta_steps)} meta steps (section headers)")
            print(f"      📝 {len(regular_steps)} regular steps")
            print(f"      🗂️  {len(steps_with_sections)} steps organized into sections")

            if meta_steps:
                sections = list(set([step.get('text', 'Unknown') for step in meta_steps]))
                print(f"      📂 Sections identified: {', '.join(sections)}")

            # Quality assessment
            print(f"\n✨ QUALITY ASSESSMENT:")
            quality_score = 0
            max_score = 5

            if recipe_dict.get('title'):
                print(f"   ✅ Title extracted")
                quality_score += 1
            else:
                print(f"   ❌ No title found")

            if ingredients_count > 0:
                print(f"   ✅ {ingredients_count} ingredients with unique IDs")
                quality_score += 1
            else:
                print(f"   ❌ No ingredients found")

            if directions_count > 0:
                print(f"   ✅ {directions_count} cooking steps")
                quality_score += 1
            else:
                print(f"   ❌ No directions found")

            if steps_with_ingredients > 0:
                print(f"   ✅ Step-ingredient matching working")
                quality_score += 1
            else:
                print(f"   ⚠️  No step-ingredient connections")

            if meta_steps or steps_with_sections:
                print(f"   ✅ Recipe organization detected")
                quality_score += 1
            else:
                print(f"   ⚠️  No meta step organization")

            grade = "F"
            if quality_score == 5:
                grade = "A+"
            elif quality_score == 4:
                grade = "A"
            elif quality_score == 3:
                grade = "B"
            elif quality_score == 2:
                grade = "C"
            elif quality_score == 1:
                grade = "D"

            print(f"\n🎯 OVERALL GRADE: {grade} ({quality_score}/{max_score})")

        except json.JSONDecodeError as e:
            print(f"\n❌ JSON PARSING ERROR: {str(e)}")
        except Exception as e:
            print(f"\n❌ ANALYSIS ERROR: {str(e)}")

        # Performance info
        print(f"\n⏱️  TOTAL PROCESSING TIME: {duration:.2f} seconds")

    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time

        print(f"\n❌ Error after {duration:.2f} seconds: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()
