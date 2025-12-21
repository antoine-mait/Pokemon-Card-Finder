import csv
import asyncio
import aiohttp
from pathlib import Path
import re

# Semaphore to limit concurrent requests
MAX_CONCURRENT_REQUESTS = 10

def extract_series_from_set_id(set_id):
    """Extract series code from set_id"""
    # Special cases - sets that have different series than their prefix
    special_cases = {
        'cel25': 'swsh',  # Celebrations is part of Sword & Shield
        'cel25gg': 'swsh',  # Celebrations: Classic Collection
        'det1': 'sm',  # Detective Pikachu is part of Sun & Moon
        'sm7.5': 'sm',  # Dragon Majesty
        'sm115': 'sm',  # Hidden Fates
        'sm3.5': 'sm',  # Shining Legends
        'g1': 'xy',  # Generations is part of XY
        'dc1': 'xy',  # Double Crisis
        'dv1': 'bw',  # Dragon Vault
        'rc': 'bw',  # Radiant Collection
    }
    
    set_id_lower = set_id.lower()
    
    # Check special cases first
    if set_id_lower in special_cases:
        return special_cases[set_id_lower]
    
    # Common patterns:
    # sv03.5 -> sv
    # xy7 -> xy
    # swsh3 -> swsh
    # swshp -> swsh (promo sets use base series)
    # xyp -> xy (promo sets use base series)
    # ecard2 -> ecard
    # base1 -> base (for older sets)
    
    # Extract alphabetic prefix (remove trailing 'p' for promo sets)
    match = re.match(r'^([a-z]+?)p?(?:\d|$)', set_id_lower)
    if match:
        return match.group(1)
    
    # Fallback: just extract alphabetic prefix
    match = re.match(r'^([a-z]+)', set_id_lower)
    if match:
        return match.group(1)
    
    return set_id  # fallback to full set_id if no pattern matches

async def download_image(session, url, filepath, semaphore):
    """Download a single image with rate limiting"""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    return True
                else:
                    print(f"      ✗ Failed (HTTP {response.status}): {url}")
                    return False
        except Exception as e:
            print(f"      ✗ Error: {str(e)}")
            return False

async def download_set_images(set_folder: Path, semaphore):
    """Download all card images for a set by reading existing CSVs"""
    
    print(f"\nProcessing: {set_folder.name}")
    
    # Extract set_id from folder name (format: SetName_SetId)
    folder_parts = set_folder.name.split('_', 1)
    if len(folder_parts) != 2:
        print(f"  ⚠ Invalid folder name format (expected SetName_SetId)")
        return
    
    set_id = folder_parts[1]
    series = extract_series_from_set_id(set_id)
    print(f"  Set ID: {set_id}, Series: {series}")
    
    # Create IMG folder
    img_folder = set_folder / "IMG"
    img_folder.mkdir(exist_ok=True)
    
    # Find all CSV files (any language)
    csv_files = list(set_folder.glob("CardList_*.csv"))
    
    if not csv_files:
        print(f"  ⚠ No CSV files found in {set_folder.name}")
        return
    
    # Use the first CSV file (they should all have the same cards, just different names)
    csv_file = csv_files[0]
    print(f"  Reading cards from: {csv_file.name}")
    
    # Track unique cards (by ID) to avoid duplicate downloads
    cards_to_download = {}
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                card_id = row.get('id', '')
                local_id = row.get('localId', '')
                
                if not card_id:
                    continue
                
                # Extract card number from card_id (e.g., "swsh3-136" -> "136")
                # Card IDs typically follow pattern: {set_id}-{card_number}
                card_parts = card_id.split('-')
                if len(card_parts) >= 2:
                    card_number = card_parts[-1]  # Get the last part (card number)
                else:
                    card_number = card_id  # Fallback to full ID if no dash
                
                # Create image filename
                safe_local_id = local_id.replace('/', '-').replace('\\', '-')
                image_filename = f"{card_id}_{safe_local_id}.jpg"
                image_filepath = img_folder / image_filename
                
                # Only add to download list if image doesn't exist
                if not image_filepath.exists():
                    # Construct image URL from TCGdex API
                    # Format: https://assets.tcgdex.net/en/{series}/{set_id}/{card_number}/high.jpg
                    # For most sets, series and set_id are different (e.g., series='swsh', set_id='swsh3')
                    # But for promo sets, they're the same (e.g., series='swshp', set_id='swshp')
                    # So we only include set_id once in the path
                    image_url = f"https://assets.tcgdex.net/en/{series}/{set_id}/{card_number}/high.jpg"
                    
                    # Store card info for download
                    if card_id not in cards_to_download:
                        cards_to_download[card_id] = {
                            'filepath': image_filepath,
                            'url': image_url,
                            'local_id': local_id,
                            'card_number': card_number
                        }
    
    except Exception as e:
        print(f"  ✗ Error reading CSV: {str(e)}")
        return
    
    if not cards_to_download:
        print(f"  ✓ All images already downloaded ({len(list(img_folder.glob('*.jpg')))} images)")
        return
    
    print(f"  Found {len(cards_to_download)} images to download")
    
    # Download all images concurrently
    async with aiohttp.ClientSession() as session:
        download_tasks = []
        
        for card_id, card_info in cards_to_download.items():
            task = download_image(
                session, 
                card_info['url'], 
                card_info['filepath'], 
                semaphore
            )
            download_tasks.append((task, card_id, card_info['local_id']))
        
        # Execute all downloads
        results = await asyncio.gather(*[task for task, _, _ in download_tasks])
        
        # Count successes
        success_count = sum(1 for r in results if r)
        print(f"  ✓ Downloaded {success_count}/{len(download_tasks)} images")
        
        # Show failed downloads
        failed_cards = [
            (card_id, local_id) 
            for (_, card_id, local_id), success in zip(download_tasks, results) 
            if not success
        ]
        
        if failed_cards:
            print(f"  ⚠ Failed to download {len(failed_cards)} images:")
            for card_id, local_id in failed_cards[:5]:  # Show first 5
                print(f"    - {card_id} ({local_id})")
            if len(failed_cards) > 5:
                print(f"    ... and {len(failed_cards) - 5} more")

