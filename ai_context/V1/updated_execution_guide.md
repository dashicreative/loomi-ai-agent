# AI Meal Planning App - Explicit Testing Execution Guide

## Current Status: iOS App Complete, Beginning Python AI Agent Development

**Your biggest risk**: "Can I build reliable AI that performs actions correctly?"
**Strategy**: iOS app shell complete ✅ → Build Python AI agent → Test each component → Debug before proceeding

**⚠️ CRITICAL RULE: DO NOT PROCEED TO THE NEXT STEP UNTIL CURRENT STEP IS TESTED AND WORKING**

---

## ✅ COMPLETED: iOS App Foundation (Weeks 1-3)
**Status**: DONE - iOS app is fully functional and ready for AI integration

### ✅ Week 1: Setup & Meals Tab (COMPLETED)
- ✅ iOS project with SwiftUI, MVVM structure
- ✅ Meal model and MealRepository with enhanced features
- ✅ MealListView with favorites and photos
- ✅ AddMealView with comprehensive meal creation
- ✅ Local JSON storage via LocalStorageService
- ✅ API endpoints structure ready

### ✅ Week 2: Schedule Tab (COMPLETED)
- ✅ ScheduledMeal model with MealOccasion enum
- ✅ ScheduleView with weekly calendar navigation
- ✅ Tap day → select meal → schedule functionality
- ✅ Local storage for scheduled meals
- ✅ Real-time meal lookup for schedule display

### ✅ Week 3: Basic Chat UI + Bonus Features (COMPLETED)
- ✅ ChatView with message interface
- ✅ ChatViewModel with conversation state
- ✅ Shopping cart system (3-tab interface)
- ✅ CartViewModel singleton with advanced features
- ✅ Cross-app integration with AddToCartButton
- ⚠️ **PENDING**: Voice recording, text-to-speech, AI backend connection

**iOS App Status**: Fully functional meal planning app with advanced shopping cart features. Ready for Python AI agent integration.

---

## 🚧 CURRENT PHASE: Python AI Agent Development

### 🎯 STEP 1: Python Project Setup & Data Models (Week 4, Day 1-2)
**Goal**: Create Python project structure with data models that exactly match iOS

**🛑 DO NOT PROCEED TO STEP 2 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Create Python FastAPI project with virtual environment
- [ ] Install dependencies: FastAPI, Pydantic, LangChain, OpenAI, Anthropic
- [ ] Create project folder structure (models/, api/, storage/, etc.)
- [ ] Implement data models that EXACTLY match iOS app

#### Required Data Models:
```python
# models/meal.py
class MealOccasion(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"

class Meal(BaseModel):
    id: UUID
    name: str
    ingredients: List[str]
    instructions: List[str]
    prep_time: Optional[int] = None
    servings: Optional[int] = None
    occasion: MealOccasion
    is_favorite: bool = False

# models/scheduled_meal.py
class ScheduledMeal(BaseModel):
    id: UUID
    meal_id: UUID
    date: date
    occasion: MealOccasion

# models/shopping_cart.py
class CartMeal(BaseModel):
    id: UUID
    meal_id: UUID
    meal_name: str
    servings: int
    date_added: datetime

class ShoppingCart(BaseModel):
    meals: List[CartMeal]
    items: List[CartItem]
```

#### MANDATORY TESTS - STEP 1:
```bash
# Test 1: Project Structure
python -c "import models.meal; import models.scheduled_meal; import models.shopping_cart; print('✅ All models import successfully')"

# Test 2: Data Model Creation
python -c "
from models.meal import Meal, MealOccasion
from models.scheduled_meal import ScheduledMeal
from datetime import date
from uuid import uuid4

meal = Meal(id=uuid4(), name='Test Meal', ingredients=['salt'], instructions=['cook'], occasion=MealOccasion.dinner, is_favorite=False)
scheduled = ScheduledMeal(id=uuid4(), meal_id=meal.id, date=date.today(), occasion=MealOccasion.dinner)
print('✅ Models create and serialize correctly')
print(f'Meal: {meal.name}')
print(f'Scheduled: {scheduled.date}')
"

# Test 3: JSON Serialization (iOS Compatibility)
python -c "
import json
from models.meal import Meal, MealOccasion
from uuid import uuid4

meal = Meal(id=uuid4(), name='Test Meal', ingredients=['salt'], instructions=['cook'], occasion=MealOccasion.dinner, is_favorite=False)
json_str = meal.model_dump_json()
parsed = json.loads(json_str)
print('✅ JSON serialization compatible with iOS')
print(f'JSON keys: {list(parsed.keys())}')
assert 'meal_id' not in json_str, 'Should be camelCase mealId for iOS'
"
```

**✅ SUCCESS CRITERIA FOR STEP 1:**
- All Python models import without errors
- Data models can be created and serialized
- JSON output is compatible with iOS expectations (camelCase where needed)
- Project structure is complete and organized

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 2.**

---

### 🎯 STEP 2: Local Storage Implementation (Week 4, Day 3)
**Goal**: Create JSON file storage that matches iOS expectations

**🛑 DO NOT PROCEED TO STEP 3 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Implement LocalStorageService for JSON files
- [ ] Create storage/data/ directory
- [ ] Implement meal storage with exact iOS format
- [ ] Implement scheduled meal storage
- [ ] Implement shopping cart storage

