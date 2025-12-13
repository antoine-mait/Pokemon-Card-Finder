import cv2
import numpy as np
import pytesseract
import re
import os
import sys
import json
from cardList import get_card_name

# Configure Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def load_set_regions(config_path='set_regions.json'):
    """Load set-specific region coordinates from JSON file"""
    if not os.path.exists(config_path):
        print(f"⚠ Warning: {config_path} not found, using default coordinates")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Error loading {config_path}: {e}")
        return {}

def get_number_region_coords(set_code, regions_config):
    """Get number region coordinates for a specific set"""
    # Normalize set code for lookup (remove dots, uppercase)
    set_key = set_code.upper().replace('.', '')
    
    print(f"\n  [DEBUG] Raw set_code from folder: '{set_code}'")
    print(f"  [DEBUG] Normalized set_key: '{set_key}'")
    
    # Try exact match first
    if set_key in regions_config:
        coords = regions_config[set_key]['number_region']
        print(f"  ✓ Using region coordinates for set '{set_key}'")
        return coords
    
    # Try with dots (original format)
    if set_code.upper() in regions_config:
        coords = regions_config[set_code.upper()]['number_region']
        print(f"  ✓ Using region coordinates for set '{set_code.upper()}'")
        return coords
    
    # Fall back to default
    if 'DEFAULT' in regions_config:
        coords = regions_config['DEFAULT']['number_region']
        print(f"  ⚠ Set '{set_code}' not in config, using DEFAULT coordinates")
        return coords
    
    # Hardcoded fallback if no config at all
    print(f"  ⚠ No config found for '{set_code}', using hardcoded default")
    return {
        'y_start': 0.9,
        'y_end': 1.0,
        'x_start': 0.0,
        'x_end': 0.4
    }

def sanitize_filename(filename):
    """Remove or replace characters that are invalid in Windows filenames"""
    # Replace problematic characters
    replacements = {
        'é': 'e',
        'è': 'e',
        'ê': 'e',
        'à': 'a',
        'ç': 'c',
        'ï': 'i',
        'ô': 'o',
        'û': 'u',
        'É': 'E',
        'ä': 'a',
        'ö': 'o',
        'ü': 'u',
        'ß': 'ss',
    }
    
    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)
    
    # Remove any remaining non-ASCII characters
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
    return 'Error' 
   
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
        area = cv2.contourArea(largest_contour)
        image_area = self.image.shape[0] * self.image.shape[1]
        
        print(f"Contour area: {(area/image_area)*100:.1f}% of image")
        
        return largest_contour
    
    def rotate_image(self, contour):
        """Rotate image to straighten the card (keep vertical orientation)"""
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.intp(box)
        
        angle = rect[-1]
        
        # Adjust angle to be small correction only (-45 to 45 degrees)
        if angle > 45:
            angle = angle - 90
        elif angle < -45:
            angle = angle + 90
        
        # If card is nearly straight, don't rotate
        if abs(angle) < 1:
            print(f"Card rotation: {angle:.2f}° (no correction needed)")
            return self.image, angle
        
        print(f"Card rotation: {angle:.2f}° (correcting...)")
        
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
        
        print(f"Center crop: x={start_x}, y={start_y}, width={end_x-start_x}, height={end_y-start_y}")
        
        self.cropped_card = self.image[start_y:end_y, start_x:end_x]
        
        return self.cropped_card
    
    def crop_card(self):
        """Crop the card using bounding rectangle with rotation correction"""
        contour = self.find_card_contour()
        
        if contour is None:
            print("Could not find card contour")
            return None
        
        # Rotate image to make card straight
        rotated_image, angle = self.rotate_image(contour)
        self.image = rotated_image
        
        # Find contour again on rotated image
        contour = self.find_card_contour()
        if contour is None:
            print("Could not find card contour after rotation")
            return None
        
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        
        print(f"Card bounding box: x={x}, y={y}, width={w}, height={h}")
        
        # Add small margin
        margin = 20
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(self.image.shape[1] - x, w + 2*margin)
        h = min(self.image.shape[0] - y, h + 2*margin)
        
        # Crop the card
        self.cropped_card = self.image[y:y+h, x:x+w]
        
        return self.cropped_card


