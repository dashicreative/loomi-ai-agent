"""
Stage 3: URL Classification
Classifies URLs as recipe pages, list pages, or other content types.

This module efficiently classifies multiple URLs using parallel content fetching and LLM processing.
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


class BatchURLClassifier:
    """
    Batch URL classifier using parallel content fetching and single LLM call.
    
    Optimized for classifying 20-60 URLs in a single operation.
    """
    
    def __init__(self, openai_key: str):
        self.openai_key = openai_key
        self.content_size_limit = 5000  # 5KB per URL
        
    async def classify_urls(self, urls: List[Dict]) -> List[URLClassification]:
        """
        Classify a batch of URLs using content sampling and LLM analysis.
        
        Args:
            urls: List of URL dictionaries with 'url' and 'title' keys
            
        Returns:
            List of URLClassification objects
        """
        print(f"   🔍 Stage 3B Details: Processing {len(urls)} URLs")
        
        # Step 1: Fetch content samples in parallel
        fetch_start = time.time()
        content_samples = await self._fetch_content_samples(urls)
        fetch_time = time.time() - fetch_start
        print(f"   ⏱️  Content Fetching: {fetch_time:.2f}s")
        
        # Step 2: Parallel classify with LLM (10 individual calls)
        llm_start = time.time()
        classification_tasks = [self._classify_single_url(sample) for sample in content_samples]
        classification_results = await asyncio.gather(*classification_tasks, return_exceptions=True)
        
        # Process results and handle any failures
        classifications = []
        for i, result in enumerate(classification_results):
            if isinstance(result, Exception):
                print(f"     ⚠️  Individual classification failed for {content_samples[i]['url']}: {result}")
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
        print(f"   ⏱️  LLM Classification (10 parallel calls): {llm_time:.2f}s")
        
        return classifications
    
    async def _fetch_content_samples(self, urls: List[Dict]) -> List[Dict]:
        """
        Fetch content samples from URLs in parallel.
        
        Returns list of dicts with url, title, and content sample.
        """
        async def fetch_single_with_client(url_data: Dict, client: httpx.AsyncClient) -> Dict:
            """Fetch content sample from a single URL using shared HTTP/2 client."""
            url = url_data.get('url', '')
            title = url_data.get('title', '')
            
            try:
                # Step 1: Quick HEAD request to check accessibility
                head_response = await client.head(url, follow_redirects=True, timeout=2.0)
                print(f"🔍 Debug: HEAD {url} returned status {head_response.status_code}")
                
                if head_response.status_code == 403:
                    print(f"⚠️  403 Forbidden for {url} - skipping content fetch")
                    return {
                        'url': url,
                        'title': title,
                        'content': '',
                        'error': '403 Forbidden (detected via HEAD)'
                    }
                elif head_response.status_code not in [200, 301, 302]:
                    print(f"⚠️  HTTP {head_response.status_code} for {url} - skipping content fetch")
                    return {
                        'url': url,
                        'title': title,
                        'content': '',
                        'error': f'HTTP {head_response.status_code} (detected via HEAD)'
                    }
                
                # Step 2: If HEAD is successful, proceed with content fetch
                async with client.stream('GET', url, follow_redirects=True) as response:
                    print(f"🔍 Debug: GET {url} returned status {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"⚠️  HTTP {response.status_code} for {url}")
                    
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
        
        # Create single client with connection pooling for all requests
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
        Classify a single URL with individual LLM call.
        
        Args:
            content_sample: Dict with url, title, and content
            
        Returns:
            URLClassification object
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
        """Fallback classification for single URL when LLM fails."""
        url = content_sample['url'].lower()
        title = content_sample['title'].lower()
        
        # Simplified pattern matching
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


# Convenience function for easy integration
async def classify_urls_batch(urls: List[Dict], openai_key: str) -> List[URLClassification]:
    """
    Classify a batch of URLs.
    
    Args:
        urls: List of dicts with 'url' and 'title' keys
        openai_key: OpenAI API key
        
    Returns:
        List of URLClassification objects
    """
    classifier = BatchURLClassifier(openai_key)
    return await classifier.classify_urls(urls)