#### Required Implementation:
```python
# storage/local_storage.py
class LocalStorage:
    def __init__(self, data_directory: str = "storage/data"):
        self.data_directory = Path(data_directory)
        self.data_directory.mkdir(parents=True, exist_ok=True)
    
    def save_meals(self, meals: List[Meal]) -> None:
        # Save to meals.json
    
    def load_meals(self) -> List[Meal]:
        # Load from meals.json
    
    def save_scheduled_meals(self, scheduled_meals: List[ScheduledMeal]) -> None:
        # Save to scheduled_meals.json
        
    def load_scheduled_meals(self) -> List[ScheduledMeal]:
        # Load from scheduled_meals.json
```

#### MANDATORY TESTS - STEP 2:
```bash
# Test 1: Storage Directory Creation
python -c "
from storage.local_storage import LocalStorage
storage = LocalStorage()
print('✅ Storage directory created successfully')
print(f'Directory exists: {storage.data_directory.exists()}')
"

# Test 2: Meal Storage Round Trip
python -c "
from storage.local_storage import LocalStorage
from models.meal import Meal, MealOccasion
from uuid import uuid4

storage = LocalStorage()
test_meal = Meal(id=uuid4(), name='Test Meal', ingredients=['salt', 'pepper'], instructions=['mix', 'cook'], occasion=MealOccasion.dinner, is_favorite=True)

# Save and load
storage.save_meals([test_meal])
loaded_meals = storage.load_meals()

assert len(loaded_meals) == 1, f'Expected 1 meal, got {len(loaded_meals)}'
assert loaded_meals[0].name == 'Test Meal', f'Expected Test Meal, got {loaded_meals[0].name}'
assert loaded_meals[0].is_favorite == True, f'Expected favorite=True, got {loaded_meals[0].is_favorite}'
print('✅ Meal storage round trip successful')
print(f'Saved and loaded: {loaded_meals[0].name}')
"

# Test 3: Scheduled Meal Storage
python -c "
from storage.local_storage import LocalStorage
from models.scheduled_meal import ScheduledMeal, MealOccasion
from datetime import date
from uuid import uuid4

storage = LocalStorage()
test_scheduled = ScheduledMeal(id=uuid4(), meal_id=uuid4(), date=date.today(), occasion=MealOccasion.lunch)

storage.save_scheduled_meals([test_scheduled])
loaded_scheduled = storage.load_scheduled_meals()

assert len(loaded_scheduled) == 1, f'Expected 1 scheduled meal, got {len(loaded_scheduled)}'
assert loaded_scheduled[0].occasion == MealOccasion.lunch, f'Expected lunch, got {loaded_scheduled[0].occasion}'
print('✅ Scheduled meal storage round trip successful')
"

# Test 4: File Format Check (iOS Compatibility)
python -c "
import json
from pathlib import Path

data_dir = Path('storage/data')
if (data_dir / 'meals.json').exists():
    with open(data_dir / 'meals.json', 'r') as f:
        data = json.load(f)
    print('✅ meals.json format check')
    print(f'File contains: {len(data)} meals')
    if data:
        print(f'Sample meal keys: {list(data[0].keys())}')
else:
    print('⚠️  meals.json not found - run storage tests first')
"
```

**✅ SUCCESS CRITERIA FOR STEP 2:**
- LocalStorage class creates directories and files successfully
- Meal data can be saved and loaded without data loss
- Scheduled meal data persists correctly
- JSON file format matches iOS expectations
- No errors during read/write operations

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 3.**

---

### 🎯 STEP 3: Basic API Endpoints (Week 4, Day 4-5)
**Goal**: Create FastAPI server with endpoints that iOS app can call

**🛑 DO NOT PROCEED TO STEP 4 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Create main.py FastAPI application
- [ ] Implement basic meal endpoints (GET, POST, DELETE)
- [ ] Implement scheduled meal endpoints
- [ ] Implement shopping cart endpoints
- [ ] Set up CORS for iOS app communication

#### Required API Endpoints:
```python
# api/meals.py
@router.get("/", response_model=List[Meal])
async def get_meals():
    # Return all meals from storage

@router.post("/", response_model=Meal)
async def create_meal(meal: MealCreate):
    # Create new meal in storage

@router.delete("/{meal_id}")
async def delete_meal(meal_id: str):
    # Delete meal from storage

# api/scheduled_meals.py
@router.get("/", response_model=List[ScheduledMeal])
async def get_scheduled_meals():
    # Return all scheduled meals

@router.post("/", response_model=ScheduledMeal)
async def create_scheduled_meal(scheduled_meal: ScheduledMealCreate):
    # Create new scheduled meal

# main.py
app = FastAPI()
app.include_router(meals.router, prefix="/api/meals")
app.include_router(scheduled_meals.router, prefix="/api/scheduled-meals")
```

