"""
Dedicated list parser for extracting individual recipe URLs from recipe list pages.

CURRENT ISSUES IDENTIFIED:
1. Generic link detection - catches navigation/footer links
2. Weak recipe indicators - misses modern blog structures  
3. No context awareness - ignores recipe card structure
4. No image-based detection - misses visual recipe indicators
5. No structured data parsing - ignores JSON-LD lists

IMPROVED STRATEGY:
1. Multi-tiered detection system
2. Recipe card structure analysis
3. Image + title + description clustering
4. URL pattern analysis specific to recipe sites
5. JSON-LD Recipe collection parsing
"""

import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
import json
import httpx


class ListParser:
    """
    Advanced parser for extracting individual recipe URLs from list pages.
    
    Handles modern food blog structures with recipe cards, previews, and galleries.
    """
    
    def __init__(self, openai_key: str = None):
        self.openai_key = openai_key
        # Common recipe card selectors used by food blogs
        self.recipe_card_selectors = [
            'article[class*="recipe"]',
            'div[class*="recipe-card"]',
            'div[class*="post-preview"]',
            'div[class*="entry"]',
            'article[class*="post"]',
            '.recipe-summary',
            '.recipe-teaser',
            '[data-recipe-id]'
        ]
        
        # Recipe link patterns - more specific than current implementation
        self.recipe_link_patterns = [
            r'/recipe/',
            r'/recipes/',
            r'-recipe/?$',
            r'-recipe\.',
            r'recipe\?',
            r'/\d{4}/\d{2}/.+',  # Date-based URLs common in food blogs
        ]
        
        # Food-related keywords for better context
        self.food_keywords = [
            'chicken', 'beef', 'pork', 'fish', 'salmon', 'tuna', 'shrimp',
            'pasta', 'noodles', 'rice', 'quinoa', 'bread', 'pizza',
            'salad', 'soup', 'stew', 'curry', 'stir fry', 'casserole',
            'cake', 'cookies', 'pie', 'muffins', 'pancakes', 'waffles',
            'breakfast', 'lunch', 'dinner', 'snack', 'appetizer', 'dessert',
            'sandwich', 'wrap', 'burger', 'tacos', 'enchiladas',
            'smoothie', 'shake', 'bowl', 'plate', 'dish'
        ]
        
        # Navigation/non-recipe patterns to exclude
        self.exclude_patterns = [
            r'/(about|contact|privacy|terms)',
            r'/(category|tag|author)',
            r'/#',
            r'/page/',
            r'/(feed|rss)',
            r'/(search|shop|store)',
            r'/wp-',
            r'javascript:',
            r'mailto:',
            r'tel:',
            r'/(login|register)',
            r'/(newsletter|subscribe)'
        ]
    
    async def extract_recipe_urls(self, url: str, content: str, max_urls: int = 5) -> List[Dict]:
        """
        Extract individual recipe URLs from a list page using multi-tiered approach.
        
        Args:
            url: The list page URL
            content: HTML content of the list page
            max_urls: Maximum URLs to extract
            
        Returns:
            List of recipe URL dictionaries
        """
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Tier 1: Try JSON-LD structured data first (most reliable)
            json_recipes = self._extract_from_json_ld(soup, url)
            if len(json_recipes) >= max_urls:
                return json_recipes[:max_urls]
            
            # Tier 2: Recipe card structure analysis
            card_recipes = self._extract_from_recipe_cards(soup, url)
            
            # Tier 3: Fallback to improved link analysis
            link_recipes = self._extract_from_links(soup, url)
            
            # Combine and deduplicate results
            all_recipes = json_recipes + card_recipes + link_recipes
            unique_recipes = self._deduplicate_recipes(all_recipes)
            
            # Final step: Intelligent URL filtering with LLM
            if unique_recipes and self.openai_key:
                filtered_recipes = await self._batch_filter_recipe_urls(unique_recipes)
                return filtered_recipes[:max_urls]
            
            return unique_recipes[:max_urls]
            
        except Exception as e:
            print(f"List parser failed for {url}: {e}")
            return []
    
    def _extract_from_json_ld(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract recipes from JSON-LD structured data."""
        recipes = []
        
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                data = json.loads(script.string)
                
                # Handle both single objects and arrays
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]
                
                for item in items:
                    # Look for Recipe collections or individual recipes
                    if item.get('@type') == 'Recipe' and item.get('url'):
                        recipes.append({
                            'title': item.get('name', ''),
                            'url': urljoin(base_url, item.get('url')),
                            'snippet': item.get('description', '')[:200] + '...',
                            'source': 'json_ld_extraction',
                            'type': 'recipe'
                        })
                    elif item.get('@type') == 'ItemList':
                        # Handle recipe collections
                        items_list = item.get('itemListElement', [])
                        for list_item in items_list:
                            if list_item.get('item', {}).get('@type') == 'Recipe':
                                recipe_data = list_item.get('item', {})
                                recipes.append({
                                    'title': recipe_data.get('name', ''),
                                    'url': urljoin(base_url, recipe_data.get('url', '')),
                                    'snippet': recipe_data.get('description', '')[:200] + '...',
                                    'source': 'json_ld_collection',
                                    'type': 'recipe'
                                })
                        
            except (json.JSONDecodeError, KeyError):
                continue
        
        return recipes
    
    def _extract_from_recipe_cards(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract recipes by analyzing recipe card structures."""
        recipes = []
        
        # Find potential recipe cards using various selectors
        for selector in self.recipe_card_selectors:
            cards = soup.select(selector)
            
            for card in cards:
                recipe_link = self._find_recipe_link_in_card(card, base_url)
                if recipe_link:
                    recipes.append(recipe_link)
        
        return recipes
    
    def _find_recipe_link_in_card(self, card: BeautifulSoup, base_url: str) -> Optional[Dict]:
        """Find the main recipe link within a recipe card."""
        
        # Look for links with recipe-specific patterns
        links = card.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            if not href:
                continue
            
            # Convert to absolute URL
            absolute_url = urljoin(base_url, href)
            
            # Check if URL matches recipe patterns
            if self._is_recipe_url(absolute_url):
                title = self._extract_recipe_title_from_card(card, link)
                snippet = self._extract_recipe_snippet_from_card(card)
                
                return {
                    'title': title,
                    'url': absolute_url,
                    'snippet': snippet,
                    'source': 'recipe_card_extraction',
                    'type': 'recipe'
                }
        
        return None
    
    def _extract_recipe_title_from_card(self, card: BeautifulSoup, link: BeautifulSoup) -> str:
        """Extract recipe title from card context."""
        
        # Try link text first
        link_text = link.get_text(strip=True)
        if link_text and len(link_text) > 5:
            return link_text
        
        # Try headings in the card
        for heading in card.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = heading.get_text(strip=True)
            if text and len(text) > 5:
                return text
        
        # Try title attributes
        title_elem = card.find(['*'], title=True)
        if title_elem:
            return title_elem.get('title', '')
        
        return "Recipe"
    
    def _extract_recipe_snippet_from_card(self, card: BeautifulSoup) -> str:
        """Extract description/snippet from card."""
        
        # Look for description elements
        desc_selectors = [
            '.description', '.excerpt', '.summary', '.intro',
            '[class*="description"]', '[class*="excerpt"]',
            'p', '.entry-content p'
        ]
        
        for selector in desc_selectors:
            desc_elem = card.select_one(selector)
            if desc_elem:
                text = desc_elem.get_text(strip=True)
                if text and len(text) > 20:
                    return text[:200] + '...' if len(text) > 200 else text
        
        return "Recipe from list page"
    
    def _extract_from_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Fallback: Extract using improved link analysis."""
        recipes = []
        
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            
            if not href or len(link_text) < 5:
                continue
            
            absolute_url = urljoin(base_url, href)
            
            # Enhanced recipe detection
            if self._is_high_confidence_recipe_link(absolute_url, link_text, link):
                recipes.append({
                    'title': link_text,
                    'url': absolute_url,
                    'snippet': f"Recipe from {urlparse(base_url).netloc}",
                    'source': 'link_analysis',
                    'type': 'recipe'
                })
        
        return recipes
    
    def _is_recipe_url(self, url: str) -> bool:
        """Check if URL matches recipe patterns."""
        url_lower = url.lower()
        
        # Exclude non-recipe patterns first
        for pattern in self.exclude_patterns:
            if re.search(pattern, url_lower):
                return False
        
        # Check for recipe patterns
        for pattern in self.recipe_link_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    def _is_high_confidence_recipe_link(self, url: str, text: str, link_elem: BeautifulSoup) -> bool:
        """Enhanced recipe link detection."""
        
        if not self._is_recipe_url(url):
            return False
        
        text_lower = text.lower()
        
        # High confidence indicators
        confidence_score = 0
        
        # URL contains recipe indicators
        if any(pattern in url.lower() for pattern in ['/recipe', 'recipe']):
            confidence_score += 2
        
        # Text contains food keywords
        if any(food in text_lower for food in self.food_keywords):
            confidence_score += 2
        
        # Reasonable title length
        if 10 <= len(text) <= 100:
            confidence_score += 1
        
        # Has associated image (common in recipe cards)
        parent = link_elem.parent
        if parent and parent.find('img'):
            confidence_score += 1
        
        # Context indicates recipe (nearby nutrition, time, etc.)
        context_text = ''
        if parent:
            context_text = parent.get_text(strip=True).lower()
        
        if any(word in context_text for word in ['minutes', 'hours', 'serves', 'calories', 'protein']):
            confidence_score += 1
        
        return confidence_score >= 3
    
    async def _batch_filter_recipe_urls(self, recipe_urls: List[Dict]) -> List[Dict]:
        """
        Batch filter recipe URLs using LLM to remove category/navigation pages.
        
        Uses single LLM call to classify all URLs as either "keep" or "discard".
        """
        if not recipe_urls or not self.openai_key:
            return recipe_urls
        
        # Step 1: First pass - Remove obvious non-recipe URLs with hardcoded patterns
        pre_filtered = []
        for recipe in recipe_urls:
            url = recipe.get('url', '').lower()
            
            # Apply existing exclude patterns
            should_exclude = any(re.search(pattern, url) for pattern in self.exclude_patterns)
            
            # Additional category/navigation patterns
            category_patterns = [
                r'/recipes/$',  # Just /recipes/
                r'/account/',  # Account pages
                r'/add-recipe',  # Add recipe forms
                r'/recipes/\d+/$',  # Category IDs like /recipes/17562/
                r'/recipes/\d+/[^/]+/$',  # Categories like /recipes/17562/dinner/
                r'/(dinner|lunch|breakfast|dessert|appetizer|snack)/$',  # Category endings
                r'/meal-ideas/',  # Meal categories
                r'/(main-dishes|side-dishes|salads|soups|beverages)/$',  # Dish categories
                r'/cooking/',  # General cooking sections
                r'/5-ingredients/',  # Special categories
                r'/everyday-cooking/',  # Lifestyle categories
                r'/more-meal-ideas/'  # More categories
            ]
            
            if not should_exclude:
                should_exclude = any(re.search(pattern, url) for pattern in category_patterns)
            
            if not should_exclude:
                pre_filtered.append(recipe)
        
        # Step 2: Batch LLM filtering for remaining URLs
        if not pre_filtered:
            return []
        
        # Limit to prevent JSON parsing issues with very long responses
        max_llm_urls = min(20, len(pre_filtered))
        urls_for_llm = pre_filtered[:max_llm_urls]
        
        # Prepare data for LLM classification
        url_data = []
        for i, recipe in enumerate(urls_for_llm):
            url_data.append({
                'index': i,
                'url': recipe['url'],
                'title': recipe.get('title', ''),
                'snippet': recipe.get('snippet', '')
            })
        
        prompt = f"""You are filtering recipe URLs to remove category pages, navigation pages, and non-recipe content.

KEEP URLs that are:
- Individual recipe pages with specific recipe names
- URLs ending with specific recipe titles (e.g., "chocolate-chip-cookies")
- URLs with recipe IDs followed by recipe names
- Direct links to cooking instructions for specific dishes

DISCARD URLs that are:
- Category/listing pages (e.g., /recipes/, /dinner/, /main-dishes/)
- Navigation pages (e.g., /account/, /add-recipe/, /search/)
- General cooking sections or meal planning pages
- URLs ending with generic categories instead of specific recipes
- Account or user-generated content pages

Analyze each URL and return classifications in this exact JSON format:
{{
  "classifications": [
    {{
      "index": 0,
      "action": "keep|discard",
      "reason": "specific recipe page|category page|navigation|etc"
    }}
  ]
}}

URLs to classify:
{json.dumps(url_data, indent=2)}"""

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
                        "max_tokens": 1000
                    }
                )
                
                if response.status_code != 200:
                    # If LLM fails, return pre-filtered results
                    return pre_filtered
                
                data = response.json()
                llm_response = data['choices'][0]['message']['content'].strip()
                
                # Parse JSON response
                if '```json' in llm_response:
                    llm_response = llm_response.split('```json')[1].split('```')[0]
                elif '```' in llm_response:
                    llm_response = llm_response.split('```')[1]
                
                # Clean up response
                llm_response = llm_response.strip()
                
                result = json.loads(llm_response)
                classifications = result.get('classifications', [])
                
                # Filter based on LLM classifications
                filtered_urls = []
                for classification in classifications:
                    idx = classification.get('index', -1)
                    action = classification.get('action', 'discard')
                    
                    if action == 'keep' and 0 <= idx < len(urls_for_llm):
                        filtered_urls.append(urls_for_llm[idx])
                
                # Add any remaining URLs that weren't sent to LLM (if we had more than max_llm_urls)
                if len(pre_filtered) > max_llm_urls:
                    filtered_urls.extend(pre_filtered[max_llm_urls:])
                
                return filtered_urls
                
        except json.JSONDecodeError as e:
            print(f"URL filtering JSON parsing failed: {e}")
            print(f"LLM response: {llm_response[:200]}...")
            # Return pre-filtered results if JSON parsing fails
            return pre_filtered
        except Exception as e:
            print(f"URL filtering failed: {e}")
            # Return pre-filtered results if LLM fails
            return pre_filtered
    
    def _deduplicate_recipes(self, recipes: List[Dict]) -> List[Dict]:
        """Remove duplicate recipes based on URL."""
        seen_urls = set()
        unique_recipes = []
        
        for recipe in recipes:
            url = recipe.get('url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_recipes.append(recipe)
        
        return unique_recipes