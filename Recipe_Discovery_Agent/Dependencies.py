from dataclasses import dataclass


@dataclass
class RecipeDeps:
    """Dependencies for the Recipe Discovery Agent"""
    serpapi_key: str  # SerpAPI key for web search
    firecrawl_key: str  # FireCrawl API key for fallback scraping
    openai_key: str  # OpenAI API key for LLM reranking
    google_search_key: str  # Google Custom Search API key for fallback search
    google_search_engine_id: str  # Google Custom Search Engine ID