#### MANDATORY TESTS - STEP 3:
```bash
# Test 1: Server Starts Successfully
# Run this in terminal:
uvicorn main:app --port 3000 &
sleep 3
curl http://localhost:3000/
# Should return FastAPI welcome message
echo "✅ Server starts on port 3000"
pkill -f uvicorn

# Test 2: Meals API Endpoints
# Start server: uvicorn main:app --port 3000 --reload
# Then run:
python -c "
import requests
import json

# Test GET meals (should return empty array initially)
response = requests.get('http://localhost:3000/api/meals')
assert response.status_code == 200, f'Expected 200, got {response.status_code}'
meals = response.json()
print(f'✅ GET /api/meals: {len(meals)} meals returned')

# Test POST meal
new_meal = {
    'name': 'API Test Meal',
    'ingredients': ['test ingredient'],
    'instructions': ['test instruction'],
    'occasion': 'dinner',
    'is_favorite': False
}
response = requests.post('http://localhost:3000/api/meals', json=new_meal)
assert response.status_code == 200, f'POST failed with {response.status_code}: {response.text}'
created_meal = response.json()
assert 'id' in created_meal, 'Created meal should have ID'
print(f'✅ POST /api/meals: Created meal with ID {created_meal[\"id\"]}')

# Test GET meals again (should now have 1 meal)
response = requests.get('http://localhost:3000/api/meals')
meals = response.json()
assert len(meals) == 1, f'Expected 1 meal, got {len(meals)}'
print(f'✅ Meal persistence: {meals[0][\"name\"]}')
"

# Test 3: Scheduled Meals API
python -c "
import requests
from datetime import date

# Test scheduled meals endpoint
response = requests.get('http://localhost:3000/api/scheduled-meals')
assert response.status_code == 200, f'Expected 200, got {response.status_code}'
print('✅ GET /api/scheduled-meals working')

# Create a scheduled meal (using meal from previous test)
meals_response = requests.get('http://localhost:3000/api/meals')
meals = meals_response.json()
if meals:
    meal_id = meals[0]['id']
    scheduled_meal = {
        'meal_id': meal_id,
        'date': str(date.today()),
        'occasion': 'dinner'
    }
    response = requests.post('http://localhost:3000/api/scheduled-meals', json=scheduled_meal)
    assert response.status_code == 200, f'POST scheduled meal failed: {response.text}'
    print('✅ POST /api/scheduled-meals working')
else:
    print('⚠️  No meals found - run meals test first')
"

# Test 4: CORS for iOS
python -c "
import requests

# Test CORS headers
response = requests.options('http://localhost:3000/api/meals')
headers = response.headers
print(f'✅ CORS test')
print(f'Access-Control-Allow-Origin: {headers.get(\"Access-Control-Allow-Origin\", \"Not set\")}')
print(f'Access-Control-Allow-Methods: {headers.get(\"Access-Control-Allow-Methods\", \"Not set\")}')
"
```

**✅ SUCCESS CRITERIA FOR STEP 3:**
- FastAPI server starts successfully on port 3000
- All meal endpoints (GET, POST, DELETE) work correctly
- Scheduled meal endpoints function properly
- Data persists between requests (storage integration working)
- CORS is configured for iOS app communication
- API responses match expected JSON format

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 4.**

---

### 🎯 STEP 4: iOS Integration Test (Week 4, Day 6-7)
**Goal**: Verify iOS app can successfully communicate with Python API

**🛑 DO NOT PROCEED TO STEP 5 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Update iOS APIService to use localhost:3000
- [ ] Test iOS app with Python backend
- [ ] Verify all iOS features work with Python API
- [ ] Debug any data format mismatches

#### iOS Integration Points:
```swift
// Update APIService.swift baseURL if needed
private let baseURL = "http://localhost:3000/api"

// Test all repository methods work with Python backend
```

#### MANDATORY TESTS - STEP 4:
```bash
# Before running these tests:
# 1. Start Python API: uvicorn main:app --port 3000 --reload
# 2. Open iOS app in Xcode simulator

echo "🧪 iOS Integration Tests"
echo "========================"

echo "Test 1: Run iOS app and verify it connects to Python API"
echo "- Open Meals tab"
echo "- Try creating a new meal"
echo "- Verify meal appears in list"
echo "- Check Python server logs for API calls"
echo ""

echo "Test 2: Schedule functionality"
echo "- Go to Schedule tab"
echo "- Try scheduling a meal"
echo "- Verify meal appears on calendar"
echo "- Check Python server logs for scheduled-meals API calls"
echo ""

echo "Test 3: Shopping cart integration"
echo "- Add a meal to shopping cart"
echo "- Verify cart shows meal and ingredients"
echo "- Check Python server logs for cart API calls"
echo ""

echo "Test 4: Data persistence across app restarts"
echo "- Create meals and schedules"
echo "- Force close iOS app"
echo "- Reopen app"
echo "- Verify all data is still there"
echo ""

echo "Test 5: Python API data verification"
```

#### MANUAL VERIFICATION CHECKLIST:
- [ ] iOS app starts without errors
- [ ] Can create new meals through iOS app
- [ ] Created meals appear in meals list
- [ ] Can schedule meals through iOS app
- [ ] Scheduled meals appear on calendar
- [ ] Can add meals to shopping cart
- [ ] Shopping cart shows correct ingredients
- [ ] Data persists when app is restarted
- [ ] Python server logs show API calls from iOS
- [ ] No network errors in iOS app

#### DEBUGGING TESTS:
```bash
# If iOS integration fails, run these debugging tests:

# Test 1: Network connectivity
curl -X GET http://localhost:3000/api/meals
echo "↑ Should return JSON array"

# Test 2: Data format compatibility
python -c "
import requests
response = requests.get('http://localhost:3000/api/meals')
data = response.json()
print('API Response Format:')
import json
print(json.dumps(data, indent=2))
"

# Test 3: Check iOS expects vs Python provides
echo "Compare iOS APIService expected format with Python API actual format"
echo "Look for camelCase vs snake_case mismatches"
```

**✅ SUCCESS CRITERIA FOR STEP 4:**
- iOS app successfully connects to Python API on localhost:3000
- All existing iOS features work with Python backend
- No data is lost when switching from iOS local storage to Python API
- API calls appear in Python server logs
- No network errors or JSON parsing errors in iOS
- Complete round-trip functionality: iOS → Python → Storage → Python → iOS

**🛑 STOP HERE UNTIL ALL TESTS PASS. THIS IS CRITICAL - IF BASIC INTEGRATION DOESN'T WORK, AI INTEGRATION WILL FAIL.**

