#!/usr/bin/env python3
"""
Test CLI for Instagram recipe parsing with detailed LLM output analysis.

Tests the complete pipeline step-by-step and shows:
1. Raw LLM outputs for ingredients and directions 
2. Final structured JSON recipe
3. Detailed conversion analysis comparing raw vs structured outputs
4. Quality assessment and performance breakdown
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Add the src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from Instagram_parser import InstagramTranscriber

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent.parent / ".env"  # Go up to loomi_ai_agent directory
load_dotenv(dotenv_path=env_path)


def main():
    """
    Test the complete Instagram recipe parsing pipeline with JSON output.
    """
    print("🍳 Instagram Recipe JSON Parser Test")
    print("=" * 50)
    
    # Get Instagram URL from user
    instagram_url = input("\nEnter Instagram URL: ").strip()
    
    if not instagram_url:
        print("❌ No URL provided. Exiting.")
        return
    
    # Validate URL format
    if "instagram.com" not in instagram_url:
        print("❌ Please provide a valid Instagram URL.")
        return
    
    print(f"\n🔄 Processing: {instagram_url}")
    print("Running complete recipe parsing pipeline...")
    print("⏱️  This includes: audio extraction → transcription → parallel recipe parsing → JSON structuring\n")
    
    # Record start time
    start_time = time.time()
    
    try:
        # Create transcriber instance
        transcriber = InstagramTranscriber()
        
        print("🚀 Running enhanced Instagram recipe parsing pipeline...")
        print("   This includes: Apify extraction → Audio transcription → LLM parsing → Enhanced analysis → JSON structuring\n")
        
        # Step 1: Extract Instagram data and transcribe
        print("📱 Step 1-5: Extracting data and transcribing...")
        apify_data = transcriber.extract_with_apify(instagram_url)
        audio_path = transcriber.download_audio_from_url(apify_data['video_url'])
        transcript = transcriber.transcribe_audio_deepgram(audio_path)
        metadata = transcriber.format_apify_metadata(apify_data)
        combined_content = transcriber.combine_content_for_parsing(transcript, metadata)
        
        # Step 2: Get raw LLM outputs for analysis
        print("🤖 Step 6: Running LLM recipe extraction...")
        ingredients_output, directions_output, meal_occasion_output = transcriber.parse_recipe_parallel(combined_content)
        
        # Display raw LLM outputs
        print("\n" + "=" * 60)
        print("📝 RAW LLM OUTPUTS (From Instagram Content)")
        print("=" * 60)
        
        print("\n🥕 RAW INGREDIENTS OUTPUT:")
        print("-" * 40)
        print(ingredients_output)
        
        print("\n📋 RAW DIRECTIONS OUTPUT:")
        print("-" * 40) 
        print(directions_output)
        
        print("\n🍽️  RAW MEAL OCCASION OUTPUT:")
        print("-" * 40)
        print(meal_occasion_output)
        
        print("=" * 60)
        
        # Step 3: Run the complete enhanced pipeline
        print("\n🔗 Running complete enhanced analysis...")
        recipe_json = transcriber.parse_instagram_recipe_to_json(instagram_url)
        
        # Record end time
        end_time = time.time()
        duration = end_time - start_time
        
        # Display final JSON
        print("\n" + "=" * 60)
        print("📦 FINAL JSON (FOR MOBILE APP)")
        print("=" * 60)
        print(f"⏱️  Total processing time: {duration:.2f} seconds")
        
        print(f"\n📋 ENHANCED RECIPE JSON:")
        print("-" * 40)
        
        # Pretty print the JSON
        try:
            # Parse and re-format for better display
            recipe_dict = json.loads(recipe_json)
            formatted_json = json.dumps(recipe_dict, indent=2, ensure_ascii=False)
            print(formatted_json)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            print(recipe_json)
        
        print("-" * 60)
        
        # Enhanced analysis
        print(f"\n📊 ENHANCED RECIPE ANALYSIS")
        print("=" * 60)
        
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
            print(f"   ⏱️  Total Time: {recipe_dict.get('total_time', 'N/A')}")
            print(f"   🔗 Source URL: {recipe_dict.get('source_url', 'N/A')}")
            
            # Enhanced features analysis
            print(f"\n🔗 ENHANCED FEATURES:")
            
            # Step-ingredient matching analysis
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
        print(f"\n⏱️  PROCESSING TIME: {duration:.2f} seconds")
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n❌ Error after {duration:.2f} seconds: {str(e)}")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()