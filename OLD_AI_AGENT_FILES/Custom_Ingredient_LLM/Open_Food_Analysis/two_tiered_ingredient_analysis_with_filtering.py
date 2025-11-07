#!/usr/bin/env python3
"""
Two-Tiered Ingredient Analysis - US FILTERED VERSION
- Skips redundant HTTP HEAD requests (validate_image_url)
- 40 parallel threads for maximum speed
- US store/brand filtering (16 stores + 433 brands)
- Clears database to start fresh with US-only ingredients
- Handles database duplicates with upserts
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
import sys
import logging
import requests
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
import numpy as np
from io import BytesIO
import os
import json
import time
import threading
from datetime import datetime, timezone
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://postgres:pllLOhmJldsAQmZfbylAJjlnmsvajVjB@gondola.proxy.rlwy.net:24439/railway"

# Output directory
OUTPUT_DIR = "output"

# Threading configuration - OPTIMIZED
MAX_IMAGE_THREADS = 40  # Increased from 10 to 40
IMAGE_TIMEOUT = 5  # Reduced from 10 to 5

# US FILTERING CONFIGURATION - Based on our analysis
US_STORES = [
    # Major 11 from our store analysis
    "walmart", "aldi", "kroger", "costco", "h-e-b", "safeway", 
    "trader joe's", "whole foods", "sams club", "target", "publix",
    # Additional coverage
    "albertsons", "food lion", "giant", "stop & shop", "stop shop"
]

# Top 433 US brands from our brand analysis (10+ occurrences each)
TOP_US_BRANDS = [
    "aldi", "great value", "kroger", "h-e-b", "kirkland", "trader joe's", "kirkland signature", 
    "heb", "walmart", "the kroger .", "gut bio", "milsani", "marketside", "compliments", 
    "simple truth", "wal-mart stores .", "gutbio", "gourmet finest cuisine", "private selection", 
    "asia green garden", "el mercado de aldi", "specially selected", "bettergoods", 
    "simple truth organic", "choceur", "h-e-b organics", "cucina nobile", "bio", "millville", 
    "special de aldi", "nur nur natur", "danone", "mucci", "cucina", "costco", "wonnemeyer", 
    "gut drei eichen", "simply nature", "goldähren", "nestlé", "signature select", "lala", 
    "almare", "bimbo", "365 everyday value", "lyttos", "rio d'oro", "king's crown", "my vay", 
    "nestle", "moser roth", "biscotto", "bbq", "h e butt grocery", "wintertraum", "golden bridge", 
    "o organics", "sigma", "böklunder", "alpura", "sun snacks", "quaker", "central market", 
    "hofburger", "whole foods market", "sabritas", "milfina", "simplement bon et bio", 
    "golden seafood", "kellogg's", "friendly farms", "natur lieblinge", "speisezeit", "clama", 
    "happy harvest", "milsa", "meine metzgerei", "all seasons", "gourmet", "mein veggie tag", 
    "le gusto", "pays gourmand", "güldenhof", "knorr", "knusperone", "barcel", "meine kuchenwelt", 
    "westminster", "i. schroeder", "bonafont", "nature active bio", "grandessa", "kühlmann", 
    "unilever", "la costeña", "river", "bramwells", "trader joe's", "hill country fare", 
    "coca-cola", "lindt", "sweet valley", "la cuisine des saveurs", "extra special", "delikato", 
    "back family", "best buy", "haribo", "el horno de aldi", "hershey's", "coca cola", "ursi", 
    "aldi einkauf gmbh & compagnie-ohg", "la finesse", "la huerta", "jütro", "molkerei gropper", 
    "peñafiel", "barilla", "château", "le marsigny", "regalo", "almare seafood", "landbeck", 
    "stonemill", "cadbury", "aurrera", "plant menu", "village bakery", "whole foods market .", 
    "market side", "el cultivador", "american", "the foodie market", "delicato", "les doris", 
    "wiha", "marinela", "harvest morn", "casa morando", "everyday essentials", "farmer naturals", 
    "meal simple", "organics", "natur aktiv", "gamesa", "sello rojo", "so delicious dairy free", 
    "post", "your fresh market", "pizz'ah", "bonifaz kohler", "ponnath", "wiesn schmankerl", 
    "clemente jacques", "heinz", "silk", "gatorade", "alpenmark", "snack time", "schmälzle", 
    "aldi bio", "nabisco", "fleurs des champs", "tante odile", "snackrite", "barissimo", 
    "the deli", "clancy's", "ben & jerry's", "l'oven fresh", "brooklea", "corril", "blm", 
    "tesoros del sur", "landfreude", "aldi süd", "mondelez", "equate", "365 whole foods market", 
    "prima della", "sans marque", "f.a. crux", "ashfields", "heritage farm", "mccormick", 
    "yoplait", "bon-ri", "fruima", "ostfriesische tee gesellschaft", "smart way", "kraft", 
    "kelloggs", "pillsbury", "storck", "mannapain", "flete", "roi de trefle", "safeway", 
    "pascual", "del valle", "good & gather", "whole foods", "arizona", "snack fun", "tuny", 
    "d'antelli", "meine käsetheke", "westcliff", "nature's pick", "emporium", "pepperidge farm", 
    "general mills", "food for life", "valblanc", "le cavalier", "cowbelle", "aldi specially selected", 
    "de-vau-ge", "farmer", "aldi sports", "santa clara", "betty crocker", "lucerne", "mars", 
    "baker's corner", "herdez", "freshness guaranteed", "great value • walmart", "verde valle", 
    "isaura", "the fishmonger", "four seasons", "la moderna", "unser bayern", "ferrero", 
    "pepsi", "philadelphia", "heb meal simple", "publix", "dr. oetker", "spring valley", 
    "our finest", "moreno", "les légendaires", "mühlengold", "rübezahl schokoladen", "hamker", 
    "jumex", "southern grove", "häagen-dazs", "nutty club", "monarc", "portland", 
    "la cocina de aldi", "belmont", "savour bakes", "nature valley", "safeway .", "welch's", 
    "higher harvest", "aldente", "bellasan", "mama mancini", "choco bistro", "amaroy", 
    "osterphantasie", "dairyfine", "worldwide foods", "belmont biscuits", "houdek", "bio natura", 
    "dare", "tyson", "nescafe", "higher harvest by h-e-b", "amy's", "act ii", "bon et bio", 
    "panache", "gletscherkrone", "la tabla de aldi", "desira", "newcoffee", "asia specialities", 
    "frischegerichte", "terrafertil", "world table", "campbells", "granvita", "meal simple by heb", 
    "chapman's", "365", "meal simple by h-e-b", "fontaine santé", "pleno sabor", "drizz", 
    "good choice", "happy farms", "restaurant item", "halo top", "so delicious", 
    "central market h-e-b", "burman's", "pepsico", "monster energy", "red bull", "talenti", 
    "swing", "carlos", "udi's", "new season", "les pâtissades", "le flutiau", "bistro vite", 
    "excellence", "af deutschland", "bäcker bachmeier", "alpenschmaus", "pirato", 
    "inspired cuisine", "dolores", "starbucks", "signature farms", "activia", "vachon", 
    "powerade", "gloria", "délifin", "westminster tea", "fair & gut", "stockmeyer", "coverna", 
    "bayernland", "scholetta", "flirt", "finest bakery", "milka", "lieken", "ibu", 
    "schneekoppe", "limited aldition", "ades", "bakery fresh", "new world pasta", "h.e.b", 
    "h-e-b central market", "natrel", "reese's", "maynards", "chobani", "la villa", "mio", 
    "parma", "colway", "narvik", "pasta mare", "hofer", "the pantry", "zoma", "steinhaus", 
    "happy snacks", "riha wesergold", "crestwood", "fud", "extra especial", "ghirardelli", 
    "amy's kitchen .", "better goods", "les malins plaisirs", "premier protein", "aga", 
    "kerrygold", "waterbridge", "boucherie st clément", "remano", "market fare", "primana", 
    "sauels", "albona", "the juice", "kuchenmeister", "jack's farm", "flying power", 
    "freiberger lebensmittel", "matithor", "milchfrischprodukte sba", "happy farms by aldi", 
    "esmeralda", "safeway kitchens", "hunts", "san giorgio", "pringles", "mi tienda", 
    "smucker´s", "ready for you", "tim hortons", "pizza pops", "mission", "market pantry", 
    "tres estrellas", "happy belly kombucha", "splenda", "lyncott", "summer fresh", "glaceau", 
    "tesouros do mar", "ofterdinger", "italpasta", "le paturon", "tamara", "farmdale", 
    "gartenkrone", "laschinger seafood", "ambiente", "hillcrest", "damora", "frostkrone", 
    "fair", "wiesgart", "mama cozzi's", "stollwerck", "hügli nahrungsmittel", 
    "schätze des orients", "sweet-land", "t.m.a.", "märsch", "myvay", "park street deli", 
    "blue dragon", "ciel", "marina azul", "la cibeles"
]

def setup_output_directory():
    """Create output directory if it doesn't exist"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info(f"📁 Created output directory: {OUTPUT_DIR}")

