import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import json
import time
import os
import re
from pathlib import Path
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue

# Language mapping
LANGUAGE_MAP = {
    'EN': 1,
    'FR': 2,
    'DE': 3
}

# Thread-safe lock for saving results
save_lock = threading.Lock()
# Thread-safe lock for driver initialization
driver_init_lock = threading.Lock()

def sanitize_card_name(card_name):
    """
    Sanitize card name by removing special characters and accents
    Spaces are replaced with hyphens
    """
    nfd = unicodedata.normalize('NFD', card_name)
    card_name = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    card_name = re.sub(r'[^\w\s-]', '', card_name)
    card_name = card_name.replace(' ', '-')
    card_name = re.sub(r'-+', '-', card_name)
    card_name = card_name.strip('-')
    return card_name

def parse_card_filename(filename):
    """Parse card filename to extract card name and number"""
    name_without_ext = os.path.splitext(filename)[0]
    parts = name_without_ext.split('_')
    if len(parts) >= 2:
        card_name = parts[0]
        card_number = parts[1]
        return card_name, card_number
    return None, None

def get_set_abbreviation(set_name):
    """Extract set abbreviation from set name"""
    words = set_name.replace('_', '-').split('-')
    abbreviation = ''.join(word[0].upper() for word in words if word)
    return abbreviation

def get_extended_abbreviation(set_name, current_abbr):
    """Get extended abbreviation by adding one more character"""
    words = set_name.replace('_', '-').split('-')
    if len(words) > 0:
        last_word = words[-1]
        current_len = len(current_abbr)
        chars_from_last_word = len([c for c in current_abbr if c in last_word.upper()])
        if len(last_word) > chars_from_last_word:
            return current_abbr + last_word[chars_from_last_word].upper()
    return current_abbr

def get_set_name(folder_name):
    """Extract set name from folder name"""
    parts = folder_name.rsplit('_', 1)
    if len(parts) >= 1:
        return parts[0].replace('_', '-')
    return folder_name

def build_cardmarket_url(set_name, card_name, set_abbr, card_number, language_code):
    """Build Cardmarket URL from components"""
    base_url = "https://www.cardmarket.com/fr/Pokemon/Products/Singles"
    card_slug = f"{card_name}-{set_abbr}{card_number}"
    url = f"{base_url}/{set_name}/{card_slug}?language={language_code}"
    return url

def load_english_card_names(set_folder_path):
    """Load English card names from CSV file"""
    csv_folder = Path(r"D:\02-Travaille\04-Coding\03-Projects\05-Rename_Pokemon_Photo\PokemonCardLists\Card_Sets")
    folder_name = set_folder_path.name
    parts = folder_name.split('_')
    if len(parts) >= 2:
        set_code = parts[-1].lower()
    else:
        return {}
    
    set_folders = list(csv_folder.glob(f"*{set_code}*"))
    if not set_folders:
        set_code_base = ''.join(c for c in set_code if not c.isdigit())
        set_folders = list(csv_folder.glob(f"*{set_code_base}*"))
    
    if not set_folders:
        return {}
    
    csv_set_folder = set_folders[0]
    csv_files = list(csv_set_folder.glob("CardList_*_en.CSV")) or list(csv_set_folder.glob("CardList_*_en.csv"))
    
    if not csv_files:
        return {}
    
    csv_file = csv_files[0]
    card_names = {}
    try:
        import csv
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                local_id = row.get('localId', '').strip()
                name = row.get('name', '').strip()
                if local_id and name:
                    card_names[local_id] = name
        return card_names
    except Exception as e:
        return {}

def save_results(all_results, output_file):
    """Save results to JSON file (thread-safe)"""
    with save_lock:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"    ⚠️  Error saving results: {e}")
            return False

def load_existing_results(output_file):
    """Load existing results from JSON file"""
    if not os.path.exists(output_file):
        return {}
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results_dict = {}
        today = datetime.now().strftime('%Y-%m-%d')
        
        for item in data:
            if not item.get('success'):
                continue
            
            card_info = item.get('card_info', {})
            timestamp = item.get('scrape_timestamp', '')
            
            if timestamp.startswith(today):
                key = f"{card_info.get('set_folder')}_{card_info.get('filename')}"
                results_dict[key] = item
        
        return results_dict
    except Exception as e:
        print(f"Warning: Could not load existing results: {e}")
        return {}

def is_card_scraped_today(card_info, existing_results):
    """Check if a card has already been scraped today"""
    key = f"{card_info['set_folder']}_{card_info['filename']}"
    return key in existing_results

def initialize_driver():
    """Initialize a Chrome driver with thread-safe locking"""
    with driver_init_lock:
        # Add a small delay to prevent race conditions
        time.sleep(0.5)
        
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--lang=fr-FR')
        # Comment out headless if you want to see the browsers
        # options.add_argument('--headless=new')
        
        try:
            driver = uc.Chrome(options=options, version_main=None)
            return driver
        except Exception as e:
            print(f"Error initializing driver: {e}")
            # Wait a bit longer and try again
            time.sleep(2)
            driver = uc.Chrome(options=options, version_main=None)
            return driver

