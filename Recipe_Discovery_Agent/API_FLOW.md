# Recipe Discovery Agent - API Flow Documentation

## APIs Used

1. **SerpAPI** - Web search for recipe URLs
2. **OpenAI GPT-3.5-turbo** - Lightweight LLM for search result reranking
3. **Custom Parsers** - Direct HTML scraping for top 4 sites
4. **FireCrawl API** - Fallback scraping with LLM extraction for other sites
5. **OpenAI GPT-4o** - Main agent LLM for conversation and decision making

## API Call Timeline & Flow

### Phase 1: Search
**When:** User provides recipe request
**API:** SerpAPI
**Purpose:** Search web for recipe URLs from prioritized sites
```
User Input → SerpAPI Search → 30 recipe URLs returned
```

### Phase 2: Reranking
**When:** After receiving search results
**API:** OpenAI GPT-3.5-turbo
**Purpose:** Intelligently rerank results based on user query match
```
30 URLs → LLM Reranking → Top 10 URLs selected
```

### Phase 3: Scraping
**When:** After selecting top recipes
**APIs:** Custom Parsers OR FireCrawl
**Purpose:** Extract structured recipe data

#### For priority sites (parallel calls):
```
allrecipes.com URL → Custom Parser → Recipe Data
simplyrecipes.com URL → Custom Parser → Recipe Data  
eatingwell.com URL → Custom Parser → Recipe Data
foodnetwork.com URL → Custom Parser → Recipe Data
```

#### For other sites:
```
other site URL → FireCrawl LLM Extract → Recipe Data
```

### Phase 4: Agent Processing
**When:** After scraping recipe data
**API:** OpenAI GPT-4o (via Pydantic AI)
**Purpose:** Analyze recipes, filter based on user preferences, generate response
```
Recipe Data → Agent Analysis → Final 3-5 recipes selected
```

## Data Flow Summary

1. **User Query** → Agent
2. Agent → **SerpAPI** (search for recipes)
3. Search Results → **GPT-3.5** (rerank by relevance)  
4. Top URLs → **Custom Parsers/FireCrawl** (extract recipe data)
5. Recipe Data → **Agent (GPT-4o)** (analyze & select best matches)
6. Agent → **User Response** (with recipe recommendations + source URLs)

## Compliance Notes

- **No recipe instructions stored** - Only extracted for agent analysis
- **No caching** - Fresh searches for each request
- **Source attribution** - Always include original recipe URL for "View Recipe" button
- **User data isolation** - Future implementation will silo data per user