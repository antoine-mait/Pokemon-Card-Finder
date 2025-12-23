import os
import json
import csv
from pathlib import Path

def load_sets_data(json_path):
    """Load the all_sets_full.json file and create a mapping of set names to ptcgoCode"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Create a mapping: set name (lowercase) -> ptcgoCode
    set_mapping = {}
    for set_info in data.get('data', []):
        set_name = set_info.get('name', '').lower()
        ptcgo_code = set_info.get('ptcgoCode', '')
        if set_name and ptcgo_code:
            set_mapping[set_name] = ptcgo_code
    
    return set_mapping

def get_set_code_from_folder(folder_name, set_mapping):
    """Extract set code from folder name using the set mapping"""
    # Remove underscores and convert to lowercase
    folder_parts = folder_name.replace('_', ' ').lower()
    
    # Try to extract just the set name (remove the ID part at the end)
    parts = folder_parts.split()
    cleaned_parts = []
    for part in parts:
        # Skip parts that are likely set IDs (short alphanumeric codes)
        if len(part) <= 4 and any(c.isdigit() for c in part):
            continue
        cleaned_parts.append(part)
    
    folder_clean = ' '.join(cleaned_parts)
    
    # Try exact match with cleaned name
    if folder_clean in set_mapping:
        return set_mapping[folder_clean]
    
    # Try matching by finding the best overlap
    best_match = None
    best_score = 0
    
    for set_name, code in set_mapping.items():
        # Check if all words in folder name are in set name
        folder_words = set(folder_clean.split())
        set_words = set(set_name.split())
        
        # Calculate overlap score
        overlap = len(folder_words & set_words)
        if overlap > best_score and overlap > 0:
            best_score = overlap
            best_match = code
    
    if best_match:
        return best_match
    
    return "UNKNOWN"

def load_english_card_names(set_folder_path, base_cardlist_path='PokemonCardLists/Card_Sets'):
    """Load English card names from CSV file for a given set"""
    csv_folder = Path(base_cardlist_path)
    folder_name = set_folder_path.name
    
    # Extract set code from folder name (last part after underscore)
    parts = folder_name.split('_')
    if len(parts) >= 2:
        set_code = parts[-1].lower()
    else:
        return {}
    
    # Find matching set folder in CardList directory
    set_folders = list(csv_folder.glob(f"*{set_code}*"))
    
    # Try zero-padded version if not found (e.g., SV6 -> SV06)
    if not set_folders:
        import re
        match = re.match(r'^([A-Za-z]+)(\d+)$', set_code)
        if match:
            letters = match.group(1)
            numbers = match.group(2)
            padded_code = f"{letters}0{numbers}"
            set_folders = list(csv_folder.glob(f"*{padded_code}*"))
    
    if not set_folders:
        print(f"  ⚠️  No CardList folder found for set code: {set_code}")
        return {}
    
    csv_set_folder = set_folders[0]
    print(f"  ✓ Found CardList folder: {csv_set_folder.name}")
    
    # Find English CSV file
    csv_files = (list(csv_set_folder.glob("CardList_*_en.CSV")) or 
                 list(csv_set_folder.glob("CardList_*_en.csv")))
    
    if not csv_files:
        print(f"  ⚠️  No English CSV found in {csv_set_folder.name}")
        return {}
    
    csv_file = csv_files[0]
    card_names = {}
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                local_id = row.get('localId', '').strip()
                name = row.get('name', '').strip()
                if local_id and name:
                    card_names[local_id] = name
        
        print(f"  ✓ Loaded {len(card_names)} English card names")
        return card_names
    except Exception as e:
        print(f"  ⚠️  Error loading English names: {e}")
        return {}

def process_cards(base_path, json_path, output_csv):
    """Process all card images and generate CSV"""
    
    # Load set mappings
    set_mapping = load_sets_data(json_path)
    
    # Prepare CSV data
    csv_data = []
    
    # Navigate to Sets folder
    sets_path = Path(base_path)
    
    if not sets_path.exists():
        print(f"Error: Folder not found at {sets_path}")
        return
    
    print(f"Looking for set folders in: {sets_path}")
    print(f"Folders found: {[f.name for f in sets_path.iterdir() if f.is_dir()]}")
    
    # Process each set folder
    for set_folder in sets_path.iterdir():
        if not set_folder.is_dir():
            continue
        
        print(f"\nProcessing set: {set_folder.name}")
        
        # Get the set code
        set_code = get_set_code_from_folder(set_folder.name, set_mapping)
        print(f"  Matched set code: {set_code}")
        
        # Load English card names for this set
        english_names = load_english_card_names(set_folder)
        
        # Navigate to renamed_cropped folder
        cropped_path = set_folder / "Renamed_Cropped"
        
        # Also try lowercase version
        if not cropped_path.exists():
            cropped_path = set_folder / "renamed_cropped"
        
        if not cropped_path.exists():
            print(f"  Warning: renamed_cropped folder not found in {set_folder.name}")
            continue
        
        # Process each language folder
        languages = ['FR', 'EN', 'DE', 'JA']
        for lang in languages:
            lang_path = cropped_path / lang
            
            if not lang_path.exists():
                print(f"  Warning: {lang} folder not found in {set_folder.name}")
                continue
            
            # Process all image files
            for img_file in lang_path.iterdir():
                if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    # Skip _BACK images
                    if '_BACK' in img_file.stem.upper():
                        continue
                    
                    # Parse filename: CardName_LocalId_SetCode_Language_FRONT.ext
                    filename = img_file.stem
                    
                    # Split from the right to get: [..., SetCode, Language, FRONT]
                    parts = filename.rsplit('_', 3)
                    
                    if len(parts) < 4:
                        print(f"  ⚠️  Skipping invalid filename: {img_file.name}")
                        continue
                    
                    # Extract card name and local ID
                    card_and_id = parts[0]
                    card_parts = card_and_id.rsplit('_', 1)
                    
                    if len(card_parts) < 2:
                        print(f"  ⚠️  Cannot extract card number: {img_file.name}")
                        continue
                    
                    local_id = card_parts[1]
                    
                    # Get English name from loaded data
                    if english_names and local_id in english_names:
                        card_name_en = english_names[local_id]
                    else:
                        # Fallback: use name from filename
                        card_name_with_underscores = card_parts[0]
                        card_name_en = card_name_with_underscores.replace('_', ' ')
                        if not english_names:
                            print(f"  ⚠️  Using filename for card #{local_id}: {card_name_en}")
                    
                    # Add to CSV data with separate collector number column
                    csv_data.append({
                        'Card Name': card_name_en,
                        'Collector Number': local_id,
                        'Set Code': set_code,
                        'Quantity': 1,
                        'Language': lang,
                        'Foil': 'no',
                        'Condition': 'NM',
                        'Comment': 'New seller, DM for more pictures'
                    })
                    
            print(f"  Processed {lang} folder: {len([f for f in lang_path.iterdir() if f.is_file() and '_BACK' not in f.stem.upper()])} cards")
    
    # Write to CSV
    if csv_data:
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Card Name', 'Collector Number', 'Set Code', 'Quantity', 'Language', 'Foil', 'Condition', 'Comment']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(csv_data)
        
        print(f"\nCSV file created successfully: {output_csv}")
        print(f"Total cards processed: {len(csv_data)}")
    else:
        print("\nNo cards found to process.")

# Main execution
if __name__ == "__main__":
    base_path_def = input(r"Base folder path (D:\05-Pokemon\01-Collection or D:\05-Pokemon\02-vente): ")
    base_path = base_path_def
    json_path = r"D:\02-Travaille\04-Coding\03-Projects\05-Rename_Pokemon_Photo\PokemonCardLists\all_sets_full.json"
    output_csv = r"D:\02-Travaille\04-Coding\03-Projects\05-Rename_Pokemon_Photo\TcgPowerTool\pokemon_cards_inventory.csv"
    
    process_cards(base_path, json_path, output_csv)