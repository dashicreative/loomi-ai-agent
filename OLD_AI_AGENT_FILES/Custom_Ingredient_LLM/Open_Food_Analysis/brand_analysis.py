import pandas as pd
import csv
from collections import defaultdict
from fuzzywuzzy import fuzz, process
import re

# Hardcode your CSV path here
CSV_PATH = "/Users/agustin/Desktop/en.openfoodfacts.org.products.csv"

# US stores for filtering (based on our previous analysis)
US_STORES = [
    "walmart", "aldi", "kroger", "costco", "h-e-b", "safeway", 
    "trader joe's", "whole foods", "sams club", "target", "publix"
]

def clean_brand_name(brand_text):
    """Clean and normalize brand names for better analysis"""
    if not brand_text or pd.isna(brand_text):
        return None
    
    # Convert to lowercase and remove extra spaces
    cleaned = str(brand_text).lower().strip()
    
    # Remove common suffixes/prefixes that might interfere
    cleaned = re.sub(r'\b(inc|llc|ltd|corp|co|company)\b', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned if cleaned else None

def is_us_product(stores_field):
    """Check if product is sold in US stores"""
    if pd.isna(stores_field) or not str(stores_field).strip():
        return False
    
    stores_list = re.split(r'[,|;]', str(stores_field).lower())
    
    for store in stores_list:
        cleaned_store = store.strip()
        for us_store in US_STORES:
            if us_store in cleaned_store:
                return True
    return False

def analyze_brands_sample(sample_size=None):
    """Analyze brand field patterns focusing on US products"""
    
    print(f"🇺🇸 Starting US brand analysis on entire CSV...")
    print(f"📁 Reading from: {CSV_PATH}")
    print(f"🏪 Filtering for US stores: {', '.join(US_STORES)}")
    
    # Brand findings
    brand_counts = defaultdict(int)
    empty_brand_count = 0
    empty_store_count = 0
    total_processed = 0
    us_products_found = 0
    
    # Read CSV in chunks for memory efficiency
    chunk_size = 10000
    
    try:
        for chunk in pd.read_csv(CSV_PATH, sep='\t', chunksize=chunk_size, 
                                usecols=['product_name', 'stores', 'brands'], 
                                dtype=str, na_values=[''], keep_default_na=True):
            
            for _, row in chunk.iterrows():
                total_processed += 1
                
                # Progress heartbeat every 50k rows
                if total_processed % 50000 == 0:
                    print(f"💓 Processed {total_processed:,} rows... Found {us_products_found:,} US products so far")
                
                stores_field = row.get('stores')
                brands_field = row.get('brands')
                
                # Skip empty stores
                if pd.isna(stores_field) or not str(stores_field).strip():
                    empty_store_count += 1
                    continue
                
                # Check if this is a US product
                if not is_us_product(stores_field):
                    continue
                
                us_products_found += 1
                
                # Skip empty brands
                if pd.isna(brands_field) or not str(brands_field).strip():
                    empty_brand_count += 1
                    continue
                
                # Split multiple brands (usually comma or pipe separated)
                brand_list = re.split(r'[,|;]', str(brands_field))
                
                for brand in brand_list:
                    cleaned_brand = clean_brand_name(brand)
                    if cleaned_brand:
                        brand_counts[cleaned_brand] += 1
                
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    print(f"\n✅ Analysis complete!")
    print(f"📊 Total rows processed: {total_processed:,}")
    print(f"🇺🇸 US products found: {us_products_found:,} ({us_products_found/total_processed*100:.1f}%)")
    print(f"🏪 Empty store fields: {empty_store_count:,} ({empty_store_count/total_processed*100:.1f}%)")
    print(f"🏷️ Empty brand fields (US products): {empty_brand_count:,} ({empty_brand_count/us_products_found*100:.1f}% of US products)")
    
    # Filter brands with at least 10 occurrences and write to file
    filtered_brands = [(brand, count) for brand, count in brand_counts.items() if count >= 10]
    filtered_brands.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n{'='*60}")
    print(f"🇺🇸 TOP 450 US BRANDS WITH 10+ OCCURRENCES ({len(filtered_brands)} total)")
    print(f"{'='*60}")
    
    # Write to output file
    output_file = "/Users/agustin/Desktop/loomi_ai_agent/Custom_Ingredient_LLM/brand_analysis_output.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("US BRAND ANALYSIS RESULTS\n")
        f.write("="*60 + "\n")
        f.write(f"Total rows processed: {total_processed:,}\n")
        f.write(f"US products found: {us_products_found:,} ({us_products_found/total_processed*100:.1f}%)\n")
        f.write(f"Empty store fields: {empty_store_count:,} ({empty_store_count/total_processed*100:.1f}%)\n")
        f.write(f"Empty brand fields (US products): {empty_brand_count:,} ({empty_brand_count/us_products_found*100:.1f}% of US products)\n")
        f.write(f"US brands with 10+ occurrences: {len(filtered_brands)}\n\n")
        
        # Show top 450 brands
        top_450 = filtered_brands[:450] if len(filtered_brands) >= 450 else filtered_brands
        
        for i, (brand, count) in enumerate(top_450, 1):
            percentage = (count / us_products_found) * 100
            line = f"{i:3d}. '{brand}' → {count:,} times ({percentage:.2f}% of US products)\n"
            print(line.strip())
            f.write(line)
        
        if len(filtered_brands) > 450:
            f.write(f"\n... and {len(filtered_brands) - 450} more brands with 10+ occurrences\n")
    
    print(f"\n💾 Results saved to: {output_file}")
    print(f"🎉 Analysis complete! Found top US brands for your filtering logic.")
    
    return brand_counts

if __name__ == "__main__":
    # Run the analysis
    brand_counts = analyze_brands_sample()