class PokemonCardReader:
    """Read card number and lookup name from card database"""
    
    def __init__(self, card_image, set_code, regions_config):
        self.image = card_image
        self.set_code = set_code
        self.regions_config = regions_config
        self.card_info = {}
    
    def extract_number_region(self):
        """Extract number region using set-specific coordinates"""
        h, w = self.image.shape[:2]
        
        # Get coordinates for this set
        coords = get_number_region_coords(self.set_code, self.regions_config)
        
        y_start = int(h * coords['y_start'])
        y_end = int(h * coords['y_end'])
        x_start = int(w * coords['x_start'])
        x_end = int(w * coords['x_end'])
        
        print(f"  Region: y={y_start}-{y_end}, x={x_start}-{x_end}")
        
        number_region = self.image[y_start:y_end, x_start:x_end]
        return number_region
    
    def preprocess_for_number(self, region):
        """Preprocess image for card number OCR - multiple methods"""
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        
        # Downscale if too large
        h, w = gray.shape
        max_width = 1500
        if w > max_width:
            scale = max_width / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
        # Upscale for OCR
        scale = 4
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        # Method 1: CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Method 2: Otsu's binarization
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Method 3: Inverted Otsu (white text on black background)
        _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
    
        # Save all versions for debugging
        tmp_folder = 'tmp_crop'
        os.makedirs(tmp_folder, exist_ok=True)
        cv2.imwrite(os.path.join(tmp_folder, '1_gray.jpg'), gray)
        cv2.imwrite(os.path.join(tmp_folder, '2_enhanced.jpg'), enhanced)
        cv2.imwrite(os.path.join(tmp_folder, '3_otsu.jpg'), otsu)
        cv2.imwrite(os.path.join(tmp_folder, '4_otsu_inv.jpg'), otsu_inv)
        
        return {
            'gray': gray,
            'enhanced': enhanced,
            'otsu': otsu,
            'otsu_inv': otsu_inv
        }

    def find_card_number(self):
        """Extract card number from configured region"""
        print("\n  Extracting card number...")
        number_region = self.extract_number_region()
        
        # Create tmp_crop folder
        tmp_folder = 'tmp_crop'
        os.makedirs(tmp_folder, exist_ok=True)
        
        # Get set card count
        from cardList import get_set_card_count
        set_card_count = get_set_card_count(self.set_code)
        
        if set_card_count:
            print(f"  ℹ Set has {set_card_count} cards total")
        
        # Preprocess - get all methods
        processed_images = self.preprocess_for_number(number_region)
        
        # Helper function to clean OCR text - convert common letter mistakes to numbers
        def clean_ocr_text(text):
            """Convert common OCR letter mistakes to numbers"""
            replacements = {
                'i': '1', 'I': '1', 'l': '1', 'L': '1', '|': '1', 'P' : '1',
                'o': '0', 'O': '0',
                'z': '2', 'Z': '2',
                's': '5', 'S': '5',
                'b': '6', 'B': '6',
                't': '7', 'T': '7',
            }
            cleaned = text
            for char, replacement in replacements.items():
                cleaned = cleaned.replace(char, replacement)
            return cleaned
        
        # Try OCR on all preprocessing methods
        for img_name, img in processed_images.items():
            for psm in [6, 7, 8, 13]:
                try:
                    # Try with whitelist first
                    config_whitelist = f'--psm {psm} -c tessedit_char_whitelist=0123456789/'
                    text_whitelist = pytesseract.image_to_string(img, lang='eng', config=config_whitelist).strip()
                    
                    # Try without whitelist (then clean it)
                    config_normal = f'--psm {psm}'
                    text_normal = pytesseract.image_to_string(img, lang='eng', config=config_normal).strip()
                    
                    # Clean the normal text (convert letters to numbers)
                    text_cleaned = clean_ocr_text(text_normal)
                    
                    # Try all three versions
                    texts_to_try = [
                        ('whitelist', text_whitelist),
                        ('normal', text_normal),
                        ('cleaned', text_cleaned)
                    ]
                    
                    for text_type, text in texts_to_try:
                        if text:
                            if text_type == 'cleaned' and text != text_normal:
                                print(f"    [DEBUG] {img_name} + PSM {psm} ({text_type}): '{text}' (from '{text_normal}')")
                            elif text:
                                print(f"    [DEBUG] {img_name} + PSM {psm} ({text_type}): '{text}'")
                        
                        # If we have set_card_count, look for pattern: X/count or just X
                        if set_card_count:
                            # Look for just a number (we'll add /count)
                            match_single = re.search(r'(\d{1,3})', text)
                            if match_single:
                                card_num = match_single.group(1)
                                # Validate it's reasonable (not 0, not > total)
                                if 0 < int(card_num) <= int(set_card_count):
                                    number_text = f"{card_num}/{set_card_count}"
                                    print(f"    ✓ Found: {number_text} ({img_name} + PSM {psm} {text_type}, added set count)")
                                    return number_text
                            
                            # Look for number before the /
                            match = re.search(r'(\d{1,3})\s*[/\\|]\s*(\d{1,3})', text)
                            if match:
                                number_text = f"{match.group(1)}/{match.group(2)}"
                                # Validate the second number matches set count
                                if match.group(2) == str(set_card_count):
                                    print(f"    ✓ Found: {number_text} ({img_name} + PSM {psm} {text_type})")
                                    return number_text
                        
                        # Standard pattern matching X/Y
                        match = re.search(r'(\d{1,3})\s*[/\\|]\s*(\d{1,3})', text)
                        if match:
                            number_text = f"{match.group(1)}/{match.group(2)}"
                            print(f"    ✓ Found: {number_text} ({img_name} + PSM {psm} {text_type})")
                            return number_text
                            
                except Exception as e:
                    continue
        
        print("    ✗ Card number not found")
        return "Unknown"
    
    def read_card(self, language='EN'):
        """Extract card number and lookup name from database"""
        print("\nExtracting card information...")
        
        # Get card number via OCR
        self.card_info['number'] = self.find_card_number()
        
        # Lookup name from card database
        if self.card_info['number'] != "Unknown":
            card_name = get_card_name(self.card_info['number'], self.set_code, language)
            if card_name:
                self.card_info['name'] = card_name
                self.card_info['source'] = 'Database'
                print(f"  ✓ Found in database: {card_name}")
            else:
                self.card_info['name'] = "Unknown"
                self.card_info['source'] = 'Not in database'
                print(f"  ✗ Card #{self.card_info['number']} not found in database")
        else:
            self.card_info['name'] = "Unknown"
            self.card_info['source'] = 'OCR failed'
        
        print(f"\n✓ Card name: {self.card_info['name']} (via {self.card_info.get('source', 'Unknown')})")
        print(f"✓ Card number: {self.card_info['number']}")
        
        return self.card_info
    
    def display_info(self):
        """Display extracted information"""
        print("\n" + "="*60)
        print("POKÉMON CARD INFORMATION")
        print("="*60)
        print(f"Name:         {self.card_info.get('name', 'N/A')}")
        print(f"Card Number:  {self.card_info.get('number', 'N/A')}")
        print(f"Source:       {self.card_info.get('source', 'N/A')}")
        print("="*60)
        
        name = self.card_info.get('name', 'Unknown')
        number = self.card_info.get('number', 'Unknown').replace('/', '-')
        print(f"\nSuggested filename: {name}_{number}.jpg")


