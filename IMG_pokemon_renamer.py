import cv2
import numpy as np
import pytesseract
import re
import os
import sys
from cardList import get_card_name

# Configure Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

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
    }
    
    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)
    
    # Remove any remaining non-ASCII characters
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    
    return filename

def get_unique_filename(output_dir, base_filename):
    """Generate unique filename by adding (1), (2), etc. if file exists
    This checks the actual filesystem each time it's called"""
    # Split into name and extension
    name_without_ext, ext = os.path.splitext(base_filename)
    
    # Start with the base filename
    test_filename = base_filename
    test_filepath = os.path.join(output_dir, test_filename)
    
    # If file doesn't exist, return original name
    if not os.path.exists(test_filepath):
        return test_filename
    
    # File exists, find next available number
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
        # Get minimum area rectangle (rotated bounding box)
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.intp(box)  # Use np.intp instead of deprecated np.int0
        
        # Get the angle
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
        
        # Get image dimensions
        (h, w) = self.image.shape[:2]
        center = (w // 2, h // 2)
        
        # Rotate image
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(self.image, M, (w, h), 
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        
        return rotated, angle
        
    def find_card_contour_back(self):
        """Find the card's contour for card backs (uniform blue pattern)"""
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Use adaptive thresholding for uniform patterns
        adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)
        
        # Also try Canny with lower thresholds
        edges = cv2.Canny(blurred, 30, 100)
        
        # Combine both methods
        combined = cv2.bitwise_or(edges, adaptive)
        
        # Stronger dilation to connect edges
        kernel = np.ones((7, 7), np.uint8)
        dilated = cv2.dilate(combined, kernel, iterations=3)
        
        # Close gaps
        kernel_close = np.ones((15, 15), np.uint8)
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel_close)
        
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Find the largest rectangular contour
        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            image_area = self.image.shape[0] * self.image.shape[1]
            
            # Filter by area (card should be at least 10% of image)
            if area > image_area * 0.1:
                # Check if contour is roughly rectangular
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                if len(approx) >= 4:  # At least 4 corners
                    valid_contours.append(contour)
        
        if not valid_contours:
            print("No valid rectangular contours found, using largest contour")
            largest_contour = max(contours, key=cv2.contourArea)
        else:
            largest_contour = max(valid_contours, key=cv2.contourArea)
        
        area = cv2.contourArea(largest_contour)
        image_area = self.image.shape[0] * self.image.shape[1]
        
        print(f"Contour area: {(area/image_area)*100:.1f}% of image")
        
        return largest_contour

    def crop_card_back(self):
        """Simple center crop for card backs"""
        h, w = self.image.shape[:2]
        
        # Define crop as percentage of image (center region)
        crop_percent_w = 0.4  # Take 40% of width
        crop_percent_h = 0.95  # Take 95% of height
        
        # Calculate crop dimensions
        crop_w = int(w * crop_percent_w)
        crop_h = int(h * crop_percent_h)
        
        # Calculate center position
        start_x = (w - crop_w) // 2
        start_y = (h - crop_h) // 2
        
        # Ensure we don't go out of bounds
        start_x = max(0, start_x)
        start_y = max(0, start_y)
        end_x = min(w, start_x + crop_w)
        end_y = min(h, start_y + crop_h)
        
        print(f"Center crop: x={start_x}, y={start_y}, width={end_x-start_x}, height={end_y-start_y}")
        
        # Crop the card
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
        
        # Update image to rotated version
        self.image = rotated_image
        
        # Find contour again on rotated image
        contour = self.find_card_contour()
        if contour is None:
            print("Could not find card contour after rotation")
            return None
        
        # Get bounding rectangle (now it should be axis-aligned)
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
    
    def __init__(self, card_image):
        self.image = card_image
        self.card_info = {}
    
    def extract_number_region(self):
        """Extract just the number region (bottom 10% of card, left side)"""
        h, w = self.image.shape[:2]
        number_region = self.image[int(h*0.9):h, 0:int(w*0.4)]
        return number_region
    
    def preprocess_for_number(self, region):
        """Preprocess image for card number OCR"""
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        
        # Downscale if too large
        h, w = gray.shape
        max_width = 1500
        if w > max_width:
            scale = max_width / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
        # Upscale for OCR
        scale = 2
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        # Binarize
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return otsu
    
    def find_card_number(self):
        """Extract card number from bottom-left region"""
        print("\n  Extracting card number...")
        number_region = self.extract_number_region()
        
        # Save region for debugging
        cv2.imwrite('debug_number_region.jpg', number_region)
        
        # Preprocess
        processed = self.preprocess_for_number(number_region)
        cv2.imwrite('debug_number_processed.jpg', processed)
        
        # Try OCR with PSM 6 (block of text) and PSM 11 (sparse text)
        for psm in [6, 11]:
            try:
                config = f'--psm {psm}'
                text = pytesseract.image_to_string(processed, lang='eng', config=config).strip()
                
                # Look for XXX/XXX pattern
                match = re.search(r'(\d{1,3})\s*[/\\|]\s*(\d{1,3})', text)
                if match:
                    number_text = f"{match.group(1)}/{match.group(2)}"
                    print(f"    ✓ Found: {number_text} (PSM {psm})")
                    return number_text
            except Exception as e:
                print(f"    OCR error with PSM {psm}: {e}")
                continue
        
        print("    ✗ Card number not found")
        return "Unknown"
    
    def read_card(self):
        """Extract card number and lookup name from database"""
        print("\nExtracting card information...")
        
        # Get card number via OCR
        self.card_info['number'] = self.find_card_number()
        
        # Lookup name from card database
        if self.card_info['number'] != "Unknown":
            card_name = get_card_name(self.card_info['number'])
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


