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

# Language mapping
LANGUAGE_MAP = {
    'EN': 1,
    'FR': 2,
    'DE': 3
}

def sanitize_card_name(card_name):
    """
    Sanitize card name by removing special characters and accents
    Spaces are replaced with hyphens
    Example: "Unown [A]" -> "Unown-A"
    Example: "Pokémon Center" -> "Pokemon-Center"
    """
    # Remove accents by decomposing unicode and filtering
    nfd = unicodedata.normalize('NFD', card_name)
    card_name = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    
    # Remove all non-alphanumeric characters except spaces and hyphens
    card_name = re.sub(r'[^\w\s-]', '', card_name)
    
    # Replace spaces with hyphens
    card_name = card_name.replace(' ', '-')
    
    # Remove consecutive hyphens
    card_name = re.sub(r'-+', '-', card_name)
    
    # Remove leading/trailing hyphens
    card_name = card_name.strip('-')
    
    return card_name

def parse_card_filename(filename):
    """
    Parse card filename to extract card name and number
    Example: Lugia_9_NEO1_EN_FRONT.jpg -> (Lugia, 9)
    """
    # Remove extension
    name_without_ext = os.path.splitext(filename)[0]
    
    # Split by underscore
    parts = name_without_ext.split('_')
    
    if len(parts) >= 2:
        card_name = parts[0]
        card_number = parts[1]
        return card_name, card_number
    
    return None, None

def get_set_abbreviation(set_name):
    """
    Extract set abbreviation from set name
    Example: Neo-Genesis -> NG
    Takes first letter of each word
    """
    # Remove any remaining underscores and split by hyphen
    words = set_name.replace('_', '-').split('-')
    
    # Take first letter of each word
    abbreviation = ''.join(word[0].upper() for word in words if word)
    
    return abbreviation

def get_extended_abbreviation(set_name, current_abbr):
    """
    Get extended abbreviation by adding one more character
    Example: ND (Neo-Discovery) -> NDI (adds 'i' from 'Discovery')
    """
    words = set_name.replace('_', '-').split('-')
    
    # If we only have the first letters, try to add second letter from last word
    if len(words) > 0:
        last_word = words[-1]
        # Find which position we're at in the last word
        current_len = len(current_abbr)
        chars_from_last_word = len([c for c in current_abbr if c in last_word.upper()])
        
        # Try to add the next character from the last word
        if len(last_word) > chars_from_last_word:
            return current_abbr + last_word[chars_from_last_word].upper()
    
    return current_abbr

def get_set_name(folder_name):
    """
    Extract set name from folder name
    Example: Neo_Genesis_NEO1 -> Neo-Genesis
    """
    # Remove the code part (everything after the last underscore)
    parts = folder_name.rsplit('_', 1)
    if len(parts) >= 1:
        # Replace underscores with hyphens
        return parts[0].replace('_', '-')
    
    return folder_name

def build_cardmarket_url(set_name, card_name, set_abbr, card_number, language_code):
    """
    Build Cardmarket URL from components
    """
    base_url = "https://www.cardmarket.com/fr/Pokemon/Products/Singles"
    
    # Format: /Set-Name/Card-Name-ABBRNUM?language=X
    card_slug = f"{card_name}-{set_abbr}{card_number}"
    
    url = f"{base_url}/{set_name}/{card_slug}?language={language_code}"
    
    return url

def load_english_card_names(set_folder_path):
    """
    Load English card names from CSV file
    Returns dict mapping card number to English name
    """
    # Try to find the CSV file
    csv_folder = Path(r"D:\02-Travaille\04-Coding\03-Projects\05-Rename_Pokemon_Photo\PokemonCardLists\Card_Sets")
    
    # Extract set identifier from folder name (e.g., Neo_Genesis_NEO1 -> neo1)
    folder_name = set_folder_path.name
    parts = folder_name.split('_')
    if len(parts) >= 2:
        set_code = parts[-1].lower()  # Get NEO1 -> neo1
    else:
        return {}
    
    # Look for matching folder
    set_folders = list(csv_folder.glob(f"*{set_code}*"))
    if not set_folders:
        # Try without the number (e.g., neo1 -> neo)
        set_code_base = ''.join(c for c in set_code if not c.isdigit())
        set_folders = list(csv_folder.glob(f"*{set_code_base}*"))
    
    if not set_folders:
        print(f"    ⚠ No CSV folder found for {folder_name}")
        return {}
    
    csv_set_folder = set_folders[0]
    
    # Find the English CSV file
    csv_files = list(csv_set_folder.glob("CardList_*_en.CSV")) or list(csv_set_folder.glob("CardList_*_en.csv"))
    
    if not csv_files:
        print(f"    ⚠ No English CSV found in {csv_set_folder.name}")
        return {}
    
    csv_file = csv_files[0]
    print(f"    📋 Loading English names from: {csv_file.name}")
    
    # Parse CSV
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
        
        print(f"    ✓ Loaded {len(card_names)} English card names")
        return card_names
    except Exception as e:
        print(f"    ⚠ Error reading CSV: {e}")
        return {}

