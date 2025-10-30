#!/usr/bin/env python3
"""
Open Food Facts Complete Dataset Processor - Professional Photo Mining
Processes all 4M products to find professional white-background photos and categorize by quality tiers
Includes graceful database failure handling, checkpoint system, and comprehensive statistics
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
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://postgres:pllLOhmJldsAQmZfbylAJjlnmsvajVjB@gondola.proxy.rlwy.net:24439/railway"

# Output directory
OUTPUT_DIR = "output"

def setup_output_directory():
    """Create output directory if it doesn't exist"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info(f"📁 Created output directory: {OUTPUT_DIR}")

def add_enhanced_columns_to_table(engine):
    """Add all required columns to the brand_ingredients table"""
    
    # Define all new columns we want to add
    new_columns = {
        'completeness': 'DECIMAL(5,4)',
        'quality_tier': 'VARCHAR(20)',
        'serving_size': 'VARCHAR(50)',
        'no_nutriments': 'BOOLEAN',
        'additives_n': 'INTEGER',
        'additives': 'TEXT',
        'additives_tags': 'TEXT',
        'ingredients_from_palm_oil_n': 'INTEGER',
        'ingredients_from_palm_oil': 'TEXT',
        'ingredients_from_palm_oil_tags': 'TEXT',
        'ingredients_that_may_be_from_palm_oil_n': 'INTEGER',
        'ingredients_that_may_be_from_palm_oil': 'TEXT',
        'ingredients_that_may_be_from_palm_oil_tags': 'TEXT',
        'nutrition_grade_fr': 'CHAR(1)',
        'main_category': 'TEXT',
        'main_category_fr': 'TEXT',
        'image_small_url': 'TEXT',
        'labels': 'TEXT',
        'labels_tags': 'TEXT',
        'labels_fr': 'TEXT',
        'emb_codes': 'TEXT',
        'emb_codes_tags': 'TEXT',
        'first_packaging_code_geo': 'TEXT',
        'cities': 'TEXT',
        'cities_tags': 'TEXT',
        'purchase_places': 'TEXT',
        'stores': 'TEXT',
        'countries': 'TEXT',
        'countries_tags': 'TEXT',
        'categories': 'TEXT',
        'categories_tags': 'TEXT'
    }
    
    try:
        with engine.connect() as conn:
            # Check which columns already exist
            check_columns_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'brand_ingredients';
            """
            
            result = conn.execute(text(check_columns_sql))
            existing_columns = [row[0] for row in result.fetchall()]
            
            # Add missing columns
            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    logger.info(f"📊 Adding '{col_name}' column to brand_ingredients table...")
                    conn.execute(text(f"ALTER TABLE brand_ingredients ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"✅ Added {col_name} column")
                else:
                    logger.info(f"✅ {col_name} column already exists")
            
            conn.commit()
            logger.info("🔧 Database schema updated successfully")
            
    except Exception as e:
        logger.error(f"❌ Error adding columns to table: {e}")
        raise

def clear_brand_ingredients_table(engine):
    """Clear all existing data from the brand_ingredients table"""
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("DELETE FROM brand_ingredients"))
            conn.commit()
            logger.info("🗑️ Cleared existing data from brand_ingredients table")
    except Exception as e:
        logger.error(f"❌ Error clearing table: {e}")
        raise

def validate_image_url(url: str, timeout: int = 5) -> bool:
    """Check if an image URL returns a valid response and isn't a placeholder"""
    
    if not url or url.strip() == '':
        return False
    
    # Skip URLs that contain 'invalid' - these are Open Food Facts placeholders
    if 'invalid' in url.lower():
        return False
    
    # Skip other common placeholder patterns
    placeholder_patterns = ['placeholder', 'default', 'missing', 'no-image']
    if any(pattern in url.lower() for pattern in placeholder_patterns):
        return False
    
    try:
        # Make a HEAD request to check if the URL is accessible
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        
        # Check if status is successful (200-299 range)
        if 200 <= response.status_code < 300:
            # Also check if it's actually an image
            content_type = response.headers.get('content-type', '').lower()
            if any(img_type in content_type for img_type in ['image/', 'jpeg', 'jpg', 'png', 'gif', 'webp']):
                return True
        
        return False
        
    except:
        return False

def check_corners_for_white(image_url: str, white_threshold: int = 235, corner_size: int = 12) -> bool:
    """Check if all four corners of the image are white (professional studio photo)"""
    
    try:
        # Download image
        response = requests.get(image_url, timeout=10, stream=True)
        response.raise_for_status()
        
        # Open image
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        width, height = img.size
        
        # Skip very small images
        if width < 50 or height < 50:
            return False
        
        # Define corner regions (small squares in each corner)
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

