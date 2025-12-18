import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
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
from urllib.parse import quote
import random

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY_FILE = os.path.join(SCRIPT_DIR, "set_strategy_cache.json")
strategy_lock = threading.Lock()
ALLSETS_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "PokemonCardLists", "all_sets_full.json")

def load_ptcgo_codes():
    """Load ptcgoCode mapping from all_set_full.json"""
    if not os.path.exists(ALLSETS_FILE):
        print(f"Warning: all_set_full.json not found at {ALLSETS_FILE}")
        return {}
    
    try:
        with open(ALLSETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        ptcgo_map = {}
        for set_data in data.get('data', []):
            set_id = set_data.get('id', '').lower()
            ptcgo_code = set_data.get('ptcgoCode', '')
            if set_id and ptcgo_code:
                ptcgo_map[set_id] = ptcgo_code
        
        return ptcgo_map
    except Exception as e:
        print(f"Error loading ptcgoCode mapping: {e}")
        return {}

ptcgo_codes = load_ptcgo_codes()

def get_ptcgo_code_for_set(folder_name):
    """Get ptcgoCode for a set based on folder name"""
    # Extract parts from folder name
    parts = folder_name.lower().split('_')
    folder_lower = folder_name.lower()
    
    # Try direct match on each part
    for part in parts:
        if part in ptcgo_codes:
            return ptcgo_codes[part]
    
    # Try matching the full folder name against set IDs
    for set_id, code in ptcgo_codes.items():
        if set_id in folder_lower or folder_lower.replace('-', '').replace('_', '') in set_id.replace('-', ''):
            return code
    
    # Try matching set name (e.g., "sandstorm" from "EX-Sandstorm_EX2")
    set_name = get_set_name(folder_name).lower().replace('-', '').replace('_', '')
    for set_id, code in ptcgo_codes.items():
        set_id_clean = set_id.replace('-', '').replace('_', '')
        if set_name in set_id_clean or set_id_clean in set_name:
            return code
    
    return None

def execute_ptcgo_code_strategy(driver, card_info, thread_id):
    """Execute ptcgoCode strategy"""
    ptcgo_code = card_info.get('ptcgo_code')
    
    if not ptcgo_code or ptcgo_code == card_info['set_abbreviation']:
        return None
        
    url_ptcgo = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        ptcgo_code,
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']]
    )
    
    prices, product_name = try_scrape_url(driver, url_ptcgo, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "ptcgo_code")
        strategy_cache[cache_key] = "ptcgo_code"
        card_info_ptcgo = card_info.copy()
        card_info_ptcgo['used_ptcgo_code'] = True
        return {
            'card_info': card_info_ptcgo,
            'product_name': product_name,
            'url': url_ptcgo,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'ptcgo_code'
        }
    return None
def execute_v2_ptcgo_code_strategy(driver, card_info, thread_id):
    """Execute V2 + ptcgo code strategy"""
    ptcgo_code = card_info.get('ptcgo_code')
    
    if not ptcgo_code:
        return None
        
    url_ptcgo_v2 = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        ptcgo_code,
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']],
        variant="V2"
    )
    
    prices, product_name = try_scrape_url(driver, url_ptcgo_v2, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "v2_ptcgo_code")
        strategy_cache[cache_key] = "v2_ptcgo_code"
        card_info_ptcgo_v2 = card_info.copy()
        card_info_ptcgo_v2['used_ptcgo_code'] = True
        card_info_ptcgo_v2['variant_used'] = 'V2'
        return {
            'card_info': card_info_ptcgo_v2,
            'product_name': product_name,
            'url': url_ptcgo_v2,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'v2_ptcgo_code'
        }
    return None

def load_strategy_cache():
    if not os.path.exists(STRATEGY_FILE):
        return {}
    with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

strategy_cache = load_strategy_cache()

def save_strategy_cache(set_folder, strategy):
    with strategy_lock:
        data = load_strategy_cache()
        if data.get(set_folder) == strategy:
            return  # already known
        data[set_folder] = strategy
        with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

