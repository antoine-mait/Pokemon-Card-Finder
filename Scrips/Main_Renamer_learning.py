import cv2
import numpy as np
import os
import sys
import json
import csv
import pickle
from pathlib import Path

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

class CardMatcher:
    """Match cropped cards against reference images using computer vision"""
    
    def __init__(self, set_code, base_path='PokemonCardLists/Card_Sets'):
        self.set_code = set_code
        self.base_path = Path(base_path)
        self.reference_images = {}
        self.card_info_map = {}  # Maps card_id to all language names
        self.csv_path = None
        self.current_language = None
        self.use_pokedex = False
        self.pokedex_db = None
        self.load_reference_images()
        self.learning = LearningSystem(self.set_code)
        self.check_if_old_set()
    
    def check_if_old_set(self):
        """Check if this is a pre-2002 set that needs Pokedex for JA language"""
        # Load all_sets_full.json to check release date
        sets_file = Path('PokemonCardLists/all_sets_full.json')
        
        if not sets_file.exists():
            print(f"  ⚠ all_sets_full.json not found at {sets_file}")
            print(f"  Checking if set code suggests old set...")
            # Fallback: Check if set code starts with known old prefixes
            old_set_prefixes = ['base', 'jungle', 'fossil', 'base2', 'gym1', 'gym2', 
                               'neo1', 'neo2', 'neo3', 'neo4', 'legendary']
            if any(self.set_code.lower().startswith(prefix) for prefix in old_set_prefixes):
                self.use_pokedex = True
                from cards_utils import PokedexDatabase
                self.pokedex_db = PokedexDatabase()
                print(f"  📖 Old set detected (pre-2003) - Pokedex lookup enabled for JA")
            return
        
        try:
            with open(sets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if data is a dict with a 'data' key or if it's directly a list
            if isinstance(data, dict):
                all_sets = data.get('data', [])
            elif isinstance(data, list):
                all_sets = data
            else:
                print(f"  ⚠ Unexpected JSON format")
                all_sets = []
            
            # Find this set
            found_set = False
            for set_info in all_sets:
                if not isinstance(set_info, dict):
                    continue
                    
                set_id = set_info.get('id', '')
                # Try exact match or partial match
                if set_id == self.set_code or set_id.lower() == self.set_code.lower():
                    release_date = set_info.get('releaseDate', '')
                    print(f"  ℹ Found set in database: {set_info.get('name', 'Unknown')}")
                    print(f"  ℹ Release date: {release_date}")
                    
                    if release_date:
                        # Parse date (format: YYYY/MM/DD)
                        year = int(release_date.split('/')[0])
                        if year <= 2002:
                            self.use_pokedex = True
                            from cards_utils import PokedexDatabase
                            self.pokedex_db = PokedexDatabase()
                            print(f"  📖 Old set detected ({year}) - Pokedex lookup enabled for JA")
                    found_set = True
                    break
            
            if not found_set:
                print(f"  ℹ Set '{self.set_code}' not found in all_sets_full.json")
                # Fallback check
                old_set_prefixes = ['base', 'jungle', 'fossil', 'base2', 'gym1', 'gym2', 
                                   'neo1', 'neo2', 'neo3', 'neo4', 'legendary']
                if any(self.set_code.lower().startswith(prefix) for prefix in old_set_prefixes):
                    self.use_pokedex = True
                    from cards_utils import PokedexDatabase
                    self.pokedex_db = PokedexDatabase()
                    print(f"  📖 Old set detected by prefix - Pokedex lookup enabled for JA")
                    
        except Exception as e:
            print(f"  ⚠ Error checking set date: {e}")
            # Still enable Pokedex for known old sets
            old_set_prefixes = ['base', 'jungle', 'fossil', 'base2', 'gym1', 'gym2', 
                               'neo1', 'neo2', 'neo3', 'neo4', 'legendary']
            if any(self.set_code.lower().startswith(prefix) for prefix in old_set_prefixes):
                self.use_pokedex = True
                from cards_utils import PokedexDatabase
                self.pokedex_db = PokedexDatabase()
                print(f"  📖 Old set detected by prefix (fallback) - Pokedex lookup enabled for JA")
            
    def load_reference_images(self):
        """Load all reference images and card info from the set folder"""
        print(f"\n  Looking for set code: '{self.set_code}'")
        
        # Find the set folder
        set_folders = []
        
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
            print(f"  Available set folders:")
            for f in sorted(self.base_path.iterdir()):
                if f.is_dir():
                    print(f"    - {f.name}")
            return
        
        set_folder = set_folders[0]
        print(f"  ✓ Found set folder: {set_folder.name}")
        
        img_folder = set_folder / "IMG"
        
        if not img_folder.exists():
            print(f"\n⚠ Warning: IMG folder not found in {set_folder.name}")
            print(f"  Please run the image downloader script first!")
            return
        
        # Load card info from CSV
        self.set_folder = set_folder
        self.csv_files = list(set_folder.glob("CardList_*.csv"))
        if self.csv_files:  
            self.load_card_info(self.csv_files[0])
        
        # Load reference images
        print(f"  Loading reference images from IMG folder...")
        image_files = list(img_folder.glob("*.jpg")) + list(img_folder.glob("*.webp")) + list(img_folder.glob("*.png"))
        
        if not image_files:
            print(f"  ⚠ No image files found. Run the image downloader first!")
            return
        
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
        
        # Find CSV for this language
        lang_lower = language.lower()
        csv_file = None
        
        for csv_path in self.csv_files:
            if f"_{lang_lower}.csv" in str(csv_path).lower():
                csv_file = csv_path
                break
        
        if not csv_file:
            print(f"  ⚠ No CSV found for language {language}")
            return
        
        print(f"  Loading card names from: {csv_file.name}")
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    card_id = row.get('id', '')
                    if card_id and card_id in self.card_info_map:
                        # Update with language-specific name
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
                        # Store base info with default name
                        self.card_info_map[card_id] = {
                            'name': row.get('name', 'Unknown'),
                            'localId': row.get('localId', ''),
                            'id': card_id,
                            'name_de': '',
                            'name_en': '',
                            'name_es': '',
                            'name_fr': '',
                            'name_it': '',
                            'name_ja': '',
                            'name_ko': '',
                            'name_pt': '',
                        }
            print(f"  ✓ Loaded info for {len(self.card_info_map)} cards")
            
            # NEW: Also load English names immediately for Pokedex matching
            self.load_card_info_for_language('EN')
            
        except Exception as e:
            print(f"  ⚠ Error loading CSV: {e}")
    
    def get_card_name_for_language(self, card_info, language):
        """Get the card name in the specified language"""
        lang_key = f'name_{language.lower()}'
        
        # Try to get the language-specific name
        if lang_key in card_info and card_info[lang_key]:
            name = card_info[lang_key]
            # Only return if it's not empty and not just "Unknown"
            if name and name != 'Unknown':
                return name
        
        # Fallback to default name
        return card_info.get('name', 'Unknown')
    
    def set_language(self, language):
        """Set the current language being processed"""
        self.current_language = language
    
    def get_card_by_number(self, card_number):
        """Get card info by card number (localId or id)"""
        # Try localId first
        for card_id, info in self.card_info_map.items():
            if info.get('localId', '').strip() == card_number.strip():
                return info
        
        # Try full id
        card_number_clean = card_number.strip()
        if card_number_clean in self.card_info_map:
            return self.card_info_map[card_number_clean]
        
        # Try searching with set code prefix
        full_id = f"{self.set_code}-{card_number_clean}"
        if full_id in self.card_info_map:
            return self.card_info_map[full_id]
        
        return None
    
    def manual_card_entry(self):
        """Prompt user to manually enter card number"""
        print("\n" + "="*70)
        print("MANUAL CARD ENTRY")
        print("="*70)
        print("Enter the card number from the card (e.g., '001', '25', '123')")
        
        # NEW: Add Pokedex option for JA language
        if self.use_pokedex and self.current_language == 'JA':
            print("💡 TIP: For Japanese cards, enter the Pokedex number")
            print("   (e.g., '184' for Azumarill, '160' for Feraligatr)")
            print("   The card will be matched and renamed with English name")
        
        print("Or enter the full card ID if you know it")
        print("Type 'list' to see all available cards")
        print("Type 'skip' to skip this card")
        print()
        
        while True:
            card_input = input("Card number: ").strip()
            
            if card_input.lower() == 'skip':
                return None
            
            if card_input.lower() == 'list':
                print("\nAvailable cards in this set:")
                for card_id, info in sorted(self.card_info_map.items(), 
                                           key=lambda x: x[1].get('localId', '')):
                    local_id = info.get('localId', 'N/A')
                    
                    # Show English name too for JA with Pokedex
                    if self.use_pokedex and self.current_language == 'JA':
                        name_ja = self.get_card_name_for_language(info, 'JA')
                        name_en = info.get('name_en', info.get('name', ''))
                        # Always show English name first for easier reading
                        if name_en and name_en != 'Unknown':
                            print(f"  #{local_id:4s} - {name_en} ({name_ja})")
                        else:
                            print(f"  #{local_id:4s} - {name_ja}")
                    else:
                        name = self.get_card_name_for_language(info, self.current_language)
                        print(f"  #{local_id:4s} - {name}")
                print()
                continue
            
            if not card_input:
                print("Please enter a card number or 'skip'\n")
                continue
            
            # NEW: Try Pokedex lookup FIRST for JA language
            card_info = None
            if self.use_pokedex and self.current_language == 'JA' and self.pokedex_db:
                # Pad the input to 4 digits for Pokedex lookup
                pokedex_num = card_input.zfill(4)
                english_name = self.pokedex_db.get_english_name(pokedex_num)
                
                if english_name:
                    print(f"  📖 Pokedex #{card_input}: {english_name}")
                    
                    # Search by English name in our card database
                    found_cards = []
                    for cid, info in self.card_info_map.items():
                        name_en = info.get('name_en', '').strip()
                        name_default = info.get('name', '').strip()
                        
                        # Try exact match first
                        if (name_en.lower() == english_name.lower() or 
                            name_default.lower() == english_name.lower()):
                            found_cards.append((cid, info, 'exact'))
                        # Try partial match (for cards with different forms)
                        elif (name_en and english_name.lower() in name_en.lower()) or \
                             (name_default and english_name.lower() in name_default.lower()):
                            found_cards.append((cid, info, 'partial'))
                    
                    if found_cards:
                        if len(found_cards) == 1:
                            card_info = found_cards[0][1]
                            print(f"  ✓ Matched to card in set")
                        else:
                            # Multiple matches - let user choose
                            print(f"\n  📋 Found {len(found_cards)} cards with this name:")
                            for i, (cid, info, match_type) in enumerate(found_cards, 1):
                                local_id = info.get('localId', 'N/A')
                                name_ja = self.get_card_name_for_language(info, 'JA')
                                name_en = info.get('name_en', info.get('name', ''))
                                print(f"    {i}. #{local_id:4s} - {name_en} ({name_ja})")
                            
                            choice = input("\n  Select card number (or Enter for first): ").strip()
                            if choice.isdigit() and 1 <= int(choice) <= len(found_cards):
                                card_info = found_cards[int(choice) - 1][1]
                            else:
                                card_info = found_cards[0][1]
                            print(f"  ✓ Selected card")
                    else:
                        print(f"  ⚠ '{english_name}' not found in this set")
                        print(f"  Trying direct card number lookup...")
                else:
                    print(f"  ⚠ Pokedex #{card_input} not found in pokedex.csv")
                    print(f"  Trying direct card number lookup...")
            
            # If not found via Pokedex, try normal card number lookup
            if not card_info:
                card_info = self.get_card_by_number(card_input)
            
            # CRITICAL: This section was already there but check it's complete
            if card_info:
                local_id = card_info.get('localId', 'N/A')
                
                # For JA language with Pokedex, show both names
                if self.use_pokedex and self.current_language == 'JA':
                    name_ja = self.get_card_name_for_language(card_info, 'JA')
                    name_en = card_info.get('name_en', card_info.get('name', 'Unknown'))
                    if not name_en or name_en == 'Unknown':
                        name_en = card_info.get('name', 'Unknown')
                    print(f"\n✓ Found: {name_en} / {name_ja} (#{local_id})")
                else:
                    if self.current_language:
                        name = self.get_card_name_for_language(card_info, self.current_language)
                    else:
                        name = card_info.get('name', 'Unknown')
                    print(f"\n✓ Found: {name} (#{local_id})")
                
                confirm = input("Is this correct? (y/n): ").strip().lower()
                if confirm == 'y':
                    return card_info  # THIS IS CRITICAL - MUST RETURN HERE
                else:
                    print("Let's try again...\n")
            else:
                print(f"\n✗ Card not found")
                if self.use_pokedex and self.current_language == 'JA':
                    print("💡 Enter Pokedex number (e.g., '184' for Azumarill)")
                    print("   or type 'list' to see all cards in this set\n")
                else:
                    print("Please try again or type 'list' to see all cards\n")
                    
    def resize_to_match(self, img1, img2):
        """Resize images to same dimensions for comparison"""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        target_h = min(h1, h2, 800)
        target_w = min(w1, w2, 600)
        
        img1_resized = cv2.resize(img1, (target_w, target_h))
        img2_resized = cv2.resize(img2, (target_w, target_h))
        
        return img1_resized, img2_resized
    
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
        score = len(good_matches) / max(len(kp1), len(kp2))
        
        return score
    
    def match_card(self, cropped_image, show_top_matches=3):
        """Find the best matching card from reference images"""
        
        # STEP 1: Check if we've learned this card before (HIGH threshold)
        learned_id, conf, _ = self.learning.check_learned_match(cropped_image)
        if learned_id and conf > 0.85:  # Only auto-match if VERY confident
            card_info = self.card_info_map.get(learned_id)
            if card_info:
                if self.current_language:
                    name = self.get_card_name_for_language(card_info, self.current_language)
                else:
                    name = card_info.get('name', 'Unknown')
                print(f"  🎯 FOUND IN MEMORY: {name} ({conf:.0%} confidence)")
                print(f"  ⚡ Auto-matched - skipping search!")
                self.learning.update_stats('auto')
                return card_info

        # STEP 2: Do normal matching (WITHOUT boosting - that was the problem!)
        if not self.reference_images:
            print("  ⚠ No reference images loaded")
            return None
        
        print(f"  Matching against {len(self.reference_images)} cards...")
        
        matches = []
        
        # STEP 3: Just filter blacklist, DON'T boost scores
        for card_id, ref_img in self.reference_images.items():
            # Skip blacklisted matches
            if self.learning.is_blacklisted(cropped_image, card_id):
                continue
                
            try:
                score = self.compare_images_features(cropped_image, ref_img)
                # REMOVED: boost = self.learning.get_confidence_boost(card_id)
                # REMOVED: score += boost
                
                matches.append((card_id, score))
            except Exception as e:
                continue
        
        matches.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\n  Top {show_top_matches} matches:")
        for i, (card_id, score) in enumerate(matches[:show_top_matches], 1):
            card_info = self.card_info_map.get(card_id, {})
            if self.current_language:
                name = self.get_card_name_for_language(card_info, self.current_language)
            else:
                name = card_info.get('name', 'Unknown')
            local_id = card_info.get('localId', '')
            
            # Show if this card has been learned before (but don't boost score)
            boost = self.learning.get_confidence_boost(card_id)
            learned_marker = " 🧠" if boost > 0 else ""
            
            print(f"    {i}. {name} (#{local_id}) - Score: {score:.3f}{learned_marker}")
        
        if matches and matches[0][1] > 0.15:
            best_card_id = matches[0][0]
            best_score = matches[0][1]
            
            card_info = self.card_info_map.get(best_card_id, {})
            
            if self.current_language:
                name = self.get_card_name_for_language(card_info, self.current_language)
            else:
                name = card_info.get('name', 'Unknown')
            
            print(f"\n  ✓ Best match: {name} (#{card_info.get('localId', '')})")
            print(f"    Match score: {best_score:.3f}")
            
            # Auto-accept high confidence or ask user
            if best_score > 0.25:
                # High confidence - auto accept and learn
                self.learning.add_confirmed_match(cropped_image, best_card_id)
                self.learning.update_stats('auto')
                return card_info
            else:
                # Lower confidence - ask user
                ref_image = self.reference_images[best_card_id]
                accepted = show_comparison(cropped_image, ref_image, name, best_score)
                
                if accepted:
                    # User accepted - learn it
                    self.learning.add_confirmed_match(cropped_image, best_card_id)
                    self.learning.update_stats('auto')
                    return card_info
                else:
                    # User rejected - blacklist it
                    print("  ✗ Match rejected by user")
                    self.learning.add_rejection(cropped_image, best_card_id)
                    result = self.manual_card_entry()
                    if result:
                        self.learning.add_confirmed_match(cropped_image, result['id'])
                        self.learning.update_stats('manual')
                    return result
            
        else:
            print(f"\n  ✗ No confident match")
            if matches:
                print(f"    (best score: {matches[0][1]:.3f})")
            
            if matches:
                card_info = self.card_info_map.get(matches[0][0], {})
                if self.current_language:
                    name = self.get_card_name_for_language(card_info, self.current_language)
                else:
                    name = card_info.get('name', 'Unknown')
                
                print(f"\n  💡 Best guess: {name} (#{card_info.get('localId', '')})")
                
                ref_image = self.reference_images[matches[0][0]]
                accepted = show_comparison(cropped_image, ref_image, name, matches[0][1])
                
                if accepted:
                    # User accepted the guess - learn it
                    self.learning.add_confirmed_match(cropped_image, matches[0][0])
                    self.learning.update_stats('auto')
                    return card_info
                else:
                    # User rejected - blacklist and go manual
                    self.learning.add_rejection(cropped_image, matches[0][0])
                    result = self.manual_card_entry()
                    if result:
                        self.learning.add_confirmed_match(cropped_image, result['id'])
                        self.learning.update_stats('manual')
                    return result
            
            # No matches at all - go straight to manual
            result = self.manual_card_entry()
            if result:
                self.learning.add_confirmed_match(cropped_image, result['id'])
                self.learning.update_stats('manual')
            return result

def show_comparison(cropped_image, reference_image, card_name, confidence):
    """Display cropped image and matched reference side by side"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        cropped_rgb = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2RGB)
        reference_rgb = cv2.cvtColor(reference_image, cv2.COLOR_BGR2RGB)
        
        img_crop = Image.fromarray(cropped_rgb)
        img_ref = Image.fromarray(reference_rgb)
        
        target_height = 600
        
        aspect_crop = img_crop.width / img_crop.height
        aspect_ref = img_ref.width / img_ref.height
        
        img_crop = img_crop.resize((int(target_height * aspect_crop), target_height), Image.Resampling.LANCZOS)
        img_ref = img_ref.resize((int(target_height * aspect_ref), target_height), Image.Resampling.LANCZOS)
        
        total_width = img_crop.width + img_ref.width + 20
        total_height = target_height + 60
        
        comparison = Image.new('RGB', (total_width, total_height), color='black')
        
        comparison.paste(img_crop, (0, 60))
        comparison.paste(img_ref, (img_crop.width + 20, 60))
        
        draw = ImageDraw.Draw(comparison)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        draw.text((10, 10), "Your Card", fill='white', font=font)
        draw.text((img_crop.width + 30, 10), f"Match: {card_name}", fill='white', font=font)
        draw.text((img_crop.width + 30, 35), f"Score: {confidence:.3f}", fill='yellow', font=font)
        
        comparison.show(title=f"Match: {card_name}")
        
        response = input("\n  Accept this match? (y/n): ").strip().lower()
        return response == 'y'
        
    except ImportError:
        print("  ℹ Install Pillow: pip install Pillow")
        response = input("  Accept this match? (y/n): ").strip().lower()
        return response == 'y'
    except Exception as e:
        print(f"  ⚠ Could not display: {e}")
        response = input("  Accept this match? (y/n): ").strip().lower()
        return response == 'y'

def process_folder(folder_path, output_folder='Renamed_Cropped', selected_language=None):
    """Process all card images in a folder - FRONT/BACK pairs"""
    
    set_code = extract_set_code(folder_path)
    print(f"Using set code: {set_code}\n")
    
    matcher = CardMatcher(set_code)
    
    if not matcher.reference_images:
        print("⚠ No reference images found!")
        print("  Please run the image downloader script first.")
        return
    
    raw_folder = os.path.join(folder_path, 'raw')
    
    if not os.path.exists(raw_folder):
        print(f"Error: 'raw' folder not found in {folder_path}")
        return
    
    language_folders = ['DE', 'EN', 'ES', 'FR', 'IT', 'JA', 'KO', 'PT']
    found_languages = []
    
    for lang in language_folders:
        lang_path = os.path.join(raw_folder, lang)
        if os.path.exists(lang_path) and os.path.isdir(lang_path):
            found_languages.append(lang)
    
    if not found_languages:
        print("No language subfolders found in raw folder")
        return
    
    if selected_language:
        if selected_language in found_languages:
            found_languages = [selected_language]
            print(f"Processing only: {selected_language}\n")
        else:
            print(f"Error: Language '{selected_language}' not found")
            return
    else:
        print(f"Found language folders: {', '.join(found_languages)}\n")
    
    for language in found_languages:
        print("\n" + "="*70)
        print(f"PROCESSING LANGUAGE: {language}")
        print("="*70)
        
        # Set the current language in the matcher
        matcher.set_language(language)
        matcher.load_card_info_for_language(language)
        
        search_path = os.path.join(raw_folder, language)
        output_dir = os.path.join(folder_path, output_folder, language)
        os.makedirs(output_dir, exist_ok=True)
        
        extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_files = sorted([f for f in os.listdir(search_path) 
                       if any(f.lower().endswith(ext) for ext in extensions)])
        
        print(f"Found {len(image_files)} images ({len(image_files)//2} card pairs)\n")
        
        results = []
        i = 0
        pair_number = 1
        
        while i < len(image_files):
            front_filename = image_files[i]
            
            print(f"\n{'='*70}")
            print(f"PAIR {pair_number}/{len(image_files)//2}")
            print(f"[{i+1}/{len(image_files)}] FRONT: {front_filename}")
            print('='*70)
            
            front_path = os.path.join(search_path, front_filename)
            
            try:
                print("\n→ Cropping FRONT card...")
                cropper = CardCropper(front_path)
                if cropper.image is None:
                    print("  ✗ Could not load image")
                    i += 2
                    continue
                
                cropped_front = cropper.crop_card()
                if cropped_front is None:
                    print("  ✗ Could not crop card")
                    i += 2
                    continue
                
                print(f"  ✓ Cropped: {cropped_front.shape[1]}x{cropped_front.shape[0]}px")
                
                print("\n→ Matching card...")
                card_info = matcher.match_card(cropped_front, show_top_matches=3)
                
                if not card_info:
                    print("\n⚠ Skipping pair (no match)")
                    results.append({'original': front_filename, 'new_name': front_filename, 'status': 'failed'})
                    i += 2
                    pair_number += 1
                    continue
                
               # Get the name in the current language
                if matcher.use_pokedex and language == 'JA':
                    # For old JA sets, use English name
                    name_en = card_info.get('name_en', '').strip()
                    if not name_en or name_en == 'Unknown':
                        # Fallback to default name
                        name_en = card_info.get('name', 'Unknown')
                    name = name_en
                    print(f"  📖 Using English name for filename: {name}")
                else:
                    name = matcher.get_card_name_for_language(card_info, language)
                    
                name = sanitize_filename(name)
                local_id = card_info.get('localId', 'Unknown').replace('/', '-')
                ext = os.path.splitext(front_filename)[1]
                
                base_front_filename = f"{name}_{local_id}_{set_code}_{language}_FRONT{ext}"
                front_new_name = get_unique_filename(output_dir, base_front_filename)
                front_output = os.path.join(output_dir, front_new_name)
                cv2.imwrite(front_output, cropped_front)
                print(f"\n✓ Saved FRONT: {front_new_name}")
                
                results.append({
                    'original': front_filename,
                    'new_name': front_new_name,
                    'status': 'success'
                })
                
                if i + 1 < len(image_files):
                    back_filename = image_files[i + 1]
                    back_path = os.path.join(search_path, back_filename)
                    
                    print(f"\n[{i+2}/{len(image_files)}] BACK: {back_filename}")
                    print("→ Cropping BACK card...")
                    
                    back_cropper = CardCropper(back_path)
                    if back_cropper.image is not None:
                        back_cropped = back_cropper.crop_card_back()
                        if back_cropped is not None:
                            base_back_filename = f"{name}_{local_id}_{set_code}_{language}_BACK{ext}"
                            back_new_name = get_unique_filename(output_dir, base_back_filename)
                            back_output = os.path.join(output_dir, back_new_name)
                            cv2.imwrite(back_output, back_cropped)
                            print(f"✓ Saved BACK: {back_new_name}")
                            
                            results.append({
                                'original': back_filename,
                                'new_name': back_new_name,
                                'status': 'success'
                            })
                
                i += 2
                pair_number += 1
                    
            except Exception as e:
                print(f"\n✗ Error: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    'original': front_filename,
                    'new_name': front_filename,
                    'status': 'error'
                })
                i += 2
                pair_number += 1
        
        print("\n" + "="*70)
        print(f"PROCESSING SUMMARY - {language}")
        print("="*70)
        success = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'failed')
        errors = sum(1 for r in results if r['status'] == 'error')
        
        print(f"Total: {len(results)} images | Success: {success} | Failed: {failed} | Errors: {errors}")
        print(f"Cards processed: {success//2} pairs")
        print(f"Output: {output_dir}")
        print("="*70)

if __name__ == "__main__":
    print("="*70)
    print("POKÉMON CARD PROCESSOR - IMAGE MATCHING WITH LEARNING")
    print("="*70)
    print("\nThis script processes FRONT/BACK image pairs")
    print("🧠 NEW: Learning system remembers your corrections!\n")
    
    folder_path = input("Enter path to set folder: ").strip().strip('"')
    
    raw_folder = os.path.join(folder_path, 'raw')
    if not os.path.exists(raw_folder):
        print(f"Error: 'raw' folder not found in {folder_path}")
    else:
        language_folders = ['DE', 'EN', 'ES', 'FR', 'IT', 'JA', 'KO', 'PT']
        found_languages = []
        
        for lang in language_folders:
            lang_path = os.path.join(raw_folder, lang)
            if os.path.exists(lang_path) and os.path.isdir(lang_path):
                found_languages.append(lang)
        
        if not found_languages:
            print("No language subfolders found")
        else:
            print(f"\nAvailable languages: {', '.join(found_languages)}")
            print("ALL - Process all languages")
            
            selected_language = input("\nEnter language code (or 'ALL'): ").strip().upper()
            
            if selected_language == 'ALL':
                process_folder(folder_path)
            elif selected_language in found_languages:
                process_folder(folder_path, selected_language=selected_language)
            else:
                print(f"Invalid! Choose from: {', '.join(found_languages)} or ALL")
    
    print("\n✅ Done!")