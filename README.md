# Loomi AI Agent

AI-powered meal planning backend service for the Loomi iOS app. This Python FastAPI service provides intelligent meal planning, recipe discovery, and shopping cart management through conversational AI.

## Project Overview

This is the backend AI agent for the Loomi meal planning iOS application. The agent uses a tiered AI system with Claude and GPT-4 to handle:

- **Meal Management**: Schedule, save, modify, and delete meals
- **Recipe Discovery**: Find recipes using Spoonacular API with AI-powered search
- **Shopping Cart Intelligence**: Automatic ingredient consolidation and list generation
- **Conversational Interface**: Natural language meal planning through voice and text

## Current Status

✅ **Phase 1 Complete**: iOS App Foundation (SwiftUI app with full meal planning features)  
🚧 **Phase 2 In Progress**: Python AI Agent Development  
📋 **Phase 3 Planned**: Advanced AI features and conversation continuity

### Completed (Step 1-2):
- ✅ Python project structure with FastAPI
- ✅ Data models matching iOS app exactly (Meal, ScheduledMeal, ShoppingCart)
- ✅ Local JSON storage with iOS-compatible field names
- ✅ Complete test suite passing (model creation, serialization, storage)

### Next Steps:
- 🎯 **Step 3**: Basic API endpoints (GET, POST, DELETE for meals/schedules)
- 🎯 **Step 4**: iOS integration testing
- 🎯 **Step 5**: AI agent infrastructure (Claude + GPT-4)

## Architecture

```
├── models/           # Data models (Meal, ScheduledMeal, ShoppingCart)
├── storage/          # Local JSON file storage
├── api/              # FastAPI endpoints (planned)
├── ai_agent/         # AI agent system (planned)
├── services/         # External API services (planned)
└── tests/            # Test suites
```

## Technology Stack

- **Framework**: FastAPI (Python)
- **AI Models**: Claude (Anthropic) + GPT-4 (OpenAI)
- **Recipe Data**: Spoonacular API
- **Storage**: Local JSON files (development), PostgreSQL (production)
- **AI Framework**: LangChain

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/dashicreative/loomi-ai-agent.git
   cd loomi-ai-agent
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys:
   # OPENAI_API_KEY=your_openai_key
   # ANTHROPIC_API_KEY=your_anthropic_key
   # SPOONACULAR_API_KEY=your_spoonacular_key
   ```

## Testing Current Implementation

Run the comprehensive test suite:

```bash
source venv/bin/activate
python -c "
from storage.local_storage import LocalStorage
from models.meal import Meal, MealOccasion

# Test data models and storage
storage = LocalStorage()
meal = Meal(name='Test Meal', ingredients=['chicken'], instructions=['cook'], occasion=MealOccasion.dinner)
storage.save_meals([meal])
print(f'✅ Created and saved meal: {meal.name}')

# Verify iOS-compatible JSON format
import json
json_str = meal.model_dump_json(by_alias=True)
parsed = json.loads(json_str)
print(f'✅ iOS-compatible fields: prepTime={\"prepTime\" in parsed}, isFavorite={\"isFavorite\" in parsed}')
"
```

## Development Workflow

This project follows the explicit testing methodology from the execution guide:

1. **Implement feature**
2. **Run mandatory tests** 
3. **Verify all tests pass**
4. **Only then proceed to next step**

### Running Tests

```bash
# Test model imports
python -c "import models.meal; import models.scheduled_meal; import models.shopping_cart; print('✅ All models import')"

# Test storage operations
python -c "
from storage.local_storage import LocalStorage
from models.meal import Meal, MealOccasion
storage = LocalStorage()
meal = Meal(name='Test', ingredients=['salt'], instructions=['cook'], occasion=MealOccasion.dinner)
storage.save_meals([meal])
loaded = storage.load_meals()
assert len(loaded) == 1
print('✅ Storage round-trip successful')
"
```

## Data Models

### Meal
```python
{
  "id": "uuid",
  "name": "Chicken Parmesan",
  "ingredients": ["chicken breast", "parmesan cheese"],
  "instructions": ["bread chicken", "cook until golden"],
  "prepTime": 30,           # iOS-compatible camelCase
  "servings": 4,
  "occasion": "dinner",     # breakfast|lunch|dinner|snack
  "isFavorite": true        # iOS-compatible camelCase
}
```

### ScheduledMeal
```python
{
  "id": "uuid",
  "mealId": "meal-uuid",    # iOS-compatible camelCase
  "date": "2025-08-05",
  "occasion": "dinner"
}
```

## AI Agent System (Planned)

**Tier 1: Master Router Agent (Claude)**
- Classifies requests as "recipe_discovery" or "meal_management"
- Routes to appropriate specialized agents

**Tier 2A: Recipe Discovery Agent (GPT-4)**
- Natural language recipe search
- Spoonacular API integration
- Preference-based filtering

**Tier 2B: Meal Management Agent (Claude)**
- CRUD operations on meals and schedules
- Shopping cart management
- Context-aware meal planning

## Success Criteria

- **95% AI accuracy** across all interaction types
- **Sub-3 second** response times
- **Complete iOS integration** with voice and text interfaces
- **Reliable action execution** on user data

## Contributing

This project follows a strict testing methodology. Before making changes:

1. Read the execution guide in `ai_context/V1/`
2. Run existing tests to ensure nothing breaks
3. Add tests for new functionality
4. Ensure 100% test coverage for critical paths

## License

Private project for Loomi meal planning application.

---

**Current Phase**: Step 2 Complete (Data Models + Storage) → Proceeding to Step 3 (API Endpoints)