# Macro Calculation Agent

A minimal Pydantic AI agent for calculating recipe macronutrients using USDA data and Gemini-2.5-flash.

## Structure

```
Ingredient_Macro_agent/
├── macro_agent.py      # Main agent setup with Gemini-2.5-flash
├── dependencies.py     # Shared resources (USDA client, conversions)
├── tools.py           # Agent tools (USDA lookup, unit conversion)
├── system_prompt.txt  # Agent instructions and behavior
├── test_cli.py        # Test CLI for ingredient input
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

## Features

- **USDA Database Integration**: Primary source for nutrition data
- **Unit Conversion**: Handles volume-to-weight conversions
- **Session Caching**: Avoids duplicate API calls
- **Type Safety**: Full Pydantic AI type safety
- **Minimal Code**: Clean, lean implementation

## Input Format

```json
[
  {
    "name": "ingredient name with description",
    "quantity": "amount as string",
    "unit": "measurement unit"
  }
]
```

## Output Format

```json
["X calories", "X g protein", "X g fat", "X g carbs"]
```

## Quick Test

```bash
cd /Users/agustin/Desktop/loomi_ai_agent/Ingredient_Macro_agent
python test_cli.py
```

## Dependencies

- Requires `GOOGLE_GEMINI_KEY` in `.env` file
- Optional: `USDA_API_KEY` for higher rate limits
- Uses existing Gemini API setup from parent project

## Tools

- `lookup_usda_nutrition()`: USDA database queries
- `convert_ingredient_to_grams()`: Unit conversions
- `calculate_ingredient_macros()`: Per-ingredient calculations
- `sum_recipe_macros()`: Recipe-level totals