def check_corners_for_white(image_url: str, white_threshold: int = 235, corner_size: int = 8) -> bool:
    """OPTIMIZED: Check white background AND validate URL in one operation"""
    
    try:
        # Download image - this also validates the URL
        response = requests.get(image_url, timeout=IMAGE_TIMEOUT, stream=True)
        response.raise_for_status()
        
        # Open image - this validates it's actually an image
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        width, height = img.size
        
        # Skip very small images
        if width < 50 or height < 50:
            return False
        
        # Define corner regions (smaller for speed)
        corners = [
            (2, 2, corner_size, corner_size),                    # Top-left
            (width - corner_size - 2, 2, corner_size, corner_size),  # Top-right  
            (2, height - corner_size - 2, corner_size, corner_size), # Bottom-left
            (width - corner_size - 2, height - corner_size - 2, corner_size, corner_size) # Bottom-right
        ]
        
        white_corners = 0
        
        for x, y, w, h in corners:
            # Extract corner region
            corner = img.crop((x, y, x + w, y + h))
            corner_array = np.array(corner)
            
            # Calculate average RGB values in this corner
            avg_r = np.mean(corner_array[:, :, 0])
            avg_g = np.mean(corner_array[:, :, 1]) 
            avg_b = np.mean(corner_array[:, :, 2])
            
            # Check if this corner is white-ish
            if (avg_r >= white_threshold and 
                avg_g >= white_threshold and 
                avg_b >= white_threshold):
                white_corners += 1
        
        # Return True only if ALL 4 corners are white
        return white_corners == 4
        
    except Exception as e:
        logger.debug(f"❌ Error checking white background for {image_url}: {e}")
        return False

