#!/usr/bin/env python3
"""
Open Food Facts to Railway Database Importer - US Market Edition
Finds 10 high-quality US market products with complete macro nutrition data and valid image URLs
Prioritizes products sold in the US with quality tiers (Premium > Good > Basic)
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
import sys
import logging
import requests
from typing import Optional, Dict, Any
from PIL import Image
import numpy as np
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://postgres:pllLOhmJldsAQmZfbylAJjlnmsvajVjB@gondola.proxy.rlwy.net:24439/railway"

def add_quality_columns_to_table(engine):
    """Add completeness and quality_tier columns to the brand_ingredients table if they don't exist"""
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            check_columns_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'brand_ingredients' 
            AND column_name IN ('completeness', 'quality_tier');
            """
            
            result = conn.execute(text(check_columns_sql))
            existing_columns = [row[0] for row in result.fetchall()]
            
            # Add completeness column if it doesn't exist
            if 'completeness' not in existing_columns:
                logger.info("📊 Adding 'completeness' column to brand_ingredients table...")
                conn.execute(text("ALTER TABLE brand_ingredients ADD COLUMN completeness DECIMAL(5,4)"))
                logger.info("✅ Added completeness column")
            else:
                logger.info("✅ Completeness column already exists")
            
            # Add quality_tier column if it doesn't exist
            if 'quality_tier' not in existing_columns:
                logger.info("🎯 Adding 'quality_tier' column to brand_ingredients table...")
                conn.execute(text("ALTER TABLE brand_ingredients ADD COLUMN quality_tier VARCHAR(20)"))
                logger.info("✅ Added quality_tier column")
            else:
                logger.info("✅ Quality_tier column already exists")
            
            conn.commit()
            logger.info("🔧 Table schema updated successfully")
            
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
        logger.debug(f"❌ Skipping placeholder URL with 'invalid': {url}")
        return False
    
    # Skip other common placeholder patterns
    placeholder_patterns = ['placeholder', 'default', 'missing', 'no-image']
    if any(pattern in url.lower() for pattern in placeholder_patterns):
        logger.debug(f"❌ Skipping placeholder URL: {url}")
        return False
    
    try:
        # Make a HEAD request to check if the URL is accessible without downloading the full image
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        
        # Check if status is successful (200-299 range)
        if 200 <= response.status_code < 300:
            # Also check if it's actually an image
            content_type = response.headers.get('content-type', '').lower()
            if any(img_type in content_type for img_type in ['image/', 'jpeg', 'jpg', 'png', 'gif', 'webp']):
                return True
        
        logger.debug(f"❌ Invalid image URL {url}: Status {response.status_code}, Content-Type: {response.headers.get('content-type', 'N/A')}")
        return False
        
    except requests.RequestException as e:
        logger.debug(f"❌ Image URL request failed {url}: {e}")
        return False
    except Exception as e:
        logger.debug(f"❌ Unexpected error validating image URL {url}: {e}")
        return False

def is_us_market_product(row: pd.Series) -> bool:
    """Check if product is sold in the US market"""
    countries = str(row.get('countries_tags', '')).lower()
    return 'united-states' in countries

def is_tier1_quality(row: pd.Series) -> bool:
    """Premium quality: US + high completeness + front image + high-res"""
    # Must be US market
    if not is_us_market_product(row):
        return False
    
    # High completeness score (top tier)
    completeness = row.get('completeness', 0)
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
    # Must be US market
    if not is_us_market_product(row):
        return False
    
    # Medium completeness score
    completeness = row.get('completeness', 0)
    if completeness < 0.6:
        return False
    
    # Any non-invalid image
    image_url = str(row.get('image_url', '')).lower()
    if 'invalid' in image_url:
        return False
    
    return True

def is_tier3_quality(row: pd.Series) -> bool:
    """Basic quality: US + basic completeness + working image"""
    # Must be US market
    if not is_us_market_product(row):
        return False
    
    # Basic completeness score
    completeness = row.get('completeness', 0)
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

def check_row_completeness(row: pd.Series, quality_tier: str = "tier1") -> bool:
    """Check if a row has all required fields and meets quality tier requirements"""
    
    required_fields = {
        'code': row.get('code'),
        'product_name': row.get('product_name'), 
        'energy-kcal_100g': row.get('energy-kcal_100g'),
        'proteins_100g': row.get('proteins_100g'),
        'carbohydrates_100g': row.get('carbohydrates_100g'),
        'fat_100g': row.get('fat_100g')
    }
    
    # Check that all required fields exist and are not null/empty
    for field_name, value in required_fields.items():
        if pd.isna(value) or value == '' or value is None:
            return False
    
    # Additional check: make sure nutritional values are reasonable numbers
    try:
        calories = float(required_fields['energy-kcal_100g'])
        protein = float(required_fields['proteins_100g'])
        carbs = float(required_fields['carbohydrates_100g'])
        fat = float(required_fields['fat_100g'])
        
        # Basic sanity checks (calories per 100g should be reasonable)
        if calories < 0 or calories > 1000:
            return False
        if protein < 0 or protein > 100:
            return False
        if carbs < 0 or carbs > 100:
            return False
        if fat < 0 or fat > 100:
            return False
            
    except (ValueError, TypeError):
        return False
    
    # Apply quality tier checks
    if quality_tier == "professional":
        if not is_professional_tier(row):
            return False
    elif quality_tier == "tier1":
        if not is_tier1_quality(row):
            return False
    elif quality_tier == "tier2":
        if not is_tier2_quality(row):
            return False
    elif quality_tier == "tier3":
        if not is_tier3_quality(row):
            return False
    
    # Finally, validate the image URL actually works
    image_url = get_best_image_url(row)
    if not image_url or not validate_image_url(image_url):
        logger.debug(f"❌ Product '{required_fields['product_name']}' has invalid image URL: {image_url}")
        return False
    
    return True

def explore_image_fields(file_path: str, sample_rows: int = 1000):
    """Explore what image-related fields are available in the CSV"""
    
    logger.info(f"🔍 Exploring image fields in first {sample_rows} rows...")
    
    try:
        # Read a small sample to see what fields are available
        sample_df = pd.read_csv(file_path, sep='\t', encoding='utf-8', nrows=sample_rows, low_memory=False)
        
        # Find all columns that might contain image URLs
        image_columns = [col for col in sample_df.columns if 'image' in col.lower()]
        
        logger.info(f"📊 Found these image-related columns: {image_columns}")
        
        # Check a few samples to see what the data looks like
        for col in image_columns[:5]:  # Check first 5 image columns
            non_null_count = sample_df[col].notna().sum()
            logger.info(f"   {col}: {non_null_count}/{sample_rows} rows have data")
            
            # Show a few sample values
            sample_values = sample_df[col].dropna().head(3).tolist()
            for val in sample_values:
                logger.info(f"      Sample: {str(val)[:80]}...")
                
    except Exception as e:
        logger.error(f"❌ Error exploring image fields: {e}")

def extract_valid_products(file_path: str, target_count: int = 10) -> list:
    """Extract US products with PROFESSIONAL white-background photos ONLY"""
    
    logger.info(f"📖 Reading CSV file: {file_path}")
    logger.info("⭐ PROFESSIONAL SEARCH: Looking for white-background studio photos only")
    logger.info("📝 Will search through entire database until target reached - no fallbacks!")
    
    valid_products = []
    rows_processed = 0
    us_products_found = 0
    
    # ONLY search for professional tier (white background photos)
    current_tier = "professional"
    
    try:
        # Read CSV in larger chunks for better performance
        chunk_size = 5000
        
        for chunk in pd.read_csv(file_path, sep='\t', encoding='utf-8', 
                                 chunksize=chunk_size, low_memory=False):
            
            for index, row in chunk.iterrows():
                rows_processed += 1
                
                if rows_processed % 25000 == 0:
                    logger.info(f"📊 Processed {rows_processed:,} rows, found {us_products_found} US products, "
                              f"⭐ {len(valid_products)} PROFESSIONAL white-background photos found")
                
                # Basic field check first (faster)
                if not all([
                    pd.notna(row.get('code')),
                    pd.notna(row.get('product_name')),
                    pd.notna(row.get('energy-kcal_100g')),
                    pd.notna(row.get('proteins_100g')),
                    pd.notna(row.get('carbohydrates_100g')),
                    pd.notna(row.get('fat_100g'))
                ]):
                    continue
                
                # Check if it's a US product first
                if not is_us_market_product(row):
                    continue
                
                us_products_found += 1
                
                # Get product info for logging
                product_name = str(row['product_name'])
                completeness = row.get('completeness', 0)
                image_url = get_best_image_url(row)
                
                logger.info(f"🔍 Checking US product: {product_name}")
                logger.info(f"    Completeness: {completeness:.3f}")
                logger.info(f"    Image URL: {image_url}")
                
                # Try current quality tier
                if check_row_completeness(row, current_tier):
                    # Get the best image URL again (we know it exists since check passed)
                    best_image_url = get_best_image_url(row)
                    
                    product = {
                        'off_code': str(row['code']),
                        'product_name': product_name[:500],
                        'brand': str(row.get('brands', ''))[:255] if pd.notna(row.get('brands')) else None,
                        'image_url': best_image_url,
                        'calories_100g': float(row['energy-kcal_100g']),
                        'protein_100g': float(row['proteins_100g']),
                        'carbs_100g': float(row['carbohydrates_100g']),
                        'fat_100g': float(row['fat_100g']),
                        'completeness': completeness,
                        'quality_tier': current_tier
                    }
                    
                    valid_products.append(product)
                    
                    logger.info(f"⭐ Found PROFESSIONAL photo #{len(valid_products)}: {product['product_name']}")
                    logger.info(f"🎯 Progress: {len(valid_products)}/{target_count} professional photos found")
                    
                    if len(valid_products) >= target_count:
                        logger.info(f"🎯 Target of {target_count} products reached!")
                        return valid_products
                
                # NO FALLBACK - Keep searching for professional photos only!
                # We'll process the entire 4M product database if needed
                        
    except Exception as e:
        logger.error(f"❌ Error reading CSV file: {e}")
        raise
    
    logger.info(f"🏁 Search completed! Processed {rows_processed:,} total rows")
    logger.info(f"📊 US products found: {us_products_found}")
    logger.info(f"⭐ PROFESSIONAL white-background photos found: {len(valid_products)}/{target_count}")
    
    if len(valid_products) < target_count:
        logger.warning(f"⚠️ Only found {len(valid_products)} professional photos (requested {target_count})")
    return valid_products

def upload_to_database(products: list, engine) -> bool:
    """Upload the products to the PostgreSQL database"""
    
    if not products:
        logger.warning("⚠️ No products to upload")
        return False
    
    try:
        # Convert to DataFrame for easy uploading
        df = pd.DataFrame(products)
        
        # Upload to database
        rows_uploaded = df.to_sql('brand_ingredients', engine, 
                                 if_exists='append', index=False, method='multi')
        
        logger.info(f"✅ Successfully uploaded {len(products)} US market products to database")
        
        # Verify upload
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM brand_ingredients"))
            total_count = result.scalar()
            logger.info(f"📊 Total products in brand_ingredients table: {total_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error uploading to database: {e}")
        return False

def display_results(products: list):
    """Display a summary of the products found"""
    
    if not products:
        logger.warning("No products found")
        return
    
    print("\n" + "="*80)
    print("⭐ PROFESSIONAL WHITE-BACKGROUND PRODUCTS FOUND!")
    print("="*80)
    
    # All products should be professional tier
    professional_count = len([p for p in products if p.get('quality_tier') == 'professional'])
    
    print(f"\n⭐ Professional photos: {professional_count}/{len(products)}")
    if professional_count == len(products):
        print("🎆 100% Professional white-background photos achieved!")
    else:
        print(f"⚠️ Warning: {len(products) - professional_count} non-professional photos found")
    
    for i, product in enumerate(products, 1):
        tier = "PROFESSIONAL" if product.get('quality_tier') == 'professional' else "NON-PROFESSIONAL"
        completeness = product.get('completeness', 0)
        
        print(f"\n{i}. [{tier}] {product['product_name']}")
        print(f"   Brand: {product.get('brand', 'N/A')}")
        print(f"   Code: {product['off_code']}")
        print(f"   Completeness: {completeness:.3f}")
        print(f"   Nutrition (per 100g): {product['calories_100g']} cal, "
              f"{product['protein_100g']}g protein, {product['carbs_100g']}g carbs, "
              f"{product['fat_100g']}g fat")
        if product['image_url']:
            print(f"   Image: {product['image_url'][:60]}...")
    
    print(f"\n🇺🇸 All products are verified to be sold in the US market!")
    print(f"\n⭐ All products have PROFESSIONAL studio white-background photography!")
    print(f"🇺🇸 All products verified to be sold in the US market!")
    print(f"🎯 Quality: PROFESSIONAL = Studio photos with white backgrounds only!")

def main():
    """Main function to run the import process"""
    
    # Option 1: Use command line argument (recommended)
    if len(sys.argv) == 2:
        csv_file_path = sys.argv[1]
    else:
        # Option 2: Hardcode the file path here if you prefer
        csv_file_path = "/Users/agustin/Desktop/en.openfoodfacts.org.products.csv"  # <-- Change this to your file path
        print(f"Using hardcoded file path: {csv_file_path}")
    
    # You can also hardcode it directly like this:
    # csv_file_path = "/full/path/to/your/en.openfoodfacts.org.products.csv"
    
    try:
        # Create database connection
        logger.info("🔗 Connecting to Railway PostgreSQL database...")
        engine = create_engine(DATABASE_URL)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
        
        # Clear existing data from table
        clear_brand_ingredients_table(engine)
        
        # Add quality columns to table if they don't exist
        add_quality_columns_to_table(engine)
        
        # First, explore what image fields are available
        explore_image_fields(csv_file_path)
        
        # Extract professional products only
        logger.info("⭐ Starting search for PROFESSIONAL white-background photos...")
        logger.info("🎯 Target: 10 professional studio photos only")
        logger.info("📝 No fallbacks - will search entire database if needed")
        valid_products = extract_valid_products(csv_file_path, target_count=10)
        
        if not valid_products:
            logger.error("❌ No valid products found. Check your CSV file format.")
            sys.exit(1)
        
        # Upload to database
        logger.info("📤 Uploading PROFESSIONAL white-background products to database...")
        success = upload_to_database(valid_products, engine)
        
        if success:
            display_results(valid_products)
            print(f"\n🎉 SUCCESS! {len(valid_products)} PROFESSIONAL white-background products uploaded!")
            print(f"⭐ All products have studio-quality professional photography")
            print(f"🇺🇸 All products verified to be sold in the United States") 
            print(f"📱 Perfect for your meal planning app - professional photos only!")
        else:
            logger.error("❌ Upload failed")
            sys.exit(1)
            
    except FileNotFoundError:
        logger.error(f"❌ File not found: {csv_file_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()