def process_card(image_path, set_code, regions_config, save_cropped=True, output_folder='Renamed_Cropped', language='EN'):
    """Complete pipeline: crop card from photo, then extract info"""
    print("="*70)
    print("POKÉMON CARD PROCESSOR - CROP AND RENAME")
    print("="*70)
    print(f"\nProcessing: {image_path}\n")
    
    # If set_code is None, try to extract from parent of raw folder
    if not set_code:
        # If path contains 'raw', go up one level
        if 'raw' in image_path:
            parent_folder = os.path.dirname(os.path.dirname(image_path))
        else:
            parent_folder = os.path.dirname(image_path)
        set_code = extract_set_code(parent_folder)
    
    print(f"[DEBUG] Using set code: {set_code}")
    
    # Step 1: Crop the card
    print("Step 1: Detecting and cropping card...")
    cropper = CardCropper(image_path)
    
    if cropper.image is None:
        print("Error: Could not load image")
        return None
    
    cropped_card = cropper.crop_card()
    
    if cropped_card is None:
        print("Error: Could not crop card")
        return None
    
    print(f"✓ Card cropped: {cropped_card.shape[1]}x{cropped_card.shape[0]} pixels")
    
    # Step 2: Read information
    print("\nStep 2: Reading card information...")
    reader = PokemonCardReader(cropped_card, set_code, regions_config)
    
    info = reader.read_card(language)
    reader.display_info()
    
    # Step 3: Save with proper naming
    if save_cropped and info:
        base_dir = os.path.dirname(image_path)
        output_dir = os.path.join(base_dir, output_folder)
        os.makedirs(output_dir, exist_ok=True)
        
        name = info.get('name', 'Unknown')
        name = sanitize_filename(name)
        number = info.get('number', 'Unknown').replace('/', '-')
        ext = os.path.splitext(image_path)[1]
        
        base_filename = f"{name}_{number}_{set_code}{ext}"
        new_filename = get_unique_filename(output_dir, base_filename)
        output_path = os.path.join(output_dir, new_filename)
        
        cv2.imwrite(output_path, cropped_card)
        print(f"\n✓ Saved as: {new_filename}")
        print(f"✓ Location: {output_dir}")
    
    return info


