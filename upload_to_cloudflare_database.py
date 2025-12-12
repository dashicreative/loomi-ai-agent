"""
Upload ingredient images and category fallback images to R2
Makes all images square with white padding
"""
import boto3
from pathlib import Path
from PIL import Image
from io import BytesIO
import re

# ===== CONFIGURATION =====
R2_ENDPOINT = 'https://982b132b29d32ceee9f494d6b9b23cec.r2.cloudflarestorage.com'
R2_ACCESS_KEY = '20cd20c57a8f359c575d4fa25b9ee515'
R2_SECRET_KEY = 'd03a43d0525524e9f6f176ea350aec34c49e9204ff568aca92f33e0d4e45fa69'
R2_BUCKET = 'loomi-ingredient-data'
R2_PUBLIC_URL = 'https://pub-4559f4553008447b97be2209a19f3b75.r2.dev'


INGREDIENT_IMAGES_FOLDER = '/Users/agustin/Desktop/Temp'
CATEGORY_IMAGES_FOLDER = 'X'
SQUARE_SIZE = 800
# =========================

def make_square_with_padding(image_path, size=800):
    """Convert any image to square with white padding"""
    img = Image.open(image_path)
    
    if img.mode != 'RGB':
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            rgb_img.paste(img, mask=img.split()[-1])
        else:
            rgb_img.paste(img)
        img = rgb_img
    
    width, height = img.size
    
    # Scale to fit
    if width > height:
        new_width = size
        new_height = int(height * (size / width))
    else:
        new_height = size
        new_width = int(width * (size / height))
    
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Create white square
    square_img = Image.new('RGB', (size, size), (255, 255, 255))
    x_offset = (size - new_width) // 2
    y_offset = (size - new_height) // 2
    square_img.paste(img, (x_offset, y_offset))
    
    return square_img

def optimize_to_bytes(img, max_size_kb=80):
    """Compress to target size"""
    quality = 85
    while quality > 20:
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        if buffer.tell() / 1024 <= max_size_kb:
            buffer.seek(0)
            return buffer.getvalue()
        quality -= 5
    buffer.seek(0)
    return buffer.getvalue()

# Setup S3 client
s3 = boto3.client('s3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY
)

print("=" * 70)
print("UPLOADING IMAGES TO CLOUDFLARE R2")
print("=" * 70)

# Upload ingredient images
print("\n📸 UPLOADING INGREDIENT IMAGES...")
print("-" * 70)

ingredient_folder = Path(INGREDIENT_IMAGES_FOLDER)
ingredient_urls = []
uploaded = 0

for img_file in sorted(ingredient_folder.glob('*')):
    if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
        continue
    
    try:
        square_img = make_square_with_padding(img_file, SQUARE_SIZE)
        image_bytes = optimize_to_bytes(square_img)
        
        # Use filename as-is (you already named them)
        filename = img_file.stem + '.jpg'
        
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=f"ingredients/{filename}",  # Store in subfolder
            Body=image_bytes,
            ContentType='image/jpeg',
            CacheControl='public, max-age=31536000'
        )
        
        url = f"{R2_PUBLIC_URL}/ingredients/{filename}"
        ingredient_urls.append({
            'filename': img_file.name,
            'new_filename': filename,
            'url': url
        })
        
        uploaded += 1
        if uploaded % 50 == 0:
            print(f"   Uploaded {uploaded} images...")
        
    except Exception as e:
        print(f"❌ Failed: {img_file.name} - {e}")

print(f"✅ Uploaded {uploaded} ingredient images")

# Save ingredient URLs for reference
import pandas as pd
pd.DataFrame(ingredient_urls).to_csv('uploaded_ingredient_urls.csv', index=False)
print(f"📄 Saved URLs to: uploaded_ingredient_urls.csv")

# Upload category/fallback images
print("\n📁 UPLOADING CATEGORY FALLBACK IMAGES...")
print("-" * 70)

category_folder = Path(CATEGORY_IMAGES_FOLDER)
category_urls = []
uploaded = 0

for img_file in sorted(category_folder.glob('*')):
    if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
        continue
    
    try:
        square_img = make_square_with_padding(img_file, SQUARE_SIZE)
        image_bytes = optimize_to_bytes(square_img)
        
        filename = img_file.stem + '.jpg'
        
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=f"categories/{filename}",  # Separate subfolder
            Body=image_bytes,
            ContentType='image/jpeg',
            CacheControl='public, max-age=31536000'
        )
        
        url = f"{R2_PUBLIC_URL}/categories/{filename}"
        category_urls.append({
            'filename': img_file.name,
            'new_filename': filename,
            'url': url
        })
        
        print(f"   ✅ {filename}")
        uploaded += 1
        
    except Exception as e:
        print(f"❌ Failed: {img_file.name} - {e}")

print(f"✅ Uploaded {uploaded} category images")

pd.DataFrame(category_urls).to_csv('uploaded_category_urls.csv', index=False)
print(f"📄 Saved URLs to: uploaded_category_urls.csv")

print("\n" + "=" * 70)
print("UPLOAD COMPLETE!")
print("=" * 70)
print(f"Ingredient images: {len(ingredient_urls)}")
print(f"Category images: {len(category_urls)}")