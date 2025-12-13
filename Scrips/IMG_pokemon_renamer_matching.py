import cv2
import numpy as np
import os
import sys
import json
import csv
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

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


class CardMatcher:
    """Match cropped cards against reference images using computer vision"""
    
    def __init__(self, set_code, base_path='PokemonCardLists/Card_Sets'):
        self.set_code = set_code
        self.base_path = Path(base_path)
        self.reference_images = {}
        self.card_info_map = {}  # Maps card_id to all language names
        self.csv_path = None
        self.current_language = None
        self.load_reference_images()
    
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
                    # Show name in current language if available
                    if self.current_language:
                        name = self.get_card_name_for_language(info, self.current_language)
                    else:
                        name = info.get('name', 'Unknown')
                    print(f"  #{local_id:4s} - {name}")
                print()
                continue
            
            if not card_input:
                print("Please enter a card number or 'skip'\n")
                continue
            
            # Try to find the card
            card_info = self.get_card_by_number(card_input)
            
            if card_info:
                local_id = card_info.get('localId', 'N/A')
                # Show name in current language
                if self.current_language:
                    name = self.get_card_name_for_language(card_info, self.current_language)
                else:
                    name = card_info.get('name', 'Unknown')
                
                print(f"\n✓ Found: {name} (#{local_id})")
                
                confirm = input("Is this correct? (y/n): ").strip().lower()
                if confirm == 'y':
                    return card_info
                else:
                    print("Let's try again...\n")
            else:
                print(f"\n✗ Card '{card_input}' not found in this set")
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
        if not self.reference_images:
            print("  ⚠ No reference images loaded")
            return None
        
        print(f"  Matching against {len(self.reference_images)} cards...")
        
        matches = []
        
        for card_id, ref_img in self.reference_images.items():
            try:
                score = self.compare_images_features(cropped_image, ref_img)
                matches.append((card_id, score))
            except Exception as e:
                continue
        
        matches.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\n  Top {show_top_matches} matches:")
        for i, (card_id, score) in enumerate(matches[:show_top_matches], 1):
            card_info = self.card_info_map.get(card_id, {})
            # Show name in current language
            if self.current_language:
                name = self.get_card_name_for_language(card_info, self.current_language)
            else:
                name = card_info.get('name', 'Unknown')
            local_id = card_info.get('localId', '')
            print(f"    {i}. {name} (#{local_id}) - Score: {score:.3f}")
        
        if matches and matches[0][1] > 0.15:
            best_card_id = matches[0][0]
            best_score = matches[0][1]
            
            card_info = self.card_info_map.get(best_card_id, {})
            
            # Show name in current language
            if self.current_language:
                name = self.get_card_name_for_language(card_info, self.current_language)
            else:
                name = card_info.get('name', 'Unknown')
            
            print(f"\n  ✓ Best match: {name} (#{card_info.get('localId', '')})")
            print(f"    Match score: {best_score:.3f}")
            
            ref_image = self.reference_images[best_card_id]
            accepted = True  # Auto-accept high confidence matches
            
            if accepted:
                return card_info
            else:
                print("  ✗ Match rejected by user")
                return self.manual_card_entry()
            
        else:
            print(f"\n  ✗ No confident match (best score: {matches[0][1]:.3f})")
            
            if matches:
                card_info = self.card_info_map.get(matches[0][0], {})
                # Show name in current language
                if self.current_language:
                    name = self.get_card_name_for_language(card_info, self.current_language)
                else:
                    name = card_info.get('name', 'Unknown')
                
                print(f"\n  💡 Best guess: {name} (#{card_info.get('localId', '')})")
                
                ref_image = self.reference_images[matches[0][0]]
                accepted = show_comparison(cropped_image, ref_image, name, matches[0][1])
                
                if accepted:
                    return card_info
                else:
                    return self.manual_card_entry()
            
            return self.manual_card_entry()


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
    print("POKÉMON CARD PROCESSOR - IMAGE MATCHING")
    print("="*70)
    print("\nThis script processes FRONT/BACK image pairs")
    print("Only the FRONT card is matched, BACK uses the same name\n")
    
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