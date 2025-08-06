# AI Meal Planning App - Complete Project Overview (Updated)

## Project Vision & Overview

### What We're Building
An AI-powered meal planning iOS application that transforms the way busy families approach meal planning through natural conversation. Instead of overwhelming users with endless recipe databases or complex planning interfaces, our app provides a conversational AI assistant that acts like a personal chef who knows your preferences, dietary restrictions, and scheduling needs.

### The Problem We're Solving
Traditional meal planning is broken. Busy parents - especially working mothers - face the same weekly stress cycle:
- **Decision Fatigue**: "What should we eat this week?" repeated 7+ times
- **Recipe Discovery Overwhelm**: Scrolling through hundreds of recipes without finding "the right one"
- **Planning Inefficiency**: Manually scheduling meals, forgetting ingredients, rewriting shopping lists
- **Preference Management**: Juggling dietary restrictions, family preferences, and nutritional goals
- **Time Constraints**: Spending 1-2 hours every weekend just planning meals

### Target User: The Busy Mom Persona
**Meet Sarah**: A working mother of two who wants to provide variety and nutrition for her family but is overwhelmed by meal planning logistics.

**Sarah's Current Pain Points:**
- Stares at the grocery store wondering what to cook this week
- Screenshots recipes from Instagram, then loses them in her camera roll
- Makes the same 5 meals repeatedly because planning is exhausting
- Writes shopping lists on paper scraps that get lost
- Spends Sunday nights stressed about the upcoming week's meals
- Wants healthy variety but doesn't have time to research new recipes

**Sarah's Dream Solution:**
- "Hey, plan healthy meals for this week avoiding dairy" → AI handles everything
- AI suggests recipes based on her family's actual preferences
- Automatic shopping list generation from planned meals
- Voice interaction while cooking or driving
- Reliable meal scheduling that adapts to her busy schedule

### Ideal End Result - The Magic Experience
**The 30-Second Meal Planning Session:**
1. Sarah opens the app and taps the voice button
2. "Plan dinners for this week. Kids have soccer Tuesday and Thursday, so quick meals those days. And find me something new with chicken."
3. AI responds: "I'll plan 5 dinners with quick meals Tuesday and Thursday, plus a new chicken recipe. I found Mediterranean Chicken Bowls that your family should love based on past preferences."
4. Sarah sees her week populated with specific meals, taps "Approve"
5. Shopping list is automatically generated and ready to use

## Technical Architecture & Current State

### Development Philosophy
**AI-First with Manual Fallbacks**: Every action can be performed either through AI conversation or traditional UI interactions. The AI is the primary interface, with manual controls as reliable alternatives.

**Separate AI Agent**: The AI agent is a completely separate Python service that can be developed, tested, and scaled independently from the iOS app.

**Voice-First Experience**: Optimized for hands-free interaction during busy moments, with full text accessibility for all scenarios.

### Current Tech Stack

#### iOS Application (COMPLETED ✅)
- **Framework**: Swift + SwiftUI
- **Architecture**: MVVM (Model-View-ViewModel) with Repository pattern
- **Local Storage**: LocalStorageService with JSON files + UserDefaults for cart
- **Networking**: APIService with async/await ready for backend integration
- **Current State**: Fully functional meal planning app with 3 tabs

#### Backend Services (IN PROGRESS 🚧)
- **API Server**: Python + FastAPI for high-performance, well-documented APIs
- **AI Integration**: LangChain + Anthropic Claude + OpenAI GPT-4
- **Recipe Data**: Spoonacular API for reliable, curated recipe database
- **Architecture**: Tiered AI agent system with specialized sub-agents
- **Development**: Local Python server on localhost:3000

#### Future Infrastructure (PLANNED 📋)
- **Database**: PostgreSQL for robust relational data management
- **Authentication**: Firebase Auth supporting phone, social, and email login
- **File Storage**: AWS S3 for recipe images and user-generated content
- **Hosting**: Railway or Render for simple deployment and scaling

## Current iOS App State (COMPLETED ✅)

### Implemented Features
The iOS app is fully functional with advanced features:

#### 1. Meals Tab
- ✅ Create, edit, delete meals with photos, ingredients, instructions
- ✅ MealListView with favorites system
- ✅ MealDetailView with full meal information
- ✅ AddMealView with comprehensive meal creation
- ✅ Local JSON storage via LocalStorageService
- ✅ Repository pattern with MealRepository

