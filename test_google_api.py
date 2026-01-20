#!/usr/bin/env python3
"""
Direct test of Google Custom Search API
"""
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Get credentials
api_key = os.getenv('GOOGLE_API_KEY')
search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

print("=" * 60)
print("🔍 GOOGLE CUSTOM SEARCH API TEST")
print("=" * 60)

# Show what we have (masked)
print(f"\n📋 Credentials:")
if api_key:
    print(f"  API Key: {api_key[:15]}...{api_key[-4:]} (length: {len(api_key)})")
else:
    print(f"  ❌ API Key: NOT FOUND")

if search_engine_id:
    print(f"  Search Engine ID: {search_engine_id[:10]}...{search_engine_id[-4:]} (length: {len(search_engine_id)})")
else:
    print(f"  ❌ Search Engine ID: NOT FOUND")

if not api_key or not search_engine_id:
    print("\n❌ Missing credentials in .env file!")
    exit(1)

# Test search
print(f"\n🔍 Testing search for: 'potato nutrition facts'")
print("-" * 60)

url = "https://www.googleapis.com/customsearch/v1"
params = {
    "key": api_key,
    "cx": search_engine_id,
    "q": "potato nutrition facts calories protein",
    "num": 3
}

print(f"\n📡 Making request to: {url}")
print(f"   Query: {params['q']}")
print(f"   Num results: {params['num']}")

try:
    response = requests.get(url, params=params)

    print(f"\n📊 Response:")
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        items = data.get('items', [])

        print(f"   ✅ SUCCESS! Got {len(items)} results")
        print(f"\n🎯 Search Results:")

        for i, item in enumerate(items, 1):
            print(f"\n   {i}. {item.get('title', 'No title')}")
            print(f"      URL: {item.get('link', 'No link')}")
            snippet = item.get('snippet', 'No snippet')[:100]
            print(f"      Snippet: {snippet}...")

        print(f"\n✅ Google Custom Search API is working correctly!")
        print(f"   Project: loomi-cec3e")
        print(f"   API enabled and configured properly")

    else:
        print(f"   ❌ FAILED")
        print(f"\n📄 Full Response:")
        print(response.text)

        # Parse error if possible
        try:
            error_data = response.json()
            error = error_data.get('error', {})
            print(f"\n🚨 Error Details:")
            print(f"   Code: {error.get('code')}")
            print(f"   Message: {error.get('message')}")

            if 'project' in error.get('message', '').lower():
                import re
                project_match = re.search(r'project (\d+)', error.get('message', ''))
                if project_match:
                    wrong_project = project_match.group(1)
                    print(f"\n⚠️  API Key is associated with project: {wrong_project}")
                    print(f"   You need to either:")
                    print(f"   1. Enable API in that project, OR")
                    print(f"   2. Create new API key in loomi-cec3e project")
        except:
            pass

except Exception as e:
    print(f"\n❌ Exception occurred: {type(e).__name__}")
    print(f"   {str(e)}")

print("\n" + "=" * 60)