---

### 🎯 STEP 5: Basic AI Infrastructure (Week 5, Day 1-2)
**Goal**: Set up AI services and basic chat endpoint

**🛑 DO NOT PROCEED TO STEP 6 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Set up environment variables for API keys
- [ ] Create LLM service with Claude and GPT-4
- [ ] Create basic chat endpoint that returns echo responses
- [ ] Test AI API connections

#### Required Implementation:
```python
# config/settings.py
class Settings(BaseSettings):
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    spoonacular_api_key: Optional[str] = None
    
    class Config:
        env_file = ".env"

# services/llm_service.py
class LLMService:
    def __init__(self):
        self.claude = ChatAnthropic(api_key=settings.anthropic_api_key)
        self.gpt4 = ChatOpenAI(api_key=settings.openai_api_key)

# api/chat.py
@router.post("/", response_model=ChatResponse)
async def chat(message: ChatMessage):
    # Return echo response for now
    return ChatResponse(
        conversational_response=f"Echo: {message.content}",
        actions=[],
        model_used="echo"
    )
```

#### MANDATORY TESTS - STEP 5:
```bash
# Test 1: Environment Setup
python -c "
from config.settings import settings
print('✅ Settings loaded')
print(f'OpenAI key present: {'Yes' if settings.openai_api_key else 'No'}')
print(f'Anthropic key present: {'Yes' if settings.anthropic_api_key else 'No'}')
print(f'Spoonacular key present: {'Yes' if settings.spoonacular_api_key else 'No'}')
"

# Test 2: LLM Service Initialization
python -c "
from services.llm_service import LLMService
try:
    llm_service = LLMService()
    print('✅ LLM Service initialized successfully')
    print(f'Claude available: {llm_service.claude is not None}')
    print(f'GPT-4 available: {llm_service.gpt4 is not None}')
except Exception as e:
    print(f'❌ LLM Service failed: {e}')
"

# Test 3: Basic AI API Connection
python -c "
from services.llm_service import LLMService
from langchain.schema import HumanMessage

llm_service = LLMService()
try:
    # Test Claude
    claude_response = llm_service.claude.invoke([HumanMessage(content='Hello')])
    print(f'✅ Claude test successful: {claude_response.content[:50]}...')
except Exception as e:
    print(f'❌ Claude test failed: {e}')

try:
    # Test GPT-4
    gpt4_response = llm_service.gpt4.invoke([HumanMessage(content='Hello')])
    print(f'✅ GPT-4 test successful: {gpt4_response.content[:50]}...')
except Exception as e:
    print(f'❌ GPT-4 test failed: {e}')
"

# Test 4: Chat Endpoint
# Start server: uvicorn main:app --port 3000 --reload
python -c "
import requests

chat_message = {
    'content': 'Hello, this is a test message',
    'user_context': {}
}

response = requests.post('http://localhost:3000/api/chat', json=chat_message)
assert response.status_code == 200, f'Chat endpoint failed: {response.status_code}'
data = response.json()
assert 'conversational_response' in data, 'Missing conversational_response'
assert 'Echo: Hello' in data['conversational_response'], f'Unexpected response: {data}'
print('✅ Chat endpoint working')
print(f'Response: {data[\"conversational_response\"]}')
"
```

**✅ SUCCESS CRITERIA FOR STEP 5:**
- API keys are loaded from environment variables
- LLM service initializes both Claude and GPT-4 successfully
- Basic AI API calls work (Claude and GPT-4 respond to "Hello")
- Chat endpoint returns echo responses in correct format
- No authentication or connection errors with AI services

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 6.**

---

### 🎯 STEP 6: Master Router Agent (Week 5, Day 3-4)
**Goal**: Create AI agent that can classify user intent

**🛑 DO NOT PROCEED TO STEP 7 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Create base agent interface
- [ ] Implement master router with prompt
- [ ] Create intent classification system
- [ ] Test intent classification accuracy

#### Required Implementation:
```python
# ai_agent/base_agent.py
class BaseAgent(ABC):
    @abstractmethod
    async def process(self, message: ChatMessage) -> AIResponse:
        pass

# ai_agent/master_router.py
class MasterRouter(BaseAgent):
    async def classify_intent(self, message: str) -> str:
        # Use Claude to classify as "recipe_discovery" or "meal_management"
        prompt = self.get_classification_prompt()
        # Return "recipe_discovery" or "meal_management"
        
    async def process(self, message: ChatMessage) -> AIResponse:
        intent = await self.classify_intent(message.content)
        return AIResponse(
            conversational_response=f"I classified your message as: {intent}",
            actions=[],
            model_used="claude"
        )
```