def display_sets_menu(set_folders):
    """Display available sets and get user selection"""
    print("\n" + "="*70)
    print("AVAILABLE POKÉMON CARD SETS")
    print("="*70)
    
    for idx, folder in enumerate(set_folders, 1):
        # Try to extract set name and ID
        folder_parts = folder.name.split('_', 1)
        if len(folder_parts) == 2:
            set_name = folder_parts[0].replace('_', ' ')
            set_id = folder_parts[1]
            
            # Check if IMG folder exists and count images
            img_folder = folder / "IMG"
            if img_folder.exists():
                img_count = len(list(img_folder.glob('*.jpg'))) + len(list(img_folder.glob('*.png'))) + len(list(img_folder.glob('*.webp')))
                status = f"✓ {img_count} images" if img_count > 0 else "⚠ empty"
            else:
                status = "⚠ no IMG folder"
            
            print(f"  {idx:3d}. {set_name} ({set_id}) - {status}")
        else:
            print(f"  {idx:3d}. {folder.name}")
    
    print(f"  {len(set_folders) + 1:3d}. Download ALL sets")
    print("="*70)

def get_user_choice(set_folders):
    """Get and validate user input"""
    while True:
        try:
            print("\nOptions:")
            print(f"  • Enter number (1-{len(set_folders)}) for specific set")
            print(f"  • Enter {len(set_folders) + 1} for ALL sets")
            print("  • Enter set name or code to search (e.g., 'celebrations' or 'cel25')")
            print("  • Enter 'q' to quit")
            
            choice = input(f"\nYour choice: ").strip()
            
            if choice.lower() == 'q':
                return None
            
            # Try as number first
            try:
                choice_num = int(choice)
                
                if 1 <= choice_num <= len(set_folders):
                    return [set_folders[choice_num - 1]]
                elif choice_num == len(set_folders) + 1:
                    return set_folders  # All sets
                else:
                    print(f"❌ Invalid number. Please enter 1-{len(set_folders) + 1}.")
                    continue
            
            except ValueError:
                # Not a number, try searching by name/code
                search_term = choice.lower()
                matches = []
                
                for folder in set_folders:
                    folder_lower = folder.name.lower()
                    # Check if search term is in folder name
                    if search_term in folder_lower:
                        matches.append(folder)
                
                if len(matches) == 0:
                    print(f"❌ No sets found matching '{choice}'")
                    continue
                elif len(matches) == 1:
                    print(f"✓ Found: {matches[0].name}")
                    confirm = input("Download this set? (y/n): ").strip().lower()
                    if confirm == 'y':
                        return matches
                    else:
                        continue
                else:
                    # Multiple matches - show submenu
                    print(f"\n🔍 Found {len(matches)} matching sets:")
                    for idx, folder in enumerate(matches, 1):
                        print(f"  {idx}. {folder.name}")
                    print(f"  {len(matches) + 1}. Download ALL matched sets")
                    
                    sub_choice = input(f"\nSelect (1-{len(matches) + 1}) or 'c' to cancel: ").strip()
                    
                    if sub_choice.lower() == 'c':
                        continue
                    
                    try:
                        sub_num = int(sub_choice)
                        if 1 <= sub_num <= len(matches):
                            return [matches[sub_num - 1]]
                        elif sub_num == len(matches) + 1:
                            return matches
                        else:
                            print(f"❌ Invalid choice")
                            continue
                    except ValueError:
                        print(f"❌ Invalid input")
                        continue
        
        except KeyboardInterrupt:
            print("\n\nOperation cancelled by user.")
            return None

async def main():
    """Main function to download images for selected sets"""
    
    print("="*70)
    print("POKÉMON CARD IMAGE DOWNLOADER")
    print("="*70)
    print("\nThis script reads existing CSV files and downloads card images")
    print("to an IMG folder within each set folder.\n")
    
    base_folder = Path("PokemonCardLists/Card_Sets")
    
    if not base_folder.exists():
        print(f"Error: '{base_folder}' folder not found!")
        print("Please run the CSV generator script first.")
        return
    
    # Find all set folders
    set_folders = sorted([f for f in base_folder.iterdir() if f.is_dir()])
    
    if not set_folders:
        print(f"Error: No set folders found in '{base_folder}'")
        return
    
    # Display menu and get user choice
    display_sets_menu(set_folders)
    selected_sets = get_user_choice(set_folders)
    
    if selected_sets is None:
        print("\nOperation cancelled by user.")
        return
    
    print(f"\n{'='*70}")
    print(f"DOWNLOADING {len(selected_sets)} SET(S)")
    print(f"{'='*70}")
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Process each selected set folder
    for idx, set_folder in enumerate(selected_sets, 1):
        print(f"\n[{idx}/{len(selected_sets)}] {set_folder.name}")
        await download_set_images(set_folder, semaphore)
    
    print("\n" + "="*70)
    print("✓ DOWNLOAD COMPLETED!")
    print("="*70)
    print(f"\nAll images saved in respective IMG folders:")
    print(f"  PokemonCardLists/Card_Sets/SetName_SetId/IMG/")

if __name__ == "__main__":
    asyncio.run(main())
    