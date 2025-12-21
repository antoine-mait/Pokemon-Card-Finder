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
    folder_name = os.path.basename(os.path.normpath(folder_path))
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
        
        best_match_id = None
        best_confidence = 0.0
        
        for stored_hash, card_id in self.data['confirmed_matches'].items():
            distance = self._hamming_distance(img_hash, stored_hash)
            # Changed from 51 to 77 (30% instead of 20%) for more tolerance
            if distance < 77:  # 77 out of 256 = ~30%
                confidence = 1.0 - (distance / 256)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match_id = card_id
        
        if best_match_id:
            return best_match_id, best_confidence, "learned"
        
        return None, 0.0, None
    
    def is_blacklisted(self, image, card_id):
        """Check if this card_id was previously rejected for this image"""
        img_hash = self._perceptual_hash(image)
        
        for stored_hash, rejected_ids in self.data['blacklist'].items():
            distance = self._hamming_distance(img_hash, stored_hash)
            # Changed from 51 to 77 for consistency
            if distance < 77 and card_id in rejected_ids:
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
        set_code_lower = self.set_code.lower()
        set_folders = [f for f in self.base_path.iterdir() 
                      if f.is_dir() and f.name.endswith(f"_{self.set_code}")]
        
        if not set_folders:
            set_folders = [f for f in self.base_path.iterdir() 
                          if f.is_dir() and set_code_lower in f.name.lower()]
        
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
        
    def crop_card_basic(self):
        """Simple center crop based on contrast with black background"""
        if self.image is None:
            return None
        
        h, w = self.image.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        
        # Threshold: anything brighter than black (> 30) is the card
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            # Fallback: return center 80% of image
            margin_h = int(h * 0.1)
            margin_w = int(w * 0.1)
            return self.image[margin_h:h-margin_h, margin_w:w-margin_w]
        
        # Get the largest contour (should be the card)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Get bounding rectangle
        x, y, cw, ch = cv2.boundingRect(largest_contour)
        
        # Add small margin (5-10 pixels)
        margin = 8
        x = max(0, x - margin)
        y = max(0, y - margin)
        cw = min(w - x, cw + 2 * margin)
        ch = min(h - y, ch + 2 * margin)
        
        # Crop
        cropped = self.image[y:y+ch, x:x+cw]
        
        return cropped
    
    def crop_card_advanced(self, is_back=False):
        """Advanced crop with multiple strategies for different lighting conditions
        
        Args:
            is_back: Set to True when processing card backs (uses different strategies)
        """
        # First do basic crop
        basic_cropped = self.crop_card_basic()
        
        if basic_cropped is None:
            return None
        
        h, w = basic_cropped.shape[:2]
        
        # Try multiple cropping strategies and pick the best one
        candidates = []
        
        if is_back:
            # BACK CARD STRATEGIES (no yellow border, blue pattern)
            
            # STRATEGY 1: Blue color detection
            try:
                candidate = self._crop_by_blue_border(basic_cropped)
                if candidate is not None:
                    candidates.append(('blue', candidate))
            except:
                pass
            
            # STRATEGY 2: Contrast-based (blue vs black background)
            try:
                candidate = self._crop_by_contrast(basic_cropped)
                if candidate is not None:
                    candidates.append(('contrast', candidate))
            except:
                pass
        else:
            # FRONT CARD STRATEGIES (yellow border)
            
            # STRATEGY 1: Color-based border detection (works well with yellow borders)
            try:
                candidate = self._crop_by_color_border(basic_cropped)
                if candidate is not None:
                    candidates.append(('color', candidate))
            except:
                pass
        
        # STRATEGY 2: Edge-based detection (works when edges are clear)
        try:
            candidate = self._crop_by_edges(basic_cropped)
            if candidate is not None:
                candidates.append(('edge', candidate))
        except:
            pass
        
        # STRATEGY 3: Brightness-based (works with dark vs light contrast)
        try:
            candidate = self._crop_by_brightness(basic_cropped)
            if candidate is not None:
                candidates.append(('brightness', candidate))
        except:
            pass
        
        # Pick the best candidate
        if candidates:
            # Score each candidate (prefer ones that crop more but stay reasonable)
            best_candidate = None
            best_score = 0
            
            for method, crop in candidates:
                ch, cw = crop.shape[:2]
                
                # Check aspect ratio (Pokemon cards are ~1.4:1)
                aspect = ch / cw
                aspect_score = 1.0 - abs(aspect - 1.4) if 1.2 < aspect < 1.6 else 0.0
                
                # Check size (prefer crops that remove ~5-15% of edges)
                size_ratio = (ch * cw) / (h * w)
                size_score = 1.0 - abs(size_ratio - 0.90)  # Target 90% of original
                
                # Combine scores
                score = aspect_score * 0.6 + size_score * 0.4
                
                if score > best_score and size_ratio > 0.7:  # Must keep at least 70%
                    best_score = score
                    best_candidate = crop
            
            if best_candidate is not None:
                return best_candidate
        
        # Fallback to basic crop
        return basic_cropped
    
    def _crop_by_blue_border(self, image):
        """Detect card back by finding the blue border/pattern"""
        h, w = image.shape[:2]
        
        # Convert to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Blue detection (wider range to catch various blue tones)
        lower_blue = np.array([90, 50, 50])   # Darker blue
        upper_blue = np.array([130, 255, 255])  # Lighter blue
        mask = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Clean up the mask
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get largest contour
        largest = max(contours, key=cv2.contourArea)
        x, y, cw, ch = cv2.boundingRect(largest)
        
        # Validate
        if cw < w * 0.6 or ch < h * 0.6:
            return None
        
        # Add margin
        margin = 5
        x = max(0, x - margin)
        y = max(0, y - margin)
        cw = min(w - x, cw + 2 * margin)
        ch = min(h - y, ch + 2 * margin)
        
        return image[y:y+ch, x:x+cw]
    
    def _crop_by_contrast(self, image):
        """Detect card by high contrast between card and background"""
        h, w = image.shape[:2]
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply bilateral filter to preserve edges while smoothing
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Clean up
        kernel = np.ones((5, 5), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get largest
        largest = max(contours, key=cv2.contourArea)
        x, y, cw, ch = cv2.boundingRect(largest)
        
        # Validate
        if cw < w * 0.6 or ch < h * 0.6:
            return None
        
        margin = 5
        x = max(0, x - margin)
        y = max(0, y - margin)
        cw = min(w - x, cw + 2 * margin)
        ch = min(h - y, ch + 2 * margin)
        
        return image[y:y+ch, x:x+cw]
    
    def _crop_by_color_border(self, image):
        """Detect card by finding the yellow/golden border"""
        h, w = image.shape[:2]
        
        # Convert to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Yellow/gold border detection (wider range)
        lower_yellow = np.array([15, 30, 100])
        upper_yellow = np.array([35, 255, 255])
        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get largest contour
        largest = max(contours, key=cv2.contourArea)
        x, y, cw, ch = cv2.boundingRect(largest)
        
        # Validate
        if cw < w * 0.6 or ch < h * 0.6:
            return None
        
        # Add margin
        margin = 5
        x = max(0, x - margin)
        y = max(0, y - margin)
        cw = min(w - x, cw + 2 * margin)
        ch = min(h - y, ch + 2 * margin)
        
        return image[y:y+ch, x:x+cw]
    
    def _crop_by_edges(self, image):
        """Detect card using edge detection"""
        h, w = image.shape[:2]
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Blur to reduce noise from holographic effects
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection with adjusted thresholds
        edges = cv2.Canny(blurred, 30, 100)
        
        # Dilate to connect edges
        kernel = np.ones((3, 3), np.uint8)
        edges_dilated = cv2.dilate(edges, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Find best rectangular contour
        for contour in sorted(contours, key=cv2.contourArea, reverse=True):
            x, y, cw, ch = cv2.boundingRect(contour)
            
            # Must be large enough
            if cw > w * 0.6 and ch > h * 0.6:
                margin = 5
                x = max(0, x - margin)
                y = max(0, y - margin)
                cw = min(w - x, cw + 2 * margin)
                ch = min(h - y, ch + 2 * margin)
                
                return image[y:y+ch, x:x+cw]
        
        return None
    
    def _crop_by_brightness(self, image):
        """Detect card by finding bright regions (card) vs dark (background)"""
        h, w = image.shape[:2]
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Use Otsu's thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Clean up
        kernel = np.ones((5, 5), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get largest
        largest = max(contours, key=cv2.contourArea)
        x, y, cw, ch = cv2.boundingRect(largest)
        
        # Validate
        if cw < w * 0.6 or ch < h * 0.6:
            return None
        
        margin = 5
        x = max(0, x - margin)
        y = max(0, y - margin)
        cw = min(w - x, cw + 2 * margin)
        ch = min(h - y, ch + 2 * margin)
        
        return image[y:y+ch, x:x+cw]