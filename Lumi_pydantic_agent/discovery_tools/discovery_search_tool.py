"""
WebSearchTool - Recipe URL Discovery Tool
Searches for recipe URLs using multiple search providers with flexible parameters.
"""

import httpx
import asyncio
import time
from typing import Dict, List, Optional, Set
from datetime import datetime

# Constants - These remain deterministic
BLOCKED_SITES = {
    # Social Media & Video-Only Platforms (NEVER allow these)
    'facebook.com', 'youtube.com', 'tiktok.com', 'instagram.com', 
    'twitter.com', 'reddit.com', 'pinterest.com', 'snapchat.com', 
    'linkedin.com',
    
    # Low Quality Recipe Aggregators & Forums
    'yummly.com', 'genius.com', 'tasty.co', 'buzzfeed.com', 
    'popsugar.com', 'chowhound.com',
    
    # Meal Planning Apps (Commercial/Subscription)
    'mealime.com', 'emeals.com', 'plantoeat.com', 'bigoven.com',
    'copymethat.com', 'recipe-scrapers.com',
    
    # Shopping & E-commerce Sites
    'amazon.com', 'walmart.com', 'target.com', 'kroger.com',
    'instacart.com', 'shipt.com',
    
    # Wiki & Generic Content Sites
    'wikipedia.org', 'wikihow.com', 'ehow.com',
    
    # Sites That Block Crawlers (403 Forbidden)
    'abrightmoment.com', 'feastandwest.com', 'cooksmarts.com'
}

PRIORITY_SITES = [
    'allrecipes.com', 'simplyrecipes.com', 'seriouseats.com',
    'bonappetit.com', 'cookinglight.com', 'eatingwell.com',
    'food52.com', 'thekitchn.com', 'budgetbytes.com',
    'skinnytaste.com', 'minimalistbaker.com', 'loveandlemons.com',
    'cookieandkate.com', 'ambitiouskitchen.com', 'cafedelites.com',
    'natashaskitchen.com', 'sallysbakingaddiction.com', 'gimmesomeoven.com',
    'recipetineats.com', 'damndelicious.net'
]


