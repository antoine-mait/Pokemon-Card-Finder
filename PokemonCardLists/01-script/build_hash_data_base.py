"""
Build Feature Hash Database
Run this ONCE to convert all reference images to feature hashes
This reduces 11GB of images to a few MB JSON file
"""

import cv2
import numpy as np
import json
from pathlib import Path
from tqdm import tqdm

def extract_features(image_path):
    """Extract ORB features from image"""
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=500)
    kp, des = orb.detectAndCompute(gray, None)
    
    if des is not None:
        # Convert to list for JSON serialization
        return des.tolist()
    return None

def build_hash_database(set_code, base_path='PokemonCardLists/Card_Sets'):
    """Build feature hash database for a set"""
    
    print(f"\n{'='*70}")
    print(f"BUILDING FEATURE DATABASE FOR SET: {set_code}")
    print(f"{'='*70}\n")
    
    set_path = Path(base_path)
    
    # Find set folder
    set_folders = [f for f in set_path.iterdir() 
                   if f.is_dir() and f.name.endswith(f"_{set_code}")]
    
    if not set_folders:
        print(f"Error: Set folder for '{set_code}' not found")
        return
    
    set_folder = set_folders[0]
    img_folder = set_folder / "IMG"
    
    if not img_folder.exists():
        print(f"Error: IMG folder not found in {set_folder}")
        return
    
    print(f"Found set folder: {set_folder.name}")
    print(f"Processing images from: {img_folder}\n")
    
    # Get all image files
    image_files = (
        list(img_folder.glob("**/*.jpg")) + 
        list(img_folder.glob("**/*.webp")) + 
        list(img_folder.glob("**/*.png"))
    )
    
    print(f"Found {len(image_files)} images\n")
    
    # Extract features for each card
    feature_db = {}
    
    for img_path in tqdm.tqdm(image_files, desc="Extracting features"):
        # Get card ID from filename
        filename = img_path.stem
        parts = filename.split('_')
        if len(parts) >= 1:
            card_id = parts[0]
            
            # Extract features
            features = extract_features(img_path)
            
            if features is not None:
                feature_db[card_id] = features
    
    # Save to JSON
    output_file = Path("PokemonCardLists/CardsFeature") / f"card_hashes_{set_code}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\nSaving to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(feature_db, f)
    
    # Calculate size
    file_size = Path(output_file).stat().st_size / (1024 * 1024)
    
    print(f"\n{'='*70}")
    print(f"✅ COMPLETE")
    print(f"{'='*70}")
    print(f"Cards processed: {len(feature_db)}")
    print(f"Database size: {file_size:.2f} MB")
    print(f"Compression: {11000 / file_size:.0f}x smaller than images!")
    print(f"{'='*70}\n")

def build_all_sets(base_path='PokemonCardLists/Card_Sets'):
    """Build databases for all sets"""
    
    base_path = Path(base_path)
    
    # Find all set folders
    set_folders = [f for f in base_path.iterdir() if f.is_dir()]
    
    print(f"\n{'='*70}")
    print(f"FOUND {len(set_folders)} SETS")
    print(f"{'='*70}\n")
    
    for i, folder in enumerate(set_folders, 1):
        parts = folder.name.split('_')
        if len(parts) > 0:
            set_code = parts[-1]
            print(f"{i}. {folder.name} (Set: {set_code})")
    
    print(f"\n{'='*70}")
    choice = input("Process all sets? (y/n): ").strip().lower()
    
    if choice == 'y':
        for folder in set_folders:
            parts = folder.name.split('_')
            if len(parts) > 0:
                set_code = parts[-1]
                try:
                    build_hash_database(set_code, base_path)
                except Exception as e:
                    print(f"Error processing {set_code}: {e}")
    else:
        set_code = input("\nEnter set code to process: ").strip()
        build_hash_database(set_code, base_path)

if __name__ == "__main__":
    print("="*70)
    print("POKEMON CARD FEATURE HASH DATABASE BUILDER")
    print("="*70)
    print("\nThis tool converts 11GB of reference images into")
    print("lightweight feature databases (~10MB each)")
    print("\nOnly needs to be run ONCE per set!")
    print("="*70 + "\n")
    
    # Install tqdm if needed
    try:
        import tqdm
    except ImportError:
        print("Installing tqdm for progress bars...")
        import subprocess
        subprocess.check_call(['pip', 'install', 'tqdm'])
        from tqdm import tqdm
    
    build_all_sets()