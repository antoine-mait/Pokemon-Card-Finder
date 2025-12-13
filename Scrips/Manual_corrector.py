import cv2
import os
import sys
import csv
import pickle
import numpy as np
from pathlib import Path

from cards_utils import (
    LearningSystem,
    CardDatabase,
    sanitize_filename,
    extract_set_code
)

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def correct_card_pair(folder_path, language):
    """Interactive tool to correct a card pair"""
    
    set_code = extract_set_code(folder_path)
    print(f"\n{'='*70}")
    print(f"MANUAL CARD CORRECTION TOOL")
    print(f"Set: {set_code} | Language: {language}")
    print(f"{'='*70}\n")
    
    # Initialize systems
    card_db = CardDatabase(set_code)
    card_db.load_card_info_for_language(language)
    learning = LearningSystem(set_code)
    
    # Get renamed cards folder
    renamed_folder = os.path.join(folder_path, 'Renamed_Cropped', language)
    
    if not os.path.exists(renamed_folder):
        print(f"❌ Error: Renamed folder not found at {renamed_folder}")
        return
    
    # List all files
    image_files = sorted([f for f in os.listdir(renamed_folder) 
                         if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    
    if not image_files:
        print("❌ No image files found")
        return
    
    print(f"Found {len(image_files)} images ({len(image_files)//2} pairs)\n")
    
    # Show some examples
    print("Examples of files:")
    for i, img in enumerate(image_files[:6]):
        print(f"  {i+1}. {img}")
    if len(image_files) > 6:
        print(f"  ... and {len(image_files) - 6} more")
    
    print("\n" + "="*70)
    print("HOW TO USE:")
    print("="*70)
    print("1. Enter the FRONT filename (or part of it)")
    print("2. Script will find both FRONT and BACK")
    print("3. Search for the correct card")
    print("4. Script will rename both and update learning database")
    print("="*70 + "\n")
    
    while True:
        # Get filename to correct
        search = input("\nEnter filename (or part of it) to correct (or 'quit'): ").strip()
        
        if search.lower() == 'quit':
            break
        
        if not search:
            continue
        
        # Find matching files
        matching_fronts = [f for f in image_files if 'FRONT' in f and search.lower() in f.lower()]
        
        if not matching_fronts:
            print(f"❌ No FRONT files found matching '{search}'")
            continue
        
        if len(matching_fronts) > 1:
            print(f"\n📋 Found {len(matching_fronts)} matching files:")
            for i, f in enumerate(matching_fronts, 1):
                print(f"  {i}. {f}")
            
            choice = input("\nEnter number to select (or Enter for first): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(matching_fronts):
                front_file = matching_fronts[int(choice) - 1]
            else:
                front_file = matching_fronts[0]
        else:
            front_file = matching_fronts[0]
        
        # Find corresponding BACK file
        back_file = front_file.replace('_FRONT', '_BACK')
        
        print(f"\n{'='*70}")
        print(f"CORRECTING CARD PAIR")
        print(f"{'='*70}")
        print(f"FRONT: {front_file}")
        
        front_path = os.path.join(renamed_folder, front_file)
        back_path = os.path.join(renamed_folder, back_file)
        
        if os.path.exists(back_path):
            print(f"BACK:  {back_file}")
        else:
            print(f"BACK:  ⚠ Not found")
            back_path = None
        
        # Load front image for learning
        front_img = cv2.imread(front_path)
        if front_img is None:
            print("❌ Could not load front image")
            continue
        
        # Search for correct card
        print(f"\n{'='*70}")
        print("SEARCH FOR CORRECT CARD")
        print(f"{'='*70}")
        print("Enter card number (e.g., '154', '157') or card name")
        print("Type 'list' to see all cards")
        print("Type 'skip' to skip this card")
        
        while True:
            card_search = input("\nSearch: ").strip()
            
            if card_search.lower() == 'skip':
                break
            
            if card_search.lower() == 'list':
                print(f"\n{'='*70}")
                print(f"ALL CARDS IN SET {set_code}")
                print(f"{'='*70}")
                cards = card_db.list_all_cards(language)
                for local_id, name, card_id in cards:
                    print(f"  #{local_id:4s} - {name}")
                print(f"{'='*70}")
                continue
            
            if not card_search:
                print("Please enter a search term")
                continue
            
            # Search
            results = card_db.search_card(card_search)
            
            if not results:
                print(f"❌ No cards found matching '{card_search}'")
                continue
            
            # Show results
            print(f"\n📋 Found {len(results)} card(s):")
            for i, (card_id, info, match_type) in enumerate(results, 1):
                local_id = info.get('localId', 'N/A')
                name = card_db.get_card_name_for_language(info, language)
                print(f"  {i}. #{local_id:4s} - {name}")
            
            # Select card
            if len(results) == 1:
                selected_idx = 0
            else:
                choice = input("\nSelect card number (or Enter for first): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(results):
                    selected_idx = int(choice) - 1
                else:
                    selected_idx = 0
            
            card_id, card_info, _ = results[selected_idx]
            local_id = card_info.get('localId', 'Unknown').replace('/', '-')
            name = card_db.get_card_name_for_language(card_info, language)
            name_sanitized = sanitize_filename(name)
            
            print(f"\n✓ Selected: {name} (#{local_id})")
            
            confirm = input("Confirm this correction? (y/n): ").strip().lower()
            
            if confirm == 'y':
                # Generate new filenames
                ext = os.path.splitext(front_file)[1]
                new_front = f"{name_sanitized}_{local_id}_{set_code}_{language}_FRONT{ext}"
                new_back = f"{name_sanitized}_{local_id}_{set_code}_{language}_BACK{ext}"
                
                new_front_path = os.path.join(renamed_folder, new_front)
                new_back_path = os.path.join(renamed_folder, new_back)
                
                # Rename FRONT
                try:
                    # Remove old learning if exists
                    learning.remove_match(front_img)
                    
                    # Rename file
                    os.rename(front_path, new_front_path)
                    print(f"  ✓ Renamed FRONT: {new_front}")
                    
                    # Add to learning database
                    front_img_new = cv2.imread(new_front_path)
                    if front_img_new is not None:
                        learning.add_confirmed_match(front_img_new, card_id)
                        print(f"  💾 Updated learning database")
                    
                    # Rename BACK if exists
                    if back_path and os.path.exists(back_path):
                        os.rename(back_path, new_back_path)
                        print(f"  ✓ Renamed BACK: {new_back}")
                    
                    print(f"\n✅ Card pair corrected successfully!")
                    
                except Exception as e:
                    print(f"❌ Error during rename: {e}")
                
                break
            else:
                print("Correction cancelled, search again...")


if __name__ == "__main__":
    print("="*70)
    print("POKÉMON CARD MANUAL CORRECTION TOOL")
    print("="*70)
    print("\nThis tool lets you:")
    print("  • Correct misnamed card pairs")
    print("  • Update the learning database")
    print("  • Fix cards like Meganium/Typhlosion mix-ups")
    print()
    
    folder_path = input("Enter path to set folder: ").strip().strip('"')
    
    if not os.path.exists(folder_path):
        print(f"❌ Error: Folder not found: {folder_path}")
    else:
        # Check for renamed folders
        renamed_base = os.path.join(folder_path, 'Renamed_Cropped')
        
        if not os.path.exists(renamed_base):
            print(f"❌ Error: No 'Renamed_Cropped' folder found")
        else:
            # Find available languages
            languages = [d for d in os.listdir(renamed_base) 
                        if os.path.isdir(os.path.join(renamed_base, d))]
            
            if not languages:
                print("❌ No language folders found")
            else:
                print(f"\nAvailable languages: {', '.join(languages)}")
                selected_lang = input("Enter language code: ").strip().upper()
                
                if selected_lang in languages:
                    correct_card_pair(folder_path, selected_lang)
                else:
                    print(f"❌ Invalid language. Choose from: {', '.join(languages)}")
    
    print("\n✅ Done!")