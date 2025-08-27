"""
Batch URL Classification Module

Efficiently classifies multiple URLs in a single operation using parallel content fetching
and batch LLM processing. Designed to be fast, accurate, and extensible.

Classification types:
- recipe: Individual recipe page
- list: Recipe collection/list page
- blog: Blog post (may contain recipe)
- social: Social media platform
- other: Unclassified content
"""

import asyncio
import httpx
import json
from typing import List, Dict, Tuple
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
        # Step 1: Fetch content samples in parallel
        content_samples = await self._fetch_content_samples(urls)
        
        # Step 2: Batch classify with LLM
        classifications = await self._batch_classify_with_llm(content_samples)
        
        return classifications
    
    async def _fetch_content_samples(self, urls: List[Dict]) -> List[Dict]:
        """
        Fetch content samples from URLs in parallel.
        
        Returns list of dicts with url, title, and content sample.
        """
        async def fetch_single(url_data: Dict) -> Dict:
            """Fetch content sample from a single URL."""
            url = url_data.get('url', '')
            title = url_data.get('title', '')
            
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # Stream partial content
                    async with client.stream('GET', url, follow_redirects=True) as response:
                        # Add debug logging
                        print(f"🔍 Debug: {url} returned status {response.status_code}")
                        
                        if response.status_code == 403:
                            print(f"⚠️  403 Forbidden for {url} - content will be empty")
                        elif response.status_code != 200:
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
        
        # Fetch all URLs in parallel
        tasks = [fetch_single(url_data) for url_data in urls]
        content_samples = await asyncio.gather(*tasks)
        
        return content_samples
    
    async def _batch_classify_with_llm(self, content_samples: List[Dict]) -> List[URLClassification]:
        """
        Classify all URLs in a single LLM call.
        
        Uses structured output for reliable parsing.
        """
        # Build classification prompt
        classification_data = []
        for i, sample in enumerate(content_samples):
            classification_data.append({
                'index': i,
                'url': sample['url'],
                'title': sample['title'],
                'content_preview': sample['content'][:2000]  # Limit per-URL content
            })
        
        prompt = f"""Classify these URLs based on their content and structure using these flexible guidelines.

URL TYPES:
- recipe: Individual recipe page with ingredients and instructions  
- list: Collection of multiple recipes (roundups, category pages, search results)
- blog: Blog post that may discuss recipes but isn't a recipe itself
- social: Social media platform (reddit, youtube, pinterest, etc.)
- other: Doesn't fit above categories

CLASSIFICATION GUIDELINES (use as flexible guides, not strict rules):

PRIMARY LIST SIGNALS (strong indicators, use judgment):
- Page titles suggesting collections (like "recipes", "best", "top", "ideas" - often plural)
- URL patterns suggesting categories (like /recipes/category/, /collections/, /roundups/ - but variations exist)  
- Multiple recipe cards or links (typically 10+ different recipe titles)
- Missing both ingredients AND nutrition sections (suggests overview page)

PRIMARY RECIPE SIGNALS (strong indicators, use judgment):
- Contains ingredients section with quantities and measurements
- Contains step-by-step cooking instructions
- Single recipe focus with one main dish

Use your judgment to weigh these signals - they're guidelines, not absolute rules.

Analyze each URL and return classifications in this exact JSON format:
{{
  "classifications": [
    {{
      "index": 0,
      "type": "recipe|list|blog|social|other",
      "confidence": 0.95,
      "signals": ["JSON-LD Recipe found", "ingredient list present"]
    }}
  ]
}}

URLs to classify:
{json.dumps(classification_data, indent=2)}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
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
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code != 200:
                    # Fallback to simple classification
                    return self._fallback_classification(content_samples)
                
                data = response.json()
                llm_response = data['choices'][0]['message']['content'].strip()
                
                # Parse JSON response
                if '```json' in llm_response:
                    llm_response = llm_response.split('```json')[1].split('```')[0]
                elif '```' in llm_response:
                    llm_response = llm_response.split('```')[1]
                
                result = json.loads(llm_response)
                classifications_data = result.get('classifications', [])
                
                # Build URLClassification objects
                classifications = []
                for class_data in classifications_data:
                    idx = class_data.get('index', 0)
                    if idx < len(content_samples):
                        sample = content_samples[idx]
                        classifications.append(URLClassification(
                            url=sample['url'],
                            type=class_data.get('type', 'other'),
                            confidence=class_data.get('confidence', 0.5),
                            title=sample['title'],
                            signals=class_data.get('signals', [])
                        ))
                
                # Add any missing URLs with fallback classification
                classified_indices = {c.get('index', -1) for c in classifications_data}
                for i, sample in enumerate(content_samples):
                    if i not in classified_indices:
                        classifications.append(URLClassification(
                            url=sample['url'],
                            type='other',
                            confidence=0.0,
                            title=sample['title'],
                            signals=['no classification']
                        ))
                
                return classifications
                
        except Exception as e:
            print(f"Batch classification failed: {e}")
            return self._fallback_classification(content_samples)
    
    def _fallback_classification(self, content_samples: List[Dict]) -> List[URLClassification]:
        """
        Simple fallback classification based on URL patterns.
        """
        classifications = []
        
        for sample in content_samples:
            url = sample['url'].lower()
            title = sample['title'].lower()
            
            # Simple pattern matching
            if any(site in url for site in ['reddit.com', 'youtube.com', 'pinterest.com']):
                url_type = 'social'
            elif 'blog' in url or 'article' in url:
                url_type = 'blog'
            elif any(pattern in title for pattern in ['best', 'top', 'recipes', 'roundup']):
                url_type = 'list'
            elif '/recipe/' in url or 'recipe' in title:
                url_type = 'recipe'
            else:
                url_type = 'other'
            
            classifications.append(URLClassification(
                url=sample['url'],
                type=url_type,
                confidence=0.3,
                title=sample['title'],
                signals=['fallback classification']
            ))
        
        return classifications


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