def extract_30d_price(prices: dict):
    """Extract 'Prix moyen 30 jours' as float"""
    value = prices.get("Prix moyen 30 jours")
    if not value:
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def build_card_uid(card_info):
    """Stable unique identifier for a card"""
    return f"{card_info['set_folder']}|{card_info['language']}|{card_info['card_number']}"

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

def get_set_id_from_folder(folder_name):
    """Extract set ID from folder name (e.g., 'PAR' from 'Paradox-Rift_PAR')"""
    parts = folder_name.rsplit('_', 1)
    if len(parts) >= 2:
        return parts[1].upper()
    return None

def build_cardmarket_url(set_name, card_name, set_abbr, card_number, language_code, variant=None):
    """Build Cardmarket URL from components"""
    base_url = "https://www.cardmarket.com/fr/Pokemon/Products/Singles"
    
    if variant:
        card_slug = f"{card_name}-{variant}-{set_abbr}{card_number}"
    else:
        card_slug = f"{card_name}-{set_abbr}{card_number}"
    url = f"{base_url}/{set_name}/{card_slug}?language={language_code}"
    return url

def build_search_url(set_name, card_number):
    """Build CardMarket search URL for a specific card within a set"""
    base_url = "https://www.cardmarket.com/fr/Pokemon/Products/Singles"
    # Search for the card number within the set
    search_url = f"{base_url}/{set_name}?searchString={card_number}&idRarity=0&perSite=30"
    return search_url

