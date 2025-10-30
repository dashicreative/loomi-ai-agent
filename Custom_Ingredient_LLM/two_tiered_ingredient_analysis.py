#!/usr/bin/env python3
"""
Two-Tiered Ingredient Analysis - MAXIMUM SPEED OPTIMIZATION
Stage 1: Fast pre-filtering to find tier1 candidates (no network operations)
Stage 2: 10-thread parallel processing for image validation + white background detection
Expected 10-50x speed improvement over sequential processing
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

# Threading configuration
MAX_IMAGE_THREADS = 10
IMAGE_TIMEOUT = 10

def setup_output_directory():
    """Create output directory if it doesn't exist"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info(f"📁 Created output directory: {OUTPUT_DIR}")

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

def validate_image_url(url: str, timeout: int = IMAGE_TIMEOUT) -> bool:
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
        response = requests.get(image_url, timeout=IMAGE_TIMEOUT, stream=True)
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
    """Process a single tier1 candidate through expensive image validation + white background check"""
    
    try:
        image_url = candidate_data['image_url']
        
        # Stage 2A: Validate image URL (expensive HTTP request)
        if not validate_image_url(image_url):
            return None
        
        # Stage 2B: Check for white background (expensive image download + processing)
        if not check_corners_for_white(image_url):
            return None
        
        # SUCCESS - this is a professional photo!
        return candidate_data
        
    except Exception as e:
        logger.debug(f"❌ Error processing candidate {candidate_data.get('product_name', 'Unknown')}: {e}")
        return None

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
            logger.info(f"📁 Professional products cannot be uploaded - upgrade storage needed")
        else:
            logger.error(f"💾 Database error: {e}")
            logger.info(f"📁 Database upload failed - can retry later")
        
        return 0, len(products)  # uploaded, failed

def save_checkpoint(checkpoint_data: dict):
    """Save current processing state to checkpoint file"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint_two_tier.json")
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)

def load_checkpoint() -> Optional[dict]:
    """Load checkpoint data if it exists"""
    checkpoint_file = os.path.join(OUTPUT_DIR, "checkpoint_two_tier.json")
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return None

def start_heartbeat_monitor(stats_dict: dict):
    """Start heartbeat monitor that prints progress every 30 seconds"""
    
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
                    
                    print(f"💓 HEARTBEAT: Row {current_row:,} | Candidates: {tier1_candidates} | Processed: {candidates_processed} | Professional: {professional_count}")
                    print(f"           Stage1: {stage1_rate:.0f} rows/sec | Stage2: {stage2_rate:.1f} candidates/sec | ETA: {eta_hours:.1f}h")
    
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    return thread

def process_two_tier_analysis(file_path: str, engine) -> dict:
    """Two-stage processing: Fast filtering + Parallel image processing"""
    
    logger.info(f"🚀 TWO-TIER INGREDIENT ANALYSIS - MAXIMUM SPEED")
    logger.info(f"📂 Input file: {file_path}")
    logger.info(f"🎯 Stage 1: Fast tier1 candidate filtering (no network)")
    logger.info(f"🎯 Stage 2: {MAX_IMAGE_THREADS}-thread parallel image processing")
    
    # Setup
    setup_output_directory()
    start_time = time.time()
    
    # Initialize stats for heartbeat
    stats_dict = {
        'active': True,
        'current_row': 0,
        'tier1_candidates': 0,
        'candidates_processed': 0,
        'professional_count': 0,
        'start_time': start_time
    }
    
    # Start heartbeat monitor
    heartbeat_thread = start_heartbeat_monitor(stats_dict)
    
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
        professional_count = checkpoint['professional_count']
        db_uploaded = checkpoint.get('db_uploaded', 0)
        db_failed = checkpoint.get('db_failed', 0)
        start_row = checkpoint['current_row']
        batch_num = checkpoint.get('last_batch_completed', 0) + 1
        total_processed = checkpoint['total_processed']
        tier1_candidates_total = checkpoint.get('tier1_candidates', 0)
        candidates_processed_total = checkpoint.get('candidates_processed', 0)
    else:
        professional_count = 0
        db_uploaded = 0
        db_failed = 0
        start_row = 0
        batch_num = 1
        total_processed = 0
        tier1_candidates_total = 0
        candidates_processed_total = 0
    
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
                    # Add to candidate queue for Stage 2 processing
                    candidate_data = extract_professional_product_data(row)
                    tier1_candidates_batch.append(candidate_data)
                    tier1_candidates_total += 1
                    stats_dict['tier1_candidates'] = tier1_candidates_total
            
            stage1_time = time.time() - stage1_start
            logger.info(f"✅ Stage 1 complete: {len(tier1_candidates_batch)} tier1 candidates found in {stage1_time:.1f}s")
            
            # ===== STAGE 2: PARALLEL IMAGE PROCESSING =====
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
            
            # Upload professional products to database
            if professional_batch:
                uploaded, failed = upload_to_database_safe(professional_batch, engine)
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
                professional_rate = (professional_count / tier1_candidates_total) * 100 if tier1_candidates_total > 0 else 0
            else:
                eta_hours = 0
                tier1_rate = 0
                professional_rate = 0
            
            print(f"\n📊 BATCH {batch_num} COMPLETE (Rows {total_processed-chunk_size+1:,} - {total_processed:,})")
            print(f"Stage 1: {len(tier1_candidates_batch)} tier1 candidates found | Stage 2: {len(professional_batch)} professional photos")
            if len(professional_batch) > 0:
                print(f"         ↳ DB Uploaded: {uploaded}, DB Failed: {failed}")
            print(f"Running Total: {tier1_candidates_total} candidates ({tier1_rate:.2f}%) | {professional_count} professional ({professional_rate:.1f}%)")
            if db_failed > 0:
                print(f"Database: {db_uploaded} uploaded, {db_failed} failed (storage limit?)")
            else:
                print(f"Database: {db_uploaded} uploaded successfully")
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
    logger.info(f"🏁 TWO-TIER ANALYSIS COMPLETE!")
    logger.info(f"⏱️ Total time: {total_time/3600:.2f} hours")
    logger.info(f"📊 Stage 1: Processed {total_processed:,} rows, found {tier1_candidates_total:,} tier1 candidates")
    logger.info(f"📊 Stage 2: Processed {candidates_processed_total:,} candidates, found {professional_count:,} professional photos")
    logger.info(f"🗄️ Database uploads: {db_uploaded}")
    
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
    """Main function to run the two-tier ingredient analysis"""
    
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
        
        # Clear existing data (keep schema - columns already exist)
        clear_brand_ingredients_table(engine)
        
        # Process complete dataset with two-tier analysis
        final_stats = process_two_tier_analysis(csv_file_path, engine)
        
        print(f"\n🎉 SUCCESS! Two-tier ingredient analysis complete!")
        print(f"📊 Stage 1 efficiency: {final_stats['tier1_candidates']:,} candidates from {final_stats['total_processed']:,} rows ({(final_stats['tier1_candidates']/final_stats['total_processed']*100):.2f}%)")
        print(f"📊 Stage 2 efficiency: {final_stats['professional']:,} professional from {final_stats['tier1_candidates']:,} candidates ({(final_stats['professional']/final_stats['tier1_candidates']*100):.1f}%)")
        print(f"⭐ Professional photos found: {final_stats['professional']:,}")
        print(f"🗄️ Professional photos uploaded to Railway database: {final_stats['db_uploaded']:,}")
        print(f"🚀 Ready to test your meal planning app with professional photos!")
        
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