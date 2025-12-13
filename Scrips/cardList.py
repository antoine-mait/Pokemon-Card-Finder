import json
import os
import csv

def find_set_folder(set_code, base_path='PokemonCardLists/Card_Sets'):
    """
    Find the set folder by set code
    
    Args:
        set_code: Set code (e.g., "XY12", "SV01", "sv03.5", "PFL")
        base_path: Base path to Card_Sets folder
    
    Returns:
        Full path to set folder or None if not found
    """
    if not os.path.exists(base_path):
        print(f"  ⚠ Warning: Card_Sets folder not found at {base_path}")
        return None
    
    # Normalize set code for comparison (handle case and dots)
    set_code_normalized = set_code.lower().replace('.', '')
    
    # Search through all folders in Card_Sets
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        if os.path.isdir(folder_path):
            # Folder format: SetName_SetCode
            if '_' in folder_name:
                folder_set_code = folder_name.split('_')[-1].lower().replace('.', '')
                if folder_set_code == set_code_normalized:
                    print(f"  ✓ Found set folder: {folder_name}")
                    return folder_path
    
    print(f"  ⚠ Warning: No folder found for set code '{set_code}'")
    return None

def get_card_name(card_number, set_code=None, language='EN'):
    """
    Get card name from set-specific database in Card_Sets folder
    
    Args:
        card_number: Card number (e.g., "001/130" or "001-130")
        set_code: Set code (e.g., "XY12", "SV01", "sv03.5", "PFL")
        language: 'FR', 'EN', 'DE', etc. (default: 'FR')
    
    Returns:
        Card name or None if not found
    """
    if not set_code:
        print(f"  ⚠ Warning: No set code provided")
        return None
    
    # Find the set folder
    set_folder = find_set_folder(set_code)
    if not set_folder:
        return None
    
    # Extract just the card number (before the / or -)
    # Remove leading zeros
    number = card_number.replace('/', '-').split('-')[0].lstrip('0')
    if not number:  # In case it was "000"
        number = "0"
    
    print(f"  Looking for card number: {number} in language: {language}")
    
    # Look for CSV files in the set folder
    all_csv_files = [f for f in os.listdir(set_folder) if f.endswith('.csv')]
    
    if not all_csv_files:
        print(f"  ⚠ Warning: No CSV files found in {set_folder}")
        return None
    
    # Prioritize CSV files by language
    language_lower = language.lower()
    csv_files_prioritized = []
    
    # First: files matching the requested language
    for csv_file in all_csv_files:
        if language_lower in csv_file.lower():
            csv_files_prioritized.append(csv_file)
    
    # Then: add remaining files
    for csv_file in all_csv_files:
        if csv_file not in csv_files_prioritized:
            csv_files_prioritized.append(csv_file)
    
    print(f"  CSV files to check (in order): {csv_files_prioritized}")
    
    # Process CSV files in priority order
    for csv_file in csv_files_prioritized:
        csv_path = os.path.join(set_folder, csv_file)
        print(f"  Checking: {csv_file}")
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Try different possible column names for the card number
                    row_number = None
                    
                    # Check for localId first (preferred for multi-language sets)
                    if 'localId' in row:
                        row_number = str(row['localId']).lstrip('0')
                    elif 'local_id' in row:
                        row_number = str(row['local_id']).lstrip('0')
                    elif 'number' in row:
                        row_number = str(row['number']).lstrip('0')
                    elif 'id' in row:
                        # id might be like "sv03.5-001", extract the number part
                        id_val = str(row['id'])
                        if '-' in id_val:
                            row_number = id_val.split('-')[-1].lstrip('0')
                        else:
                            row_number = id_val.lstrip('0')
                    
                    # Ensure empty string becomes "0"
                    if not row_number:
                        row_number = "0"
                    
                    # Match the card number
                    if row_number == number:
                        # Return the card name
                        card_name = None
                        if 'name' in row:
                            card_name = row['name']
                        elif 'card_name' in row:
                            card_name = row['card_name']
                        
                        if card_name:
                            print(f"  ✓ Found: {card_name} (from {csv_file})")
                            return card_name
                        
        except Exception as e:
            print(f"  ⚠ Error reading {csv_file}: {e}")
            continue
    
    print(f"  ✗ Card #{card_number} not found in set {set_code}")
    return None

def get_set_card_count(set_code, base_path='PokemonCardLists/Card_Sets'):
    """Get total card count for a set from CSV"""
    set_folder = find_set_folder(set_code, base_path)
    if not set_folder:
        return None
    
    csv_files = [f for f in os.listdir(set_folder) if f.endswith('.csv')]
    
    for csv_file in csv_files:
        csv_path = os.path.join(set_folder, csv_file)
        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'set_cardCount' in row and row['set_cardCount']:
                        count = row['set_cardCount'].strip()
                        if count:
                            print(f"  ✓ Found set card count: {count}")
                            return count
        except Exception as e:
            continue
    
    return None