def search_card_in_set(driver, set_name, card_number, card_name, thread_id, language_code):
    """
    Search for a card within a set using CardMarket's search input
    Returns the product URL if found, None otherwise
    """
    # Build the base search URL for the set
    base_url = f"https://www.cardmarket.com/fr/Pokemon/Products/Singles/{set_name}"
    search_url = f"{base_url}?idRarity=0&perSite=30"
    
    try:
        print(f"    [{thread_id}] 🔍 Opening search page: {search_url}")
        driver.get(search_url)
        time.sleep(random.uniform(5, 12))
        
        # Find the search input field
        try:
            search_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "searchString"))
            )
            
            # Clear and input the card name
            search_input.clear()
            search_input.send_keys(card_name.replace('-', ' '))
            
            print(f"    [{thread_id}] 🔍 Searching for: {card_name.replace('-', ' ')}")
            
            # Submit the search (press Enter)
            from selenium.webdriver.common.keys import Keys
            search_input.send_keys(Keys.RETURN)
            
            # Wait for results to load
            time.sleep(3)
            
        except Exception as e:
            print(f"    [{thread_id}] ⚠️ Could not find or use search input: {e}")
            return None
        
        # Parse the results page
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Look for product links
        product_links = soup.find_all('a', href=True)
        
        for link in product_links:
            href = link['href']
            link_text = link.get_text(strip=True)
            
            # Check if this link contains our card number pattern
            # Looking for patterns like "DP 17", "DP17", "(DP 17)", etc.
            card_num_clean = card_number.upper().strip()
            
            # Try to match the card number in various formats
            if any([
                f"{card_num_clean}" in href.upper(),
                f"({card_num_clean})" in link_text.upper(),
                f"{card_num_clean.replace('-', ' ')}" in link_text.upper(),
                f"{card_num_clean.replace('-', '')}" in link_text.upper()
            ]):
                # Verify it's a singles product page
                if '/Singles/' in href and set_name in href:
                    # Build full URL
                    if href.startswith('/'):
                        full_url = f"https://www.cardmarket.com{href}"
                    else:
                        full_url = href
                    
                    # Add language parameter if not present
                    if '?language=' not in full_url:
                        full_url = f"{full_url}?language={language_code}"
                    
                    print(f"    [{thread_id}] ✓ Found match: {link_text}")
                    print(f"    [{thread_id}] 🔗 URL: {full_url}")
                    return full_url
        
        print(f"    [{thread_id}] ✗ No matching card found in search results")
        return None
        
    except Exception as e:
        print(f"    [{thread_id}] ❌ Error during search: {e}")
        return None
    
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
            # Load existing collection history
            collection_history = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                        if isinstance(old_data, dict):
                            collection_history = old_data.get('collection_history', [])
                except:
                    pass
            
            set_strategies = {}
            total_value = 0.0
            seen_cards = set()

            for result in all_results:
                if not result.get('success'):
                    continue

                card_info = result.get('card_info', {})
                set_name = card_info.get('set_folder')
                strategy = result.get('strategy', 'unknown')

                # ---- strategy stats ----
                if set_name:
                    set_strategies.setdefault(set_name, {})
                    set_strategies[set_name].setdefault(strategy, 0)
                    set_strategies[set_name][strategy] += 1

                # ---- collection total value (unique cards only) ----
                uid = build_card_uid(card_info)
                if uid in seen_cards:
                    continue
                seen_cards.add(uid)

                price_30d = extract_30d_price(result.get('prices', {}))
                if price_30d is not None:
                    total_value += price_30d
            
            # Update collection history
            today = datetime.now().strftime('%Y-%m-%d')
            if not collection_history or collection_history[-1]['date'] != today:
                collection_history.append({
                    'date': today,
                    'total_value': round(total_value, 2)
                })

            output_data = {
                'Collection_Total_Value': round(total_value, 2),
                'collection_history': collection_history,
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'set_strategies': set_strategies,
                'results': all_results
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            print(f"    ⚠️ Error saving results: {e}")
            return False
        
def load_existing_results(output_file):
    """Load existing results from JSON file and extract set strategies"""
    if not os.path.exists(output_file):
        return {}, {}, {}
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both old and new format
        if isinstance(data, list):
            results_list = data
            set_strategies = {}
        else:
            results_list = data.get('results', [])
            set_strategies = data.get('set_strategies', {})
        
        results_dict = {}
        today = datetime.now().strftime('%Y-%m-%d')
        
        for item in results_list:
            if not item.get('success'):
                continue
            
            card_info = item.get('card_info', {})
            timestamp = item.get('scrape_timestamp', '')
            
            if timestamp.startswith(today):
                key = f"{card_info.get('set_folder')}_{card_info.get('filename')}"
                results_dict[key] = item
        
        price_history = {}

        for item in results_list:
            if not item.get('success'):
                continue
                
            card_info = item.get('card_info', {})
            uid = build_card_uid(card_info)

            if 'price_history' in item:
                price_history[uid] = item['price_history']

        return results_dict, set_strategies, price_history

    except Exception as e:
        print(f"Warning: Could not load existing results: {e}")
        return {}, {}, {}

def get_best_strategy_for_set(set_folder, set_strategies):
    """Get the most successful strategy for a given set"""
    if set_folder not in set_strategies:
        return None
    
    strategies = set_strategies[set_folder]
    if not strategies:
        return None
    
    # Return the strategy with the most successes
    best_strategy = max(strategies.items(), key=lambda x: x[1])
    return best_strategy[0]

def is_card_scraped_today(card_info, existing_results):
    """Check if a card has already been scraped today"""
    key = f"{card_info['set_folder']}_{card_info['filename']}"
    return key in existing_results

def initialize_driver():
    """Initialize a Chrome driver with thread-safe locking"""
    with driver_init_lock:
        time.sleep(0.5)
        
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--lang=fr-FR')
        
        try:
            driver = uc.Chrome(options=options, version_main=None)
            return driver
        except Exception as e:
            print(f"Error initializing driver: {e}")
            time.sleep(2)
            driver = uc.Chrome(options=options, version_main=None)
            return driver

def try_scrape_url(driver, url, thread_id):
    """Attempt to scrape a single URL and return prices if found"""
    try:
        print(f"  [{thread_id}] Loading: {url}")
        driver.get(url)
        time.sleep(random.uniform(5, 12))
        
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
        # print(f"    [{thread_id}] 🧾 Extracted prices:", prices)
        return prices, product_name
    except Exception as e:
        print(f"    [{thread_id}] Error loading URL: {e}")
        return {}, "Unknown"

def try_strategy_first(driver, card_info, english_names, strategy, thread_id):
    """Try a specific strategy first based on previous successes"""
    print(f"    [{thread_id}] 🎯 Trying preferred strategy: {strategy}")
    
    strategy_map = {
        'direct_url': lambda: execute_direct_url_strategy(driver, card_info, thread_id),
        'ptcgo_code': lambda: execute_ptcgo_code_strategy(driver, card_info, thread_id),
        'english_name': lambda: execute_english_name_strategy(driver, card_info, english_names, thread_id),
        'set_id': lambda: execute_set_id_strategy(driver, card_info, thread_id),
        'extended_abbr': lambda: execute_extended_abbr_strategy(driver, card_info, thread_id),
        'v2_variant': lambda: execute_v2_variant_strategy(driver, card_info, thread_id),
        'v2_ptcgo_code': lambda: execute_v2_ptcgo_code_strategy(driver, card_info, thread_id),
        'v2_set_id': lambda: execute_v2_set_id_strategy(driver, card_info, thread_id),
        'search': lambda: execute_search_strategy(driver, card_info,english_names, thread_id)
    }
    
    if strategy in strategy_map:
        return strategy_map[strategy]()
    
    return None

def get_cache_key(card_info):
    return card_info["set_folder"]

def scrape_single_card(driver, url, card_info, english_names, strategy_cache, price_history):
    """Scrape price data for a single card with multiple fallback strategies"""
    thread_id = threading.current_thread().name
    tried_strategies = set()
    
    # Try cached strategy FIRST (per set)
    cache_key = get_cache_key(card_info)
    preferred = strategy_cache.get(cache_key)

    if preferred:
        print(f"    [{thread_id}] 🎯 Using cached strategy: {preferred}")
        result = try_strategy_first(
            driver, card_info, english_names, preferred, thread_id
        )
        if result:
            price_30d = extract_30d_price(result.get('prices', {}))
            today = datetime.now().strftime('%Y-%m-%d')

            uid = build_card_uid(card_info)
            history = price_history.get(uid, [])

            if price_30d is not None and (not history or history[-1]['date'] != today):
                history.append({
                    "date": today,
                    "price": price_30d
                })

            price_history[uid] = history
            result['price_history'] = history

            return result

    
    # Try all strategies in order
    strategies = [
        ('direct_url', lambda: execute_direct_url_strategy(driver, card_info, thread_id)),
        ('ptcgo_code', lambda: execute_ptcgo_code_strategy(driver, card_info, thread_id)),
        ('english_name', lambda: execute_english_name_strategy(driver, card_info, english_names, thread_id)),
        ('set_id', lambda: execute_set_id_strategy(driver, card_info, thread_id)),
        ('extended_abbr', lambda: execute_extended_abbr_strategy(driver, card_info, thread_id)),
        ('v2_variant', lambda: execute_v2_variant_strategy(driver, card_info, thread_id)),
        ('v2_ptcgo_code', lambda: execute_v2_ptcgo_code_strategy(driver, card_info, thread_id)),
        ('v2_set_id', lambda: execute_v2_set_id_strategy(driver, card_info, thread_id)),
        ('search', lambda: execute_search_strategy(driver, card_info,english_names, thread_id))
    ]
    
    for strategy_name, strategy_func in strategies:
        if strategy_name in tried_strategies:
            continue
        
            
        print(f"    [{thread_id}] Strategy: {strategy_name}")
        result = strategy_func()
        
        if result:
            print(f"    [{thread_id}] ✅ Success with {strategy_name}!")
            return result
    
    # All strategies failed
    print(f"    [{thread_id}] ✗ No prices found after trying all strategies")
    return {
        'card_info': card_info,
        'url': url,
        'prices': {},
        'success': False
    }
    
def execute_direct_url_strategy(driver, card_info, thread_id):
    """Execute direct URL strategy"""
    url = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        card_info['set_abbreviation'],
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']]
    )
    prices, product_name = try_scrape_url(driver, url, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "direct_url")
        strategy_cache[cache_key] = "direct_url"
        return {
            'card_info': card_info,
            'product_name': product_name,
            'url': url,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'direct_url'
        }
    return None

