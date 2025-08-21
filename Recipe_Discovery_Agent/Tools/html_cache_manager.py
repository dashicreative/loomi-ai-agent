"""
HTML Cache Manager for batch fetching and reuse.
Eliminates redundant HTML fetches and enables parallel processing.
"""
from typing import Dict, List, Optional
import httpx
import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class CachedHTML:
    """Represents cached HTML content"""
    url: str
    html: str
    fetched_at: datetime
    status_code: int

class HTMLCacheManager:
    """Manages HTML fetching and caching with domain-specific rate limiting"""
    
    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: int = 30,
        max_retries: int = 2,
        firecrawl_key: Optional[str] = None
    ):
        self.cache: Dict[str, CachedHTML] = {}
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_retries = max_retries
        self.firecrawl_key = firecrawl_key
        
        # Conservative rate limits for recipe sites to avoid being blocked
        self.domain_limits = {
            "default": 5,  # Default concurrent requests per domain
            "allrecipes.com": 3,
            "foodnetwork.com": 3,
            "simplyrecipes.com": 4,
            "eatingwell.com": 3,
            "delish.com": 3,
            "seriouseats.com": 4,
            "foodandwine.com": 3,
            "thepioneerwoman.com": 3,
            "food.com": 4,
            "epicurious.com": 3,
            "cookinglight.com": 3,
            "myrecipes.com": 3,
            "tasteofhome.com": 3,
            "bettycrocker.com": 3,
            "yummly.com": 4
        }
        
        # Track fetch statistics
        self.stats = {
            "total_attempted": 0,
            "successful": 0,
            "failed": 0,
            "cache_hits": 0,
            "firecrawl_fallbacks": 0
        }
    
    async def batch_fetch(self, urls: List[str]) -> Dict[str, Optional[str]]:
        """
        Fetch multiple URLs in parallel with domain-specific rate limiting.
        Returns dict mapping URL to HTML content (or None if failed).
        """
        # Filter out already cached URLs
        urls_to_fetch = []
        results = {}
        
        for url in urls:
            if self.has_html(url):
                results[url] = self.get_html(url)
                self.stats["cache_hits"] += 1
                logger.debug(f"Cache hit for {url}")
            else:
                urls_to_fetch.append(url)
        
        if not urls_to_fetch:
            logger.info(f"All {len(urls)} URLs served from cache")
            return results
        
        logger.info(f"Fetching {len(urls_to_fetch)} URLs ({len(results)} from cache)")
        
        # Group URLs by domain
        from urllib.parse import urlparse
        domain_groups = {}
        for url in urls_to_fetch:
            domain = urlparse(url).netloc
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(url)
        
        # Log domain distribution
        for domain, domain_urls in domain_groups.items():
            logger.debug(f"Domain {domain}: {len(domain_urls)} URLs")
        
        # Fetch with domain-specific concurrency
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = []
            for domain, domain_urls in domain_groups.items():
                limit = self.domain_limits.get(domain, self.domain_limits["default"])
                logger.debug(f"Using concurrency limit {limit} for {domain}")
                
                # Create semaphore for this domain
                semaphore = asyncio.Semaphore(limit)
                
                # Create tasks for this domain's URLs
                for url in domain_urls:
                    task = self._fetch_with_limit(client, url, semaphore)
                    tasks.append(task)
            
            # Execute all tasks
            fetch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for url, result in zip(urls_to_fetch, fetch_results):
                self.stats["total_attempted"] += 1
                
                if isinstance(result, Exception):
                    # Try FireCrawl fallback if available
                    if self.firecrawl_key:
                        logger.info(f"Trying FireCrawl fallback for {url}")
                        firecrawl_result = await self._firecrawl_fallback(url)
                        if firecrawl_result:
                            self.stats["successful"] += 1
                            self.stats["firecrawl_fallbacks"] += 1
                            results[url] = firecrawl_result
                            # Cache FireCrawl results too
                            self.cache[url] = CachedHTML(
                                url=url,
                                html=firecrawl_result,
                                fetched_at=datetime.now(),
                                status_code=200
                            )
                            logger.info(f"FireCrawl fallback successful for {url}")
                        else:
                            self.stats["failed"] += 1
                            results[url] = None
                            logger.warning(f"Both direct fetch and FireCrawl failed for {url}")
                    else:
                        self.stats["failed"] += 1
                        results[url] = None
                        logger.warning(f"Failed to fetch {url}: {str(result)}")
                else:
                    if result:
                        self.stats["successful"] += 1
                        results[url] = result
                        # Cache successful fetches
                        self.cache[url] = CachedHTML(
                            url=url,
                            html=result,
                            fetched_at=datetime.now(),
                            status_code=200
                        )
                        logger.debug(f"Successfully fetched and cached {url}")
                    else:
                        # Try FireCrawl fallback if available
                        if self.firecrawl_key:
                            logger.info(f"Trying FireCrawl fallback for {url} (empty response)")
                            firecrawl_result = await self._firecrawl_fallback(url)
                            if firecrawl_result:
                                self.stats["successful"] += 1
                                self.stats["firecrawl_fallbacks"] += 1
                                results[url] = firecrawl_result
                                # Cache FireCrawl results too
                                self.cache[url] = CachedHTML(
                                    url=url,
                                    html=firecrawl_result,
                                    fetched_at=datetime.now(),
                                    status_code=200
                                )
                                logger.info(f"FireCrawl fallback successful for {url}")
                            else:
                                self.stats["failed"] += 1
                                results[url] = None
                                logger.warning(f"Both direct fetch and FireCrawl failed for {url}")
                        else:
                            self.stats["failed"] += 1
                            results[url] = None
                            logger.warning(f"Failed to fetch {url}: Empty response")
        
        # Log fetch statistics
        success_rate = (self.stats["successful"] / self.stats["total_attempted"] * 100 
                       if self.stats["total_attempted"] > 0 else 0)
        logger.info(f"Fetch stats - Success: {self.stats['successful']}, "
                   f"Failed: {self.stats['failed']}, "
                   f"Cache hits: {self.stats['cache_hits']}, "
                   f"FireCrawl fallbacks: {self.stats['firecrawl_fallbacks']}, "
                   f"Success rate: {success_rate:.1f}%")
        
        return results
    
    async def _fetch_with_limit(
        self,
        client: httpx.AsyncClient,
        url: str,
        semaphore: asyncio.Semaphore
    ) -> Optional[str]:
        """Fetch single URL with semaphore limiting"""
        async with semaphore:
            for attempt in range(self.max_retries):
                try:
                    logger.debug(f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})")
                    response = await client.get(url, follow_redirects=True, timeout=15.0)
                    
                    if response.status_code == 200:
                        return response.text
                    elif response.status_code >= 500 and attempt < self.max_retries - 1:
                        # Retry on server errors
                        wait_time = 2 ** attempt
                        logger.debug(f"Server error {response.status_code} for {url}, retrying in {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.debug(f"HTTP {response.status_code} for {url}")
                        return None
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return None
                except Exception as e:
                    logger.warning(f"Error fetching {url}: {str(e)} (attempt {attempt + 1})")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return None
        return None
    
    async def _firecrawl_fallback(self, url: str) -> Optional[str]:
        """Fallback to FireCrawl for difficult URLs"""
        if not self.firecrawl_key:
            return None
        
        try:
            logger.debug(f"FireCrawl fallback for {url}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={
                        "Authorization": f"Bearer {self.firecrawl_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "url": url,
                        "formats": ["html"],
                        "onlyMainContent": False,
                        "includeTags": ["a", "img", "div", "span", "h1", "h2", "h3", "p"]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data", {}).get("html"):
                        return data["data"]["html"]
                
                logger.warning(f"FireCrawl API returned status {response.status_code} for {url}")
                return None
                
        except Exception as e:
            logger.warning(f"FireCrawl fallback failed for {url}: {str(e)}")
            return None
    
    def get_html(self, url: str) -> Optional[str]:
        """Get HTML from cache if available"""
        cached = self.cache.get(url)
        return cached.html if cached else None
    
    def has_html(self, url: str) -> bool:
        """Check if HTML is cached"""
        return url in self.cache
    
    def get_stats(self) -> Dict[str, int]:
        """Get fetch statistics"""
        return self.stats.copy()
    
    def clear_cache(self):
        """Clear the HTML cache"""
        self.cache.clear()
        logger.debug("Cache cleared")