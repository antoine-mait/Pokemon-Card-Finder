import os
import csv
from pathlib import Path

def parse_card_filename(filename):
    """
    Parse a card filename to extract card name and ID.
    
    Example: Dark Houndoom_7_NEO4_JA_FRONT.jpg
    Returns: ('Dark Houndoom', 'NEO4-7')
    """
    # Remove file extension
    name_without_ext = filename.rsplit('.', 1)[0]
    
    # Skip if it's a BACK image
    if name_without_ext.endswith('_BACK'):
        return None, None
    
    # Remove _FRONT suffix if present
    if name_without_ext.endswith('_FRONT'):
        name_without_ext = name_without_ext[:-6]
    
    # Split by underscore
    parts = name_without_ext.split('_')
    
    # Expected format: CardName_Number_SetCode_Language_FRONT
    # Parts: [...card name parts..., number, set_code, language]
    if len(parts) < 3:
        print(f"Warning: Skipping malformed filename: {filename}")
        return None, None
    
    # Last parts should be: language, set_code, number
    language = parts[-1]
    set_code = parts[-2]
    number = parts[-3]
    
    # Everything before number is the card name
    card_name_parts = parts[:-3]
    card_name = ' '.join(card_name_parts)
    
    # Create card ID in format: SETCODE-NUMBER (lowercase for API compatibility)
    card_id = f"{set_code.lower()}-{number}"
    
    return card_name, card_id


def scan_collection_folder(base_path):
    """
    Scan the collection folder structure and extract card information.
    
    Args:
        base_path: Path to D:\05-Vente_Carte
    
    Returns:
        List of tuples (card_name, card_id, set_name, language)
    """
    cards = []
    base_path = Path(base_path)
    
    if not base_path.exists():
        print(f"Error: Base path does not exist: {base_path}")
        return cards
    
    # Iterate through set folders
    for set_folder in base_path.iterdir():
        if not set_folder.is_dir():
            continue
        
        set_name = set_folder.name
        print(f"\nScanning set: {set_name}")
        
        # Look for renamed_cropped folder
        renamed_cropped_path = set_folder / "renamed_cropped"
        
        if not renamed_cropped_path.exists():
            print(f"  Warning: 'renamed_cropped' folder not found in {set_name}")
            continue
        
        # Iterate through language folders (DE, EN, FR, JA)
        for language_folder in renamed_cropped_path.iterdir():
            if not language_folder.is_dir():
                continue
            
            language = language_folder.name
            
            # Scan all image files in the language folder
            image_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
            image_files = [f for f in language_folder.iterdir() 
                          if f.suffix in image_extensions]
            
            for image_file in image_files:
                card_name, card_id = parse_card_filename(image_file.name)
                
                if card_name and card_id:
                    cards.append({
                        'card_name': card_name,
                        'card_id': card_id,
                        'set_folder': set_name,
                        'language': language,
                        'filename': image_file.name
                    })
            
            if image_files:
                print(f"  {language}: Found {len(image_files)} images")
    
    return cards


def create_collection_csv(cards, output_file='my_pokemon_collection.csv', include_set_info=False):
    """
    Create a CSV file from the card list.
    
    Args:
        cards: List of card dictionaries
        output_file: Output CSV filename
        include_set_info: Whether to include set and language columns
    """
    if not cards:
        print("No cards found to export!")
        return
    
    # Remove duplicates (same card_id)
    unique_cards = {}
    for card in cards:
        card_id = card['card_id']
        if card_id not in unique_cards:
            unique_cards[card_id] = card
    
    print(f"\n{'='*70}")
    print(f"Found {len(cards)} total card images")
    print(f"Found {len(unique_cards)} unique cards")
    print(f"{'='*70}")
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if include_set_info:
            fieldnames = ['card_name', 'card_id', 'set_folder', 'language', 'quantity', 'condition', 'reverse_holo']
        else:
            fieldnames = ['card_name', 'card_id', 'quantity', 'condition', 'reverse_holo']
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for card_id, card_info in sorted(unique_cards.items()):
            row = {
                'card_name': card_info['card_name'],
                'card_id': card_id,
                'quantity': 1,  # Default quantity
                'condition': 'nm',  # Default condition
                'reverse_holo': 'no'  # Default not reverse holo
            }
            
            if include_set_info:
                row['set_folder'] = card_info['set_folder']
                row['language'] = card_info['language']
            
            writer.writerow(row)
    
    print(f"\n✓ Collection CSV created: {output_file}")
    print(f"  Total unique cards: {len(unique_cards)}")
    print(f"\nYou can now edit the CSV to adjust:")
    print("  - quantity (how many copies you have)")
    print("  - condition (nm, lp, mp, hp, dmg)")
    print("  - reverse_holo (yes/no)")


def create_detailed_report(cards, output_file='collection_detailed.csv'):
    """
    Create a detailed CSV with all card instances (including duplicates across languages).
    """
    if not cards:
        print("No cards found!")
        return
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['card_name', 'card_id', 'set_folder', 'language', 'filename']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(cards, key=lambda x: (x['card_id'], x['language'])))
    
    print(f"✓ Detailed report created: {output_file}")
    print(f"  Total card images: {len(cards)}")


def main():
    # Configuration
    BASE_PATH = r"D:\05-Vente_Carte"
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    OUTPUT_CSV = script_dir / "my_pokemon_collection.csv"
    DETAILED_CSV = script_dir / "collection_detailed.csv"
    
    print("="*70)
    print("Pokemon Collection CSV Generator")
    print("="*70)
    print(f"Scanning folder: {BASE_PATH}")
    
    # Scan the collection
    cards = scan_collection_folder(BASE_PATH)
    
    if cards:
        # Create simple CSV for price tracking (unique cards only)
        create_collection_csv(cards, OUTPUT_CSV, include_set_info=False)
        
        # Create detailed report (all instances)
        create_detailed_report(cards, DETAILED_CSV)
        
        print("\n" + "="*70)
        print("Summary by Set:")
        print("="*70)
        
        # Group by set
        sets = {}
        for card in cards:
            set_name = card['set_folder']
            if set_name not in sets:
                sets[set_name] = []
            sets[set_name].append(card)
        
        for set_name, set_cards in sorted(sets.items()):
            unique_in_set = len(set(c['card_id'] for c in set_cards))
            print(f"{set_name:40} {unique_in_set:3} unique cards, {len(set_cards):3} total images")
        
        print("="*70)
        print("\nNext steps:")
        print(f"1. Open '{OUTPUT_CSV}' and adjust quantities/conditions")
        print("2. Use this CSV with CardPrice.py to get CardMarket prices")
        print("="*70)
    else:
        print("\n⚠️  No cards found! Check your folder structure:")
        print("  Expected: D:\\05-Vente_Carte\\SetName\\renamed_cropped\\LANGUAGE\\*.jpg")


if __name__ == "__main__":
    main()