def execute_english_name_strategy(driver, card_info, english_names, thread_id):
    """Execute English name strategy"""
    if not english_names or card_info['language'] == 'EN':
        return None
        
    english_name = english_names.get(card_info['card_number'])
    if not english_name:
        return None
        
    english_sanitized = sanitize_card_name(english_name)
    original_sanitized = sanitize_card_name(card_info['card_name'])
    
    if english_sanitized == original_sanitized:
        return None
        
    url_en = build_cardmarket_url(
        card_info['set_name'],
        english_sanitized,
        card_info['set_abbreviation'],
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']]
    )
    prices, product_name = try_scrape_url(driver, url_en, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "english_name")
        strategy_cache[cache_key] = "english_name"
        card_info_en = card_info.copy()
        card_info_en['card_name_sanitized'] = english_sanitized
        card_info_en['tried_english_name'] = True
        card_info_en['original_name'] = card_info['card_name']
        card_info_en['english_name'] = english_name
        return {
            'card_info': card_info_en,
            'product_name': product_name,
            'url': url_en,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'english_name'
        }
    return None

def execute_set_id_strategy(driver, card_info, thread_id):
    """Execute set ID strategy"""
    set_id = card_info.get('set_id')
    if not set_id or set_id == card_info['set_abbreviation']:
        return None
        
    url_set_id = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        set_id,
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']]
    )
    prices, product_name = try_scrape_url(driver, url_set_id, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "set_id")
        strategy_cache[cache_key] = "set_id"
        card_info_set_id = card_info.copy()
        card_info_set_id['used_set_id'] = True
        return {
            'card_info': card_info_set_id,
            'product_name': product_name,
            'url': url_set_id,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'set_id'
        }
    return None