def scrape_single_card(driver, url, card_info, retry_with_extended_abbr=True):
    """Scrape price data for a single card"""
    try:
        thread_id = threading.current_thread().name
        print(f"  [{thread_id}] Loading: {url}")
        driver.get(url)
        
        time.sleep(3)
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "labeled"))
            )
        except:
            pass
        
        time.sleep(1)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        price_rows = soup.find_all(class_='labeled row mx-auto g-0')
        prices = {}
        
        for row in price_rows:
            dts = row.find_all('dt')
            dds = row.find_all('dd')
            
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True).replace('€', '').strip()
                prices[label] = value
        
        product_name_elem = soup.find('h1')
        product_name = product_name_elem.get_text(strip=True) if product_name_elem else "Unknown"
        
        if not prices and retry_with_extended_abbr:
            print(f"    [{thread_id}] ⚠️  No prices found, trying with extended abbreviation...")
            
            extended_abbr = get_extended_abbreviation(card_info['set_name'], card_info['set_abbreviation'])
            
            if extended_abbr and extended_abbr != card_info['set_abbreviation']:
                print(f"    [{thread_id}] Trying {card_info['set_abbreviation']} → {extended_abbr}")
                
                new_url = build_cardmarket_url(
                    card_info['set_name'],
                    card_info['card_name_sanitized'],
                    extended_abbr,
                    card_info['card_number'],
                    LANGUAGE_MAP[card_info['language']]
                )
                
                card_info_extended = card_info.copy()
                card_info_extended['set_abbreviation'] = extended_abbr
                card_info_extended['abbreviation_extended'] = True
                
                return scrape_single_card(driver, new_url, card_info_extended, retry_with_extended_abbr=False)
        
        result = {
            'card_info': card_info,
            'product_name': product_name,
            'url': url,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': len(prices) > 0
        }
        
        if prices:
            print(f"    [{thread_id}] ✓ Extracted {len(prices)} price fields")
        else:
            print(f"    [{thread_id}] ✗ No prices found")
        
        return result
        
    except Exception as e:
        thread_id = threading.current_thread().name
        print(f"    [{thread_id}] ✗ Error: {e}")
        return {
            'card_info': card_info,
            'url': url,
            'error': str(e),
            'success': False
        }

def worker_thread(thread_id, task_queue, results_list, output_file, save_interval):
    """Worker thread that processes cards from the queue"""
    print(f"[Thread-{thread_id}] Starting worker thread")
    
    # Initialize browser for this thread with locking
    driver = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            driver = initialize_driver()
            print(f"[Thread-{thread_id}] Browser initialized successfully")
            break
        except Exception as e:
            print(f"[Thread-{thread_id}] Failed to initialize browser (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))  # Exponential backoff
            else:
                print(f"[Thread-{thread_id}] Could not initialize browser after {max_retries} attempts. Exiting thread.")
                return
    
    cards_processed = 0
    
    try:
        while True:
            try:
                # Get task from queue (timeout after 5 seconds)
                task = task_queue.get(timeout=5)
                
                if task is None:  # Poison pill to stop the thread
                    break
                
                url, card_info, english_names = task
                
                # Scrape the card
                result = scrape_single_card(driver, url, card_info)
                results_list.append(result)
                cards_processed += 1
                
                # Try with English name if failed and not EN language
                if not result['success'] and card_info['language'] != 'EN' and english_names:
                    english_name = english_names.get(card_info['card_number'])
                    
                    if english_name:
                        original_sanitized = sanitize_card_name(card_info['card_name'])
                        english_sanitized = sanitize_card_name(english_name)
                        
                        if english_sanitized != original_sanitized:
                            print(f"    [Thread-{thread_id}] 🔄 Trying with English name: {english_name}")
                            
                            url_en = build_cardmarket_url(
                                card_info['set_name'],
                                english_sanitized,
                                card_info['set_abbreviation'],
                                card_info['card_number'],
                                LANGUAGE_MAP[card_info['language']]
                            )
                            
                            card_info_en = card_info.copy()
                            card_info_en['card_name_sanitized'] = english_sanitized
                            card_info_en['tried_english_name'] = True
                            card_info_en['original_name'] = card_info['card_name']
                            card_info_en['english_name'] = english_name
                            
                            result_en = scrape_single_card(driver, url_en, card_info_en, retry_with_extended_abbr=True)
                            
                            if result_en['success']:
                                print(f"    [Thread-{thread_id}] ✓ Success with English name!")
                                results_list[-1] = result_en
                
                # Periodic save
                if cards_processed % save_interval == 0:
                    print(f"    [Thread-{thread_id}] 💾 Auto-saving progress...")
                    save_results(results_list, output_file)
                
                task_queue.task_done()
                time.sleep(1)  # Small delay between requests
                
            except queue.Empty:
                continue  # No tasks available, keep waiting
            except Exception as e:
                print(f"[Thread-{thread_id}] Error processing task: {e}")
                task_queue.task_done()
    
    finally:
        print(f"[Thread-{thread_id}] Closing browser...")
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"[Thread-{thread_id}] Browser cleanup warning: {e}")

