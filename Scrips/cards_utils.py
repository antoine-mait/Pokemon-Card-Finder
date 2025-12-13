"""
Pokemon Card Processing Utilities
Shared functions and classes for card matching, learning, and database access
"""

import cv2
import numpy as np
import os
import sys
import csv
import pickle
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


# ============================================================================
# FILENAME UTILITIES
# ============================================================================

def sanitize_filename(filename):
    """Remove or replace characters that are invalid in Windows filenames"""
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'à': 'a', 'ç': 'c',
        'ï': 'i', 'ô': 'o', 'û': 'u', 'É': 'E', 'ä': 'a',
        'ö': 'o', 'ü': 'u', 'ß': 'ss',
    }
    
    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)
    
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    return filename


def get_unique_filename(output_dir, base_filename):
    """Generate unique filename by adding (1), (2), etc. if file exists"""
    name_without_ext, ext = os.path.splitext(base_filename)
    test_filename = base_filename
    test_filepath = os.path.join(output_dir, test_filename)
    
    if not os.path.exists(test_filepath):
        return test_filename
    
    counter = 1
    while True:
        test_filename = f"{name_without_ext}({counter}){ext}"
        test_filepath = os.path.join(output_dir, test_filename)
        
        if not os.path.exists(test_filepath):
            return test_filename
        
        counter += 1


def extract_set_code(folder_path):
    """Extract the set code from folder name (last part after last underscore)"""
    folder_name = os.path.basename(folder_path)
    parts = folder_name.split('_')
    if len(parts) > 0:
        return parts[-1]
    return 'unknown'


# ============================================================================
# LEARNING SYSTEM
# ============================================================================

