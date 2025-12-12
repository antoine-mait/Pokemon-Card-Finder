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

def get_card_name(card_number, language='FR'):
    """
    Get card name from card number
    card_number: string like "017/094" or "017-094"
    language: 'FR' or 'EN'
    """
    # Clean the card number (remove set info)
    number = card_number.split('/')[0].split('-')[0]
    
    # Pad with zeros if needed
    number = number.zfill(3)
    
    # Load the appropriate JSON file
    json_file = 'cardList_EN.json' if language == 'EN' else 'cardList.json'
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            card_data = json.load(f)
            return card_data.get(number, None)
    except FileNotFoundError:
        print(f"Error: {json_file} not found")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {json_file}")
        return None