#### MANDATORY TESTS - STEP 6:
```bash
# Test 1: Base Agent Structure
python -c "
from ai_agent.base_agent import BaseAgent
from ai_agent.master_router import MasterRouter
router = MasterRouter()
print('✅ Agent classes created successfully')
print(f'Router type: {type(router)}')
"

# Test 2: Intent Classification Accuracy
python -c "
import asyncio
from ai_agent.master_router import MasterRouter
from models.ai_models import ChatMessage

async def test_classification():
    router = MasterRouter()
    
    # Test meal management intents
    meal_management_tests = [
        'Add pasta to Tuesday dinner',
        'Schedule chicken for tomorrow',
        'Remove Monday lunch',
        'Put salmon on Friday',
        'Add chicken to my cart'
    ]
    
    # Test recipe discovery intents
    recipe_discovery_tests = [
        'Find me chicken recipes',
        'I want vegetarian pasta',
        'Show me Italian food',
        'What can I make with tomatoes',
        'Find healthy dinner ideas'
    ]
    
    print('Testing Meal Management Classification:')
    for test in meal_management_tests:
        intent = await router.classify_intent(test)
        correct = intent == 'meal_management'
        print(f'  \"{test}\" → {intent} {'✅' if correct else '❌'}')
    
    print('\nTesting Recipe Discovery Classification:')
    for test in recipe_discovery_tests:
        intent = await router.classify_intent(test)
        correct = intent == 'recipe_discovery'
        print(f'  \"{test}\" → {intent} {'✅' if correct else '❌'}')

asyncio.run(test_classification())
"

# Test 3: Full Router Process
python -c "
import asyncio
from ai_agent.master_router import MasterRouter
from models.ai_models import ChatMessage

async def test_router():
    router = MasterRouter()
    
    test_message = ChatMessage(content='Find me chicken recipes')
    response = await router.process(test_message)
    
    assert hasattr(response, 'conversational_response'), 'Missing conversational_response'
    assert hasattr(response, 'actions'), 'Missing actions'
    assert hasattr(response, 'model_used'), 'Missing model_used'
    
    print('✅ Router process working')
    print(f'Response: {response.conversational_response}')
    print(f'Actions: {len(response.actions)}')

asyncio.run(test_router())
"

# Test 4: Chat Endpoint with Router
# Update chat endpoint to use MasterRouter, then test:
python -c "
import requests

test_messages = [
    'Find me chicken recipes',
    'Add pasta to Tuesday',
    'Show me vegetarian options',
    'Schedule salmon for Friday'
]

for message in test_messages:
    chat_data = {'content': message, 'user_context': {}}
    response = requests.post('http://localhost:3000/api/chat', json=chat_data)
    
    assert response.status_code == 200, f'Chat failed for: {message}'
    data = response.json()
    print(f'Message: \"{message}\"')
    print(f'Response: {data[\"conversational_response\"]}')
    print('---')
"
```

**✅ SUCCESS CRITERIA FOR STEP 6:**
- Master router classifies meal management intents correctly (80%+ accuracy)
- Master router classifies recipe discovery intents correctly (80%+ accuracy)
- Router process returns proper AIResponse format
- Chat endpoint uses router and returns classified responses
- No errors in agent processing or AI API calls

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 7.**

---

### 🎯 STEP 7: Meal Management Agent (Week 5, Day 5-7)
**Goal**: Create agent that can understand and execute meal planning actions

**🛑 DO NOT PROCEED TO STEP 8 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Create meal management agent
- [ ] Implement action parameter extraction
- [ ] Create action execution system
- [ ] Test meal scheduling through AI

#### Required Implementation:
```python
# ai_agent/meal_management_agent.py
class MealManagementAgent(BaseAgent):
    async def extract_action(self, message: str, user_context: dict) -> AIAction:
        # Use Claude to extract action type and parameters
        # Return AIAction with type and parameters
        
    async def process(self, message: ChatMessage) -> AIResponse:
        action = await self.extract_action(message.content, message.user_context)
        return AIResponse(
            conversational_response="I'll help you with that meal planning task",
            actions=[action],
            model_used="claude"
        )

# ai_agent/action_executor.py
class ActionExecutor:
    async def execute_action(self, action: AIAction, user_id: str) -> dict:
        if action.type == ActionType.SCHEDULE_MEAL:
            return await self._schedule_meal(action.parameters, user_id)
        # Handle other action types
```

#### MANDATORY TESTS - STEP 7:
```bash
# Test 1: Action Parameter Extraction
python -c "
import asyncio
from ai_agent.meal_management_agent import MealManagementAgent
from models.ai_models import ChatMessage

async def test_action_extraction():
    agent = MealManagementAgent()
    
    # Test scheduling action
    message = 'Add chicken parmesan to Tuesday dinner'
    user_context = {'saved_meals': ['chicken parmesan', 'pasta', 'salad']}
    
    action = await agent.extract_action(message, user_context)
    
    print('✅ Action extraction test')
    print(f'Action type: {action.type}')
    print(f'Parameters: {action.parameters}')
    
    # Verify expected parameters
    assert action.type == 'schedule_meal', f'Expected schedule_meal, got {action.type}'
    assert 'meal_name' in action.parameters, 'Missing meal_name parameter'
    assert 'date' in action.parameters, 'Missing date parameter'
    assert 'meal_type' in action.parameters, 'Missing meal_type parameter'
    
    print(f'✅ Extracted meal: {action.parameters.get(\"meal_name\")}')
    print(f'✅ Extracted date: {action.parameters.get(\"date\")}')
    print(f'✅ Extracted meal type: {action.parameters.get(\"meal_type\")}')

asyncio.run(test_action_extraction())
"

# Test 2: Multiple Action Types
python -c "
import asyncio
from ai_agent.meal_management_agent import MealManagementAgent

async def test_multiple_actions():
    agent = MealManagementAgent()
    user_context = {'saved_meals': ['pasta', 'chicken', 'salad']}
    
    test_cases = [
        ('Add pasta to Monday lunch', 'schedule_meal'),
        ('Remove Tuesday dinner', 'delete_scheduled_meal'),
        ('Add chicken to cart', 'add_to_cart'),
        ('Delete my pasta meal', 'delete_meal')
    ]
    
    print('Testing Multiple Action Types:')
    for message, expected_type in test_cases:
        try:
            action = await agent.extract_action(message, user_context)
            correct = action.type == expected_type
            print(f'  \"{message}\" → {action.type} {'✅' if correct else '❌'}')
        except Exception as e:
            print(f'  \"{message}\" → ERROR: {e} ❌')

asyncio.run(test_multiple_actions())
"

# Test 3: Action Execution
python -c "
import asyncio
from ai_agent.action_executor import ActionExecutor
from models.ai_models import AIAction, ActionType

async def test_action_execution():
    executor = ActionExecutor()
    
    # Test meal scheduling
    schedule_action = AIAction(
        type=ActionType.SCHEDULE_MEAL,
        parameters={
            'meal_name': 'Test Meal',
            'date': '2025-08-10',
            'meal_type': 'dinner'
        }
    )
    
    try:
        result = await executor.execute_action(schedule_action, 'test_user')
        print('✅ Action execution successful')
        print(f'Result: {result}')
        
        # Verify meal was actually scheduled
        import requests
        response = requests.get('http://localhost:3000/api/scheduled-meals')
        scheduled_meals = response.json()
        
        # Check if our meal was scheduled
        found = any(meal.get('date') == '2025-08-10' for meal in scheduled_meals)
        print(f'✅ Meal found in schedule: {found}')
        
    except Exception as e:
        print(f'❌ Action execution failed: {e}')

asyncio.run(test_action_execution())
"

# Test 4: End-to-End Meal Management
python -c "
import requests

# Test complete meal management flow through chat
test_messages = [
    'Add chicken parmesan to Tuesday dinner',
    'Schedule pasta for Monday lunch',
    'Add salmon to my cart for 4 servings'
]

print('Testing End-to-End Meal Management:')
for message in test_messages:
    chat_data = {'content': message, 'user_context': {'saved_meals': ['chicken parmesan', 'pasta', 'salmon']}}
    response = requests.post('http://localhost:3000/api/chat', json=chat_data)
    
    if response.status_code == 200:
        data = response.json()
        print(f'✅ \"{message}\"')
        print(f'   Response: {data[\"conversational_response\"]}')
        print(f'   Actions: {len(data.get(\"actions\", []))}')
    else:
        print(f'❌ \"{message}\" failed: {response.status_code}')
    print('---')
"
```

