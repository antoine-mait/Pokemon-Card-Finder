import json
import os

def fix_encoding(text):
    """Fix common UTF-8 encoding issues"""
    replacements = {
        'Ã©': 'é',
        'Ã¨': 'è',
        'Ãª': 'ê',
        'Ã ': 'à',
        'Ã§': 'ç',
        'Ã¯': 'ï',
        'Ã´': 'ô',
        'Ã»': 'û',
        'Ã‰': 'É',
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    return text

def get_card_name(card_number, set_code, language='FR'):
    """
    Get card name from set-specific database
    
    Args:
        card_number: Card number (e.g., "001/130")
        set_code: Set code (e.g., "XY12", "SV01")
        language: 'FR' or 'EN' (default: 'FR')
    
    Returns:
        Card name or None if not found
    """
    # Determine which JSON file to use
    if language.upper() == 'EN':
        json_file = 'cardList_EN.json'
    else:
        json_file = 'cardList.json'
    
    if not os.path.exists(json_file):
        print(f"  ⚠ Warning: Card list file {json_file} not found")
        return None
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            all_sets = json.load(f)
        
        # Check if set exists
        if set_code not in all_sets:
            print(f"  ⚠ Warning: Set '{set_code}' not found in {json_file}")
            return None
        
        # Extract just the card number (before the /)
        number = card_number.split('/')[0].lstrip('0')
        if not number:  # In case it was "000"
            number = "0"
        
        # Look up the card
        card_name = all_sets[set_code].get(number)
        
        if card_name:
            return card_name
        else:
            print(f"  ⚠ Card #{card_number} not found in set {set_code}")
            return None
            
    except json.JSONDecodeError as e:
        print(f"  ✗ Error: Invalid JSON in {json_file}: {e}")
        return None
    except Exception as e:
        print(f"  ✗ Error reading card list: {e}")
        return None