def is_us_market_product(row: pd.Series) -> bool:
    """Check if product is sold in the US market"""
    countries = str(row.get('countries_tags', '')).lower()
    return 'united-states' in countries

def passes_us_filter(row: pd.Series) -> bool:
    """Check if product passes US store OR brand filter"""
    stores_field = str(row.get('stores', '')).lower()
    brands_field = str(row.get('brands', '')).lower()
    
    # Check for US store match
    has_us_store = any(store in stores_field for store in US_STORES)
    
    # Check for US brand match  
    has_us_brand = any(brand in brands_field for brand in TOP_US_BRANDS)
    
    # Must match at least ONE US store OR ONE US brand
    return has_us_store or has_us_brand

def get_best_image_url(row: pd.Series) -> Optional[str]:
    """Try to find the best available image URL from multiple possible fields"""
    
    # List of possible image fields in order of preference
    image_fields = [
        'image_url',
        'image_small_url', 
        'image_front_url',
        'image_front_small_url',
        'image_nutrition_url',
        'image_ingredients_url'
    ]
    
    for field in image_fields:
        if field in row and pd.notna(row[field]):
            url = str(row[field]).strip()
            if url and not url.lower().startswith('nan') and 'invalid' not in url.lower():
                return url
    
    return None

def calculate_completeness_score(row: pd.Series) -> float:
    """Calculate a completeness score for the product data"""
    
    # Core fields (high weight)
    core_fields = ['code', 'product_name', 'energy-kcal_100g', 'proteins_100g', 'carbohydrates_100g', 'fat_100g']
    core_score = sum(1 for field in core_fields if pd.notna(row.get(field)) and str(row.get(field, '')).strip() != '') / len(core_fields)
    
    # Additional fields (medium weight)
    additional_fields = ['brands', 'categories', 'ingredients_text', 'nutrition_grade_fr', 'serving_size']
    additional_score = sum(1 for field in additional_fields if pd.notna(row.get(field)) and str(row.get(field, '')).strip() != '') / len(additional_fields)
    
    # Optional fields (low weight)
    optional_fields = ['labels', 'stores', 'countries', 'main_category', 'additives_n']
    optional_score = sum(1 for field in optional_fields if pd.notna(row.get(field)) and str(row.get(field, '')).strip() != '') / len(optional_fields)
    
    # Weighted average
    completeness = (core_score * 0.6) + (additional_score * 0.3) + (optional_score * 0.1)
    return round(completeness, 4)

