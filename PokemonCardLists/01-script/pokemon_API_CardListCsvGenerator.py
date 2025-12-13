import csv
import asyncio
import aiohttp
from pathlib import Path

# Semaphore to limit concurrent requests
MAX_CONCURRENT_REQUESTS = 10

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
                    print(f"      ✗ Failed to download (HTTP {response.status})")
                    return False
        except Exception as e:
            print(f"      ✗ Error downloading image: {str(e)}")
            return False

async def download_set_images(set_folder: Path, semaphore):
    """Download all card images for a set by reading existing CSVs"""
    
    print(f"\nProcessing: {set_folder.name}")
    
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
                
                # Create image filename
                safe_local_id = local_id.replace('/', '-').replace('\\', '-')
                image_filename = f"{card_id}_{safe_local_id}.jpg"
                image_filepath = img_folder / image_filename
                
                # Only add to download list if image doesn't exist
                if not image_filepath.exists():
                    # Construct image URL from TCGdex API
                    # Format: https://assets.tcgdex.net/[language]/[series]/[set]/[cardId]
                    # We'll use the high resolution image
                    image_url = f"https://assets.tcgdex.net/en/swsh/base1/{card_id}/high.webp"
                    
                    # Store card info for download
                    if card_id not in cards_to_download:
                        cards_to_download[card_id] = {
                            'filepath': image_filepath,
                            'url': image_url,
                            'local_id': local_id
                        }
    
    except Exception as e:
        print(f"  ✗ Error reading CSV: {str(e)}")
        return
    
    if not cards_to_download:
        print(f"  ⊙ All images already downloaded ({len(list(img_folder.glob('*.jpg')))} images)")
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

async def main():
    """Main function to download images for all sets"""
    
    print("="*70)
    print("POKÉMON CARD IMAGE DOWNLOADER")
    print("="*70)
    print("\nThis script reads existing CSV files and downloads card images")
    print("to an IMG folder within each set folder.\n")
    
    # Get the script's directory first
    script_dir = Path(__file__).parent
    
    # Go up to the project root, then into PokemonCardLists/Card_Sets
    project_root = script_dir.parent.parent  # Go up from 01-script to PokemonCardLists, then to project root
    card_sets_folder = project_root / "PokemonCardLists" / "Card_Sets"
    
    print(f"Looking in: {card_sets_folder.absolute()}\n")
    
    if not card_sets_folder.exists():
        print(f"Error: '{card_sets_folder}' folder not found!")
        print("Please check your folder structure.")
        return
    
    # Get all folders inside Card_Sets
    all_items = list(card_sets_folder.iterdir())
    print(f"Found {len(all_items)} items in Card_Sets folder")
    
    # Find all set folders that contain CSV files
    set_folders = []
    for item in all_items:
        if item.is_dir():
            csv_files = list(item.glob("CardList_*.csv"))
            if csv_files:
                set_folders.append(item)
                print(f"  ✓ {item.name} - {len(csv_files)} CSV files")
            else:
                print(f"  ⊙ Skipping '{item.name}' (no CSV files)")
    
    if not set_folders:
        print(f"\nError: No set folders with CSV files found")
        return
    
    print(f"\n{'='*70}")
    print(f"Processing {len(set_folders)} set folders")
    print(f"{'='*70}\n")
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Process each set folder
    for idx, set_folder in enumerate(set_folders, 1):
        await download_set_images(set_folder, semaphore)
    
    print("\n" + "="*70)
    print("✓ DOWNLOAD COMPLETED!")
    print("="*70)
    print(f"\nAll images saved in respective IMG folders:")
    print(f"  PokemonCardLists/Card_Sets/[SetName]/IMG/")

if __name__ == "__main__":
    asyncio.run(main())