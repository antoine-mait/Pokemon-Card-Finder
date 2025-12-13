import os
import csv
import re
from cardList import get_card_name

def extract_set_code(folder_path):
    """Extract the set code from folder name (last part after last underscore)"""
    folder_name = os.path.basename(folder_path)
    parts = folder_name.split('_')
    if len(parts) > 0:
        return parts[-1]
    return 'ERROR'

def generate_csv_from_images(folder_path, output_folder='Renamed_Cropped'):
    """Generate CSV from renamed card images"""
    print("="*70)
    print("POKÉMON CARD CSV GENERATOR")
    print("="*70)
    
    output_dir = os.path.join(folder_path, output_folder)
    
    # Check if renamed folder exists
    if not os.path.exists(output_dir):
        print(f"\n✗ Folder '{output_folder}' not found in {folder_path}")
        return None
    
    # Find all FRONT images
    extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = sorted([f for f in os.listdir(output_dir) 
                         if any(f.lower().endswith(ext) for ext in extensions) 
                         and '_FRONT' in f])
    
    if len(image_files) == 0:
        print(f"\n✗ No FRONT card images found in {output_dir}")
        return None
    
    print(f"\nFound {len(image_files)} front card images")
    
    # Extract set code
    set_code = extract_set_code(folder_path)
    print(f"Using set code: {set_code}")
    
    # Get script directory for CSV output
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, f'cardList_tcgPowerTool_{set_code}.csv')
    
    # Dictionary to track card quantities: key = (card_name, local_id, set_code)
    card_quantities = {}
    
    # Process each image
    for filename in image_files:
        try:
            # Parse filename: Name_Number_Set_FR_FRONT.ext or Name_Number_Set_FR_FRONT(1).ext
            # Remove duplicate suffix like (1), (2), etc. before processing
            clean_filename = re.sub(r'\(\d+\)', '', filename)
            
            # Split from right to get: [..., Set, FR, FRONT.ext]
            parts = clean_filename.rsplit('_', 3)
            
            if len(parts) >= 3:
                name_number = parts[0]  # Everything before last 3 underscores
                name_parts = name_number.rsplit('_', 1)  # Split name and number
                
                if len(name_parts) == 2:
                    card_number = name_parts[1]  # "017-094" or "017/094"
                    
                    # Extract local_id (the number before the /)
                    local_id = card_number.replace('/', '-').split('-')[0]
                    
                    # Get English name from database using set code
                    card_name_en = get_card_name(card_number, set_code=set_code, language='EN')
                    
                    if card_name_en:
                        card_key = (card_name_en, local_id, set_code)
                        card_quantities[card_key] = card_quantities.get(card_key, 0) + 1
                        print(f"✓ Counted: {card_name_en} #{local_id} (quantity: {card_quantities[card_key]})")
                    else:
                        # Fallback to French name from filename if English not found
                        card_name_fr = name_parts[0]
                        card_key = (card_name_fr, local_id, set_code)
                        card_quantities[card_key] = card_quantities.get(card_key, 0) + 1
                        print(f"✓ Counted: {card_name_fr} #{local_id} (from filename, quantity: {card_quantities[card_key]})")
                        
        except Exception as e:
            print(f"✗ Error processing {filename}: {e}")
            continue
    
    # Write CSV with aggregated quantities
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Card Name', 'Card Number', 'Set Code', 'Quantity', 'Language', 'Finish Type', 'Condition', 'Comment'])
        
        for (card_name, local_id, set_code), quantity in sorted(card_quantities.items()):
            writer.writerow([card_name, local_id, set_code, quantity, 'FR', 'regular', 'NM', 'Booster -> Sleeve'])
    
    print(f"\n✓ CSV saved: {csv_path}")
    print(f"  Unique cards: {len(card_quantities)}")
    print(f"  Total cards: {sum(card_quantities.values())}")
    print("="*70)
    
    return csv_path


# Main execution
if __name__ == "__main__":
    print("="*70)
    print("POKÉMON CARD CSV GENERATOR")
    print("="*70)
    
    folder_path = input("\nEnter full path to folder containing renamed cards: ").strip().strip('"')
    
    if os.path.exists(folder_path):
        generate_csv_from_images(folder_path)
    else:
        print(f"\n✗ Folder not found: {folder_path}")
    
    print("\n✅ Done!")