def process_folder(folder_path, output_folder='Renamed_Cropped', selected_language=None):
    """Process all card images in a folder with language subfolders"""
    
    # Load region configurations
    config_path = os.path.join('PokemonCardLists', 'set_regions.json')
    regions_config = load_set_regions(config_path)
    
    set_code = extract_set_code(folder_path)
    print(f"Using set code: {set_code}")
    
    raw_folder = os.path.join(folder_path, 'raw')
    
    if not os.path.exists(raw_folder):
        print(f"Error: 'raw' folder not found in {folder_path}")
        return
    
    # Check for language subfolders
    language_folders = ['DE', 'EN', 'FR', 'JA']
    found_languages = []
    
    for lang in language_folders:
        lang_path = os.path.join(raw_folder, lang)
        if os.path.exists(lang_path) and os.path.isdir(lang_path):
            found_languages.append(lang)
    
    if not found_languages:
        print("No language subfolders (DE/EN/FR/JA) found in raw folder")
        return
    
    # Filter to selected language if specified
    if selected_language:
        if selected_language in found_languages:
            found_languages = [selected_language]
            print(f"Processing only: {selected_language}\n")
        else:
            print(f"Error: Language '{selected_language}' not found in available languages")
            return
    else:
        print(f"Found language folders: {', '.join(found_languages)}\n")
    
    # Process each language folder
    for language in found_languages:
        print("\n" + "="*70)
        print(f"PROCESSING LANGUAGE: {language}")
        print("="*70)
        
        search_path = os.path.join(raw_folder, language)
        output_dir = os.path.join(folder_path, output_folder, language)
        os.makedirs(output_dir, exist_ok=True)
        
        # Find all images
        extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_files = sorted([f for f in os.listdir(search_path) 
                       if any(f.lower().endswith(ext) for ext in extensions)])
        
        print(f"Found {len(image_files)} images in {language} folder\n")
        
        results = []
        i = 0
        
        while i < len(image_files):
            filename = image_files[i]
            
            print(f"\n{'='*70}")
            print(f"[{i+1}/{len(image_files)}] Processing {filename} ({language})...")
            print('='*70)
            
            input_path = os.path.join(search_path, filename)
            
            try:
                # Process the FRONT card
                info = process_card(input_path, set_code, regions_config, save_cropped=False, output_folder=output_folder, language=language)
                
                if info and info.get('name') != 'Unknown':
                    name = sanitize_filename(info.get('name', 'Unknown'))
                    number = info.get('number', 'Unknown').replace('/', '-')
                    ext = os.path.splitext(filename)[1]
                    
                    # Crop and save FRONT
                    cropper = CardCropper(input_path)
                    if cropper.image is not None:
                        cropped_card = cropper.crop_card()
                        if cropped_card is not None:
                            base_front_filename = f"{name}_{number}_{set_code}_{language}_FRONT{ext}"
                            front_filename = get_unique_filename(output_dir, base_front_filename)
                            front_path = os.path.join(output_dir, front_filename)
                            cv2.imwrite(front_path, cropped_card)
                            print(f"✓ Saved FRONT as: {front_filename}")
                            
                            results.append({
                                'original': filename,
                                'new_name': front_filename,
                                'status': 'success'
                            })
                    
                    # Process BACK (next image)
                    if i + 1 < len(image_files):
                        back_filename = image_files[i + 1]
                        back_input_path = os.path.join(search_path, back_filename)
                        
                        print(f"\n{'='*70}")
                        print(f"[{i+2}/{len(image_files)}] Processing {back_filename} (BACK)...")
                        print('='*70)
                        
                        back_cropper = CardCropper(back_input_path)
                        if back_cropper.image is not None:
                            back_cropped = back_cropper.crop_card_back()
                            if back_cropped is not None:
                                base_back_filename = f"{name}_{number}_{set_code}_{language}_BACK{ext}"
                                back_new_filename = get_unique_filename(output_dir, base_back_filename)
                                back_path = os.path.join(output_dir, back_new_filename)
                                cv2.imwrite(back_path, back_cropped)
                                print(f"✓ Saved BACK as: {back_new_filename}")
                                
                                results.append({
                                    'original': back_filename,
                                    'new_name': back_new_filename,
                                    'status': 'success'
                                })
                        
                        i += 2
                    else:
                        i += 1
                else:
                    results.append({
                        'original': filename,
                        'new_name': filename,
                        'status': 'failed'
                    })
                    i += 1
                    
            except Exception as e:
                print(f"Error: {e}")
                results.append({
                    'original': filename,
                    'new_name': filename,
                    'status': 'error'
                })
                i += 1
        
        # Print summary for this language
        print("\n" + "="*70)
        print(f"PROCESSING SUMMARY - {language}")
        print("="*70)
        success = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'failed')
        errors = sum(1 for r in results if r['status'] == 'error')
        
        print(f"Total: {len(results)} | Success: {success} | Failed: {failed} | Errors: {errors}")
        print(f"Output folder: {output_dir}")
        print("="*70)
        
        for r in results:
            status_icon = "✓" if r['status'] == 'success' else "✗"
            print(f"{status_icon} {r['original']:40} -> {r['new_name']}")
        print("="*70)


