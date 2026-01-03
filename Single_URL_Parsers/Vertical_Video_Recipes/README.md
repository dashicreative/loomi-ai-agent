# Vertical Video Recipes - Shared Module

Shared recipe processing for ALL vertical video parsers (Instagram, TikTok, Facebook, YouTube).

## Architecture

```
┌─────────────────────────────────────────┐
│ Platform-Specific (Steps 1-4)           │
│ - Instagram: Apify Instagram Scraper    │
│ - TikTok: Apify TikTok Audio Downloader │
│ - Facebook: TBD                         │
│ - YouTube: TBD                          │
│ Output: transcript + metadata           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ Shared VerticalVideoProcessor (Steps 5+)│
│ - Combine content                       │
│ - Parallel LLM extraction               │
│ - Quality control (shared module)       │
│ - Meta step extraction                  │
│ - Step-ingredient matching              │
│ - JSON structuring                      │
└─────────────────────────────────────────┘
```

## Source-Agnostic Processing

Once you have `transcript + metadata`, ALL vertical video parsers use the **exact same pipeline**:

1. ✅ Combine content for LLM parsing
2. ✅ Extract ingredients/directions/meal occasion (parallel)
3. ✅ Clean ingredients (remove editorial notes, split multi-ingredients)
4. ✅ Paraphrase directions (copyright protection)
5. ✅ Rescue failed parses (fix regex failures with LLM)
6. ✅ Extract meta steps (prep time, cook time, sections)
7. ✅ Match ingredients to steps
8. ✅ Structure as JSON

## Usage

### From Instagram Parser:
```python
from Vertical_Video_Recipes import VerticalVideoProcessor

processor = VerticalVideoProcessor(google_model)

recipe_json = processor.process_recipe(
    transcript=transcript,
    metadata={
        'caption': apify_data['caption'],
        'creator_username': apify_data['creator_username'],
        # ... other metadata
    },
    source_url=instagram_url,
    parser_method="Instagram"
)
```

### From TikTok Parser:
```python
from Vertical_Video_Recipes import VerticalVideoProcessor

processor = VerticalVideoProcessor(google_model)

recipe_json = processor.process_recipe(
    transcript=transcript,
    metadata={
        'caption': tiktok_data['caption'],
        'creator_username': tiktok_data['uploader'],
        # ... other metadata
    },
    source_url=tiktok_url,
    parser_method="TikTok"
)
```

## LLM Prompts

All prompts are stored in `/llm_prompts/`:
- `Ingredients_LLM_Parsing_Prompt.txt` - Extract ingredients from content
- `Directions_LLM_Parsing_Prompt.txt` - Extract title and cooking steps
- `Meal_Occasion_LLM_Parsing_Prompt.txt` - Classify meal type

These prompts are **shared across all vertical video parsers** for consistency.

## Benefits

✅ **DRY Principle** - No duplicate code across parsers
✅ **Consistency** - All platforms use same quality control
✅ **Easy to Add Platforms** - Just implement steps 1-4
✅ **Centralized Improvements** - Fix once, benefits all
✅ **Tested & Proven** - Based on production Instagram parser

## Dependencies

- `Recipe_Quality_Control` - Shared quality control module
- `Instagram_Parser/src` - Recipe structurer, meta step extractor, step matcher (will be moved to shared later)
- Google Gemini API for LLM processing