def is_tier1_quality(row: pd.Series) -> bool:
    """Premium quality: US + high completeness + front image + high-res"""
    if not is_us_market_product(row):
        return False
    
    completeness = calculate_completeness_score(row)
    if completeness < 0.8:
        return False
    
    # Must have front image, high resolution, not invalid
    image_url = str(row.get('image_url', '')).lower()
    if ('invalid' in image_url or 
        'front' not in image_url or 
        ('.400.' not in image_url and '.600.' not in image_url)):
        return False
    
    return True

def is_tier2_quality(row: pd.Series) -> bool:
    """Good quality: US + medium completeness + any decent image"""
    if not is_us_market_product(row):
        return False
    
    completeness = calculate_completeness_score(row)
    if completeness < 0.6:
        return False
    
    # Any non-invalid image
    image_url = str(row.get('image_url', '')).lower()
    if 'invalid' in image_url:
        return False
    
    return True

def is_tier3_quality(row: pd.Series) -> bool:
    """Basic quality: US + basic completeness + working image"""
    if not is_us_market_product(row):
        return False
    
    completeness = calculate_completeness_score(row)
    if completeness < 0.4:
        return False
    
    # Just needs a working image (not invalid)
    image_url = str(row.get('image_url', ''))
    if not image_url or 'invalid' in image_url.lower():
        return False
    
    return True

def is_professional_tier(row: pd.Series) -> bool:
    """Tier 0 - Professional: US + tier1 quality + WHITE BACKGROUND"""
    
    # Must pass existing tier1 quality checks first
    if not is_tier1_quality(row):
        return False
    
    # PLUS white background requirement
    image_url = get_best_image_url(row)
    if not image_url:
        return False
    
    return check_corners_for_white(image_url)

def classify_product_tier(row: pd.Series) -> str:
    """Classify product into exactly one tier"""
    
    # Check basic requirements first
    required_fields = ['code', 'product_name', 'energy-kcal_100g', 'proteins_100g', 'carbohydrates_100g', 'fat_100g']
    for field in required_fields:
        if pd.isna(row.get(field)) or str(row.get(field, '')).strip() == '':
            return "rejected"
    
    # Validate nutrition values
    try:
        calories = float(row['energy-kcal_100g'])
        protein = float(row['proteins_100g'])
        carbs = float(row['carbohydrates_100g'])
        fat = float(row['fat_100g'])
        
        if not all(0 <= val <= 1000 for val in [calories, protein, carbs, fat]):
            return "rejected"
    except (ValueError, TypeError):
        return "rejected"
    
    # Validate image URL
    image_url = get_best_image_url(row)
    if not image_url or not validate_image_url(image_url):
        return "rejected"
    
    # Classify by tier (order matters - check professional first!)
    if is_professional_tier(row):
        return "professional"
    elif is_tier1_quality(row):  
        return "tier1"
    elif is_tier2_quality(row):
        return "tier2" 
    elif is_tier3_quality(row):
        return "tier3"
    else:
        return "rejected"

def extract_product_data(row: pd.Series, tier: str) -> dict:
    """Extract product data with all the new optional fields"""
    
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
        'quality_tier': tier,
        
        # Optional fields (new additions)
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

def append_to_csv(filename: str, products: List[dict]):
    """Append products to existing CSV or create new one"""
    if not products:
        return
        
    file_exists = os.path.exists(filename)
    
    df = pd.DataFrame(products)
    df.to_csv(filename, 
              mode='a',           # Append mode
              header=not file_exists,  # Only add header if new file
              index=False)

def upload_to_database_safe(products: List[dict], engine) -> Tuple[int, int]:
    """Safely upload products to database with graceful failure handling"""
    
    if not products:
        return 0, 0
    
    try:
        # Convert to DataFrame for easy uploading
        df = pd.DataFrame(products)
        
        # Upload to database
        rows_uploaded = df.to_sql('brand_ingredients', engine, 
                                 if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Successfully uploaded {len(products)} professional products to database")
        return len(products), 0  # uploaded, failed
        
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['storage', 'limit', 'space', 'quota']):
            logger.error(f"🚫 DATABASE STORAGE LIMIT HIT: {e}")
            logger.info(f"📁 Products saved to CSV - upgrade storage to continue uploading")
        else:
            logger.error(f"💾 Database error: {e}")
            logger.info(f"📁 Products saved to CSV - can retry upload later")
        
        return 0, len(products)  # uploaded, failed