class WebSearchTool:
    """
    Flexible web search tool for recipe discovery.
    Supports multiple search providers and customizable parameters.
    """
    
    def __init__(self, serpapi_key: str = None, google_key: str = None, google_cx: str = None):
        """
        Initialize with API credentials.
        At least one search provider must be configured.
        """
        self.serpapi_key = serpapi_key
        self.google_key = google_key
        self.google_cx = google_cx
        self.query_start_time = None
        
    async def search(
        self,
        query: str,
        result_count: int = 45,  # Discovery optimized: higher volume for early exit
        search_strategy: str = "mixed",  # "priority_only", "mixed", "broad" - balanced for discovery
        exclude_urls: Optional[Set[str]] = None,
        additional_blocked_sites: Optional[Set[str]] = None,
        region: str = "us",
        language: str = "en",
        time_range: Optional[str] = None,  # "d" (day), "w" (week), "m" (month), "y" (year)
        safe_search: bool = True,
    ) -> Dict:
        """
        Execute recipe search optimized for discovery mode.
        Higher volume for early exit classification, balanced strategy for variety.
        
        Args:
            query: Search query (will auto-append "recipe" if not present)
            result_count: Number of results to return (default 45 for discovery optimization)
            search_strategy: 
                - "priority_only": Only search priority recipe sites
                - "mixed": Start with priority, then expand
                - "broad": Search all sites except blocked
            exclude_urls: URLs to exclude from results (for deduplication)
            additional_blocked_sites: Extra sites to block beyond defaults
            region: Country code for regional results
            language: Language code
            time_range: Recency filter
            safe_search: Enable safe search filtering
            
        Returns:
            Dictionary with search results and metadata
        """
        # Track timing
        if not self.query_start_time:
            self.query_start_time = time.time()
        start_time = time.time()
        
        # Auto-append "recipe" if not present
        if "recipe" not in query.lower():
            query = f"{query} recipe"
        
        # Build site restrictions based on strategy
        site_filter = self._build_site_filter(search_strategy, additional_blocked_sites)
        if site_filter:
            query = f"{query} {site_filter}"
        
        # Execute search
        raw_results = await self._execute_search(
            query, result_count, region, language, time_range, safe_search
        )
        
        # Filter results
        filtered_results = self._filter_results(
            raw_results, exclude_urls, additional_blocked_sites
        )
        
        # Calculate timing
        elapsed = time.time() - self.query_start_time
        
        # Analyze distribution
        distribution = self._analyze_distribution(filtered_results)
        
        return {
            "urls": filtered_results,
            "total_found": len(filtered_results),
            "source_distribution": distribution,
            "query_used": query,
            "strategy_used": search_strategy,
            "_timing": {
                "elapsed_since_query": round(elapsed, 1),
                "elapsed_readable": f"{int(elapsed)} seconds",
                "time_status": self._get_time_status(elapsed, search_strategy),
                "recommended_action": self._get_recommended_action(elapsed, len(filtered_results))
            }
        }
    
    def _build_site_filter(self, strategy: str, additional_blocked: Optional[Set[str]]) -> str:
        """Build Google search site restrictions based on strategy."""
        all_blocked = BLOCKED_SITES.copy()
        if additional_blocked:
            all_blocked.update(additional_blocked)
        
        if strategy == "priority_only":
            # Only search priority sites
            site_includes = " OR ".join(f"site:{site}" for site in PRIORITY_SITES[:10])
            return f"({site_includes})"
        elif strategy == "broad":
            # Exclude blocked sites only
            site_excludes = " ".join(f"-site:{site}" for site in all_blocked)
            return site_excludes
        else:  # mixed
            # Prefer priority sites but don't exclude others
            # Google will naturally rank these higher
            return " ".join(f"-site:{site}" for site in all_blocked)
    
    async def _execute_search(
        self, query: str, count: int, region: str, 
        language: str, time_range: Optional[str], safe_search: bool
    ) -> List[Dict]:
        """Execute search using available providers."""
        if self.google_key and self.google_cx:
            return await self._google_search(query, count, region, language, time_range, safe_search)
        elif self.serpapi_key:
            return await self._serpapi_search(query, count, region, language, time_range)
        else:
            raise ValueError("No search provider configured. Need either Google Custom Search or SerpAPI credentials.")
    
    async def _serpapi_search(
        self, query: str, count: int, region: str, 
        language: str, time_range: Optional[str]
    ) -> List[Dict]:
        """Execute search using SerpAPI with pagination for high result counts."""
        all_results = []
        results_per_page = 10  # SerpAPI max per request
        total_pages = min((count + results_per_page - 1) // results_per_page, 10)  # Max 10 pages (100 results)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(total_pages):
                params = {
                    "api_key": self.serpapi_key,
                    "engine": "google",
                    "q": query,
                    "num": results_per_page,
                    "start": page * results_per_page,  # Pagination offset
                    "hl": language,
                    "gl": region
                }
            
                if time_range:
                    # Convert to SerpAPI format (qdr:d, qdr:w, qdr:m, qdr:y)
                    params["tbs"] = f"qdr:{time_range}"
                
                try:
                    response = await client.get("https://serpapi.com/search", params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    page_results = []
                    for item in data.get("organic_results", []):
                        page_results.append({
                            "url": item.get("link"),
                            "title": item.get("title"),
                            "snippet": item.get("snippet", ""),
                            "source": "serpapi"
                        })
                    
                    all_results.extend(page_results)
                    
                    # Break early if we have enough results or no more results
                    if len(all_results) >= count or len(page_results) < results_per_page:
                        break
                        
                except Exception as e:
                    print(f"SerpAPI search page {page + 1} failed: {e}")
                    break
                    
        return all_results[:count]  # Return only requested count
    
    async def _google_search(
        self, query: str, count: int, region: str,
        language: str, time_range: Optional[str], safe_search: bool
    ) -> List[Dict]:
        """Execute search using Google Custom Search with pagination for high result counts."""
        all_results = []
        results_per_page = 10  # Google CSE max per request
        total_pages = min((count + results_per_page - 1) // results_per_page, 10)  # Max 10 pages (100 results)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(total_pages):
                params = {
                    "key": self.google_key,
                    "cx": self.google_cx,
                    "q": query,
                    "num": results_per_page,
                    "start": page * results_per_page + 1,  # Google pagination starts at 1
                    "gl": region,
                    "hl": language,
                    "safe": "active" if safe_search else "off"
                }
            
                if time_range:
                    # Google CSE date restrict format
                    params["dateRestrict"] = f"{time_range}1"  # d1, w1, m1, y1
                
                try:
                    response = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=params
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    page_results = []
                    for item in data.get("items", []):
                        page_results.append({
                            "url": item.get("link"),
                            "title": item.get("title"),
                            "snippet": item.get("snippet", ""),
                            "source": "google_cse"
                        })
                    
                    all_results.extend(page_results)
                    
                    # Break early if we have enough results or no more results
                    if len(all_results) >= count or len(page_results) < results_per_page:
                        break
                        
                except Exception as e:
                    print(f"Google Custom Search page {page + 1} failed: {e}")
                    break
                    
        return all_results[:count]  # Return only requested count
    
    def _filter_results(
        self, results: List[Dict], 
        exclude_urls: Optional[Set[str]], 
        additional_blocked: Optional[Set[str]]
    ) -> List[Dict]:
        """Filter out blocked sites and excluded URLs with robust domain checking."""
        if not results:
            return []
        
        all_blocked = BLOCKED_SITES.copy()
        if additional_blocked:
            all_blocked.update(additional_blocked)
        
        exclude_set = exclude_urls or set()
        
        filtered = []
        filtered_count = 0
        
        for result in results:
            url = result.get("url", "")
            
            # Check if excluded first
            if url in exclude_set:
                filtered_count += 1
                continue
            
            # Extract domain from URL for robust checking
            domain = self._extract_domain(url)
            if not domain:
                filtered_count += 1
                continue  # Skip invalid URLs
            
            # Check if domain is blocked (exact match or subdomain)
            is_blocked = False
            for blocked_site in all_blocked:
                if domain == blocked_site or domain.endswith('.' + blocked_site):
                    is_blocked = True
                    print(f"🚫 BLOCKED: {url} (matches {blocked_site})")
                    break
            
            if is_blocked:
                filtered_count += 1
                continue
            
            # Only block if it's a video-only platform (domain-based blocking handles this)
            # Recipe sites with supplementary videos are OK
            filtered.append(result)
        
        if filtered_count > 0:
            print(f"🛡️ Filtered out {filtered_count} blocked/invalid results")
        
        return filtered
    
    def _extract_domain(self, url: str) -> str:
        """Extract clean domain from URL for filtering."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url.lower())
            domain = parsed.netloc
            
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
                
            return domain
        except:
            return ""
    
    def _analyze_distribution(self, results: List[Dict]) -> Dict:
        """Analyze the distribution of results across priority/other sites."""
        priority_count = 0
        other_count = 0
        
        for result in results:
            url = result.get("url", "").lower()
            if any(priority in url for priority in PRIORITY_SITES):
                priority_count += 1
            else:
                other_count += 1
        
        return {
            "priority": priority_count,
            "other": other_count,
            "total": len(results)
        }
    
    def _get_time_status(self, elapsed: float, strategy: str) -> str:
        """Determine time status based on elapsed time and search type."""
        # Assuming search type budgets (can be parameterized)
        budgets = {
            "priority_only": 30,
            "mixed": 60,
            "broad": 90
        }
        budget = budgets.get(strategy, 60)
        
        if elapsed > budget:
            return "exceeded"
        elif elapsed > budget * 0.5:
            return "approaching_limit"
        else:
            return "on_track"
    
    def _get_recommended_action(self, elapsed: float, result_count: int) -> str:
        """Recommend next action based on time and results."""
        if elapsed > 60:
            return "ask_user"
        elif elapsed > 30 and result_count < 10:
            return "pivot"
        elif result_count < 5:
            return "expand"
        else:
            return "continue"


# For agent integration
async def execute_web_search_tool(context: Dict) -> Dict:
    """
    Agent-callable wrapper for WebSearchTool.
    
    Expected context:
    - input: Dict with search parameters
    - deps: Dependencies with API keys
    """
    input_params = context.get("input", {})
    deps = context.get("deps", {})
    
    # Initialize tool
    tool = WebSearchTool(
        serpapi_key=deps.get("serpapi_key"),
        google_key=deps.get("google_key"),
        google_cx=deps.get("google_cx")
    )
    
    # Execute search
    return await tool.search(
        query=input_params.get("query"),
        result_count=input_params.get("result_count", 30),
        search_strategy=input_params.get("search_strategy", "mixed"),
        exclude_urls=input_params.get("exclude_urls"),
        additional_blocked_sites=input_params.get("additional_blocked_sites"),
        region=input_params.get("region", "us"),
        language=input_params.get("language", "en"),
        time_range=input_params.get("time_range"),
        safe_search=input_params.get("safe_search", True)
    )