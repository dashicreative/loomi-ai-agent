"""
ListParsingTool - Recipe List Page Processing  
Exact copy of backlog list processing logic from batch_processor.py
"""

import asyncio
import httpx
import time
from typing import List, Dict
import logfire


class ListParsingBasic:
    """Simplified version of ListParser for extracting recipe URLs."""
    
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
    
    async def extract_recipe_urls(self, url: str, html_content: str, max_urls: int = 10) -> List[Dict]:
        """
        PLACEHOLDER - will copy exact ListParser.extract_recipe_urls logic.
        For now, basic implementation.
        """
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        import re
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Basic recipe link extraction
            recipe_links = []
            
            # Find all links that look like recipes
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href:
                    full_url = urljoin(url, href)
                    title = link.get_text().strip()
                    
                    # Basic recipe URL patterns
                    if ('/recipe/' in full_url.lower() or 
                        'recipe' in title.lower()):
                        
                        recipe_links.append({
                            'url': full_url,
                            'title': title,
                            'snippet': '',
                            'source': 'list_extraction',
                            'type': 'recipe'
                        })
                        
                        if len(recipe_links) >= max_urls:
                            break
            
            return recipe_links
            
        except Exception as e:
            print(f"List extraction failed: {e}")
            return []


class ListParsingTool:
    """
    List page parsing tool.
    Exact copy of backlog list processing logic with multiple URL support.
    """
    
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
        self.query_start_time = None
    
    async def extract_recipe_urls_from_lists(
        self,
        urls: List[Dict],  # Enriched URL objects from classification
        max_recipes_per_list: int = 10,
        list_fetch_timeout: int = 15
    ) -> Dict:
        """
        Extract individual recipe URLs from multiple list pages.
        Returns enriched URL objects for agent to then parse with RecipeParsingTool.
        
        Args:
            urls: List of enriched URL objects (must have type='list')  
            max_recipes_per_list: Max recipe URLs to extract from each list
            list_fetch_timeout: Timeout for fetching list page HTML
            
        Returns:
            Dict with extracted recipe URL objects (not parsed recipes)
        """
        if not self.query_start_time:
            self.query_start_time = time.time()
        
        start_time = time.time()
        
        if not urls:
            return self._empty_result()
        
        # Filter to only list URLs
        list_urls = [url_obj for url_obj in urls if url_obj.get('type') == 'list']
        
        if not list_urls:
            return {
                "extracted_recipes": [],
                "failed_lists": [],
                "skipped_urls": urls,
                "processing_stats": {
                    "lists_attempted": 0,
                    "lists_successful": 0,
                    "recipes_extracted": 0,
                    "recipes_parsed": 0
                },
                "_timing": self._get_timing_info(time.time() - self.query_start_time, len(urls))
            }
        
        print(f"📋 Extracting recipe URLs from {len(list_urls)} list pages...")
        
        all_extracted_recipe_urls = []
        failed_lists = []
        
        # Process each list URL to extract recipe URLs only
        for list_url_obj in list_urls:
            url = list_url_obj.get('url', '')
            
            try:
                # Fetch list page HTML
                async with httpx.AsyncClient(timeout=float(list_fetch_timeout)) as client:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    html_content = response.text
                
                # Extract recipe URLs from list page
                intelligent_parser = ListParsingBasic(self.openai_key)
                extracted_recipe_urls = await intelligent_parser.extract_recipe_urls(
                    url, 
                    html_content, 
                    max_urls=max_recipes_per_list
                )
                
                # Add to collection (these are URL objects, not parsed recipes)
                if extracted_recipe_urls:
                    for recipe_url_obj in extracted_recipe_urls:
                        # Mark the source list for traceability
                        recipe_url_obj['extracted_from_list'] = url
                        recipe_url_obj['list_title'] = list_url_obj.get('title', '')
                        all_extracted_recipe_urls.append(recipe_url_obj)
            
            except Exception as e:
                # Track failed list expansion
                failed_lists.append({
                    "url_object": list_url_obj,
                    "error": str(e),
                    "failure_point": "List_URL_Fetch_Failure"
                })
        
        # Calculate results
        elapsed = time.time() - self.query_start_time
        
        return {
            "extracted_recipe_urls": all_extracted_recipe_urls,  # URL objects, not parsed recipes
            "failed_lists": failed_lists,
            "processing_stats": {
                "lists_attempted": len(list_urls),
                "lists_successful": len(list_urls) - len(failed_lists),
                "recipe_urls_extracted": len(all_extracted_recipe_urls),
                "avg_urls_per_list": round(len(all_extracted_recipe_urls) / len(list_urls), 1) if list_urls else 0
            },
            "_timing": self._get_timing_info(elapsed, len(list_urls))
        }
    
    # Removed recipe parsing - ListParsingTool only extracts URLs now
    # Agent will pass extracted URLs to RecipeParsingTool separately
    
    def _get_timing_info(self, elapsed: float, url_count: int) -> Dict:
        """Generate timing information."""
        return {
            "elapsed_since_query": round(elapsed, 1),
            "elapsed_readable": f"{int(elapsed)} seconds",
            "time_status": self._get_time_status(elapsed),
            "recommended_action": self._get_recommended_action(elapsed, url_count),
            "urls_per_second": round(url_count / elapsed, 1) if elapsed > 0 else 0
        }
    
    def _get_time_status(self, elapsed: float) -> str:
        """Time status assessment."""
        if elapsed > 90:  # List processing takes longer
            return "exceeded"
        elif elapsed > 45:
            return "approaching_limit"
        else:
            return "on_track"
    
    def _get_recommended_action(self, elapsed: float, url_count: int) -> str:
        """Recommended action based on timing."""
        if elapsed > 90:
            return "ask_user"
        elif elapsed > 45 and url_count > 5:
            return "reduce_scope"
        else:
            return "continue"
    
    def _empty_result(self) -> Dict:
        """Empty result structure."""
        return {
            "extracted_recipe_urls": [],
            "failed_lists": [],
            "processing_stats": {
                "lists_attempted": 0,
                "lists_successful": 0,
                "recipe_urls_extracted": 0,
                "avg_urls_per_list": 0.0
            },
            "_timing": {
                "elapsed_since_query": 0.0,
                "elapsed_readable": "0 seconds",
                "time_status": "on_track",
                "recommended_action": "continue",
                "urls_per_second": 0.0
            }
        }


# Agent integration function
async def execute_list_parsing_tool(context: Dict) -> Dict:
    """Agent-callable wrapper for ListParsingTool."""
    input_params = context.get("input", {})
    deps = context.get("deps", {})
    
    # Initialize tool
    tool = ListParsingTool(openai_key=deps.get("openai_key"))
    
    # Execute list URL extraction (NOT parsing)
    return await tool.extract_recipe_urls_from_lists(
        urls=input_params.get("urls", []),
        max_recipes_per_list=input_params.get("max_recipes_per_list", 10),
        list_fetch_timeout=input_params.get("list_fetch_timeout", 15)
    )