from PIL import Image
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

print_lock = Lock()

def rotate_image(img_path, img_file):
    """Rotate a single image by 180 degrees."""
    try:
        with Image.open(img_path) as img:
            rotated = img.rotate(180)
            rotated.save(img_path)
        
        with print_lock:
            print(f"✓ Rotated: {img_file}")
        return True
        
    except Exception as e:
        with print_lock:
            print(f"✗ Failed to rotate {img_file}: {str(e)}")
        return False

def rotate_images_in_folder(folder_path, max_workers=8):
    """Rotate all images in the specified folder by 180 degrees using multiple threads."""
    
    # Supported image formats
    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')
    
    # Check if folder exists
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return
    
    # Get all files in the folder
    files = os.listdir(folder_path)
    image_files = [f for f in files if f.lower().endswith(supported_formats)]
    
    if not image_files:
        print("No image files found in the folder.")
        return
    
    print(f"Found {len(image_files)} image(s). Starting rotation with {max_workers} threads...\n")
    
    # Process images in parallel
    success_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(rotate_image, os.path.join(folder_path, img_file), img_file): img_file
            for img_file in image_files
        }
        
        for future in as_completed(futures):
            if future.result():
                success_count += 1
    
    print(f"\nDone! Successfully processed {success_count}/{len(image_files)} image(s).")

if __name__ == "__main__":
    folder = input("Enter folder path: ").strip()
    rotate_images_in_folder(folder)