def save_results(all_results, output_file):
    """
    Save results to JSON file
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"    ⚠ Error saving results: {e}")
        return False

def load_existing_results(output_file):
    """
    Load existing results from JSON file
    Returns dict with card keys mapped to their data
    """
    if not os.path.exists(output_file):
        return {}
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Create a lookup dictionary using unique card identifiers
        results_dict = {}
        today = datetime.now().strftime('%Y-%m-%d')
        
        for item in data:
            if not item.get('success'):
                continue
            
            card_info = item.get('card_info', {})
            timestamp = item.get('scrape_timestamp', '')
            
            # Check if scraped today
            if timestamp.startswith(today):
                # Create unique key: set_folder + filename
                key = f"{card_info.get('set_folder')}_{card_info.get('filename')}"
                results_dict[key] = item
        
        return results_dict
    except Exception as e:
        print(f"Warning: Could not load existing results: {e}")
        return {}

def is_card_scraped_today(card_info, existing_results):
    """
    Check if a card has already been scraped today
    """
    key = f"{card_info['set_folder']}_{card_info['filename']}"
    return key in existing_results

def prompt_user_for_abbreviation(set_name, card_name, card_number, tried_abbrs):
    """
    Prompt user to manually enter the correct abbreviation
    """
    print(f"\n{'!'*60}")
    print(f"❌ Could not find prices for: {card_name} #{card_number}")
    print(f"   Set: {set_name}")
    print(f"   Tried: {', '.join(tried_abbrs)}")
    print(f"{'!'*60}")
    print(f"\nPlease provide the correct abbreviation for this set,")
    print(f"or press Enter to skip this set entirely.")
    print(f"Example: If the URL uses 'NDO' instead of 'ND', enter: NDO")
    
    user_input = input(f"\nCorrect abbreviation for {set_name} (or Enter to skip): ").strip().upper()
    
    return user_input if user_input else None

def scrape_single_card(driver, url, card_info, retry_with_extended_abbr=True):
    """
    Scrape price data for a single card
    If no prices found and retry_with_extended_abbr is True, will try with extended abbreviation
    """
    try:
        print(f"  Loading: {url}")
        driver.get(url)
        
        # Wait for Cloudflare and page load
        time.sleep(3)
        
        # Wait for content
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "labeled"))
            )
        except:
            print("    Warning: Timeout waiting for elements")
        
        time.sleep(1)
        
        # Parse page
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find price rows
        price_rows = soup.find_all(class_='labeled row mx-auto g-0')
        
        prices = {}
        
        # Extract dt/dd pairs
        for row in price_rows:
            dts = row.find_all('dt')
            dds = row.find_all('dd')
            
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True).replace('⬩', '').strip()
                prices[label] = value
        
        # Get product name
        product_name_elem = soup.find('h1')
        product_name = product_name_elem.get_text(strip=True) if product_name_elem else "Unknown"
        
        # If no prices found and retry is enabled, try with extended abbreviation
        if not prices and retry_with_extended_abbr:
            print(f"    ⚠ No prices found, trying with extended abbreviation...")
            
            # Get extended abbreviation (add one more character)
            extended_abbr = get_extended_abbreviation(card_info['set_name'], card_info['set_abbreviation'])
            
            if extended_abbr and extended_abbr != card_info['set_abbreviation']:
                print(f"    Trying {card_info['set_abbreviation']} → {extended_abbr}")
                
                # Build new URL with extended abbreviation
                new_url = build_cardmarket_url(
                    card_info['set_name'],
                    card_info['card_name_sanitized'],
                    extended_abbr,
                    card_info['card_number'],
                    LANGUAGE_MAP[card_info['language']]
                )
                
                # Update card_info with extended abbreviation
                card_info_extended = card_info.copy()
                card_info_extended['set_abbreviation'] = extended_abbr
                card_info_extended['abbreviation_extended'] = True
                
                # Recursive call with retry disabled to prevent infinite loop
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
            print(f"    ✓ Extracted {len(prices)} price fields")
        else:
            print(f"    ✗ No prices found")
        
        return result
        
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return {
            'card_info': card_info,
            'url': url,
            'error': str(e),
            'success': False
        }

def scan_and_scrape(base_folder, output_file='cardmarket_all_prices.json'):
    """
    Scan folder structure and scrape all cards
    """
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"Error: Folder not found: {base_folder}")
        return
    
    # Load existing results to check what's already scraped today
    print("Loading existing results...")
    existing_results = load_existing_results(output_file)
    print(f"Found {len(existing_results)} cards already scraped today")
    
    all_results = []
    skipped_count = 0
    cards_processed = 0
    save_interval = 5  # Save every 5 cards
    
    # Dictionary to remember which abbreviation worked for each set
    set_abbreviations = {}
    
    # Initialize browser once for all scraping
    print("\nInitializing browser...")
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=fr-FR')
    
    driver = uc.Chrome(options=options, version_main=None)
    
    try:
        # Iterate through set folders
        for set_folder in base_path.iterdir():
            if not set_folder.is_dir():
                continue
            
            print(f"\n{'='*60}")
            print(f"Processing Set: {set_folder.name}")
            print(f"{'='*60}")
            
            # Get set info
            set_name = get_set_name(set_folder.name)
            
            # Check if we already know the correct abbreviation for this set
            if set_folder.name in set_abbreviations:
                set_abbr = set_abbreviations[set_folder.name]
                print(f"  Set Name: {set_name}")
                print(f"  Set Abbreviation: {set_abbr} (remembered from previous cards)")
            else:
                set_abbr = get_set_abbreviation(set_name)
                print(f"  Set Name: {set_name}")
                print(f"  Set Abbreviation: {set_abbr} (initial)")
            
            if not set_abbr:
                print(f"  ⚠ Could not extract abbreviation from {set_name}, skipping...")
                continue
            
            # Check for Renamed_Cropped folder
            renamed_cropped_path = set_folder / "Renamed_Cropped"
            if not renamed_cropped_path.exists():
                print(f"  ⚠ Renamed_Cropped folder not found, skipping...")
                continue
            
            # Load English card names from CSV
            english_names = load_english_card_names(set_folder)
            
            # Process each language folder (DE, EN, FR)
            for lang in ['EN', 'FR', 'DE']:
                lang_folder = renamed_cropped_path / lang
                
                if not lang_folder.exists():
                    print(f"  ⚠ {lang} folder not found, skipping...")
                    continue
                
                print(f"\n  Language: {lang}")
                lang_code = LANGUAGE_MAP[lang]
                
                # Get all card files (only FRONT images)
                card_files = [f for f in lang_folder.iterdir() 
                             if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] 
                             and '_FRONT' in f.name]
                
                print(f"    Found {len(card_files)} cards")
                
                # Process each card
                for card_file in card_files:
                    card_name, card_number = parse_card_filename(card_file.name)
                    
                    if not card_name or not card_number:
                        print(f"    ⚠ Could not parse: {card_file.name}")
                        continue
                    
                    # Sanitize card name for URL
                    sanitized_card_name = sanitize_card_name(card_name)
                    
                    # Create card_info for checking
                    card_info_check = {
                        'set_folder': set_folder.name,
                        'filename': card_file.name
                    }
                    
                    # Check if already scraped today
                    if is_card_scraped_today(card_info_check, existing_results):
                        print(f"    ⏭ Skipping {card_file.name} (already scraped today)")
                        skipped_count += 1
                        # Add existing result to current results
                        key = f"{card_info_check['set_folder']}_{card_info_check['filename']}"
                        all_results.append(existing_results[key])
                        continue
                    
                    # Use the current set_abbr (which might have been updated)
                    current_abbr = set_abbreviations.get(set_folder.name, set_abbr)
                    
                    # Build URL
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
                    
                    # Scrape the card
                    result = scrape_single_card(driver, url, card_info)
                    all_results.append(result)
                    cards_processed += 1
                    
                    # Save periodically
                    if cards_processed % save_interval == 0:
                        print(f"    💾 Auto-saving progress... ({cards_processed} cards processed)")
                        save_results(all_results, output_file)
                    
                    # If successful and abbreviation was extended, remember it for this set
                    if result['success'] and result.get('card_info', {}).get('abbreviation_extended'):
                        new_abbr = result['card_info']['set_abbreviation']
                        set_abbreviations[set_folder.name] = new_abbr
                        print(f"    ✓ Remembering abbreviation '{new_abbr}' for remaining cards in this set")
                    
                    # If still no success, try with English name (for non-EN folders)
                    elif not result['success'] and lang != 'EN' and english_names:
                        english_name = english_names.get(card_number)
                        
                        if english_name:
                            # Sanitize original card name to compare
                            original_sanitized = sanitize_card_name(card_name)
                            english_sanitized = sanitize_card_name(english_name)
                            
                            # Only try if English name is different
                            if english_sanitized != original_sanitized:
                                print(f"    🔄 Trying with English name: {english_name} (instead of {card_name})")
                                
                                url_en = build_cardmarket_url(set_name, english_sanitized, current_abbr, card_number, lang_code)
                                
                                card_info_en = card_info.copy()
                                card_info_en['card_name_sanitized'] = english_sanitized
                                card_info_en['tried_english_name'] = True
                                card_info_en['original_name'] = card_name
                                card_info_en['english_name'] = english_name
                                
                                result_en = scrape_single_card(driver, url_en, card_info_en, retry_with_extended_abbr=True)
                                
                                if result_en['success']:
                                    print(f"    ✓ Success with English name!")
                                    all_results[-1] = result_en  # Replace the failed result
                                    result = result_en  # Update result for next checks
                            else:
                                print(f"    ℹ English name is same as local name: {english_name}")
                        else:
                            print(f"    ⚠ No English name found for card #{card_number} in CSV")
                    
                    # If still no success after trying English name, prompt user
                    if not result['success']:
                        tried_abbrs = [set_abbr]
                        extended_abbr = get_extended_abbreviation(set_name, set_abbr)
                        if extended_abbr != set_abbr:
                            tried_abbrs.append(extended_abbr)
                        
                        user_abbr = prompt_user_for_abbreviation(set_name, card_name, card_number, tried_abbrs)
                        
                        if user_abbr:
                            # Save the user-provided abbreviation
                            set_abbreviations[set_folder.name] = user_abbr
                            print(f"\n✓ Using '{user_abbr}' for all remaining cards in {set_name}")
                            
                            # Retry with user-provided abbreviation
                            url = build_cardmarket_url(set_name, sanitized_card_name, user_abbr, card_number, lang_code)
                            card_info['set_abbreviation'] = user_abbr
                            card_info['user_provided_abbreviation'] = True
                            
                            result = scrape_single_card(driver, url, card_info, retry_with_extended_abbr=False)
                            all_results[-1] = result  # Replace the failed result
                            
                            if result['success']:
                                print(f"    ✓ Success with user-provided abbreviation!")
                                
                                # Save after successful user abbreviation
                                save_results(all_results, output_file)
                        else:
                            print(f"\n⏭ Skipping remaining cards in {set_name}")
                            break  # Skip the rest of this set
                    
                    # Small delay between requests
                    time.sleep(2)
        
        # Save all results (final save)
        print(f"\n{'='*60}")
        print(f"Scraping complete!")
        print(f"{'='*60}")
        
        # Merge with existing results (keep all data)
        if existing_results:
            # Add any existing results that weren't updated today
            for key, value in existing_results.items():
                # Check if this card is not in our new results
                if not any(r.get('card_info', {}).get('set_folder') == value['card_info']['set_folder'] 
                          and r.get('card_info', {}).get('filename') == value['card_info']['filename'] 
                          for r in all_results):
                    all_results.append(value)
        
        print(f"💾 Saving final results...")
        if save_results(all_results, output_file):
            print(f"✓ Results saved to: {output_file}")
        else:
            print(f"✗ Failed to save results")
        
        # Print summary
        successful = sum(1 for r in all_results if r.get('success', False))
        # Count only newly processed cards as failed
        failed = sum(1 for r in all_results if not r.get('success', False))        
        print(f"\nSummary:")
        print(f"  ✓ Successful: {successful}")
        print(f"  ⏭ Skipped (already scraped today): {skipped_count}")
        print(f"  ✗ Failed: {failed}")
        print(f"  📊 Total in file: {len(all_results)}")
        
    finally:
        print("\nClosing browser...")
        try:
            driver.quit()
            del driver  # Explicitly delete to prevent double cleanup
        except Exception as e:
            print(f"Note: Browser cleanup warning (can be ignored): {e}")

# Main execution
if __name__ == "__main__":
    base_folder = r"D:\05-Vente_Carte"
    
    print("="*60)
    print("Cardmarket Batch Price Scraper")
    print("="*60)
    print(f"Base folder: {base_folder}")
    print()
    
    scan_and_scrape(base_folder)
    
    print("\n" + "="*60)
    print("Done!")
    print("="*60)
    
    # Suppress garbage collector errors from undetected_chromedriver
    import sys
    import warnings
    warnings.filterwarnings('ignore')
    # Redirect stderr to suppress the final cleanup error
    sys.stderr = open(os.devnull, 'w')