def save_checkpoint(checkpoint_data: dict):
    """Save current processing state to checkpoint file"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint.json")
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)

def load_checkpoint() -> Optional[dict]:
    """Load checkpoint data if it exists"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint.json")
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return None

def print_batch_summary(batch_num: int, batch_stats: dict, running_stats: dict, start_time: float):
    """Print detailed batch statistics"""
    
    current_time = time.time()
    elapsed_time = current_time - start_time
    rows_processed = running_stats['total_processed']
    
    # Calculate rates and estimates
    if elapsed_time > 0:
        rows_per_second = rows_processed / elapsed_time
        estimated_total_time = 4000000 / rows_per_second if rows_per_second > 0 else 0
        remaining_time = estimated_total_time - elapsed_time
    else:
        remaining_time = 0
    
    print(f"\n📊 BATCH {batch_num} COMPLETE (Rows {rows_processed-5000+1:,} - {rows_processed:,})")
    print("=" * 65)
    
    # This batch statistics
    print(f"This Batch:   Prof: {batch_stats['professional']}, T1: {batch_stats['tier1']}, "
          f"T2: {batch_stats['tier2']}, T3: {batch_stats['tier3']}, Rejected: {batch_stats['rejected']}")
    
    if batch_stats['professional'] > 0:
        print(f"              ↳ DB Uploaded: {batch_stats['db_uploaded']}, DB Failed: {batch_stats['db_failed']}")
    
    # Running totals
    print(f"Running Total: Prof: {running_stats['professional']}, T1: {running_stats['tier1']}, "
          f"T2: {running_stats['tier2']}, T3: {running_stats['tier3']}, Rejected: {running_stats['rejected']}")
    
    # Database status
    if running_stats['db_uploaded'] > 0 or running_stats['db_failed'] > 0:
        print(f"Database:     ↳ Uploaded: {running_stats['db_uploaded']}, Failed: {running_stats['db_failed']}")
        
        if running_stats['db_failed'] > 0:
            print(f"Status:       🔴 Database issues | 📁 All products backed up to CSV")
        else:
            print(f"Status:       🟢 Database healthy | 📁 All products backed up to CSV")
    
    # Hit rates
    total = running_stats['total_processed']
    if total > 0:
        prof_rate = (running_stats['professional'] / total) * 100
        t1_rate = (running_stats['tier1'] / total) * 100
        t2_rate = (running_stats['tier2'] / total) * 100
        t3_rate = (running_stats['tier3'] / total) * 100
        
        print(f"Hit Rates:    Prof: {prof_rate:.3f}%, T1: {t1_rate:.2f}%, T2: {t2_rate:.2f}%, T3: {t3_rate:.2f}%")
    
    # Time estimates
    elapsed_hours = elapsed_time / 3600
    remaining_hours = remaining_time / 3600
    print(f"Time:         Elapsed: {elapsed_hours:.1f}h | Est. Remaining: {remaining_hours:.1f}h")
    
    if running_stats['db_failed'] > 0:
        print(f"\n⚠️  Note: {running_stats['db_failed']} professional products awaiting database upload")