def scan_and_scrape(base_folder, output_file=None, num_threads=4):
    """
    Scan folder structure and scrape all cards using multiple threads
    
    Args:
        base_folder: Base folder containing card sets
        output_file: Output JSON file path
        num_threads: Number of concurrent threads (default: 4)
    """
    if output_file is None:
        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cardmarket_all_prices.json')
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"Error: Folder not found: {base_folder}")
        return
    
    print("Loading existing results...")
    existing_results = load_existing_results(output_file)
    print(f"Found {len(existing_results)} cards already scraped today")
    
    # Thread-safe results list
    all_results = []
    skipped_count = 0
    save_interval = 5
    
    # Task queue for distributing work to threads
    task_queue = queue.Queue()
    
    # Dictionary to remember abbreviations
    set_abbreviations = {}
    
    # First pass: collect all tasks
    print("\nScanning cards...")
    total_cards = 0
    
    for set_folder in base_path.iterdir():
        if not set_folder.is_dir():
            continue
        
        set_name = get_set_name(set_folder.name)
        set_abbr = set_abbreviations.get(set_folder.name, get_set_abbreviation(set_name))
        
        if not set_abbr:
            continue
        
        renamed_cropped_path = set_folder / "Renamed_Cropped"
        if not renamed_cropped_path.exists():
            continue
        
        english_names = load_english_card_names(set_folder)
        
        for lang in ['EN', 'FR', 'DE']:
            lang_folder = renamed_cropped_path / lang
            
            if not lang_folder.exists():
                continue
            
            lang_code = LANGUAGE_MAP[lang]
            card_files = [f for f in lang_folder.iterdir() 
                         if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] 
                         and '_FRONT' in f.name]
            
            for card_file in card_files:
                card_name, card_number = parse_card_filename(card_file.name)
                
                if not card_name or not card_number:
                    continue
                
                card_info_check = {
                    'set_folder': set_folder.name,
                    'filename': card_file.name
                }
                
                # Check if already scraped today
                if is_card_scraped_today(card_info_check, existing_results):
                    skipped_count += 1
                    key = f"{card_info_check['set_folder']}_{card_info_check['filename']}"
                    all_results.append(existing_results[key])
                    continue
                
                sanitized_card_name = sanitize_card_name(card_name)
                current_abbr = set_abbreviations.get(set_folder.name, set_abbr)
                url = build_cardmarket_url(set_name, sanitized_card_name, current_abbr, card_number, lang_code)
                
                card_info = {
                    'set_folder': set_folder.name,
                    'set_name': set_name,
                    'set_abbreviation': current_abbr,
                    'card_name': card_name,
                    'card_name_sanitized': sanitized_card_name,
                    'card_number': card_number,
                    'language': lang,
                    'filename': card_file.name
                }
                
                # Add task to queue
                task_queue.put((url, card_info, english_names))
                total_cards += 1
    
    print(f"Found {total_cards} cards to scrape")
    print(f"Skipped {skipped_count} cards (already scraped today)")
    print(f"\nStarting {num_threads} worker threads...\n")
    
    # Start worker threads
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(
            target=worker_thread,
            args=(i+1, task_queue, all_results, output_file, save_interval),
            name=f"Thread-{i+1}"
        )
        thread.start()
        threads.append(thread)
        # Stagger thread starts to prevent driver initialization conflicts
        time.sleep(1)
    
    # Wait for all tasks to complete
    task_queue.join()
    
    # Stop worker threads
    for _ in range(num_threads):
        task_queue.put(None)  # Poison pill
    
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    
    # Final save
    print(f"\n{'='*60}")
    print(f"Scraping complete!")
    print(f"{'='*60}")
    
    print(f"💾 Saving final results...")
    if save_results(all_results, output_file):
        print(f"✓ Results saved to: {output_file}")
    else:
        print(f"✗ Failed to save results")
    
    # Print summary
    successful = sum(1 for r in all_results if r.get('success', False))
    failed = sum(1 for r in all_results if not r.get('success', False))
    print(f"\nSummary:")
    print(f"  ✓ Successful: {successful}")
    print(f"  ⭐ Skipped (already scraped today): {skipped_count}")
    print(f"  ✗ Failed: {failed}")
    print(f"  📊 Total in file: {len(all_results)}")

# Main execution
if __name__ == "__main__":
    base_folder = r"D:\05-Vente_Carte"
    num_threads = 4  # Adjust this based on your system (3-4 is safer for undetected_chromedriver)
    
    print("="*60)
    print("Cardmarket Multithreaded Price Scraper")
    print("="*60)
    print(f"Base folder: {base_folder}")
    print(f"Number of threads: {num_threads}")
    print()
    
    scan_and_scrape(base_folder, num_threads=num_threads)
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60)
    
    import sys
    import warnings
    warnings.filterwarnings('ignore')
    sys.stderr = open(os.devnull, 'w')