def process_card(image_path, save_cropped=True, output_folder='Renamed_Cropped'):
    """Complete pipeline: crop card from photo, then extract info"""
    print("="*70)
    print("POKÉMON CARD PROCESSOR - CROP AND RENAME")
    print("="*70)
    print(f"\nProcessing: {image_path}\n")
    
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
    reader = PokemonCardReader(cropped_card)
    
    info = reader.read_card()
    reader.display_info()
    
    # Step 3: Save with proper naming
    if save_cropped and info:
        # Create output folder if it doesn't exist
        base_dir = os.path.dirname(image_path)
        output_dir = os.path.join(base_dir, output_folder)
        os.makedirs(output_dir, exist_ok=True)
        
        # Create filename: Name_Number_Set.ext
        name = info.get('name', 'Unknown')
        name = sanitize_filename(name)
        number = info.get('number', 'Unknown').replace('/', '-')
        set_code = extract_set_code(base_dir)
        ext = os.path.splitext(image_path)[1]
        
        base_filename = f"{name}_{number}_{set_code}{ext}"
        new_filename = get_unique_filename(output_dir, base_filename)
        output_path = os.path.join(output_dir, new_filename)
        
        cv2.imwrite(output_path, cropped_card)
        print(f"\n✓ Saved as: {new_filename}")
        print(f"✓ Location: {output_dir}")
    
    return info


def process_folder(folder_path, output_folder='Renamed_Cropped'):
    """Process all card images in a folder (handles front/back pairs)"""
    output_dir = os.path.join(folder_path, output_folder)
    os.makedirs(output_dir, exist_ok=True)
    
    set_code = extract_set_code(folder_path)
    print(f"Using set code: {set_code}")

    raw_folder = os.path.join(folder_path, 'raw')
    
    # Check if raw folder exists, otherwise use main folder
    if os.path.exists(raw_folder):
        search_path = raw_folder
        print(f"Found 'raw' folder, processing images from: {search_path}")
    else:
        search_path = folder_path
        print(f"No 'raw' folder found, processing images from: {search_path}")
        
    # Find all images
    extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = sorted([f for f in os.listdir(search_path) 
                   if any(f.lower().endswith(ext) for ext in extensions)])
    
    print(f"Found {len(image_files)} images to process\n")
    
    results = []
    i = 0
    
    while i < len(image_files):
        filename = image_files[i]
        
        print(f"\n{'='*70}")
        print(f"[{i+1}/{len(image_files)}] Processing {filename}...")
        print('='*70)
        
        input_path = os.path.join(search_path, filename)
        
        try:
            # Process the FRONT card
            info = process_card(input_path, save_cropped=False, output_folder=output_folder)
            
            if info and info.get('name') != 'Unknown':
                name = sanitize_filename(info.get('name', 'Unknown'))
                number = info.get('number', 'Unknown').replace('/', '-')
                ext = os.path.splitext(filename)[1]
                
                # Crop and save FRONT - check for duplicates RIGHT BEFORE saving
                cropper = CardCropper(input_path)
                if cropper.image is not None:
                    cropped_card = cropper.crop_card()
                    if cropped_card is not None:
                        base_front_filename = f"{name}_{number}_{set_code}_FR_FRONT{ext}"
                        # This will check the filesystem and find next available filename
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
                    
                    # Crop and save BACK - check for duplicates RIGHT BEFORE saving
                    back_cropper = CardCropper(back_input_path)
                    if back_cropper.image is not None:
                        back_cropped = back_cropper.crop_card_back()
                        if back_cropped is not None:
                            base_back_filename = f"{name}_{number}_{set_code}_FR_BACK{ext}"
                            # This will check the filesystem and find next available filename
                            back_new_filename = get_unique_filename(output_dir, base_back_filename)
                            back_path = os.path.join(output_dir, back_new_filename)
                            cv2.imwrite(back_path, back_cropped)
                            print(f"✓ Saved BACK as: {back_new_filename}")
                            
                            results.append({
                                'original': back_filename,
                                'new_name': back_new_filename,
                                'status': 'success'
                            })
                    
                    i += 2  # Skip both front and back
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
    
    # Print summary
    print("\n" + "="*70)
    print("PROCESSING SUMMARY")
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
        process_card(image_path, save_cropped=True)
    elif choice == "2":
        folder_path = input("\nEnter full path to folder: ").strip().strip('"')
        process_folder(folder_path)
    else:
        print("Invalid choice!")
    
    print("\n✅ Done!")