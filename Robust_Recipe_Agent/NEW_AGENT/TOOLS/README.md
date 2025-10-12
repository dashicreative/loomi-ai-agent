# Recipe Discovery Agent - Tools

This directory contains all the tools for the Robust Recipe Agent, organized for maintainability and testing.

## Structure

```
TOOLS/
├── src/                    # Source code for all tools
│   ├── __init__.py        # Package initialization  
│   └── web_search_tool.py # WebSearchTool implementation
├── test/                   # Unit tests for all tools
│   ├── __init__.py        # Test package initialization
│   └── test_web_search_tool.py # WebSearchTool tests
├── run_tests.py           # Test runner for all tools
└── README.md              # This file
```

## Running Tests

### Test Individual Tools
```bash
# Test just the web search tool
cd test/
python test_web_search_tool.py
```

### Test All Tools
```bash
# Run all tool tests
python run_tests.py
```

## Adding New Tools

1. **Create the tool**: Add new tool to `src/` directory
2. **Create tests**: Add corresponding test file to `test/` directory
3. **Update imports**: Add tool to `src/__init__.py`
4. **Test**: Run `python run_tests.py` to verify

## Tool Standards

Each tool should:
- ✅ Be fully self-contained with minimal dependencies
- ✅ Include comprehensive error handling
- ✅ Return timing information in `_timing` field
- ✅ Have dedicated unit tests covering edge cases
- ✅ Support the agent-callable wrapper pattern

## Environment Setup

Tools may require API keys in environment variables:
- `SERPAPI_KEY` - For SerpAPI web search
- `GOOGLE_SEARCH_KEY` and `GOOGLE_SEARCH_ENGINE_ID` - For Google Custom Search
- Add other keys as needed for new tools

## Current Tools

### 1. WebSearchTool
**Purpose**: Flexible web search for recipe URLs with strategy control

**Key Features**:
- Multiple search strategies (priority_only, mixed, broad)
- Regional and time-based filtering
- Automatic blocked site filtering
- Timing-aware recommendations

**Usage**:
```python
from src.web_search_tool import WebSearchTool

tool = WebSearchTool(serpapi_key="your_key")
result = await tool.search(
    query="chocolate cake",
    search_strategy="mixed",
    result_count=20
)
```

### 2. URLClassificationTool
**Purpose**: Classify URLs as recipe pages or list/collection pages

**Key Features**:
- 5KB lightweight content sampling (not full HTML)
- LLM classification with deterministic fallback
- Enriched URL objects with classification metadata
- Parallel processing for efficiency

**Usage**:
```python
from src.url_classification_tool import URLClassificationTool

tool = URLClassificationTool(openai_key="your_key")
result = await tool.classify_urls(urls_from_search)
classified_urls = result["classified_urls"]  # Enriched with type metadata
```

### 3. RecipeParsingTool  
**Purpose**: Parse individual recipe pages to extract complete recipe data

**Key Features**:
- Multi-tiered extraction (JSON-LD → Structured HTML)
- Parallel processing of multiple URLs
- Handles recipe URLs only (auto-filters)
- Exact copy of proven hybrid_recipe_parser logic

**Usage**:
```python
from src.recipe_parsing_tool import RecipeParsingTool

tool = RecipeParsingTool(openai_key="your_key")
result = await tool.parse_recipes(
    urls=recipe_urls,  # URLs with type='recipe'
    parsing_depth="standard",
    timeout_seconds=25
)
```

### 4. ListParsingTool
**Purpose**: Extract and parse recipes from list/collection pages  

**Key Features**:
- Extracts recipe URLs from list pages using ListParser
- Automatically parses extracted recipes
- Handles list URLs only (auto-filters) 
- Exact copy of backlog list processing logic

**Usage**:
```python
from src.list_parsing_tool import ListParsingTool

tool = ListParsingTool(openai_key="your_key")
result = await tool.parse_list_pages(
    urls=list_urls,  # URLs with type='list'
    max_recipes_per_list=10
)
```

## Tool Flow Architecture

```
1. WebSearchTool → Raw URLs + metadata
2. URLClassificationTool → Enriched URLs (type='recipe'|'list')  
3a. RecipeParsingTool → Parse recipe URLs → Complete recipes
3b. ListParsingTool → Extract from lists → Parse recipes → Complete recipes
4. [Future] RequirementsVerificationTool → Filter by constraints
5. [Future] RelevanceRankingTool → Final ranking
```

## Future Tools

- RequirementsVerificationTool - Verify recipes meet user constraints
- RelevanceRankingTool - Rank recipes by relevance to query
- QualityAssessmentTool - Assess recipe quality before processing
- UserCommunicationTool - Generate user-friendly explanations