# Main execution
if __name__ == "__main__":
    print("="*70)
    print("POKÉMON CARD PROCESSOR - CROP AND RENAME")
    print("="*70)
    
    print("\nWhat would you like to do?")
    print("1. Process single card")
    print("2. Process entire folder")
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        image_path = input("\nEnter full path to image: ").strip().strip('"')
        
        if 'raw' in image_path.lower():
            # Image is in raw folder, go up one level to get set folder
            set_folder = os.path.dirname(os.path.dirname(image_path))
        else:
            # Image is in set folder directly
            set_folder = os.path.dirname(image_path)
        
        set_code = extract_set_code(set_folder)
        print(f"[DEBUG] Extracted set code: '{set_code}' from folder: {set_folder}")
        
        # Load regions config
        config_path = os.path.join('PokemonCardLists', 'set_regions.json')
        regions_config = load_set_regions(config_path)
        
        process_card(image_path, set_code, regions_config, save_cropped=True)
    elif choice == "2":
        folder_path = input("\nEnter full path to folder: ").strip().strip('"')
        
        # Check available languages
        raw_folder = os.path.join(folder_path, 'raw')
        if not os.path.exists(raw_folder):
            print(f"Error: 'raw' folder not found in {folder_path}")
        else:
            language_folders = ['DE', 'EN', 'FR', 'JA']
            found_languages = []
            
            for lang in language_folders:
                lang_path = os.path.join(raw_folder, lang)
                if os.path.exists(lang_path) and os.path.isdir(lang_path):
                    found_languages.append(lang)
            
            if not found_languages:
                print("No language subfolders (DE/EN/FR/JA) found in raw folder")
            else:
                print(f"\nAvailable languages: {', '.join(found_languages)}")
                print("ALL - Process all languages")
                
                selected_language = input("\nEnter language code (or 'ALL' for all languages): ").strip().upper()
                
                if selected_language == 'ALL':
                    process_folder(folder_path)
                elif selected_language in found_languages:
                    process_folder(folder_path, selected_language=selected_language)
                else:
                    print(f"Invalid language code! Please choose from: {', '.join(found_languages)} or ALL")
    else:
        print("Invalid choice!")
    
    print("\n✅ Done!")