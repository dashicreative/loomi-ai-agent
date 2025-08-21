# Recipe Discovery Agent

**AI-powered recipe discovery system designed for iOS app integration with structured data output and intelligent ranking.**

## Overview

The Recipe Discovery Agent transforms natural language queries like *"breakfast recipes with 30g+ protein"* into curated recipe collections with structured ingredients, nutrition facts, and cooking instructions optimized for mobile app consumption.

## Query-to-Output Flow

### 🔍 **User Input**
```
"Find me breakfast recipes with 30g of protein or more"
```

### 🎯 **Agent Processing Pipeline**

#### **Stage 1: Web Search & URL Discovery**
- **SerpAPI Integration**: Queries Google for ~40 recipe URLs
- **Social Media Filtering**: Removes Reddit, YouTube, Instagram, Pinterest, etc.
- **Output**: ~30 high-quality recipe website URLs

#### **Stage 2: Smart URL Expansion**
The system intelligently processes different types of URLs:

**Individual Recipes** → Kept as-is
- Example: `allrecipes.com/recipe/chocolate-chip-cookies`

**List Pages** → Extract individual recipe URLs using **Multi-Tiered List Parser**:
- **Tier 1**: JSON-LD structured data parsing (most reliable)
- **Tier 2**: Recipe card structure analysis (context-aware)
- **Tier 3**: Enhanced link analysis with confidence scoring
- Example: `"25 Best Breakfast Recipes"` → Extracts 5 individual recipe URLs

**Technical**: Direct HTTP scraping first, FireCrawl fallback for blocked sites
- **Output**: 18-60 individual recipe URLs ready for parsing

#### **Stage 3: Initial LLM Ranking**
- **GPT-3.5 Turbo** ranks URLs by title/snippet relevance to query
- Fast relevance filtering before expensive parsing
- **Output**: All URLs ranked by initial relevance

#### **Stage 4: Deep Recipe Parsing**
Extracts structured data from top 25 URLs using:

**Priority Site Parsers** (AllRecipes, FoodNetwork, etc.)
- Custom JSON-LD + HTML fallback parsers
- **Extracts**: Title, ingredients, instructions, cook time, servings, image, **nutrition**

**FireCrawl Universal Parser** (other sites)
- AI-powered extraction with compliance handling
- **Technical**: LLM-based structured data extraction

**Structured Output Format**:
```json
{
  "title": "High-Protein Greek Yogurt Pancakes",
  "ingredients": [
    {
      "quantity": "1",
      "unit": "cup", 
      "ingredient": "Greek yogurt",
      "original": "1 cup Greek yogurt"
    }
  ],
  "nutrition": [
    {
      "name": "protein",
      "amount": "32",
      "unit": "g", 
      "original": "32g protein"
    },
    {
      "name": "calories", 
      "amount": "285",
      "unit": "kcal",
      "original": "285 calories"
    }
  ],
  "instructions": ["Step 1...", "Step 2..."],
  "cook_time": "15 minutes",
  "servings": "4",
  "image_url": "https://...",
  "source_url": "https://..."
}
```

#### **Stage 5: Advanced LLM Re-Ranking**
**GPT-3.5 Turbo** performs intelligent content-based ranking using:

**Critical Requirements Analysis**:
- **Required Inclusions**: "blueberry cheesecake" → must contain blueberry
- **Exclusions**: "without cane sugar" → check ingredients for absence
- **Nutrition Constraints**: "30g protein" → analyze actual nutrition data
- **Equipment Requirements**: "no-bake", "slow cooker", "air fryer"
- **Cooking Methods**: "grilled", "baked", "fried"

**Technical**: Full ingredient lists, nutrition facts, and instruction analysis
- **Output**: 5 perfectly matched recipes ranked by true relevance

### 📱 **iOS App Output**

#### **Agent Response Format**
```json
{
  "response": "I've found amazing high-protein breakfast recipes...",
  "recipes": [
    {
      "title": "High-Protein Greek Yogurt Pancakes",
      "ingredients": [...structured ingredient objects...],
      "nutrition": [...structured nutrition objects...], 
      "readyInMinutes": "15",
      "servings": "4",
      "image": "https://...",
      "sourceUrl": "https://..."
    }
  ],
  "totalResults": 5,
  "searchQuery": "breakfast recipes with 30g+ protein",
  "_failed_parse_report": {
    "total_failed": 3,
    "content_scraping_failures": 1,
    "recipe_parsing_failures": 2,
    "failed_urls": [...business analytics...]
  }
}
```

#### **Key iOS Integration Features**
- **Structured Ingredients**: Separate quantity, unit, ingredient for recipe scaling
- **Nutrition Data**: Required calories, protein, fat, carbs for dietary tracking
- **Instruction Compliance**: Instructions available for analysis but not displayed (copyright compliance)
- **Source Attribution**: Always links back to original recipe source
- **Failure Reporting**: Business analytics for parser improvements

## Technical Architecture

### **Core Components**
- **Discovery_Agent.py**: Pydantic AI agent with single tool interface
- **Tools/Tools.py**: Main pipeline orchestration with 5-stage processing
- **Detailed_Recipe_Parsers/**: Custom parsers for 10+ major recipe sites
- **List Parser**: Advanced multi-tiered list page processing
- **Nutrition Parser**: Structured nutrition data extraction

### **Error Handling & Resilience**
- **Two Failure Point Tracking**: Content scraping failures vs recipe parsing failures
- **FireCrawl Rate Limit Management**: Direct HTTP first, API fallback
- **Graceful Degradation**: Continue with successful parses even if some fail
- **Business Analytics**: Detailed failure reporting for system improvements

### **Compliance Features**
- **robots.txt Respect**: Automatic compliance checking with crawl delays
- **Content Attribution**: Always preserve source URLs for proper attribution
- **Instruction Handling**: Extract for analysis only, never display (fair use)
- **Rate Limiting**: Respectful scraping with fallback mechanisms

## Query Examples

**Nutrition-Specific**:
- *"breakfast with 30g protein"* → Nutrition-aware ranking
- *"low carb dinner under 400 calories"* → Multi-constraint filtering

**Dietary Restrictions**:  
- *"pasta without gluten"* → Exclusion-based ingredient filtering
- *"vegan dessert recipes"* → Inclusion requirement matching

**Equipment-Specific**:
- *"slow cooker chicken recipes"* → Equipment requirement matching
- *"no-bake desserts"* → Cooking method analysis

**Complex Queries**:
- *"quick healthy lunch under 30 minutes"* → Time + dietary constraint analysis

## Performance Characteristics

- **Average Query Time**: 15-30 seconds end-to-end
- **Success Rate**: 95%+ for individual recipes, 85%+ for list pages  
- **Cost Optimization**: Direct scraping reduces API costs by ~75%
- **Scalability**: Processes 25-60 URLs per query with parallel parsing

---

*Built with Pydantic AI, featuring intelligent web scraping, multi-tiered parsing, and LLM-powered relevance ranking for iOS recipe app integration.*