def is_tier1_quality_fast(row: pd.Series) -> bool:
    """Premium quality check WITHOUT expensive image validation - FAST VERSION"""
    # Must be US market
    if not is_us_market_product(row):
        return False
    
    # High completeness score (top tier)
    completeness = calculate_completeness_score(row)
    if completeness < 0.8:
        return False
    
    # Must have front image, high resolution, not invalid (URL pattern check only - FAST)
    image_url = str(row.get('image_url', '')).lower()
    if ('invalid' in image_url or 
        'front' not in image_url or 
        ('.400.' not in image_url and '.600.' not in image_url)):
        return False
    
    return True

def extract_professional_product_data(row: pd.Series) -> dict:
    """Extract product data for professional products only"""
    
    completeness = calculate_completeness_score(row)
    
    product = {
        # Core fields
        'off_code': str(row['code']),
        'product_name': str(row.get('product_name', ''))[:500],
        'brand': str(row.get('brands', ''))[:255] if pd.notna(row.get('brands')) else None,
        'image_url': get_best_image_url(row),
        'calories_100g': float(row['energy-kcal_100g']),
        'protein_100g': float(row['proteins_100g']),
        'carbs_100g': float(row['carbohydrates_100g']),
        'fat_100g': float(row['fat_100g']),
        'completeness': completeness,
        'quality_tier': 'professional',
        
        # Optional fields (already added to database schema)
        'serving_size': str(row.get('serving_size', ''))[:50] if pd.notna(row.get('serving_size')) else None,
        'no_nutriments': str(row.get('no_nutriments')).lower() in ['true', '1', 'yes'] if pd.notna(row.get('no_nutriments')) else None,
        'additives_n': int(float(row.get('additives_n'))) if pd.notna(row.get('additives_n')) and str(row.get('additives_n')).replace('.','').replace('-','').isdigit() else None,
        'additives': str(row.get('additives', '')) if pd.notna(row.get('additives')) else None,
        'additives_tags': str(row.get('additives_tags', '')) if pd.notna(row.get('additives_tags')) else None,
        'ingredients_from_palm_oil_n': int(float(row.get('ingredients_from_palm_oil_n'))) if pd.notna(row.get('ingredients_from_palm_oil_n')) and str(row.get('ingredients_from_palm_oil_n')).replace('.','').replace('-','').isdigit() else None,
        'ingredients_from_palm_oil': str(row.get('ingredients_from_palm_oil', '')) if pd.notna(row.get('ingredients_from_palm_oil')) else None,
        'ingredients_from_palm_oil_tags': str(row.get('ingredients_from_palm_oil_tags', '')) if pd.notna(row.get('ingredients_from_palm_oil_tags')) else None,
        'ingredients_that_may_be_from_palm_oil_n': int(float(row.get('ingredients_that_may_be_from_palm_oil_n'))) if pd.notna(row.get('ingredients_that_may_be_from_palm_oil_n')) and str(row.get('ingredients_that_may_be_from_palm_oil_n')).replace('.','').replace('-','').isdigit() else None,
        'ingredients_that_may_be_from_palm_oil': str(row.get('ingredients_that_may_be_from_palm_oil', '')) if pd.notna(row.get('ingredients_that_may_be_from_palm_oil')) else None,
        'ingredients_that_may_be_from_palm_oil_tags': str(row.get('ingredients_that_may_be_from_palm_oil_tags', '')) if pd.notna(row.get('ingredients_that_may_be_from_palm_oil_tags')) else None,
        'nutrition_grade_fr': str(row.get('nutrition_grade_fr', ''))[:1] if pd.notna(row.get('nutrition_grade_fr')) else None,
        'main_category': str(row.get('main_category', '')) if pd.notna(row.get('main_category')) else None,
        'main_category_fr': str(row.get('main_category_fr', '')) if pd.notna(row.get('main_category_fr')) else None,
        'image_small_url': str(row.get('image_small_url', '')) if pd.notna(row.get('image_small_url')) else None,
        'labels': str(row.get('labels', '')) if pd.notna(row.get('labels')) else None,
        'labels_tags': str(row.get('labels_tags', '')) if pd.notna(row.get('labels_tags')) else None,
        'labels_fr': str(row.get('labels_fr', '')) if pd.notna(row.get('labels_fr')) else None,
        'emb_codes': str(row.get('emb_codes', '')) if pd.notna(row.get('emb_codes')) else None,
        'emb_codes_tags': str(row.get('emb_codes_tags', '')) if pd.notna(row.get('emb_codes_tags')) else None,
        'first_packaging_code_geo': str(row.get('first_packaging_code_geo', '')) if pd.notna(row.get('first_packaging_code_geo')) else None,
        'cities': str(row.get('cities', '')) if pd.notna(row.get('cities')) else None,
        'cities_tags': str(row.get('cities_tags', '')) if pd.notna(row.get('cities_tags')) else None,
        'purchase_places': str(row.get('purchase_places', '')) if pd.notna(row.get('purchase_places')) else None,
        'stores': str(row.get('stores', '')) if pd.notna(row.get('stores')) else None,
        'countries': str(row.get('countries', '')) if pd.notna(row.get('countries')) else None,
        'countries_tags': str(row.get('countries_tags', '')) if pd.notna(row.get('countries_tags')) else None,
        'categories': str(row.get('categories', '')) if pd.notna(row.get('categories')) else None,
        'categories_tags': str(row.get('categories_tags', '')) if pd.notna(row.get('categories_tags')) else None,
    }
    
    return product