**✅ SUCCESS CRITERIA FOR STEP 7:**
- Meal management agent extracts action parameters correctly
- Multiple action types are recognized accurately
- Action executor can schedule meals successfully
- Scheduled meals appear in the database/storage
- End-to-end chat → agent → action → storage workflow works
- iOS app can see AI-scheduled meals in the schedule tab

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 8.**

---

### 🎯 STEP 8: iOS AI Integration Test (Week 6, Day 1-2)
**Goal**: Connect iOS chat to working AI agent

**🛑 DO NOT PROCEED TO STEP 9 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Update iOS ChatView to call Python AI chat endpoint
- [ ] Implement voice recording in iOS ChatView
- [ ] Implement text-to-speech in iOS ChatView
- [ ] Test complete voice workflow

#### MANDATORY TESTS - STEP 8:
```bash
echo "🧪 iOS AI Integration Tests"
echo "============================"

echo "Test 1: Text Chat Integration"
echo "- Open iOS app Chat tab"
echo "- Type: 'Add chicken parmesan to Tuesday dinner'"
echo "- Verify AI responds with confirmation"
echo "- Go to Schedule tab and verify meal was scheduled"
echo ""

echo "Test 2: Voice Recording"
echo "- Tap voice button in chat"
echo "- Say: 'Find me chicken recipes'"
echo "- Verify speech is converted to text"
echo "- Verify AI processes the message"
echo ""

echo "Test 3: Text-to-Speech"
echo "- Send any message to AI"
echo "- Verify AI response is read aloud"
echo "- Verify text is also visible on screen"
echo ""

echo "Test 4: Complete Voice Workflow"
echo "- Tap voice button"
echo "- Say: 'Schedule pasta for Monday lunch'"
echo "- Listen to AI confirmation"
echo "- Verify meal appears in schedule"
echo ""

echo "Test 5: Error Handling"
echo "- Try scheduling non-existent meal"
echo "- Verify graceful error handling"
echo "- Try unclear voice input"
echo "- Verify AI asks for clarification"
```

#### iOS Integration Verification:
- [ ] ChatView connects to Python API successfully
- [ ] Voice recording works (Speech framework)
- [ ] Text-to-speech works (AVSpeechSynthesizer)
- [ ] AI responses trigger actual app changes
- [ ] Schedule tab reflects AI-scheduled meals
- [ ] No network errors or crashes

**✅ SUCCESS CRITERIA FOR STEP 8:**
- iOS chat successfully calls Python AI endpoint
- Voice input is accurately converted to text
- AI responses are read aloud automatically
- AI-scheduled meals appear in iOS schedule tab
- Complete voice workflow: speak → AI processes → confirms → updates app
- Error handling works gracefully for edge cases

**🛑 STOP HERE UNTIL ALL TESTS PASS. THIS IS THE CRITICAL AI-iOS INTEGRATION POINT.**

---

### 🎯 STEP 9: Recipe Discovery Agent (Week 6, Day 3-5)
**Goal**: Add AI recipe search with Spoonacular integration

**🛑 DO NOT PROCEED TO STEP 10 UNTIL ALL TESTS PASS**

#### Tasks:
- [ ] Set up Spoonacular API integration
- [ ] Create recipe discovery agent with GPT-4
- [ ] Implement recipe search parameter extraction
- [ ] Test recipe discovery through chat