def execute_extended_abbr_strategy(driver, card_info, thread_id):
    """Execute extended abbreviation strategy"""
    extended_abbr = get_extended_abbreviation(card_info['set_name'], card_info['set_abbreviation'])
    if not extended_abbr or extended_abbr == card_info['set_abbreviation']:
        return None
        
    url_extended = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        extended_abbr,
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']]
    )
    prices, product_name = try_scrape_url(driver, url_extended, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "extended_abbr")
        strategy_cache[cache_key] = "extended_abbr"
        card_info_extended = card_info.copy()
        card_info_extended['abbreviation_extended'] = True
        return {
            'card_info': card_info_extended,
            'product_name': product_name,
            'url': url_extended,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'extended_abbr'
        }
    return None

def execute_v2_variant_strategy(driver, card_info, thread_id):
    """Execute V2 variant strategy"""
    url_v2 = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        card_info['set_abbreviation'],
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']],
        variant="V2"
    )
    prices, product_name = try_scrape_url(driver, url_v2, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "v2_variant")
        strategy_cache[cache_key] = "v2_variant"
        card_info_v2 = card_info.copy()
        card_info_v2['variant_used'] = 'V2'
        return {
            'card_info': card_info_v2,
            'product_name': product_name,
            'url': url_v2,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'v2_variant'
        }
    return None

def execute_v2_set_id_strategy(driver, card_info, thread_id):
    """Execute V2 + set ID strategy"""
    set_id = card_info.get('set_id')
    if not set_id or set_id == card_info['set_abbreviation']:
        return None
        
    url_set_id_v2 = build_cardmarket_url(
        card_info['set_name'],
        card_info['card_name_sanitized'],
        set_id,
        card_info['card_number'],
        LANGUAGE_MAP[card_info['language']],
        variant="V2"
    )
    prices, product_name = try_scrape_url(driver, url_set_id_v2, thread_id)
    if prices:
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "v2_set_id")
        strategy_cache[cache_key] = "v2_set_id"
        card_info_set_id_v2 = card_info.copy()
        card_info_set_id_v2['used_set_id'] = True
        card_info_set_id_v2['variant_used'] = 'V2'
        return {
            'card_info': card_info_set_id_v2,
            'product_name': product_name,
            'url': url_set_id_v2,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'v2_set_id'
        }
    return None