def process_complete_dataset(file_path: str, engine) -> dict:
    """Process the complete 4M product dataset"""
    
    logger.info(f"🚀 STARTING COMPLETE DATASET PROCESSING")
    logger.info(f"📂 Input file: {file_path}")
    logger.info(f"📁 Output directory: {OUTPUT_DIR}")
    logger.info(f"🎯 Mission: Find ALL professional white-background photos in 4M products")
    
    # Setup
    setup_output_directory()
    start_time = time.time()
    
    # Check for existing checkpoint
    checkpoint = load_checkpoint()
    if checkpoint:
        logger.info(f"📋 Found existing checkpoint at row {checkpoint['current_row']}")
        response = input("Resume from checkpoint? (y/n): ").lower().strip()
        if response != 'y':
            checkpoint = None
            logger.info("🔄 Starting fresh processing")
    
    # Initialize counters
    if checkpoint:
        running_stats = checkpoint['tier_counts'].copy()
        running_stats['total_processed'] = checkpoint['total_processed']
        running_stats['db_uploaded'] = checkpoint.get('db_uploaded', 0)
        running_stats['db_failed'] = checkpoint.get('db_failed', 0)
        start_row = checkpoint['current_row']
        batch_num = checkpoint.get('last_batch_completed', 0) + 1
    else:
        running_stats = {
            'professional': 0, 'tier1': 0, 'tier2': 0, 'tier3': 0, 'rejected': 0,
            'total_processed': 0, 'db_uploaded': 0, 'db_failed': 0
        }
        start_row = 0
        batch_num = 1
    
    # Batch processing
    chunk_size = 5000
    batch_products = {'professional': [], 'tier1': [], 'tier2': [], 'tier3': [], 'rejected': []}
    batch_stats = {'professional': 0, 'tier1': 0, 'tier2': 0, 'tier3': 0, 'rejected': 0, 'db_uploaded': 0, 'db_failed': 0}
    
    try:
        # Process CSV in chunks
        csv_reader = pd.read_csv(file_path, sep='\t', encoding='utf-8', 
                                chunksize=chunk_size, low_memory=False)
        
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
            
            for index, row in chunk.iterrows():
                # Classify product
                tier = classify_product_tier(row)
                
                # Extract product data
                if tier != "rejected":
                    product_data = extract_product_data(row, tier)
                    batch_products[tier].append(product_data)
                
                # Update counters
                batch_stats[tier] += 1
                running_stats[tier] += 1
                running_stats['total_processed'] += 1
                
                # Log professional finds immediately
                if tier == "professional":
                    logger.info(f"⭐ Found PROFESSIONAL photo #{running_stats['professional']}: {row.get('product_name', 'Unknown')}")
            
            # Process batch completion
            # 1. Save all tiers to CSV files
            for tier, products in batch_products.items():
                if products:
                    csv_file = os.path.join(OUTPUT_DIR, f"{tier}_products.csv")
                    append_to_csv(csv_file, products)
            
            # 2. Upload professional products to database (with graceful failure)
            if batch_products['professional']:
                uploaded, failed = upload_to_database_safe(batch_products['professional'], engine)
                batch_stats['db_uploaded'] += uploaded
                batch_stats['db_failed'] += failed
                running_stats['db_uploaded'] += uploaded
                running_stats['db_failed'] += failed
            
            # 3. Print batch summary
            print_batch_summary(batch_num, batch_stats, running_stats, start_time)
            
            # 4. Save checkpoint
            checkpoint_data = {
                'current_row': running_stats['total_processed'],
                'total_processed': running_stats['total_processed'],
                'tier_counts': {k: v for k, v in running_stats.items() if k.startswith(('professional', 'tier', 'rejected'))},
                'db_uploaded': running_stats['db_uploaded'],
                'db_failed': running_stats['db_failed'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'last_batch_completed': batch_num
            }
            save_checkpoint(checkpoint_data)
            
            # 5. Reset batch counters
            batch_products = {'professional': [], 'tier1': [], 'tier2': [], 'tier3': [], 'rejected': []}
            batch_stats = {'professional': 0, 'tier1': 0, 'tier2': 0, 'tier3': 0, 'rejected': 0, 'db_uploaded': 0, 'db_failed': 0}
            batch_num += 1
            
    except Exception as e:
        logger.error(f"❌ Processing error: {e}")
        logger.info(f"📋 Progress saved to checkpoint - can resume later")
        raise
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"🏁 PROCESSING COMPLETE!")
    logger.info(f"⏱️ Total time: {total_time/3600:.2f} hours")
    logger.info(f"📊 Final statistics:")
    logger.info(f"   Professional: {running_stats['professional']:,}")
    logger.info(f"   Tier 1: {running_stats['tier1']:,}")
    logger.info(f"   Tier 2: {running_stats['tier2']:,}")
    logger.info(f"   Tier 3: {running_stats['tier3']:,}")
    logger.info(f"   Rejected: {running_stats['rejected']:,}")
    logger.info(f"   Total processed: {running_stats['total_processed']:,}")
    
    if running_stats['db_failed'] > 0:
        logger.warning(f"⚠️ {running_stats['db_failed']} professional products need database upload")
        logger.info(f"💡 Upgrade Railway storage and run resume script to upload remaining products")
    
    return running_stats

def main():
    """Main function to run the complete dataset processing"""
    
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
        
        # Setup database schema
        clear_brand_ingredients_table(engine)
        add_enhanced_columns_to_table(engine)
        
        # Process complete dataset
        final_stats = process_complete_dataset(csv_file_path, engine)
        
        print(f"\n🎉 SUCCESS! Complete 4M dataset processing finished!")
        print(f"⭐ Professional photos found: {final_stats['professional']:,}")
        print(f"📁 All data saved to CSV files in '{OUTPUT_DIR}' directory")
        print(f"🗄️ Professional photos uploaded to Railway database")
        print(f"🔬 Ready for pattern analysis on categorized tiers!")
        
    except FileNotFoundError:
        logger.error(f"❌ File not found: {csv_file_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()