#### MANDATORY TESTS - STEP 9:
```bash
# Test 1: Spoonacular API Connection
python -c "
import requests
from config.settings import settings

if not settings.spoonacular_api_key:
    print('❌ Spoonacular API key not set')
    exit(1)

# Test basic recipe search
url = f'https://api.spoonacular.com/recipes/complexSearch'
params = {
    'apiKey': settings.spoonacular_api_key,
    'query': 'chicken',
    'number': 3
}

response = requests.get(url, params=params)
assert response.status_code == 200, f'Spoonacular API failed: {response.status_code}'

data = response.json()
recipes = data.get('results', [])
print(f'✅ Spoonacular API working: {len(recipes)} recipes found')
for recipe in recipes[:2]:
    print(f'  - {recipe[\"title\"]}')
"

# Test 2: Recipe Discovery Agent
python -c "
import asyncio
from ai_agent.recipe_discovery_agent import RecipeDiscoveryAgent
from models.ai_models import ChatMessage

async def test_recipe_discovery():
    agent = RecipeDiscoveryAgent()
    
    test_message = ChatMessage(
        content='Find me healthy chicken recipes',
        user_context={'dietary_preferences': ['healthy', 'low-carb']}
    )
    
    response = await agent.process(test_message)
    
    print('✅ Recipe discovery test')
    print(f'Response: {response.conversational_response}')
    print(f'Actions: {len(response.actions)}')
    
    # Check if recipes were found
    if response.actions:
        recipe_action = response.actions[0]
        if recipe_action.type == 'find_recipe':
            recipes = recipe_action.parameters.get('recipes', [])
            print(f'✅ Found {len(recipes)} recipes')
            for i, recipe in enumerate(recipes[:2]):
                print(f'  {i+1}. {recipe.get(\"title\", \"Unknown\")}')

asyncio.run(test_recipe_discovery())
"

# Test 3: Recipe Search Parameter Extraction
python -c "
import asyncio
from ai_agent.recipe_discovery_agent import RecipeDiscoveryAgent

async def test_parameter_extraction():
    agent = RecipeDiscoveryAgent()
    
    test_cases = [
        ('Find me vegetarian pasta recipes', {'diet': 'vegetarian', 'query': 'pasta'}),
        ('I want healthy Italian chicken dishes', {'cuisine': 'italian', 'query': 'chicken'}),
        ('Show me quick dinner ideas under 30 minutes', {'maxReadyTime': 30, 'query': 'dinner'})
    ]
    
    print('Testing Recipe Parameter Extraction:')
    for message, expected_params in test_cases:
        try:
            params = await agent.extract_search_parameters(message)
            print(f'✅ \"{message}\"')
            print(f'   Extracted: {params}')
            
            # Check if key parameters were extracted
            for key in expected_params:
                if key in params:
                    print(f'   ✅ Found {key}: {params[key]}')
                else:
                    print(f'   ⚠️  Missing {key}')
        except Exception as e:
            print(f'❌ \"{message}\" failed: {e}')
        print('---')

asyncio.run(test_parameter_extraction())
"

# Test 4: End-to-End Recipe Discovery
python -c "
import requests

recipe_messages = [
    'Find me chicken recipes',
    'I want vegetarian pasta',
    'Show me healthy Italian dishes',
    'Find quick dinner ideas'
]

print('Testing End-to-End Recipe Discovery:')
for message in recipe_messages:
    chat_data = {
        'content': message,
        'user_context': {'dietary_preferences': ['healthy']}
    }
    
    response = requests.post('http://localhost:3000/api/chat', json=chat_data)
    
    if response.status_code == 200:
        data = response.json()
        print(f'✅ \"{message}\"')
        print(f'   Response: {data[\"conversational_response\"][:100]}...')
        actions = data.get('actions', [])
        if actions and actions[0].get('type') == 'find_recipe':
            recipes = actions[0].get('parameters', {}).get('recipes', [])
            print(f'   Found {len(recipes)} recipes')
        else:
            print(f'   No recipes in response')
    else:
        print(f'❌ \"{message}\" failed: {response.status_code}')
    print('---')
"
```

**✅ SUCCESS CRITERIA FOR STEP 9:**
- Spoonacular API returns recipe results successfully
- Recipe discovery agent extracts search parameters correctly
- GPT-4 agent returns properly formatted recipe responses
- End-to-end recipe discovery works through chat
- Recipes are returned in expected format for iOS app
- Different recipe search types work (cuisine, diet, time constraints)

**🛑 STOP HERE UNTIL ALL TESTS PASS. DO NOT PROCEED TO STEP 10.**

---

### 🎯 STEP 10: 95% Accuracy Testing (Week 7)
**Goal**: Achieve and verify 95% AI accuracy across all test scenarios

**🛑 DO NOT PROCEED TO PHASE 3 UNTIL 95% ACCURACY IS ACHIEVED**