class LearningSystem:
    """Smart learning system that remembers matches and rejections"""
    
    def __init__(self, set_code):
        self.set_code = set_code
        self.db_file = f"learning_db_{set_code}.pkl"
        self.data = {
            'confirmed_matches': {},  # image_hash -> card_id
            'blacklist': {},          # image_hash -> [rejected_card_ids]
            'confidence_boost': {},   # card_id -> boost_score
            'stats': {'auto_matches': 0, 'manual_entries': 0, 'total_processed': 0}
        }
        self.load()
    
    def _perceptual_hash(self, image):
        """Create a simple perceptual hash of the image"""
        small = cv2.resize(image, (16, 16))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        median = np.median(gray)
        hash_matrix = gray > median
        hash_str = ''.join(['1' if val else '0' for val in hash_matrix.flatten()])
        return hash_str
    
    def _hamming_distance(self, hash1, hash2):
        """Calculate how similar two hashes are (lower = more similar)"""
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
    
    def check_learned_match(self, image):
        """Check if we've seen this card before"""
        img_hash = self._perceptual_hash(image)
        
        for stored_hash, card_id in self.data['confirmed_matches'].items():
            distance = self._hamming_distance(img_hash, stored_hash)
            if distance < 51:  # 51 out of 256 = ~20%
                confidence = 1.0 - (distance / 256)
                return card_id, confidence, "learned"
        
        return None, 0.0, None
    
    def is_blacklisted(self, image, card_id):
        """Check if this card_id was previously rejected for this image"""
        img_hash = self._perceptual_hash(image)
        
        for stored_hash, rejected_ids in self.data['blacklist'].items():
            distance = self._hamming_distance(img_hash, stored_hash)
            if distance < 51 and card_id in rejected_ids:
                return True
        
        return False
    
    def add_confirmed_match(self, image, card_id):
        """Remember this correct match"""
        img_hash = self._perceptual_hash(image)
        self.data['confirmed_matches'][img_hash] = card_id
        
        if card_id not in self.data['confidence_boost']:
            self.data['confidence_boost'][card_id] = 0
        self.data['confidence_boost'][card_id] += 0.05
        
        print(f"  💾 Learned: This card will be auto-matched next time")
        self.save()
    
    def add_rejection(self, image, card_id):
        """Remember this card was wrong for this image"""
        img_hash = self._perceptual_hash(image)
        
        if img_hash not in self.data['blacklist']:
            self.data['blacklist'][img_hash] = []
        
        if card_id not in self.data['blacklist'][img_hash]:
            self.data['blacklist'][img_hash].append(card_id)
            print(f"  🚫 Blacklisted: Will never suggest this card for this image again")
        
        self.save()
    
    def remove_match(self, image):
        """Remove a learned match (used when correcting mistakes)"""
        img_hash = self._perceptual_hash(image)
        if img_hash in self.data['confirmed_matches']:
            del self.data['confirmed_matches'][img_hash]
            print(f"  🗑️ Removed old learned match")
            self.save()
            return True
        return False
    
    def get_confidence_boost(self, card_id):
        """Get the confidence boost for a frequently matched card"""
        return self.data['confidence_boost'].get(card_id, 0.0)
    
    def update_stats(self, match_type):
        """Track statistics"""
        self.data['stats']['total_processed'] += 1
        if match_type == 'auto':
            self.data['stats']['auto_matches'] += 1
        elif match_type == 'manual':
            self.data['stats']['manual_entries'] += 1
        self.save()
    
    def get_stats(self):
        """Get learning statistics"""
        return {
            'learned_cards': len(self.data['confirmed_matches']),
            'blacklisted_combos': sum(len(v) for v in self.data['blacklist'].values()),
            'total_processed': self.data['stats']['total_processed'],
            'auto_match_rate': (self.data['stats']['auto_matches'] / 
                               max(1, self.data['stats']['total_processed']) * 100)
        }
    
    def save(self):
        """Save to disk"""
        try:
            with open(self.db_file, 'wb') as f:
                pickle.dump(self.data, f)
        except Exception as e:
            print(f"  ⚠ Could not save learning data: {e}")
    
    def load(self):
        """Load from disk"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'rb') as f:
                    self.data = pickle.load(f)
                
                stats = self.get_stats()
                print(f"  🧠 Loaded learning database:")
                print(f"     • {stats['learned_cards']} cards learned")
                print(f"     • {stats['blacklisted_combos']} rejections remembered")
                if stats['total_processed'] > 0:
                    print(f"     • {stats['auto_match_rate']:.1f}% auto-match rate")
            except Exception as e:
                print(f"  ⚠ Could not load learning data: {e}")


# ============================================================================
# CARD DATABASE
# ============================================================================

class CardDatabase:
    """Load and search card database from CSV files"""
    
    def __init__(self, set_code, base_path='PokemonCardLists/Card_Sets'):
        self.set_code = set_code
        self.base_path = Path(base_path)
        self.card_info_map = {}
        self.csv_files = []
        self.set_folder = None
        self.load_card_database()
    
    def load_card_database(self):
        """Load card database from CSV files"""
        print(f"\n  Looking for set code: '{self.set_code}'")
        
        # Find set folder
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
        
        self.set_folder = set_folders[0]
        print(f"  ✓ Found set folder: {self.set_folder.name}")
        
        # Load CSV files
        self.csv_files = list(self.set_folder.glob("CardList_*.csv"))
        
        if not self.csv_files:
            print("  ⚠ No CSV files found")
            return
        
        # Load base card info
        try:
            with open(self.csv_files[0], 'r', encoding='utf-8') as f:
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
        except Exception as e:
            print(f"  ⚠ Error loading CSV: {e}")
    
    def load_card_info_for_language(self, language):
        """Load card information from the language-specific CSV"""
        if not self.csv_files:
            return
        
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
                        lang_key = f'name_{language.lower()}'
                        self.card_info_map[card_id][lang_key] = row.get('name', 'Unknown')
        except Exception as e:
            print(f"  ⚠ Error loading CSV: {e}")
    
    def get_card_name_for_language(self, card_info, language):
        """Get card name in specific language"""
        lang_key = f'name_{language.lower()}'
        if lang_key in card_info and card_info[lang_key]:
            name = card_info[lang_key]
            if name and name != 'Unknown':
                return name
        return card_info.get('name', 'Unknown')
    
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
    
    def search_card(self, search_term):
        """Search for cards by number or name"""
        results = []
        search_lower = search_term.lower().strip()
        
        for card_id, info in self.card_info_map.items():
            # Check localId
            if info.get('localId', '').strip() == search_term.strip():
                results.append((card_id, info, 'exact_number'))
            # Check card_id
            elif card_id.lower() == search_lower:
                results.append((card_id, info, 'exact_id'))
            # Check all names
            else:
                for key, value in info.items():
                    if key.startswith('name') and search_lower in value.lower():
                        results.append((card_id, info, 'name_match'))
                        break
        
        return results
    
    def list_all_cards(self, language='en'):
        """List all cards in the set"""
        cards = []
        for card_id, info in sorted(self.card_info_map.items(), 
                                    key=lambda x: x[1].get('localId', '')):
            local_id = info.get('localId', 'N/A')
            name = self.get_card_name_for_language(info, language)
            cards.append((local_id, name, card_id))
        return cards

class PokedexDatabase:
    """Load Pokedex CSV for old Japanese sets"""
    
    def __init__(self, base_path='PokemonCardLists'):
        self.base_path = Path(base_path)
        self.pokedex = {}
        self.load_pokedex()
    
    def load_pokedex(self):
        """Load the pokedex.csv file"""
        pokedex_file = self.base_path / "pokedex.csv"
        
        if not pokedex_file.exists():
            print(f"  ⚠ Pokedex file not found at {pokedex_file}")
            return
        
        try:
            with open(pokedex_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    number = row.get('Number', '').strip()
                    japanese = row.get('Japanese', '').strip()
                    english = row.get('English', '').strip()
                    
                    if number and english:
                        self.pokedex[number] = {
                            'japanese': japanese,
                            'english': english
                        }
            
            print(f"  ✓ Loaded Pokedex with {len(self.pokedex)} entries")
        except Exception as e:
            print(f"  ⚠ Error loading Pokedex: {e}")
    
    def get_english_name(self, number):
        """Get English name for a Pokedex number"""
        number_clean = number.strip().zfill(4)  # Pad to 4 digits
        return self.pokedex.get(number_clean, {}).get('english', None)
    
    def search_by_japanese(self, japanese_name):
        """Search for English name by Japanese name"""
        japanese_lower = japanese_name.lower().strip()
        for number, data in self.pokedex.items():
            if data['japanese'].lower() == japanese_lower:
                return data['english']
        return None
# ============================================================================
# CARD CROPPER
# ============================================================================

class CardCropper:
    """Automatically detects and crops Pokémon cards from images"""
    
    def __init__(self, image_path):
        self.image_path = image_path
        self.image = cv2.imread(image_path)
        self.cropped_card = None
        
    def find_card_contour(self):
        """Find the card's contour in the image"""
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        largest_contour = max(contours, key=cv2.contourArea)
        return largest_contour
    
    def rotate_image(self, contour):
        """Rotate image to straighten the card"""
        rect = cv2.minAreaRect(contour)
        angle = rect[-1]
        
        if angle > 45:
            angle = angle - 90
        elif angle < -45:
            angle = angle + 90
        
        if abs(angle) < 1:
            return self.image, angle
        
        (h, w) = self.image.shape[:2]
        center = (w // 2, h // 2)
        
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(self.image, M, (w, h), 
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        
        return rotated, angle

    def crop_card_back(self):
        """Simple center crop for card backs"""
        h, w = self.image.shape[:2]
        
        crop_percent_w = 0.4
        crop_percent_h = 0.95
        
        crop_w = int(w * crop_percent_w)
        crop_h = int(h * crop_percent_h)
        
        start_x = (w - crop_w) // 2
        start_y = (h - crop_h) // 2
        
        start_x = max(0, start_x)
        start_y = max(0, start_y)
        end_x = min(w, start_x + crop_w)
        end_y = min(h, start_y + crop_h)
        
        self.cropped_card = self.image[start_y:end_y, start_x:end_x]
        return self.cropped_card
    
    def crop_card(self):
        """Crop the card using bounding rectangle with rotation correction"""
        contour = self.find_card_contour()
        
        if contour is None:
            return None
        
        rotated_image, angle = self.rotate_image(contour)
        self.image = rotated_image
        
        contour = self.find_card_contour()
        if contour is None:
            return None
        
        x, y, w, h = cv2.boundingRect(contour)
        
        margin = 20
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(self.image.shape[1] - x, w + 2*margin)
        h = min(self.image.shape[0] - y, h + 2*margin)
        
        self.cropped_card = self.image[y:y+h, x:x+w]
        return self.cropped_card