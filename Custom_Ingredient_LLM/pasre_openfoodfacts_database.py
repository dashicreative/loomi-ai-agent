
    #!/usr/bin/env python3
"""
Open Food Facts to Railway Database Importer
Finds 10 products with complete macro nutrition data and valid image URLs, uploads to PostgreSQL
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
import sys
import logging
import requests
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://postgres:pllLOhmJldsAQmZfbylAJjlnmsvajVjB@gondola.proxy.rlwy.net:24439/railway"

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

def check_row_completeness(row: pd.Series) -> bool:
    """Check if a row has all required fields and valid image URL"""
    
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
    
    # IMPORTANT: Try to get a valid image URL
    image_url = get_best_image_url(row)
    if not image_url:
        logger.debug(f"❌ Product '{required_fields['product_name']}' has no valid image URL")
        return False
    
    # Validate the image URL actually works
    if not validate_image_url(image_url):
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
    """Extract products that meet our criteria from the CSV file"""
    
    logger.info(f"📖 Reading CSV file: {file_path}")
    
    valid_products = []
    rows_processed = 0
    invalid_image_count = 0
    
    try:
        # Read CSV in chunks to avoid memory issues with large files
        chunk_size = 1000
        
        for chunk in pd.read_csv(file_path, sep='\t', encoding='utf-8', 
                                 chunksize=chunk_size, low_memory=False):
            
            for index, row in chunk.iterrows():
                rows_processed += 1
                
                if rows_processed % 10000 == 0:
                    logger.info(f"Processed {rows_processed:,} rows, found {len(valid_products)} valid products, {invalid_image_count} invalid images")
                
                # Basic field check first (faster) - removed image_url check since we'll find the best one
                if not all([
                    pd.notna(row.get('code')),
                    pd.notna(row.get('product_name')),
                    pd.notna(row.get('energy-kcal_100g')),
                    pd.notna(row.get('proteins_100g')),
                    pd.notna(row.get('carbohydrates_100g')),
                    pd.notna(row.get('fat_100g'))
                ]):
                    continue
                
                # If basic fields look good, find best image URL and validate
                product_name = str(row['product_name'])
                image_url = get_best_image_url(row)
                
                logger.info(f"🔍 Checking product: {product_name}")
                if image_url:
                    logger.info(f"    Best image URL found: {image_url}")
                else:
                    logger.info(f"    No valid image URL found")
                    invalid_image_count += 1
                    continue
                
                if check_row_completeness(row):
                    # Get the best image URL again (we know it exists since check_row_completeness passed)
                    best_image_url = get_best_image_url(row)
                    
                    product = {
                        'off_code': str(row['code']),
                        'product_name': product_name[:500],  # Limit length
                        'brand': str(row.get('brands', ''))[:255] if pd.notna(row.get('brands')) else None,
                        'image_url': best_image_url,
                        'calories_100g': float(row['energy-kcal_100g']),
                        'protein_100g': float(row['proteins_100g']),
                        'carbs_100g': float(row['carbohydrates_100g']),
                        'fat_100g': float(row['fat_100g'])
                    }
                    
                    valid_products.append(product)
                    logger.info(f"✅ Found valid product {len(valid_products)}: {product['product_name']}")
                    
                    if len(valid_products) >= target_count:
                        logger.info(f"🎯 Target of {target_count} products reached!")
                        return valid_products
                else:
                    invalid_image_count += 1
                    logger.info(f"❌ Product failed validation (likely bad image URL)")
                        
    except Exception as e:
        logger.error(f"❌ Error reading CSV file: {e}")
        raise
    
    logger.info(f"📊 Finished processing. Found {len(valid_products)} valid products out of {rows_processed:,} rows")
    logger.info(f"📊 {invalid_image_count} products had invalid images")
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
        
        logger.info(f"✅ Successfully uploaded {len(products)} products to database")
        
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
    print("🎉 PRODUCTS FOUND AND UPLOADED")
    print("="*80)
    
    for i, product in enumerate(products, 1):
        print(f"\n{i}. {product['product_name']}")
        print(f"   Brand: {product.get('brand', 'N/A')}")
        print(f"   Code: {product['off_code']}")
        print(f"   Nutrition (per 100g): {product['calories_100g']} cal, "
              f"{product['protein_100g']}g protein, {product['carbs_100g']}g carbs, "
              f"{product['fat_100g']}g fat")
        if product['image_url']:
            print(f"   Image: {product['image_url'][:60]}...")

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
        
        # First, explore what image fields are available
        explore_image_fields(csv_file_path)
        
        # Extract valid products
        logger.info("🔍 Starting search for valid products...")
        valid_products = extract_valid_products(csv_file_path, target_count=10)
        
        if not valid_products:
            logger.error("❌ No valid products found. Check your CSV file format.")
            sys.exit(1)
        
        # Upload to database
        logger.info("📤 Uploading products to database...")
        success = upload_to_database(valid_products, engine)
        
        if success:
            display_results(valid_products)
            print(f"\n🎉 Successfully completed! {len(valid_products)} products uploaded to Railway database.")
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