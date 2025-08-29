"""
Constants for Recipe Search Pipeline

Contains all shared constants used across different stages.
"""

# Priority recipe sites for search
PRIORITY_SITES = [
    "allrecipes.com",
    "simplyrecipes.com", 
    "eatingwell.com",
    "foodnetwork.com",
    "delish.com",
    "seriouseats.com",
    "foodandwine.com",
    "thepioneerwoman.com",
    "food.com",
    "epicurious.com",
    "bbcgoodfood.com"  # Added at bottom - good site but lower priority
]

# Sites to completely block from processing
BLOCKED_SITES = [
    "reddit.com",
    "youtube.com",
    "instagram.com", 
    "pinterest.com",
    "facebook.com",
    "tiktok.com",
    "twitter.com"
]