def _search_with_name(driver, card_info, thread_id, search_name):
    """Internal helper to search CardMarket using a given card name"""
    try:
        base_url = "https://www.cardmarket.com/fr/Pokemon/Products/Singles"
        driver.get(base_url)
        time.sleep(random.uniform(5, 12))

        # Expansion selection
        expansion_select = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "idExpansion"))
        )

        set_first_word = card_info['set_name'].replace('-', ' ')
        expansion_select.click()
        time.sleep(0.5)
        expansion_select.send_keys(set_first_word)
        time.sleep(1)
        expansion_select.send_keys(Keys.RETURN)
        time.sleep(2)

        # Search input
        search_form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "SearchResultForm"))
        )

        search_input = search_form.find_element(By.NAME, "searchString")
        search_input.clear()
        search_input.send_keys(search_name)
        search_input.send_keys(Keys.RETURN)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        product_links = soup.find_all('a', href=True)
        card_num_clean = card_info['card_number'].upper().strip()

        for link in product_links:
            href = link['href']
            text = link.get_text(strip=True).upper()

            if card_num_clean in href.upper() or card_num_clean in text:
                if '/Singles/' in href:
                    full_url = f"https://www.cardmarket.com{href}" if href.startswith('/') else href
                    full_url = re.sub(
                        r'\?language=\d+',
                        f'?language={LANGUAGE_MAP[card_info["language"]]}',
                        full_url
                    )

                    prices, product_name = try_scrape_url(driver, full_url, thread_id)
                    if prices:
                        return full_url, prices, product_name

    except Exception as e:
        print(f"    [{thread_id}] ❌ Search error: {e}")

    return None

def execute_search_strategy(driver, card_info, english_names, thread_id):
    """Execute search-based strategy with English fallback"""

    # 1️⃣ Normal search (localized name)
    localized_name = card_info['card_name_sanitized'].replace('-', ' ')
    result = _search_with_name(driver, card_info, thread_id, localized_name)

    if result:
        url, prices, product_name = result
        cache_key = get_cache_key(card_info)
        save_strategy_cache(cache_key, "search")
        strategy_cache[cache_key] = "search"

        card_info_found = card_info.copy()
        card_info_found['found_via_search'] = True

        return {
            'card_info': card_info_found,
            'product_name': product_name,
            'url': url,
            'prices': prices,
            'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'success': True,
            'strategy': 'search'
        }

    # 2️⃣ LAST RESORT: English name search
    english_name = english_names.get(card_info['card_number']) if english_names else None
    if english_name:
        english_search = sanitize_card_name(english_name).replace('-', ' ')
        print(f"    [{thread_id}] 🌍 Retrying search with EN name: {english_search}")

        result = _search_with_name(driver, card_info, thread_id, english_search)

        if result:
            url, prices, product_name = result
            cache_key = get_cache_key(card_info)
            save_strategy_cache(cache_key, "search")
            strategy_cache[cache_key] = "search"

            card_info_found = card_info.copy()
            card_info_found['found_via_search_english'] = True
            card_info_found['english_name'] = english_name

            return {
                'card_info': card_info_found,
                'product_name': product_name,
                'url': url,
                'prices': prices,
                'scrape_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'success': True,
                'strategy': 'search'
            }

    print(f"    [{thread_id}] ✗ Search failed (including English fallback)")
    return None
      
