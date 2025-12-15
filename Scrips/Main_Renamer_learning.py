import cv2
import numpy as np
import os
import sys
import json
import csv
import pickle
from pathlib import Path
from threading import Thread, Lock
from queue import Queue
import time

user_interaction_lock = Lock()

from cards_utils import (
    LearningSystem, 
    CardDatabase, 
    CardCropper,
    sanitize_filename, 
    get_unique_filename, 
    extract_set_code
)

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Global lock for user interaction
user_interaction_lock = Lock()
csv_write_lock = Lock()

class CardMatcher:
    """Match cropped cards against reference images using computer vision"""
    
    def __init__(self, set_code, base_path='PokemonCardLists/Card_Sets'):
        self.set_code = set_code
        self.base_path = Path(base_path)
        self.reference_images = {}
        self.card_info_map = {}
        self.csv_path = None
        self.current_language = None
        self.use_pokedex = False
        self.pokedex_db = None
        self.load_reference_images()
        self.learning = LearningSystem(self.set_code)
        self.check_if_old_set()
        self.window_name = None
    
    def show_comparison_window(self, cropped_image, card_id, card_name):
        """Show side-by-side comparison of cropped card and reference"""
        if card_id not in self.reference_images:
            return
        
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            ref_img = self.reference_images[card_id]
            
            # Convert BGR to RGB
            crop_rgb = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2RGB)
            ref_rgb = cv2.cvtColor(ref_img, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL
            img_crop = Image.fromarray(crop_rgb)
            img_ref = Image.fromarray(ref_rgb)
            
            # Resize to same height
            target_height = 600
            aspect_crop = img_crop.width / img_crop.height
            aspect_ref = img_ref.width / img_ref.height
            
            img_crop = img_crop.resize((int(target_height * aspect_crop), target_height), 
                                      Image.Resampling.LANCZOS)
            img_ref = img_ref.resize((int(target_height * aspect_ref), target_height), 
                                    Image.Resampling.LANCZOS)
            
            # Create side-by-side comparison
            total_width = img_crop.width + img_ref.width + 20
            total_height = target_height + 60
            
            comparison = Image.new('RGB', (total_width, total_height), color=(0, 0, 0))
            comparison.paste(img_crop, (0, 60))
            comparison.paste(img_ref, (img_crop.width + 20, 60))
            
            # Add labels
            draw = ImageDraw.Draw(comparison)
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except:
                font = ImageFont.load_default()
            
            draw.text((10, 10), "Your Card", fill='white', font=font)
            draw.text((img_crop.width + 30, 10), f"Match: {card_name}", fill='white', font=font)
            
            # Show in default image viewer (same as old code)
            comparison.show(title=f"Match: {card_name} [{self.current_language}]")
            self.window_name = "PIL_COMPARISON"
            
        except ImportError:
            print(f"  ⚠️  Cannot display comparison (Pillow not installed)")
            print(f"  💡 Install: pip install Pillow")
        except Exception as e:
            print(f"  ⚠️  Cannot display comparison: {e}")
    
    def close_comparison_window(self):
        """Close the comparison window"""
        if self.window_name:
            self.window_name = None
            
    def check_if_old_set(self):
        """Check if this is a pre-2002 set that needs Pokedex for JA language"""
        sets_file = Path('PokemonCardLists/all_sets_full.json')
        
        if not sets_file.exists():
            old_set_prefixes = ['base', 'jungle', 'fossil', 'base2', 'gym1', 'gym2', 
                               'neo1', 'neo2', 'neo3', 'neo4', 'legendary']
            if any(self.set_code.lower().startswith(prefix) for prefix in old_set_prefixes):
                self.use_pokedex = True
                from cards_utils import PokedexDatabase
                self.pokedex_db = PokedexDatabase()
                print(f"  📖 Old set detected - Pokedex lookup enabled for JA")
            return
        
        try:
            with open(sets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                all_sets = data.get('data', [])
            elif isinstance(data, list):
                all_sets = data
            else:
                all_sets = []
            
            found_set = False
            for set_info in all_sets:
                if not isinstance(set_info, dict):
                    continue
                    
                set_id = set_info.get('id', '')
                if set_id == self.set_code or set_id.lower() == self.set_code.lower():
                    release_date = set_info.get('releaseDate', '')
                    
                    if release_date:
                        year = int(release_date.split('/')[0])
                        if year <= 2002:
                            self.use_pokedex = True
                            from cards_utils import PokedexDatabase
                            self.pokedex_db = PokedexDatabase()
                            print(f"  📖 Old set ({year}) - Pokedex enabled for JA")
                    found_set = True
                    break
                    
        except Exception as e:
            print(f"  ⚠ Error checking set date: {e}")
            
    def load_reference_images(self):
        """Load all reference images and card info from the set folder"""
        print(f"\n  Looking for set code: '{self.set_code}'")
        
        set_folders = [f for f in self.base_path.iterdir() 
                       if f.is_dir() and f.name.endswith(f"_{self.set_code}")]
        
        if not set_folders:
            set_folders = [f for f in self.base_path.iterdir() 
                           if f.is_dir() and f.name.lower().endswith(f"_{self.set_code.lower()}")]
        
        if not set_folders:
            set_folders = [f for f in self.base_path.iterdir() 
                           if f.is_dir() and self.set_code.lower() in f.name.lower()]
        
        if not set_folders:
            print(f"\n⚠ Warning: Set folder for '{self.set_code}' not found")
            return
        
        set_folder = set_folders[0]
        print(f"  ✓ Found set folder: {set_folder.name}")
        
        img_folder = set_folder / "IMG"
        
        if not img_folder.exists():
            print(f"\n⚠ Warning: IMG folder not found")
            return
        
        self.set_folder = set_folder
        self.csv_files = list(set_folder.glob("CardList_*.csv"))
        if self.csv_files:  
            self.load_card_info(self.csv_files[0])
        
        print(f"  Loading reference images...")
        image_files = list(img_folder.glob("*.jpg")) + list(img_folder.glob("*.webp")) + list(img_folder.glob("*.png"))
        
        for img_path in image_files:
            filename = img_path.stem
            parts = filename.split('_')
            if len(parts) >= 1:
                card_id = parts[0]
                img = cv2.imread(str(img_path))
                if img is not None:
                    self.reference_images[card_id] = img
        
        print(f"  ✓ Loaded {len(self.reference_images)} reference images")
    
    def load_card_info_for_language(self, language):
        """Load card information from the language-specific CSV"""
        if not hasattr(self, 'csv_files') or not self.csv_files:
            return
        
        lang_lower = language.lower()
        csv_file = None
        
        for csv_path in self.csv_files:
            if f"_{lang_lower}.csv" in str(csv_path).lower():
                csv_file = csv_path
                break
        
        if not csv_file:
            return
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    card_id = row.get('id', '')
                    if card_id and card_id in self.card_info_map:
                        lang_key = f'name_{language.lower()}'
                        self.card_info_map[card_id][lang_key] = row.get('name', 'Unknown')
        except Exception as e:
            print(f"  ⚠ Error loading CSV: {e}")
        
    def load_card_info(self, csv_path):
        """Load card information from CSV with base structure"""
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    card_id = row.get('id', '')
                    if card_id:
                        self.card_info_map[card_id] = {
                            'name': row.get('name', 'Unknown'),
                            'localId': row.get('localId', ''),
                            'id': card_id,
                            'name_de': '', 'name_en': '', 'name_es': '',
                            'name_fr': '', 'name_it': '', 'name_ja': '',
                            'name_ko': '', 'name_pt': '',
                        }
            print(f"  ✓ Loaded info for {len(self.card_info_map)} cards")
            
            # Load English names for CSV generation
            self.load_card_info_for_language('EN')
            
        except Exception as e:
            print(f"  ⚠ Error loading CSV: {e}")
    
    def get_card_name_for_language(self, card_info, language):
        """Get the card name in the specified language"""
        lang_key = f'name_{language.lower()}'
        
        if lang_key in card_info and card_info[lang_key]:
            name = card_info[lang_key]
            if name and name != 'Unknown':
                return name
        
        return card_info.get('name', 'Unknown')
    
    def get_english_name(self, card_info):
        """Get English name for CSV export"""
        name_en = card_info.get('name_en', '').strip()
        if name_en and name_en != 'Unknown':
            return name_en
        return card_info.get('name', 'Unknown')
    
    def set_language(self, language):
        """Set the current language being processed"""
        self.current_language = language
    
    def get_card_by_number(self, card_number):
        """Get card info by card number"""
        for card_id, info in self.card_info_map.items():
            if info.get('localId', '').strip() == card_number.strip():
                return info
        
        card_number_clean = card_number.strip()
        if card_number_clean in self.card_info_map:
            return self.card_info_map[card_number_clean]
        
        full_id = f"{self.set_code}-{card_number_clean}"
        if full_id in self.card_info_map:
            return self.card_info_map[full_id]
        
        return None
    
    def manual_card_entry(self):
        """Prompt user to manually enter card number - THREAD SAFE"""
        # Lock is already held by caller (match_card)
        print(f"\n{'='*60}")
        print(f"[{self.current_language}] MANUAL ENTRY NEEDED")
        print(f"{'='*60}")
        print("Enter card number or 'list' to see all cards, 'skip' to skip")
        
        if self.use_pokedex and self.current_language == 'JA':
            print("💡 TIP: For JA cards, enter Pokedex number")
        
        while True:
            card_input = input(f"[{self.current_language}] Card number: ").strip()
            
            if card_input.lower() == 'skip':
                return None
            
            if card_input.lower() == 'list':
                print(f"\nCards in set:")
                for card_id, info in sorted(self.card_info_map.items(), 
                                           key=lambda x: x[1].get('localId', '')):
                    local_id = info.get('localId', 'N/A')
                    name = self.get_card_name_for_language(info, self.current_language)
                    name_en = self.get_english_name(info)
                    if name_en != name:
                        print(f"  #{local_id:4s} - {name_en} ({name})")
                    else:
                        print(f"  #{local_id:4s} - {name}")
                print()
                continue
            
            if not card_input:
                continue
            
            # Try Pokedex lookup for JA
            card_info = None
            if self.use_pokedex and self.current_language == 'JA' and self.pokedex_db:
                pokedex_num = card_input.zfill(4)
                english_name = self.pokedex_db.get_english_name(pokedex_num)
                
                if english_name:
                    print(f"  📖 Pokedex #{card_input}: {english_name}")
                    
                    found_cards = []
                    for cid, info in self.card_info_map.items():
                        name_en = info.get('name_en', '').strip()
                        name_default = info.get('name', '').strip()
                        
                        if (name_en.lower() == english_name.lower() or 
                            name_default.lower() == english_name.lower()):
                            found_cards.append((cid, info, 'exact'))
                    
                    if len(found_cards) == 1:
                        card_info = found_cards[0][1]
                    elif len(found_cards) > 1:
                        print(f"\n  Found {len(found_cards)} cards:")
                        for i, (cid, info, _) in enumerate(found_cards, 1):
                            print(f"    {i}. #{info.get('localId', 'N/A'):4s} - {self.get_english_name(info)}")
                        choice = input("\n  Select (or Enter for first): ").strip()
                        idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(found_cards) else 0
                        card_info = found_cards[idx][1]
            
            if not card_info:
                card_info = self.get_card_by_number(card_input)
            
            if card_info:
                name_en = self.get_english_name(card_info)
                name_lang = self.get_card_name_for_language(card_info, self.current_language)
                local_id = card_info.get('localId', 'N/A')
                
                if name_en != name_lang:
                    print(f"\n✓ Found: {name_en} / {name_lang} (#{local_id})")
                else:
                    print(f"\n✓ Found: {name_en} (#{local_id})")
                
                confirm = input("Correct? (y/n): ").strip().lower()
                if confirm == 'y':
                    return card_info
            else:
                print(f"\n✗ Card not found")               
    
    def resize_to_match(self, img1, img2):
        """Resize images to same dimensions"""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        target_h = min(h1, h2, 800)
        target_w = min(w1, w2, 600)
        
        return cv2.resize(img1, (target_w, target_h)), cv2.resize(img2, (target_w, target_h))
    
    def compare_images_features(self, img1, img2):
        """Compare images using ORB feature matching"""
        img1_resized, img2_resized = self.resize_to_match(img1, img2)
        
        gray1 = cv2.cvtColor(img1_resized, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2_resized, cv2.COLOR_BGR2GRAY)
        
        orb = cv2.ORB_create(nfeatures=2000)
        kp1, des1 = orb.detectAndCompute(gray1, None)
        kp2, des2 = orb.detectAndCompute(gray2, None)
        
        if des1 is None or des2 is None:
            return 0.0
        
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)
        
        if len(matches) == 0:
            return 0.0
        
        good_matches = [m for m in matches if m.distance < 50]
        return len(good_matches) / max(len(kp1), len(kp2))
    
    def match_card(self, cropped_image, show_top_matches=3):
        """Find the best matching card - THREAD SAFE for user prompts"""
        
        # Check learned matches
        learned_id, conf, _ = self.learning.check_learned_match(cropped_image)
        if learned_id and conf > 0.85:
            card_info = self.card_info_map.get(learned_id)
            if card_info:
                name = self.get_card_name_for_language(card_info, self.current_language)
                print(f"  🎯 MEMORY: {name} ({conf:.0%})")
                self.learning.update_stats('auto')
                return card_info

        # Do matching
        if not self.reference_images:
            return None
        
        matches = []
        for card_id, ref_img in self.reference_images.items():
            if self.learning.is_blacklisted(cropped_image, card_id):
                continue
            try:
                score = self.compare_images_features(cropped_image, ref_img)
                matches.append((card_id, score))
            except:
                continue
        
        matches.sort(key=lambda x: x[1], reverse=True)
        
        # CRITICAL: Acquire lock BEFORE showing matches to prevent output interleaving
        with user_interaction_lock:
            print(f"\n{'='*60}")
            print(f"[{self.current_language}] MATCH REQUEST")
            print(f"{'='*60}")
            print(f"  Top matches:")
            for i, (card_id, score) in enumerate(matches[:show_top_matches], 1):
                card_info = self.card_info_map.get(card_id, {})
                name = self.get_card_name_for_language(card_info, self.current_language)
                local_id = card_info.get('localId', '')
                print(f"    {i}. {name} (#{local_id}) - {score:.3f}")
            
            if matches : #and matches[0][1] > 0.15:
                best_card_id = matches[0][0]
                best_score = matches[0][1]
                card_info = self.card_info_map.get(best_card_id, {})
                name = self.get_card_name_for_language(card_info, self.current_language)
                
                print(f"\n  ✓ Best: {name} ({best_score:.3f})")
                
                if best_score > 0.25:
                    # Auto-accept high confidence
                    self.learning.add_confirmed_match(cropped_image, best_card_id)
                    self.learning.update_stats('auto')
                    print(f"{'='*60}\n")
                    return card_info
                else:
                    # Show visual comparison
                    self.show_comparison_window(cropped_image, best_card_id, name)
                    
                    # Ask user with clear prompt
                    print(f"\n  👀 CHECK THE COMPARISON WINDOW!")
                    response = input(f"  [{self.current_language}] Accept '{name}'? (y/n): ").strip().lower()
                    
                    # Close window after response
                    self.close_comparison_window()
                    
                    if response == 'y':
                        self.learning.add_confirmed_match(cropped_image, best_card_id)
                        self.learning.update_stats('auto')
                        print(f"{'='*60}\n")
                        return card_info
                    else:
                        self.learning.add_rejection(cropped_image, best_card_id)
                        
                        # Ask if crop is bad
                        print(f"\n  ❓ Is the crop quality bad? (y/n): ", end='')
                        crop_bad = input().strip().lower()
                        
                        if crop_bad == 'y':
                            print(f"  🔄 Crop issue detected - returning None to trigger basic recrop")
                            self.close_comparison_window()
                            print(f"{'='*60}\n")
                            return 'RECROP'  
                        
                        result = self.manual_card_entry()
                        
                        if result:
                            self.learning.add_confirmed_match(cropped_image, result['id'])
                            self.learning.update_stats('manual')
                        self.close_comparison_window()
                        print(f"{'='*60}\n")
                        return result
            
            # No match - manual entry
            print(f"{'='*60}\n")
            result = self.manual_card_entry()
            if result:
                self.learning.add_confirmed_match(cropped_image, result['id'])
                self.learning.update_stats('manual')
            return result
         
def load_set_names_mapping():
    """Load set names from all_sets_full.json"""
    json_path = Path('PokemonCardLists/all_sets_full.json')
    
    if not json_path.exists():
        print(f"⚠ Warning: all_sets_full.json not found")
        return {}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            all_sets = data.get('data', [])
        elif isinstance(data, list):
            all_sets = data
        else:
            return {}
        
        # Map set code to set name
        set_mapping = {}
        for set_info in all_sets:
            if not isinstance(set_info, dict):
                continue
            set_id = set_info.get('id', '').lower()
            set_name = set_info.get('name', '')
            if set_id and set_name:
                set_mapping[set_id] = set_name
        
        return set_mapping
    except Exception as e:
        print(f"⚠ Error loading set names: {e}")
        return {}

def append_to_collection_list(card_name_en, set_name, card_number):
    """Append a card to the collection_list.txt file"""
    collection_file = Path('PokemonTCGAPI/collection_list.txt')
    
    # Create directory if doesn't exist
    collection_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Format: "Ampharos Pokemon Neo Genesis set #1"
    line = f"{card_name_en} Pokemon {set_name} set #{card_number}\n"
    
    with open(collection_file, 'a', encoding='utf-8') as f:
        f.write(line)

def write_to_csv(csv_path, card_data):
    """Thread-safe CSV writing"""
    with csv_write_lock:
        file_exists = os.path.exists(csv_path)
        
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['Card Name', 'Set Code', 'Quantity', 'Language', 
                         'Foil', 'Condition', 'Comment']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(card_data)

def process_language_folder(folder_path, language, set_code, output_folder, csv_path, set_name):
    """Process a single language folder - designed to run in thread"""
    
    print(f"\n[{language}] Starting processing...")
    
    matcher = CardMatcher(set_code)
    matcher.set_language(language)
    matcher.load_card_info_for_language(language)
    
    search_path = os.path.join(folder_path, 'raw', language)
    output_dir = os.path.join(folder_path, output_folder, language)
    os.makedirs(output_dir, exist_ok=True)
    
    extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = sorted([f for f in os.listdir(search_path) 
                   if any(f.lower().endswith(ext) for ext in extensions)])
    
    print(f"[{language}] Found {len(image_files)} images ({len(image_files)//2} pairs)")
    
    i = 0
    pair_number = 1
    success_count = 0
    
    while i < len(image_files):
        front_filename = image_files[i]
        
        print(f"\n[{language}] Pair {pair_number}/{len(image_files)//2}")
        
        front_path = os.path.join(search_path, front_filename)
        
        try:
            cropper = CardCropper(front_path)
            if cropper.image is None:
                i += 2
                pair_number += 1
                continue
            
            cropped_front = cropper.crop_card()
            if cropped_front is None:
                i += 2
                pair_number += 1
                continue
            
            card_info = matcher.match_card(cropped_front)
            
            if card_info == 'RECROP':
                # Delete the bad crop and retry with basic crop
                print(f"  🔄 Retrying with basic crop method...")
                
                cropper = CardCropper(front_path)
                if cropper.image is not None:
                    cropped_front = cropper.crop_card_basic()
                    
                    if cropped_front is not None:
                        # Try matching again with new crop
                        card_info = matcher.match_card(cropped_front)
                        
                        if not card_info or card_info == 'RECROP':
                            print(f"  ❌ Still failed after basic crop - skipping pair")
                            i += 2
                            pair_number += 1
                            continue
                    else:
                        print(f"  ❌ Basic crop failed - skipping pair")
                        i += 2
                        pair_number += 1
                        continue
                else:
                    i += 2
                    pair_number += 1
                    continue
    
            if not card_info:
                i += 2
                pair_number += 1
                continue
            
            # Get filename name (language-specific for file)
            if matcher.use_pokedex and language == 'JA':
                name_for_file = matcher.get_english_name(card_info)
            else:
                name_for_file = matcher.get_card_name_for_language(card_info, language)
            
            # Get English name for CSV and collection list
            name_for_csv = matcher.get_english_name(card_info)
            local_id = card_info.get('localId', 'Unknown').replace('/', '-')
            
            name_sanitized = sanitize_filename(name_for_file)
            ext = os.path.splitext(front_filename)[1]
            
            # Save FRONT
            base_front = f"{name_sanitized}_{local_id}_{set_code}_{language}_FRONT{ext}"
            front_new_name = get_unique_filename(output_dir, base_front)
            front_output = os.path.join(output_dir, front_new_name)
            cv2.imwrite(front_output, cropped_front)
            
            # Save BACK
            if i + 1 < len(image_files):
                back_filename = image_files[i + 1]
                back_path = os.path.join(search_path, back_filename)
                back_cropper = CardCropper(back_path)
                
                if back_cropper.image is not None:
                    back_cropped = back_cropper.crop_card_back()
                    if back_cropped is not None:
                        base_back = f"{name_sanitized}_{local_id}_{set_code}_{language}_BACK{ext}"
                        back_new_name = get_unique_filename(output_dir, base_back)
                        back_output = os.path.join(output_dir, back_new_name)
                        cv2.imwrite(back_output, back_cropped)
            
            # Write to CSV (thread-safe)
            csv_data = {
                'Card Name': name_for_csv,  # English name for CSV
                'Set Code': set_code,
                'Quantity': 1,
                'Language': language,
                'Foil': 'no',
                'Condition': 'NM',
                'Comment': 'Booster -> Sleeve'
            }
            write_to_csv(csv_path, csv_data)
            
            # Append to collection_list.txt (thread-safe)
            append_to_collection_list(name_for_csv, set_name, local_id)
            
            success_count += 1
            i += 2
            pair_number += 1
                
        except Exception as e:
            print(f"\n[{language}] Error: {e}")
            i += 2
            pair_number += 1
    
    print(f"\n[{language}] ✅ Completed: {success_count} cards processed")

def process_folder_multithreaded(folder_path, output_folder='Renamed_Cropped', selected_languages=None, clear_output=False):
    """Process multiple language folders using threads"""
    
    set_code = extract_set_code(folder_path)
    
    # Get set name
    set_names = load_set_names_mapping()
    set_name = set_names.get(set_code.lower(), f"Unknown Set ({set_code})")
    
    print(f"\n{'='*70}")
    print(f"MULTITHREADED PROCESSING - Set: {set_name} ({set_code})")
    print(f"{'='*70}\n")
    
     # Clear Renamed_Cropped folder if processing ALL languages
    if clear_output:
        output_path = os.path.join(folder_path, output_folder)
        if os.path.exists(output_path):
            import shutil
            try:
                shutil.rmtree(output_path)
                print(f"🗑️  Cleared old {output_folder} folder\n")
            except Exception as e:
                print(f"⚠️  Could not clear {output_folder}: {e}\n")
                
    raw_folder = os.path.join(folder_path, 'raw')
    
    if not os.path.exists(raw_folder):
        print(f"Error: 'raw' folder not found")
        return
    
    # Find available languages
    language_folders = ['DE', 'EN', 'ES', 'FR', 'IT', 'JA', 'KO', 'PT']
    found_languages = [lang for lang in language_folders 
                      if os.path.exists(os.path.join(raw_folder, lang))]
    
    if not found_languages:
        print("No language folders found")
        return
    
    # Filter languages if specified
    if selected_languages:
        if isinstance(selected_languages, str):
            selected_languages = [selected_languages]
        found_languages = [lang for lang in found_languages if lang in selected_languages]
    
    print(f"Processing languages: {', '.join(found_languages)}")
    print(f"Using {len(found_languages)} threads\n")
    
    # CSV path
    csv_path = os.path.join(folder_path, f'{set_code}_inventory.csv')
    
    # Delete old CSV if exists
    if os.path.exists(csv_path):
        os.remove(csv_path)
        print(f"Removed old CSV: {csv_path}\n")
    
    # Create threads
    threads = []
    for language in found_languages:
        thread = Thread(
            target=process_language_folder,
            args=(folder_path, language, set_code, output_folder, csv_path, set_name)
        )
        threads.append(thread)
        thread.start()
        time.sleep(0.5)  # Slight delay to stagger startup
    
    # Wait for all threads
    for thread in threads:
        thread.join()
    
    print(f"\n{'='*70}")
    print("✅ ALL THREADS COMPLETED")
    print(f"{'='*70}")
    print(f"CSV saved: {csv_path}")

def find_set_folders_with_raw(base_path):
    """Recursively find all folders that contain a 'raw' subfolder"""
    set_folders = []
    
    try:
        base_path = Path(base_path)
        
        # Check if the given path itself has a raw folder
        if (base_path / 'raw').exists():
            set_folders.append(base_path)
            return set_folders
        
        # Otherwise, search in subdirectories
        for item in base_path.iterdir():
            if item.is_dir():
                raw_folder = item / 'raw'
                if raw_folder.exists() and raw_folder.is_dir():
                    set_folders.append(item)
    
    except Exception as e:
        print(f"Error scanning folder: {e}")
    
    return set_folders

def process_multiple_sets(base_path, selected_languages=None):
    """Process multiple set folders"""
    
    set_folders = find_set_folders_with_raw(base_path)
    
    if not set_folders:
        print(f"❌ No folders with 'raw' subfolder found in {base_path}")
        return
    
    # Filter out empty/test folders
    valid_folders = []
    for folder in set_folders:
        set_name = folder.name.lower()
        # Skip folders that look like empty/test folders
        if 'empty' in set_name or 'test' in set_name:
            print(f"⏭️  Skipping: {folder.name} (appears to be empty/test folder)")
            continue
        valid_folders.append(folder)
    
    if not valid_folders:
        print(f"❌ No valid set folders found")
        return
    
    print(f"\n{'='*70}")
    print(f"FOUND {len(valid_folders)} VALID SET FOLDER(S) WITH RAW DATA")
    print(f"{'='*70}")
    
    for i, folder in enumerate(valid_folders, 1):
        set_name = folder.name
        set_code = extract_set_code(folder)
        print(f"  {i}. {set_name} (Set: {set_code})")
    
    print(f"\n{'='*70}")
    
    # For batch processing, ask for language selection ONCE
    clear_files = False
    if len(valid_folders) > 1:
        print("BATCH PROCESSING MODE")
        print("Select languages to process for ALL sets:")
        print("  ALL - Process all available languages")
        print("  EN,FR,JA - Specific languages (comma-separated)")
        print()
        
        lang_choice = input("Languages for all sets: ").strip().upper()
        
        if not lang_choice or lang_choice == 'ALL':
            batch_languages = None  # Will use all available languages
            # Ask about clearing files when processing ALL
            print(f"\n{'='*70}")
            print("⚠️  DELETION CONFIRMATION")
            print(f"{'='*70}")
            print("Processing ALL folders and ALL languages")
            print("This will:")
            print("  • Delete all Renamed_Cropped folders in each set")
            print("  • Clear collection_list.txt")
            print("\nDo you want to clear existing data? (y/n)")
            print("  'y' = Start fresh (recommended for full reprocessing)")
            print("  'n' = Keep existing data and add new cards")
            
            choice = input("\nClear existing data? (y/n): ").strip().lower()
            clear_files = (choice == 'y')
            
            if clear_files:
                print("✓ Will clear existing data before processing")
            else:
                print("✓ Will keep existing data and append new cards")
        else:
            batch_languages = [l.strip() for l in lang_choice.split(',')]
            print(f"✓ Will process: {', '.join(batch_languages)}\n")
    else:
        batch_languages = selected_languages
    
    # Clear collection_list.txt if requested
    if clear_files:
        collection_file = Path('PokemonTCGAPI/collection_list.txt')
        if collection_file.exists():
            collection_file.unlink()
            print(f"\n🗑️  Cleared collection_list.txt")
            
    # Process all sets without asking again
    for folder in valid_folders:
        print(f"\n{'='*70}")
        print(f"PROCESSING: {folder.name}")
        print(f"{'='*70}")
        process_single_set(str(folder), batch_languages, ask_language=False, clear_output=clear_files)
    
    print(f"\n{'='*70}")
    print("✅ BATCH PROCESSING COMPLETE")
    print(f"{'='*70}")

def process_single_set(folder_path, selected_languages=None, ask_language=True, clear_output=False):
    """Process a single set folder"""
    
    raw_folder = os.path.join(folder_path, 'raw')
    
    if not os.path.exists(raw_folder):
        print(f"❌ Error: 'raw' folder not found in {folder_path}")
        return
    
    language_folders = ['DE', 'EN', 'ES', 'FR', 'IT', 'JA', 'KO', 'PT']
    found_languages = [lang for lang in language_folders
                      if os.path.exists(os.path.join(raw_folder, lang))]
    
    if not found_languages:
        print("❌ No language folders found")
        return
    
    print(f"Available languages: {', '.join(found_languages)}")
    
    # Use provided languages or ask user
    if selected_languages is None and ask_language:
        print("Enter languages separated by commas (e.g., 'FR,EN')")
        print("Or 'ALL' to process all\n")
        
        lang_input = input("Languages: ").strip().upper()
        
        if lang_input == 'ALL':
            selected_languages = found_languages
        else:
            selected = [l.strip() for l in lang_input.split(',')]
            selected_languages = [l for l in selected if l in found_languages]
            
            if not selected_languages:
                print(f"❌ Invalid languages")
                return
    elif selected_languages is None:
        # Batch mode - use all found languages
        selected_languages = found_languages
    else:
        # Filter selected languages to only available ones
        selected_languages = [l for l in selected_languages if l in found_languages]
    
    process_folder_multithreaded(folder_path, selected_languages=selected_languages, clear_output=clear_output)

if __name__ == "__main__":
    print("="*70)
    print("POKÉMON CARD PROCESSOR - MULTITHREADED WITH CSV EXPORT")
    print("="*70)
    print("\n🚀 Parallel processing + automatic CSV generation!")
    print("📊 CSV uses English names for TCG compatibility")
    print("📝 Creates collection_list.txt in PokemonTCGAPI folder")
    print("🔍 Can process single set or batch process multiple sets\n")
    
    folder_path = input("Enter path (set folder or parent folder): ").strip().strip('"')
    
    if not os.path.exists(folder_path):
        print(f"❌ Error: Path not found: {folder_path}")
    else:
        # Check if this is a set folder or parent folder
        raw_folder = os.path.join(folder_path, 'raw')
        
        if os.path.exists(raw_folder):
            # Single set folder
            print(f"\n✓ Found raw folder - processing single set")
            process_single_set(folder_path)
        else:
            # Parent folder - search for sets
            print(f"\n🔍 Searching for set folders in: {folder_path}")
            process_multiple_sets(folder_path)
    
    print("\n✅ All processing complete!")