def process_image_candidate(candidate_data: dict) -> Optional[dict]:
    """OPTIMIZED: Process candidate with ONLY white background check (no redundant HTTP request)"""
    
    try:
        image_url = candidate_data['image_url']
        
        # SINGLE OPERATION: Check white background (also validates URL + image)
        if not check_corners_for_white(image_url):
            return None
        
        # SUCCESS - this is a professional photo!
        return candidate_data
        
    except Exception as e:
        logger.debug(f"❌ Error processing candidate {candidate_data.get('product_name', 'Unknown')}: {e}")
        return None

def upload_to_database_upsert(products: List[dict], engine) -> Tuple[int, int]:
    """Upload with UPSERT to handle duplicates gracefully"""
    
    if not products:
        return 0, 0
    
    try:
        # Use ON CONFLICT to handle duplicates
        with engine.connect() as conn:
            inserted_count = 0
            
            for product in products:
                # Build the INSERT ... ON CONFLICT statement
                columns = list(product.keys())
                placeholders = [f":{col}" for col in columns]
                
                # Create update set for ON CONFLICT
                update_set = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'off_code'])
                
                upsert_sql = f"""
                INSERT INTO brand_ingredients ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (off_code) DO UPDATE SET
                {update_set}
                """
                
                conn.execute(text(upsert_sql), product)
                inserted_count += 1
            
            conn.commit()
            logger.info(f"✅ Successfully upserted {inserted_count} professional products to database")
            return inserted_count, 0  # uploaded, failed
        
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['storage', 'limit', 'space', 'quota']):
            logger.error(f"🚫 DATABASE STORAGE LIMIT HIT: {e}")
            logger.info(f"📁 Professional products cannot be uploaded - upgrade storage needed")
        else:
            logger.error(f"💾 Database error: {e}")
            logger.info(f"📁 Database upload failed - can retry later")
        
        return 0, len(products)  # uploaded, failed

def save_checkpoint(checkpoint_data: dict):
    """Save current processing state to checkpoint file"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint_optimized.json")
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)

def load_checkpoint() -> Optional[dict]:
    """Load checkpoint data if it exists"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint_optimized.json")
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return None

def clear_database(engine):
    """Clear all existing brand_ingredients data to start fresh with US filtering"""
    try:
        with engine.connect() as conn:
            # Get current count before clearing
            result = conn.execute(text("SELECT COUNT(*) FROM brand_ingredients"))
            current_count = result.scalar() or 0
            
            if current_count > 0:
                logger.info(f"🗑️ Clearing {current_count:,} existing ingredients from database")
                logger.info("💡 Previous data was processed without US filtering - starting fresh")
                
                # Clear the table
                conn.execute(text("DELETE FROM brand_ingredients"))
                conn.commit()
                
                logger.info("✅ Database cleared successfully - ready for US-filtered ingredients")
            else:
                logger.info("📊 Database is already empty - ready for processing")
                
    except Exception as e:
        logger.error(f"❌ Error clearing database: {e}")
        raise