#### 2. Schedule Tab  
- ✅ Weekly calendar view with navigation
- ✅ Schedule meals for specific dates and occasions (breakfast, lunch, dinner, snack)
- ✅ ScheduledMeal model with meal references
- ✅ ScheduleView with date-based meal planning
- ✅ Real-time meal lookup for scheduled items

#### 3. Shopping Cart (Bonus Feature)
- ✅ Three-tab cart interface (Meals, Items, Shopped)
- ✅ Add meals to cart with serving adjustments
- ✅ Intelligent ingredient consolidation
- ✅ CartViewModel singleton with UserDefaults persistence
- ✅ Cross-app cart integration with AddToCartButton

#### 4. Chat Tab (Basic Structure)
- ✅ ChatView with message interface
- ✅ ChatViewModel with conversation state
- ✅ Ready for AI integration
- ⚠️ Missing: Voice recording, text-to-speech, AI backend connection

### Data Models (Current)
```swift
struct Meal: Identifiable, Codable {
    let id: UUID
    var name: String
    var ingredients: [String]
    var instructions: [String]
    var photo: UIImage?
    var prepTime: Int?
    var servings: Int?
    var occasion: MealOccasion
    var isFavorite: Bool
}

struct ScheduledMeal: Identifiable, Codable {
    let id: UUID
    let mealId: UUID
    let date: Date
    let occasion: MealOccasion
}

enum MealOccasion: String, CaseIterable, Codable {
    case breakfast = "breakfast"
    case lunch = "lunch"
    case dinner = "dinner"
    case snack = "snack"
}

struct ShoppingCart: Codable {
    var meals: [CartMeal]
    var items: [CartItem]
}
```

### API Infrastructure (Ready)
- ✅ APIService class with HTTP methods
- ✅ Async/await patterns throughout
- ✅ Error handling infrastructure
- ✅ Repository protocols ready for backend integration
- ✅ Base URL configured for localhost:3000

## AI Agent Architecture (TO BE BUILT 🚧)

### Tiered Agent System
**Tier 1: Master Router Agent (Claude)**
- Classifies incoming requests as "recipe_discovery" or "meal_management"
- Routes to appropriate specialized agents
- Handles multi-intent requests that require both agents

**Tier 2A: Recipe Discovery Agent (GPT-4)**
- Processes recipe search requests
- Extracts search parameters from natural language
- Calls Spoonacular API and formats results
- Iterates with user on recipe preferences
- Specialized in food knowledge and culinary understanding

**Tier 2B: Meal Management Agent (Claude)**
- Handles all meal planning actions (schedule, save, modify, delete)
- CRUD operations on meals and schedules
- Shopping cart management
- Maintains context of user's current meal plan and preferences

### AI Response Format
```json
{
  "model_used": "claude" | "gpt4",
  "conversational_response": "I'll add chicken parmesan to Tuesday dinner!",
  "actions": [
    {
      "type": "schedule_meal",
      "parameters": {
        "meal_name": "chicken parmesan",
        "date": "2025-01-15", 
        "meal_type": "dinner"
      }
    }
  ],
  "preview_message": "Adding 1 meal to your dinner schedule"
}
```

### Voice Integration Strategy
**Interaction Model**: Tap-to-start, tap-to-stop conversation style
- User taps voice button to begin listening
- Visual feedback shows active listening state
- User taps again to stop and process request
- Optimal for complex, multi-part meal planning requests

**Response Strategy**: Always read responses aloud while displaying text
- Maintains conversational assistant experience
- Text remains visible for noisy environments or accessibility needs
- Creates authentic "talking to a personal chef" feeling

## Required Python Project Structure

