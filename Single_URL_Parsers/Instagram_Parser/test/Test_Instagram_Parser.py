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
        
        print("🔄 Running pipeline step by step to show raw LLM outputs...\n")
        
        # Step 1-5: Get combined content (Apify + audio + transcript + metadata)
        print("🚀 Steps 1-5: Extracting Instagram data, audio, transcription, and metadata...")
        step_start = time.time()
        
        # Extract Instagram data
        apify_data = transcriber.extract_with_apify(instagram_url)
        print(f"   ✅ Instagram data extracted")
        
        # Download and transcribe audio  
        audio_path = transcriber.download_audio_from_url(apify_data['video_url'])
        transcript = transcriber.transcribe_audio_deepgram(audio_path)
        print(f"   ✅ Audio transcribed")
        
        # Debug: Show transcript content
        if transcript and transcript.strip():
            transcript_preview = transcript[:100] + "..." if len(transcript) > 100 else transcript
            print(f"   📝 Transcript preview: \"{transcript_preview}\"")
            print(f"   📏 Transcript length: {len(transcript)} characters")
        else:
            print(f"   ⚠️  WARNING: Transcript is empty or None!")
            print(f"   📊 Transcript value: {repr(transcript)}")
        
        # Format metadata and combine content
        metadata = transcriber.format_apify_metadata(apify_data)
        combined_content = transcriber.combine_content_for_parsing(transcript, metadata)
        
        # Debug: Show combined content
        print(f"   📋 Combined content preview:")
        if combined_content and combined_content.strip():
            content_preview = combined_content[:200] + "..." if len(combined_content) > 200 else combined_content
            print(f"      \"{content_preview}\"")
            print(f"   📏 Combined content length: {len(combined_content)} characters")
        else:
            print(f"      ⚠️  WARNING: Combined content is empty!")
            print(f"      📊 Combined content value: {repr(combined_content)}")
        
        step1_5_time = time.time() - step_start
        print(f"   ⏱️  Steps 1-5 completed in {step1_5_time:.2f}s\n")
        
        # Step 6: Get raw LLM outputs
        print("🤖 Step 6: Running parallel LLM recipe extraction...")
        llm_start = time.time()
        
        ingredients_output, directions_output, meal_occasion_output = transcriber.parse_recipe_parallel(combined_content)
        
        llm_time = time.time() - llm_start
        print(f"   ✅ LLM parsing complete in {llm_time:.2f}s\n")
        
        # Display raw LLM outputs
        print("=" * 60)
        print("📝 RAW LLM OUTPUTS (Before JSON Structuring)")
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
        
        print("-" * 60)
        
        # Step 7: Structure into JSON
        print("\n📦 Step 7: Structuring into JSON...")
        json_start = time.time()
        
        recipe_json = transcriber.recipe_structurer.process_llm_outputs(
            ingredients_output, 
            directions_output, 
            instagram_url,
            apify_data.get("image_url", ""),  # Pass the image URL from apify_data
            meal_occasion_output  # Pass the meal occasion from LLM
        )
        
        json_time = time.time() - json_start
        print(f"   ✅ JSON structuring complete in {json_time:.2f}s")
        
        # Record end time
        end_time = time.time()
        duration = end_time - start_time
        
        # Display final JSON
        print("\n" + "=" * 60)
        print("🍳 FINAL STRUCTURED RECIPE JSON")
        print("=" * 60)
        print(f"⏱️  Total processing time: {duration:.2f} seconds")
        
        print(f"\n📋 STRUCTURED JSON OUTPUT:")
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
        
        # Show comprehensive analysis
        print(f"\n📊 DETAILED ANALYSIS & COMPARISON")
        print("=" * 60)
        
        # Raw output analysis
        ingredients_lines = len([line.strip() for line in ingredients_output.split('\n') if line.strip()])
        directions_lines = len([line.strip() for line in directions_output.split('\n') if line.strip()])
        
        print(f"\n📝 RAW LLM OUTPUT STATS:")
        print(f"   🥕 Raw ingredients: {ingredients_lines} lines")
        print(f"   📋 Raw directions: {directions_lines} lines")
        print(f"   📏 Raw ingredients length: {len(ingredients_output)} characters")
        print(f"   📏 Raw directions length: {len(directions_output)} characters")
        
        # Structured JSON analysis
        try:
            recipe_dict = json.loads(recipe_json)
            structured_ingredients = len(recipe_dict.get('ingredients', []))
            structured_directions = len(recipe_dict.get('directions', []))
            
            print(f"\n🍳 STRUCTURED JSON STATS:")
            print(f"   📝 Title: {recipe_dict.get('title', 'N/A')}")
            print(f"   🥕 Structured ingredients: {structured_ingredients} items")
            print(f"   📋 Structured directions: {structured_directions} steps")
            print(f"   🔗 Source URL: {recipe_dict.get('source_url', 'N/A')}")
            print(f"   📏 Final JSON length: {len(recipe_json)} characters")
            
            # Conversion analysis
            print(f"\n🔄 CONVERSION ANALYSIS:")
            ingredient_conversion = f"{ingredients_lines} → {structured_ingredients}"
            direction_conversion = f"{directions_lines} → {structured_directions}"
            
            print(f"   🥕 Ingredients conversion: {ingredient_conversion}")
            if structured_ingredients != ingredients_lines:
                diff = structured_ingredients - ingredients_lines
                if diff > 0:
                    print(f"      ➕ Added {diff} items (possibly merged/split)")
                else:
                    print(f"      ➖ Removed {abs(diff)} items (possibly filtered/merged)")
            else:
                print(f"      ✅ Perfect 1:1 conversion")
            
            print(f"   📋 Directions conversion: {direction_conversion}")
            if structured_directions != directions_lines:
                diff = structured_directions - directions_lines
                if diff > 0:
                    print(f"      ➕ Added {diff} steps (possibly split/detailed)")
                else:
                    print(f"      ➖ Removed {abs(diff)} steps (possibly merged/filtered)")
            else:
                print(f"      ✅ Perfect 1:1 conversion")
                
            # Quality assessment
            print(f"\n✨ QUALITY ASSESSMENT:")
            quality_indicators = []
            
            if recipe_dict.get('title'):
                quality_indicators.append("✅ Title extracted")
            else:
                quality_indicators.append("⚠️  No title found")
                
            if structured_ingredients > 0:
                quality_indicators.append(f"✅ {structured_ingredients} ingredients structured")
            else:
                quality_indicators.append("❌ No ingredients found")
                
            if structured_directions > 0:
                quality_indicators.append(f"✅ {structured_directions} directions structured")
            else:
                quality_indicators.append("❌ No directions found")
                
            for indicator in quality_indicators:
                print(f"   {indicator}")
                
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON PARSING ERROR: {str(e)}")
            print("   The recipe structurer may have produced invalid JSON")
        except Exception as e:
            print(f"\n❌ ANALYSIS ERROR: {str(e)}")
            
        # Performance breakdown
        print(f"\n⏱️  TIMING BREAKDOWN:")
        print(f"   🔧 Pipeline (Steps 1-5): {step1_5_time:.2f}s ({step1_5_time/duration*100:.1f}%)")
        print(f"   🤖 LLM Processing: {llm_time:.2f}s ({llm_time/duration*100:.1f}%)")
        print(f"   📦 JSON Structuring: {json_time:.2f}s ({json_time/duration*100:.1f}%)")
        print(f"   📊 Total Pipeline: {duration:.2f}s")
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n❌ Error after {duration:.2f} seconds: {str(e)}")
    
    print("\n🎉 Test complete!")


if __name__ == "__main__":
    main()