def worker_thread(thread_id, task_queue, results_list, output_file, save_interval, price_history):
    """Worker thread that processes cards from the queue"""
    print(f"[Thread-{thread_id}] Starting worker thread")
    
    driver = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            driver = initialize_driver()
            strategy_cache = load_strategy_cache()
            print(f"[Thread-{thread_id}] Browser initialized successfully")
            break
        except Exception as e:
            print(f"[Thread-{thread_id}] Failed to initialize browser (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"[Thread-{thread_id}] Could not initialize browser after {max_retries} attempts. Exiting thread.")
                return
    
    cards_processed = 0
    
    try:
        while True:
            try:
                task = task_queue.get(timeout=5)
                
                if task is None:
                    break
                
                url, card_info, english_names= task
                
                result = scrape_single_card(driver, url, card_info, english_names, strategy_cache, price_history)
                results_list.append(result)
                cards_processed += 1
                
                if cards_processed % save_interval == 0:
                    print(f"    [Thread-{thread_id}] 💾 Auto-saving progress...")
                    save_results(results_list, output_file)
                
                task_queue.task_done()
                time.sleep(1)
                
            except queue.Empty:
                continue
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
    """Scan folder structure and scrape all cards using multiple threads"""
    strategy_cache = load_strategy_cache()

    if output_file is None:
        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cardmarket_all_prices.json')
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"Error: Folder not found: {base_folder}")
        return
    
    print("Loading existing results...")
    existing_results, set_strategies, price_history = load_existing_results(output_file)
    print(f"Found {len(existing_results)} cards already scraped today")
    
    all_results = []
    skipped_count = 0
    save_interval = 5
    task_queue = queue.Queue()
    set_abbreviations = {}
    
    print("\nScanning cards...")
    total_cards = 0
    
    for set_folder in base_path.iterdir():
        if not set_folder.is_dir():
            continue
        
        set_name = get_set_name(set_folder.name)
        set_id = get_set_id_from_folder(set_folder.name)
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
                
                if is_card_scraped_today(card_info_check, existing_results):
                    skipped_count += 1
                    key = f"{card_info_check['set_folder']}_{card_info_check['filename']}"
                    existing_result = existing_results[key].copy()
                    
                    # Preserve price history from price_history dict
                    uid = build_card_uid(existing_result['card_info'])
                    if uid in price_history and 'price_history' not in existing_result:
                        existing_result['price_history'] = price_history[uid]
                    
                    all_results.append(existing_result)
                    continue
                
                sanitized_card_name = sanitize_card_name(card_name)
                current_abbr = set_abbreviations.get(set_folder.name, set_abbr)
                url = build_cardmarket_url(set_name, sanitized_card_name, current_abbr, card_number, lang_code)
                
                card_info = {
                    'set_folder': set_folder.name,
                    'set_name': set_name,
                    'set_abbreviation': current_abbr,
                    'set_id': set_id,
                    'ptcgo_code': get_ptcgo_code_for_set(set_folder.name),
                    'card_name': card_name,
                    'card_name_sanitized': sanitized_card_name,
                    'card_number': card_number,
                    'language': lang,
                    'filename': card_file.name
                }
                
                task_queue.put((url, card_info, english_names))
                total_cards += 1
    
    print(f"Found {total_cards} cards to scrape")
    print(f"Skipped {skipped_count} cards (already scraped today)")
    print(f"\nStarting {num_threads} worker threads...\n")
    
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(
            target=worker_thread,
            args=(i+1, task_queue, all_results, output_file, save_interval, price_history),
            name=f"Thread-{i+1}"
        )
        thread.start()
        threads.append(thread)
        time.sleep(1)
    
    task_queue.join()
    
    for _ in range(num_threads):
        task_queue.put(None)
    
    for thread in threads:
        thread.join()
    
    print(f"\n{'='*60}")
    print(f"Scraping complete!")
    print(f"{'='*60}")
    
    print(f"💾 Saving final results...")
    if save_results(all_results, output_file):
        print(f"✓ Results saved to: {output_file}")
    else:
        print(f"✗ Failed to save results")
    
    successful = sum(1 for r in all_results if r.get('success', False))
    failed = sum(1 for r in all_results if not r.get('success', False))
    print(f"\nSummary:")
    print(f"  ✓ Successful: {successful}")
    print(f"  ⭐ Skipped (already scraped today): {skipped_count}")
    print(f"  ✗ Failed: {failed}")
    print(f"  📊 Total in file: {len(all_results)}")

if __name__ == "__main__":
    base_folder = r"D:\05-Vente_Carte"
    num_threads = 1
    
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