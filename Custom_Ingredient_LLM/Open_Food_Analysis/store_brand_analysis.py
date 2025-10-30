import pandas as pd
import csv
from collections import defaultdict
from fuzzywuzzy import fuzz, process
import re

# Hardcode your CSV path here
CSV_PATH = "/Users/agustin/Desktop/en.openfoodfacts.org.products.csv"

# Target stores to analyze (top 15 US grocery chains)
TARGET_STORES = [
    "walmart", "kroger", "whole foods", "costco", "albertsons", 
    "safeway", "food lion", "giant", "stop shop", "publix", 
    "heb", "sams club", "target", "aldi", "sprouts", "trader joe"
]

def clean_store_name(store_text):
    """Clean and normalize store names for better matching"""
    if not store_text or pd.isna(store_text):
        return None
    
    # Convert to lowercase and remove extra spaces
    cleaned = str(store_text).lower().strip()
    
    # Remove common suffixes/prefixes that might interfere
    cleaned = re.sub(r'\b(store|supermarket|grocery|market|supercenter)\b', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned if cleaned else None

def analyze_stores_sample(sample_size=None):
    """Analyze store field patterns in a large sample"""
    
    print(f"🔍 Starting store analysis on entire CSV...")
    print(f"📁 Reading from: {CSV_PATH}")
    
    # Store findings
    store_variants = defaultdict(set)
    store_counts = defaultdict(int)
    empty_store_count = 0
    total_processed = 0
    
    # Read CSV in chunks for memory efficiency
    chunk_size = 10000
    rows_read = 0
    
    try:
        for chunk in pd.read_csv(CSV_PATH, sep='\t', chunksize=chunk_size, 
                                usecols=['product_name', 'stores', 'brands'], 
                                dtype=str, na_values=[''], keep_default_na=True):
            
            for _, row in chunk.iterrows():
                    
                rows_read += 1
                total_processed += 1
                
                # Progress heartbeat every 25k rows
                if total_processed % 25000 == 0:
                    print(f"💓 Processed {total_processed:,} rows...")
                
                stores_field = row.get('stores')
                
                # Skip empty stores
                if pd.isna(stores_field) or not str(stores_field).strip():
                    empty_store_count += 1
                    continue
                
                # Split multiple stores (usually comma or pipe separated)
                store_list = re.split(r'[,|;]', str(stores_field))
                
                for store in store_list:
                    cleaned_store = clean_store_name(store)
                    if not cleaned_store:
                        continue
                    
                    store_counts[cleaned_store] += 1
                    
                    # Check fuzzy matches against our target stores
                    for target in TARGET_STORES:
                        similarity = fuzz.partial_ratio(target, cleaned_store)
                        if similarity >= 70:  # 70% similarity threshold
                            store_variants[target].add(cleaned_store)
            
                
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    print(f"\n✅ Analysis complete! Processed {total_processed:,} rows")
    print(f"📊 Empty store fields: {empty_store_count:,} ({empty_store_count/total_processed*100:.1f}%)")
    
    # Report findings for each target store
    print(f"\n{'='*60}")
    print("🏪 STORE ANALYSIS RESULTS")
    print(f"{'='*60}")
    
    for target_store in TARGET_STORES:
        variants = store_variants[target_store]
        if variants:
            total_count = sum(store_counts[variant] for variant in variants)
            print(f"\n🎯 {target_store.upper()}:")
            print(f"   📈 Total occurrences: {total_count:,}")
            print(f"   🏷️  Variants found ({len(variants)}):")
            
            # Sort variants by frequency
            sorted_variants = sorted(variants, key=lambda x: store_counts[x], reverse=True)
            for variant in sorted_variants[:10]:  # Show top 10 variants
                count = store_counts[variant]
                percentage = (count / total_processed) * 100
                print(f"      • '{variant}' → {count:,} times ({percentage:.2f}%)")
                
            if len(sorted_variants) > 10:
                print(f"      ... and {len(sorted_variants) - 10} more variants")
        else:
            print(f"\n❌ {target_store.upper()}: No matches found")
    
    # Filter stores with at least 10 occurrences and write to file
    filtered_stores = [(store, count) for store, count in store_counts.items() if count >= 10]
    filtered_stores.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n{'='*60}")
    print(f"📋 STORES WITH 10+ OCCURRENCES ({len(filtered_stores)} total)")
    print(f"{'='*60}")
    
    # Write to output file
    output_file = "/Users/agustin/Desktop/loomi_ai_agent/Custom_Ingredient_LLM/store_analysis_output.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("STORE ANALYSIS RESULTS\n")
        f.write("="*60 + "\n")
        f.write(f"Total rows processed: {total_processed:,}\n")
        f.write(f"Empty store fields: {empty_store_count:,} ({empty_store_count/total_processed*100:.1f}%)\n")
        f.write(f"Stores with 10+ occurrences: {len(filtered_stores)}\n\n")
        
        for i, (store, count) in enumerate(filtered_stores, 1):
            percentage = (count / total_processed) * 100
            line = f"{i:3d}. '{store}' → {count:,} times ({percentage:.2f}%)\n"
            print(line.strip())
            f.write(line)
    
    print(f"\n💾 Results saved to: {output_file}")
    print(f"🎉 Analysis complete! Use these exact store names in your filtering logic.")
    
    return store_variants, store_counts

if __name__ == "__main__":
    # Run the analysis
    variants, counts = analyze_stores_sample()