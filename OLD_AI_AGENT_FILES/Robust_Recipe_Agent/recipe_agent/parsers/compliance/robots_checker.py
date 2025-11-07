"""
Robots.txt compliance checking for ethical web scraping.

This module ensures we respect website robots.txt rules and crawl delays.
"""

import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from typing import Tuple

# Cache for robots.txt to avoid repeated fetches
ROBOTS_CACHE = {}


async def check_robots_txt(url: str, user_agent: str = "RecipeDiscoveryBot") -> Tuple[bool, float]:
    """
    Check if we're allowed to scrape this URL according to robots.txt
    
    COMPLIANCE: We respect robots.txt as part of ethical web scraping.
    
    Args:
        url: The URL to check
        user_agent: Our bot's user agent string
        
    Returns:
        Tuple of (is_allowed, crawl_delay_seconds)
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    # Check cache first
    if base_url in ROBOTS_CACHE:
        rp = ROBOTS_CACHE[base_url]
    else:
        # Fetch and parse robots.txt
        rp = RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        
        try:
            # Use httpx to fetch robots.txt
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/robots.txt", timeout=15.0)
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                else:
                    # If no robots.txt, assume we can crawl
                    rp.allow_all = True
        except:
            # If we can't fetch robots.txt, be conservative and allow
            # (many sites don't have robots.txt but allow scraping)
            rp.allow_all = True
        
        ROBOTS_CACHE[base_url] = rp
    
    # Check if URL is allowed
    is_allowed = rp.can_fetch(user_agent, url)
    
    # Get crawl delay if specified
    crawl_delay = rp.crawl_delay(user_agent) or 0
    
    return is_allowed, crawl_delay