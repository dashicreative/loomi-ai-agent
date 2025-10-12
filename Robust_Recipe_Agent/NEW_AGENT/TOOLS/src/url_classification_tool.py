"""
URLClassificationTool - Recipe vs List Page Classification
Exact copy of proven classification logic with enriched URL object output.
"""

import asyncio
import httpx
import json
import time
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class URLClassification:
    """Classification result for a single URL."""
    url: str
    type: str  # 'recipe', 'list', 'blog', 'social', 'other'
    confidence: float  # 0.0 to 1.0
    title: str
    signals: List[str]  # What signals led to this classification


class URLClassificationTool:
    """
    Exact copy of BatchURLClassifier logic with enriched URL object output.
    """
    
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
        self.content_size_limit = 5000  # 5KB per URL - exact match
        self.query_start_time = None
        
    async def classify_urls(self, urls: List[Dict]) -> Dict:
        """
        Classify URLs and return enriched URL objects.
        EXACT COPY of current BatchURLClassifier.classify_urls() logic.
        """
        if not self.query_start_time:
            self.query_start_time = time.time()
            
        if not urls:
            return self._empty_result()
        
        # Step 1: Fetch content samples in parallel (EXACT COPY)
        fetch_start = time.time()
        content_samples = await self._fetch_content_samples(urls)
        fetch_time = time.time() - fetch_start
        print(f"   ⏱️  Content Fetching: {fetch_time:.2f}s")
        
        # Step 2: Parallel classify with LLM (EXACT COPY - individual calls)
        llm_start = time.time()
        classification_tasks = [self._classify_single_url(sample) for sample in content_samples]
        classification_results = await asyncio.gather(*classification_tasks, return_exceptions=True)
        
        # Process results and handle any failures (EXACT COPY)
        classifications = []
        for i, result in enumerate(classification_results):
            if isinstance(result, Exception):
                # Fallback classification for failed calls
                classifications.append(URLClassification(
                    url=content_samples[i]['url'],
                    type='other',
                    confidence=0.0,
                    title=content_samples[i]['title'],
                    signals=['classification_failed']
                ))
            else:
                classifications.append(result)
        
        llm_time = time.time() - llm_start
        print(f"   ⏱️  LLM Classification ({len(classification_tasks)} parallel calls): {llm_time:.2f}s")
        
        # Convert URLClassification objects to enriched URL objects
        enriched_urls = []
        for i, classification in enumerate(classifications):
            original_url = urls[i]
            enriched_url = original_url.copy()
            
            # Add classification metadata to URL object
            enriched_url.update({
                'type': classification.type,
                'confidence': classification.confidence,
                'classification_method': 'llm' if classification.confidence > 0.5 else 'fallback',
                'classification_signals': classification.signals
            })
            
            enriched_urls.append(enriched_url)
        
        # Calculate timing and distribution
        elapsed = time.time() - self.query_start_time
        distribution = self._calculate_distribution(enriched_urls)
        
        return {
            "classified_urls": enriched_urls,
            "total_processed": len(enriched_urls),
            "type_distribution": distribution,
            "processing_stats": {
                "successful_classifications": len([c for c in classifications if c.confidence > 0.0]),
                "failed_classifications": len([c for c in classifications if c.confidence == 0.0]),
                "content_fetches": len(content_samples)
            },
            "_timing": {
                "elapsed_since_query": round(elapsed, 1),
                "elapsed_readable": f"{int(elapsed)} seconds",
                "time_status": self._get_time_status(elapsed),
                "recommended_action": self._get_recommended_action(elapsed, len(enriched_urls))
            }
        }
    
    async def _fetch_content_samples(self, urls: List[Dict]) -> List[Dict]:
        """
        EXACT COPY of current _fetch_content_samples implementation.
        """
        async def fetch_single_with_client(url_data: Dict, client: httpx.AsyncClient) -> Dict:
            """EXACT COPY - Fetch content sample from a single URL using shared HTTP/2 client."""
            url = url_data.get('url', '')
            title = url_data.get('title', '')
            
            try:
                # Step 1: Quick HEAD request to check accessibility
                head_response = await client.head(url, follow_redirects=True, timeout=2.0)
                
                if head_response.status_code == 403:
                    return {
                        'url': url,
                        'title': title,
                        'content': '',
                        'error': '403 Forbidden (detected via HEAD)'
                    }
                elif head_response.status_code not in [200, 301, 302]:
                    return {
                        'url': url,
                        'title': title,
                        'content': '',
                        'error': f'HTTP {head_response.status_code} (detected via HEAD)'
                    }
                
                # Step 2: If HEAD is successful, proceed with content fetch
                async with client.stream('GET', url, follow_redirects=True) as response:
                    
                    if response.status_code != 200:
                        pass
                    
                    content = b""
                    async for chunk in response.aiter_bytes(chunk_size=1024):
                        content += chunk
                        if len(content) >= self.content_size_limit:
                            break
                    
                    # Decode and clean
                    text_content = content.decode('utf-8', errors='ignore')
                    
                    return {
                        'url': url,
                        'title': title,
                        'content': text_content[:self.content_size_limit]
                    }
                        
            except Exception as e:
                # Return minimal data on failure
                return {
                    'url': url,
                    'title': title,
                    'content': '',
                    'error': str(e)
                }
        
        # Create single client with connection pooling for all requests (EXACT COPY)
        async with httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3)
        ) as shared_client:
            # Fetch all URLs in parallel using the shared HTTP/2 client
            tasks = [fetch_single_with_client(url_data, shared_client) for url_data in urls]
            content_samples = await asyncio.gather(*tasks)
        
        return content_samples
    
    async def _classify_single_url(self, content_sample: Dict) -> URLClassification:
        """
        EXACT COPY of current _classify_single_url implementation.
        """
        url = content_sample['url']
        title = content_sample['title']
        content_preview = content_sample['content'][:2000]  # Limit content
        
        prompt = f"""Classify this URL as "recipe", "list", or "other".

TYPES:
- recipe: Individual recipe page (ingredients + instructions for ONE recipe)
- list: Collection page with MULTIPLE recipes (roundups, "best of" pages)
- other: Not a recipe or recipe collection (gets discarded)

Return JSON: {{"type": "recipe|list|other"}}

URL: {url}
Title: {title}
Content: {content_preview[:800]}"""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": [
                            {"role": "system", "content": "You are a URL classification expert. Return only valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 50  # Very small - just need "recipe", "list", or "other"
                    }
                )
            
            if response.status_code != 200:
                # Fallback to pattern-based classification
                return self._fallback_single_classification(content_sample)
            
            data = response.json()
            llm_response = data['choices'][0]['message']['content'].strip()
            
            # Parse JSON response
            if '```json' in llm_response:
                llm_response = llm_response.split('```json')[1].split('```')[0]
            elif '```' in llm_response:
                llm_response = llm_response.split('```')[1]
            
            result = json.loads(llm_response)
            
            return URLClassification(
                url=url,
                type=result.get('type', 'other'),
                confidence=0.9,  # High confidence for simplified classification
                title=title,
                signals=['simplified_classification']
            )
            
        except Exception as e:
            # Fallback to pattern-based classification
            return self._fallback_single_classification(content_sample)
    
    def _fallback_single_classification(self, content_sample: Dict) -> URLClassification:
        """EXACT COPY of current fallback classification."""
        url = content_sample['url'].lower()
        title = content_sample['title'].lower()
        
        # Simplified pattern matching (EXACT COPY)
        if any(pattern in title for pattern in ['best', 'top', 'recipes', 'roundup']):
            url_type = 'list'
        elif '/recipe/' in url or 'recipe' in title:
            url_type = 'recipe'
        else:
            url_type = 'other'
        
        return URLClassification(
            url=content_sample['url'],
            type=url_type,
            confidence=0.3,
            title=content_sample['title'],
            signals=['fallback classification']
        )
    
    def _calculate_distribution(self, enriched_urls: List[Dict]) -> Dict:
        """Calculate distribution of classified types."""
        distribution = {'recipe': 0, 'list': 0, 'other': 0}
        
        for url_obj in enriched_urls:
            url_type = url_obj.get('type', 'other')
            if url_type in distribution:
                distribution[url_type] += 1
            else:
                distribution['other'] += 1
        
        distribution['total'] = len(enriched_urls)
        return distribution
    
    def _get_time_status(self, elapsed: float) -> str:
        """Time status for classification."""
        if elapsed > 10:
            return "exceeded"
        elif elapsed > 5:
            return "approaching_limit"
        else:
            return "on_track"
    
    def _get_recommended_action(self, elapsed: float, result_count: int) -> str:
        """Recommended action based on results."""
        if elapsed > 10:
            return "continue_with_current"
        elif result_count == 0:
            return "expand_search"
        else:
            return "continue"
    
    def _empty_result(self) -> Dict:
        """Empty result structure."""
        return {
            "classified_urls": [],
            "total_processed": 0,
            "type_distribution": {"recipe": 0, "list": 0, "other": 0, "total": 0},
            "processing_stats": {
                "successful_classifications": 0,
                "failed_classifications": 0,
                "content_fetches": 0
            },
            "_timing": {
                "elapsed_since_query": 0.0,
                "elapsed_readable": "0 seconds",
                "time_status": "on_track",
                "recommended_action": "continue"
            }
        }


# Agent integration function
async def execute_url_classification_tool(context: Dict) -> Dict:
    """
    Agent-callable wrapper for URLClassificationTool.
    """
    input_params = context.get("input", {})
    deps = context.get("deps", {})
    
    # Initialize tool
    tool = URLClassificationTool(openai_key=deps.get("openai_key"))
    
    # Execute classification
    return await tool.classify_urls(urls=input_params.get("urls", []))