```
meal-planner-api/
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables (API keys, etc.)
├── .gitignore                      # Git ignore file
├── README.md                       # Project documentation
├── config/
│   ├── __init__.py
│   ├── settings.py                 # Configuration management
│   └── database.py                 # Database configuration
├── models/
│   ├── __init__.py
│   ├── base.py                     # Base model classes
│   ├── meal.py                     # Meal data models (match iOS)
│   ├── scheduled_meal.py           # ScheduledMeal models (match iOS)
│   ├── shopping_cart.py            # Shopping cart models (match iOS)
│   └── ai_models.py                # AI request/response models
├── repositories/
│   ├── __init__.py
│   ├── base_repository.py          # Base repository interface
│   ├── meal_repository.py          # Meal data access
│   ├── scheduled_meal_repository.py # Schedule data access
│   └── cart_repository.py          # Shopping cart data access
├── api/
│   ├── __init__.py
│   ├── deps.py                     # API dependencies
│   ├── meals.py                    # Meal API endpoints
│   ├── scheduled_meals.py          # Schedule API endpoints
│   ├── shopping_cart.py            # Cart API endpoints
│   └── chat.py                     # AI chat endpoints
├── storage/
│   ├── __init__.py
│   ├── local_storage.py            # JSON file storage implementation
│   └── data/                       # Local JSON data files
│       ├── meals.json
│       ├── scheduled_meals.json
│       └── shopping_cart.json
├── ai_agents/
│   ├── __init__.py
│   ├── base_agent.py               # Base agent interface
│   ├── master_router.py            # Main routing agent
│   ├── recipe_discovery_agent.py   # Recipe search and iteration
│   ├── meal_management_agent.py    # CRUD and scheduling operations
│   ├── action_executor.py          # Executes actions on data
│   └── tools/
│       ├── __init__.py
│       ├── spoonacular_tool.py     # Spoonacular API integration
│       ├── meal_crud_tool.py       # Meal CRUD operations
│       ├── schedule_tool.py        # Scheduling operations
│       └── cart_tool.py            # Shopping cart operations
├── prompts/
│   ├── __init__.py
│   ├── master_router.txt           # Router agent prompts
│   ├── recipe_discovery.txt        # Recipe agent prompts
│   ├── meal_management.txt         # Meal management prompts
│   └── system_prompts.txt          # Shared system prompts
├── chains/
│   ├── __init__.py
│   ├── recipe_chain.py             # Recipe discovery chain
│   ├── meal_management_chain.py    # Meal management chain
│   └── routing_chain.py            # Request routing chain
├── utils/
│   ├── __init__.py
│   ├── prompt_loader.py            # Load prompts from files
│   ├── response_formatter.py       # Format AI responses
│   └── validators.py               # Input validation
├── services/
│   ├── __init__.py
│   ├── spoonacular_service.py      # External recipe API
│   ├── llm_service.py              # LLM client management
│   └── cache_service.py            # Response caching
└── tests/
    ├── __init__.py
    ├── test_agents/
    │   ├── test_master_router.py
    │   ├── test_recipe_agent.py
    │   └── test_meal_agent.py
    ├── test_api/
    │   ├── test_meals.py
    │   ├── test_scheduled_meals.py
    │   ├── test_shopping_cart.py
    │   └── test_chat.py
    └── test_tools/
        ├── test_spoonacular.py
        └── test_meal_crud.py
```

## Success Criteria
**AI Reliability Standard**: 95% accuracy across all interaction types
- Intent recognition: AI correctly understands user requests
- Action execution: AI performs correct operations on user data  
- Data handling: AI respects user preferences and constraints
- Testing methodology: 100 diverse conversation scenarios before phase completion

## Authentication Strategy (Future)
**Three-Tier Approach for Maximum Accessibility**:
1. **Primary**: Phone number + SMS verification (fastest, most universal)
2. **Secondary**: Apple/Google social login (privacy-focused users)
3. **Backup**: Email/password (users who prefer traditional methods)

## Offline Functionality Scope
**Available Offline**:
- View saved meals and scheduled meals
- Add, edit, delete saved meals
- Modify meal schedule (add/remove meals from calendar)
- Shopping cart management
- Create custom meals and recipes

**Requires Internet**:
- AI Assistant conversations
- Recipe discovery through APIs
- Data synchronization between devices
- User authentication

## Development Environment
- **iOS Development**: Xcode with SwiftUI
- **Python Development**: Local FastAPI server on localhost:3000
- **AI Integration**: LangChain + Claude + GPT-4 APIs
- **Testing**: Local development with JSON file storage
- **Version Control**: Git with separate repositories for iOS and Python

## Key Integration Points
1. **iOS ↔ Python API**: HTTP calls to localhost:3000
2. **Python API ↔ AI Agents**: Function calling with LangChain
3. **AI Agents ↔ External APIs**: Spoonacular for recipe discovery
4. **Data Consistency**: Shared model definitions between iOS and Python
5. **Voice Integration**: iOS Speech framework → Python AI → iOS TTS

## Next Development Phase
**Focus**: Build Python FastAPI server with AI agent integration
**Goal**: Connect iOS app to working AI assistant
**Timeline**: 4-6 weeks to achieve 95% AI reliability
**Priority**: Prove AI can reliably control app functions before adding complexity

This overview represents the current state after completing iOS app development (Phase 1) and beginning Python AI agent development (Phase 2).