#### MANDATORY COMPREHENSIVE TESTING:
```bash
# Test Suite: 50 Diverse Scenarios
python create_test_suite.py  # Creates comprehensive test file

# Run full test suite
python -c "
import asyncio
import requests
from datetime import date, timedelta

async def run_comprehensive_test_suite():
    test_scenarios = [
        # Basic meal management (20 tests)
        ('Add chicken parmesan to Tuesday dinner', 'meal_management', 'schedule_meal'),
        ('Schedule pasta for Monday lunch', 'meal_management', 'schedule_meal'),
        ('Remove Wednesday breakfast', 'meal_management', 'delete_scheduled_meal'),
        ('Put salmon on Friday dinner', 'meal_management', 'schedule_meal'),
        ('Add chicken to my cart', 'meal_management', 'add_to_cart'),
        
        # Recipe discovery (20 tests)  
        ('Find me chicken recipes', 'recipe_discovery', 'find_recipe'),
        ('Show me vegetarian pasta', 'recipe_discovery', 'find_recipe'),
        ('I want healthy Italian food', 'recipe_discovery', 'find_recipe'),
        ('Find quick dinner ideas', 'recipe_discovery', 'find_recipe'),
        ('What can I make with tomatoes', 'recipe_discovery', 'find_recipe'),
        
        # Complex scenarios (10 tests)
        ('Plan Italian food this week', 'meal_management', 'schedule_meal'),
        ('Find me 3 chicken recipes and add them to cart', 'mixed', 'multiple'),
        ('Schedule the pasta recipe for tomorrow', 'meal_management', 'schedule_meal'),
        ('Add all my scheduled meals to cart', 'meal_management', 'add_to_cart'),
        ('Generate shopping list for this week', 'meal_management', 'generate_list')
    ]
    
    results = {'total': 0, 'correct': 0, 'failed': []}
    
    for message, expected_intent, expected_action in test_scenarios:
        results['total'] += 1
        
        try:
            chat_data = {
                'content': message,
                'user_context': {
                    'saved_meals': ['chicken parmesan', 'pasta', 'salmon', 'salad'],
                    'scheduled_meals': [],
                    'dietary_preferences': []
                }
            }
            
            response = requests.post('http://localhost:3000/api/chat', json=chat_data)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if response makes sense
                if 'conversational_response' in data and len(data['conversational_response']) > 10:
                    # Check if correct actions were generated for action-based tests
                    if expected_action != 'multiple' and 'actions' in data:
                        actions = data['actions']
                        if expected_action == 'find_recipe':
                            success = any(action.get('type') == 'find_recipe' for action in actions)
                        elif expected_action == 'schedule_meal':
                            success = any(action.get('type') == 'schedule_meal' for action in actions)
                        else:
                            success = len(actions) > 0  # At least some action
                    else:
                        success = True  # Response exists
                    
                    if success:
                        results['correct'] += 1
                        print(f'✅ \"{message}\"')
                    else:
                        results['failed'].append((message, 'Wrong action type'))
                        print(f'❌ \"{message}\" - Wrong action')
                else:
                    results['failed'].append((message, 'Poor response'))
                    print(f'❌ \"{message}\" - Poor response')
            else:
                results['failed'].append((message, f'HTTP {response.status_code}'))
                print(f'❌ \"{message}\" - HTTP error')
                
        except Exception as e:
            results['failed'].append((message, str(e)))
            print(f'❌ \"{message}\" - Exception: {e}')
    
    accuracy = (results['correct'] / results['total']) * 100
    print(f'\n📊 ACCURACY RESULTS:')
    print(f'Total tests: {results[\"total\"]}')
    print(f'Passed: {results[\"correct\"]}')
    print(f'Failed: {len(results[\"failed\"])}')
    print(f'Accuracy: {accuracy:.1f}%')
    
    if accuracy >= 95:
        print('✅ 95% ACCURACY ACHIEVED - READY FOR PHASE 3')
    else:
        print('❌ ACCURACY BELOW 95% - MUST DEBUG BEFORE PROCEEDING')
        print('\nFailed tests:')
        for message, error in results['failed'][:5]:  # Show first 5 failures
            print(f'  - \"{message}\": {error}')
    
    return accuracy >= 95

success = asyncio.run(run_comprehensive_test_suite())
"
```

**✅ SUCCESS CRITERIA FOR STEP 10:**
- 95% or higher accuracy across all 50 test scenarios
- AI correctly classifies intent for 90%+ of messages
- AI generates appropriate actions for 90%+ of action-based requests
- Error handling works gracefully for edge cases
- Performance: Average response time under 3 seconds
- No system crashes or unhandled exceptions

**🛑 CRITICAL CHECKPOINT: DO NOT PROCEED TO PHASE 3 UNTIL 95% ACCURACY IS ACHIEVED AND VERIFIED**

---

## 🎯 PHASE 3: ADVANCED FEATURES (Week 8-10)
**Only proceed here after achieving 95% accuracy in Phase 2**

This phase will add:
- Conversation continuity
- Multi-action processing
- Recipe saving workflow
- Shopping list intelligence
- Advanced context management

**Each week in Phase 3 will follow the same explicit testing pattern established above.**

---

## Critical Success Checkpoints

### ✅ Checkpoint 1: iOS Foundation (COMPLETED)
**Status**: ACHIEVED - Working meal planning app ready for AI

### 🎯 Checkpoint 2: Basic AI Integration (Week 6)
**Must Have**: iOS app successfully controlled by AI for basic operations
**Test**: "Add chicken to Tuesday" works end-to-end (voice → AI → schedule → visible in iOS)

### 🎯 Checkpoint 3: 95% AI Accuracy (Week 7)
**Must Have**: 95% accuracy on 50 diverse test scenarios
**Test**: Comprehensive test suite passes with 47+ successful scenarios

### 🎯 Checkpoint 4: Advanced Features (Week 10)
**Must Have**: Complete AI meal planning workflow with advanced capabilities
**Test**: Complex multi-action conversations work reliably

---

## Red Flags to Watch For:
- 🚨 **Any test failing** - STOP and debug before proceeding
- 🚨 **AI accuracy dropping below 90%** - Fix before adding complexity
- 🚨 **iOS integration breaking** - Critical foundation issue
- 🚨 **API response times over 5 seconds** - Performance problem
- 🚨 **Data corruption or loss** - Storage integrity issue

**Remember**: Test everything thoroughly at each step. The explicit testing approach ensures you always have a working system and can debug issues quickly.