def get_current_database_count(engine) -> int:
    """Get current count of professional products in database"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM brand_ingredients WHERE quality_tier = 'professional'"))
            return result.scalar() or 0
    except:
        return 0

def start_heartbeat_monitor(stats_dict: dict):
    """OPTIMIZED heartbeat monitor with better ETA calculation"""
    
    def heartbeat():
        while stats_dict.get('active', True):
            time.sleep(30)
            if stats_dict.get('active', True):
                current_row = stats_dict.get('current_row', 0)
                tier1_candidates = stats_dict.get('tier1_candidates', 0)
                candidates_processed = stats_dict.get('candidates_processed', 0)
                professional_count = stats_dict.get('professional_count', 0)
                elapsed = time.time() - stats_dict.get('start_time', time.time())
                
                if current_row > 0:
                    stage1_rate = current_row / elapsed if elapsed > 0 else 0
                    stage2_rate = candidates_processed / elapsed if elapsed > 0 else 0
                    remaining_rows = 4000000 - current_row
                    eta_seconds = remaining_rows / stage1_rate if stage1_rate > 0 else 0
                    eta_hours = eta_seconds / 3600
                    
                    # Calculate efficiency
                    conversion_rate = (professional_count / candidates_processed * 100) if candidates_processed > 0 else 0
                    
                    print(f"💓 HEARTBEAT: Row {current_row:,} | Candidates: {tier1_candidates} | Processed: {candidates_processed} | Professional: {professional_count}")
                    print(f"           Stage1: {stage1_rate:.0f} rows/sec | Stage2: {stage2_rate:.1f} cand/sec | Conversion: {conversion_rate:.1f}% | ETA: {eta_hours:.1f}h")
    
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    return thread

def process_optimized_analysis(file_path: str, engine) -> dict:
    """ULTRA OPTIMIZED: Resume from current position with 40 threads and no redundant requests"""
    
    logger.info(f"🚀 US-FILTERED TWO-TIER ANALYSIS")
    logger.info(f"📂 Input file: {file_path}")
    logger.info(f"⚡ Optimizations: 40 threads, no HTTP HEAD requests, upsert duplicates")
    logger.info(f"🇺🇸 US Filtering: 16 stores + 433 brands | Database cleared for fresh start")
    
    # Setup
    setup_output_directory()
    start_time = time.time()
    
    # Get current database count
    existing_professional_count = get_current_database_count(engine)
    logger.info(f"📊 Found {existing_professional_count} existing professional products in database")
    
    # Initialize stats for heartbeat
    stats_dict = {
        'active': True,
        'current_row': 0,
        'tier1_candidates': 0,
        'candidates_processed': 0,
        'professional_count': existing_professional_count,  # Start with existing count
        'start_time': start_time
    }
    
    # Start heartbeat monitor
    heartbeat_thread = start_heartbeat_monitor(stats_dict)
    
    # Start fresh with US filtering
    logger.info(f"🎯 Starting fresh from Row 1 with US filtering enabled")
    logger.info(f"📊 Database cleared - looking for US grocery ingredients only")
    
    # Check for existing checkpoint (but start fresh since we cleared database)
    checkpoint = load_checkpoint()
    if checkpoint:
        logger.info(f"📋 Found existing checkpoint at row {checkpoint['current_row']:,}")
        response = input("Resume from checkpoint? (y/n - 'n' starts fresh): ").lower().strip()
        if response != 'y':
            checkpoint = None
            logger.info("🔄 Starting fresh from Row 1 with US filtering")
    
    # Initialize counters
    if checkpoint:
        # Use checkpoint but with cleared database
        professional_count = 0  # Start fresh since database was cleared
        db_uploaded = 0
        db_failed = 0
        start_row = checkpoint['current_row']
        batch_num = checkpoint.get('last_batch_completed', 0) + 1
        total_processed = checkpoint['total_processed']
        tier1_candidates_total = 0  # Reset since we're filtering differently now
        candidates_processed_total = 0  # Reset since we're filtering differently now
        logger.info(f"📋 Resuming from checkpoint at row {start_row:,} (database cleared)")
    else:
        # Start fresh with US filtering
        professional_count = 0  # Database is cleared
        db_uploaded = 0
        db_failed = 0
        start_row = 0  # Start from beginning
        batch_num = 1  # Start with batch 1
        total_processed = 0  # Start from scratch
        tier1_candidates_total = 0
        candidates_processed_total = 0
        logger.info(f"🚀 Starting fresh from Row 1 with US filtering enabled")
        logger.info(f"📊 Looking for US grocery ingredients from the beginning")
    
    # Update stats dict
    stats_dict['current_row'] = start_row
    stats_dict['tier1_candidates'] = tier1_candidates_total
    stats_dict['candidates_processed'] = candidates_processed_total
    stats_dict['professional_count'] = professional_count
    
    # Batch processing
    chunk_size = 25000
    professional_batch = []
    tier1_candidates_batch = []
    
    try:
        # Process CSV in chunks with error handling for malformed rows
        csv_reader = pd.read_csv(file_path, sep='\t', encoding='utf-8', 
                                chunksize=chunk_size, low_memory=False,
                                on_bad_lines='warn')  # Skip bad rows instead of crashing
        
        # Skip to resume point if needed
        rows_skipped = 0
        for chunk in csv_reader:
            if start_row > 0 and rows_skipped < start_row:
                skip_this_chunk = min(len(chunk), start_row - rows_skipped)
                rows_skipped += skip_this_chunk
                if skip_this_chunk == len(chunk):
                    continue
                else:
                    chunk = chunk.iloc[skip_this_chunk:]
                    rows_skipped = start_row
            
            # ===== STAGE 1: FAST PRE-FILTERING =====
            logger.info(f"🔍 Stage 1: Fast filtering batch {batch_num} (rows {total_processed+1:,} - {total_processed+len(chunk):,})")
            stage1_start = time.time()
            
            for index, row in chunk.iterrows():
                total_processed += 1
                stats_dict['current_row'] = total_processed
                
                # Quick validation of basic requirements (FAST)
                required_fields = ['code', 'product_name', 'energy-kcal_100g', 'proteins_100g', 'carbohydrates_100g', 'fat_100g']
                if not all(pd.notna(row.get(field)) and str(row.get(field, '')).strip() != '' for field in required_fields):
                    continue
                
                # Validate nutrition values (FAST)
                try:
                    calories = float(row['energy-kcal_100g'])
                    protein = float(row['proteins_100g'])
                    carbs = float(row['carbohydrates_100g'])
                    fat = float(row['fat_100g'])
                    
                    if not all(0 <= val <= 1000 for val in [calories, protein, carbs, fat]):
                        continue
                except (ValueError, TypeError):
                    continue
                
                # Check if this could be a tier1 candidate (FAST - no network operations)
                if is_tier1_quality_fast(row):
                    # NEW: Apply US store/brand filter (FAST - no network operations)
                    if passes_us_filter(row):
                        # Add to candidate queue for Stage 2 processing
                        candidate_data = extract_professional_product_data(row)
                        tier1_candidates_batch.append(candidate_data)
                        tier1_candidates_total += 1
                        stats_dict['tier1_candidates'] = tier1_candidates_total
            
            stage1_time = time.time() - stage1_start
            logger.info(f"✅ Stage 1 complete: {len(tier1_candidates_batch)} US-filtered tier1 candidates found in {stage1_time:.1f}s")
            
            # ===== STAGE 2: PARALLEL IMAGE PROCESSING (40 THREADS) =====
            if tier1_candidates_batch:
                logger.info(f"🖼️ Stage 2: Processing {len(tier1_candidates_batch)} candidates with {MAX_IMAGE_THREADS} threads")
                stage2_start = time.time()
                
                # Process candidates in parallel using ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=MAX_IMAGE_THREADS) as executor:
                    # Submit all candidates for processing
                    future_to_candidate = {
                        executor.submit(process_image_candidate, candidate): candidate 
                        for candidate in tier1_candidates_batch
                    }
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_candidate):
                        candidates_processed_total += 1
                        stats_dict['candidates_processed'] = candidates_processed_total
                        
                        result = future.result()
                        if result:  # Professional photo found!
                            professional_batch.append(result)
                            professional_count += 1
                            stats_dict['professional_count'] = professional_count
                            
                            logger.info(f"⭐ Found PROFESSIONAL photo #{professional_count}: {result['product_name']}")
                
                stage2_time = time.time() - stage2_start
                candidates_per_sec = len(tier1_candidates_batch) / stage2_time if stage2_time > 0 else 0
                logger.info(f"✅ Stage 2 complete: {len(professional_batch)} professional photos found in {stage2_time:.1f}s ({candidates_per_sec:.1f} candidates/sec)")
            
            # Upload professional products to database with UPSERT
            if professional_batch:
                uploaded, failed = upload_to_database_upsert(professional_batch, engine)
                db_uploaded += uploaded
                db_failed += failed
            
            # Print batch summary
            elapsed_time = time.time() - start_time
            elapsed_hours = elapsed_time / 3600
            
            if total_processed > 0:
                overall_rate = total_processed / elapsed_hours if elapsed_hours > 0 else 0
                remaining_rows = 4000000 - total_processed
                eta_hours = remaining_rows / overall_rate if overall_rate > 0 else 0
                tier1_rate = (tier1_candidates_total / total_processed) * 100 if total_processed > 0 else 0
                professional_rate = (len(professional_batch) / len(tier1_candidates_batch)) * 100 if tier1_candidates_batch else 0
            else:
                eta_hours = 0
                tier1_rate = 0
                professional_rate = 0
            
            print(f"\n📊 BATCH {batch_num} COMPLETE (Rows {total_processed-len(chunk)+1:,} - {total_processed:,})")
            print(f"Stage 1: {len(tier1_candidates_batch)} tier1 candidates | Stage 2: {len(professional_batch)} professional ({professional_rate:.1f}%)")
            if len(professional_batch) > 0:
                print(f"         ↳ DB Upserted: {uploaded}, DB Failed: {failed}")
            print(f"This Session: {tier1_candidates_total} candidates | Session Professional: {professional_count - existing_professional_count}")
            print(f"Grand Total: {professional_count} professional photos in database (started with {existing_professional_count})")
            if db_failed > 0:
                print(f"Database: {db_uploaded} uploaded, {db_failed} failed (storage limit?)")
            else:
                print(f"Database: Total professional products: {professional_count}")
            print(f"Progress: {total_processed:,}/4M rows | {elapsed_hours:.1f}h elapsed | {overall_rate:.0f} rows/h | ETA: {eta_hours:.1f}h")
            
            # Save checkpoint
            checkpoint_data = {
                'current_row': total_processed,
                'total_processed': total_processed,
                'tier1_candidates': tier1_candidates_total,
                'candidates_processed': candidates_processed_total,
                'professional_count': professional_count,
                'db_uploaded': db_uploaded,
                'db_failed': db_failed,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'last_batch_completed': batch_num
            }
            save_checkpoint(checkpoint_data)
            
            # Reset batch counters
            professional_batch = []
            tier1_candidates_batch = []
            batch_num += 1
            
    except Exception as e:
        logger.error(f"❌ Processing error: {e}")
        logger.info(f"📋 Progress saved to checkpoint - can resume later")
        stats_dict['active'] = False
        raise
    
    # Stop heartbeat
    stats_dict['active'] = False
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"🏁 ULTRA OPTIMIZED ANALYSIS COMPLETE!")
    logger.info(f"⏱️ Total time: {total_time/3600:.2f} hours")
    logger.info(f"📊 Stage 1: Processed {total_processed:,} rows, found {tier1_candidates_total:,} tier1 candidates")
    logger.info(f"📊 Stage 2: Processed {candidates_processed_total:,} candidates, found {professional_count - existing_professional_count:,} NEW professional photos")
    logger.info(f"📊 Grand total professional photos: {professional_count:,} (started with {existing_professional_count:,})")
    logger.info(f"🗄️ Total professional products in database: {professional_count}")
    
    if db_failed > 0:
        logger.warning(f"⚠️ {db_failed} professional products need database upload (storage limit hit)")
        logger.info(f"💡 Upgrade Railway storage to upload remaining products")
    
    return {
        'professional': professional_count,
        'tier1_candidates': tier1_candidates_total,
        'candidates_processed': candidates_processed_total,
        'total_processed': total_processed,
        'db_uploaded': db_uploaded,
        'db_failed': db_failed
    }

def main():
    """Main function to run the ultra optimized analysis"""
    
    # Get CSV file path
    if len(sys.argv) == 2:
        csv_file_path = sys.argv[1]
    else:
        csv_file_path = "/Users/agustin/Desktop/en.openfoodfacts.org.products.csv"
        print(f"Using hardcoded file path: {csv_file_path}")
    
    # Validate CSV file exists
    if not os.path.exists(csv_file_path):
        logger.error(f"❌ CSV file not found: {csv_file_path}")
        logger.error("💡 Please check the file path and try again")
        sys.exit(1)
    
    try:
        # Create database connection
        logger.info("🔗 Connecting to Railway PostgreSQL database...")
        engine = create_engine(DATABASE_URL)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
        
        # DATABASE PRESERVATION - keep existing data (clearing disabled)
        logger.info("🔄 Preserving existing professional products - no database clearing")
        
        # Process complete dataset with ultra optimized analysis
        final_stats = process_optimized_analysis(csv_file_path, engine)
        
        print(f"\n🎉 SUCCESS! US-filtered analysis complete!")
        print(f"📊 Stage 1 efficiency: {final_stats['tier1_candidates']:,} US candidates from {final_stats['total_processed']:,} rows ({(final_stats['tier1_candidates']/final_stats['total_processed']*100):.2f}%)")
        print(f"📊 Stage 2 efficiency: {final_stats['professional']:,} professional US ingredients")
        print(f"🇺🇸 US-filtered professional photos: {final_stats['professional']:,}")
        print(f"🏪 Filtered by: 16 US stores + 433 US brands")
        print(f"🚀 Ready to test your meal planning app with US grocery ingredients!")
        
    except FileNotFoundError:
        logger.error(f"❌ File not found: {csv_file_path}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info(f"⏸️ Processing interrupted by user")
        logger.info(f"📋 Progress saved to checkpoint - can resume with same command")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()