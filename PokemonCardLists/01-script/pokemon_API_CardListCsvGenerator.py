import csv
import asyncio
import os
from pathlib import Path
from tcgdexsdk import TCGdex, Language

# Define languages to export
LANGUAGES = {
    'en': Language.EN,
    'de': Language.DE,
    'fr': Language.FR,
    'ja': Language.JA
}

# Semaphore to limit concurrent requests (avoid overwhelming the API)
MAX_CONCURRENT_REQUESTS = 10

async def export_set_to_csv(set_id: str, set_name: str, language_code: str, language_enum, semaphore):
    """Export a single set in a specific language to CSV"""
    
    async with semaphore:
        # Initialize SDK with specific language
        tcgdex = TCGdex(language_enum)
        
        try:
            # Create folder structure: PokemonCardLists/SetName_SetId/
            base_folder = Path("PokemonCardLists")
            set_folder = base_folder / f"{set_name}_{set_id}".replace('/', '_').replace('\\', '_')
            set_folder.mkdir(parents=True, exist_ok=True)
            
            # Create filename inside the set folder
            filename = set_folder / f"CardList_{set_id}_{language_code}.csv"
            
            # Check if file already exists
            if filename.exists():
                print(f"  ⊙ Skipped {filename.name} (already exists)")
                return
            
            # Fetch the set details with all cards
            card_set = await tcgdex.set.get(set_id)
            
            if not card_set or not card_set.cards:
                print(f"  ✗ No cards found for set {set_id} in {language_code}")
                return
            
            # Define CSV headers
            headers = [
                'id', 'localId', 'name', 'hp', 'types', 'evolveFrom',
                'stage', 'rarity', 'illustrator', 'variants',
                'set_name', 'set_series', 'set_cardCount'
            ]
            
            # Write to CSV
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                
                # Write each card
                for card in card_set.cards:
                    # Fetch full card details
                    full_card = await tcgdex.card.get(card.id)
                    
                    # Handle variants - check if it's iterable or has attributes
                    variants_str = ''
                    if hasattr(full_card, 'variants') and full_card.variants:
                        try:
                            # Try to iterate if it's a list
                            variants_str = ', '.join([v.name for v in full_card.variants])
                        except TypeError:
                            # If not iterable, try to get attributes
                            variant_obj = full_card.variants
                            variant_parts = []
                            if hasattr(variant_obj, 'normal') and variant_obj.normal:
                                variant_parts.append('normal')
                            if hasattr(variant_obj, 'reverse') and variant_obj.reverse:
                                variant_parts.append('reverse')
                            if hasattr(variant_obj, 'holo') and variant_obj.holo:
                                variant_parts.append('holo')
                            if hasattr(variant_obj, 'firstEdition') and variant_obj.firstEdition:
                                variant_parts.append('1st edition')
                            if hasattr(variant_obj, 'wStamp') and variant_obj.wStamp:
                                variant_parts.append('wStamp')
                            variants_str = ', '.join(variant_parts)
                    
                    row = {
                        'id': full_card.id,
                        'localId': full_card.localId,
                        'name': full_card.name,
                        'hp': full_card.hp if hasattr(full_card, 'hp') else '',
                        'types': ', '.join(full_card.types) if hasattr(full_card, 'types') and full_card.types else '',
                        'evolveFrom': full_card.evolveFrom if hasattr(full_card, 'evolveFrom') else '',
                        'stage': full_card.stage if hasattr(full_card, 'stage') else '',
                        'rarity': full_card.rarity if hasattr(full_card, 'rarity') else '',
                        'illustrator': full_card.illustrator if hasattr(full_card, 'illustrator') else '',
                        'variants': variants_str,
                        'set_name': card_set.name,
                        'set_series': card_set.serie.name if hasattr(card_set, 'serie') else '',
                        'set_cardCount': card_set.cardCount.total if hasattr(card_set, 'cardCount') else ''
                    }
                    
                    writer.writerow(row)
            
            print(f"  ✓ Created {filename.name} with {len(card_set.cards)} cards")
            
        except Exception as e:
            print(f"  ✗ Error exporting {set_id} in {language_code}: {str(e)}")

async def process_set(card_set, idx, total, semaphore):
    """Process a single set in all languages concurrently"""
    print(f"[{idx}/{total}] Processing set: {card_set.name} ({card_set.id})")
    
    # Create tasks for all languages for this set
    tasks = []
    for lang_code, lang_enum in LANGUAGES.items():
        task = export_set_to_csv(card_set.id, card_set.name, lang_code, lang_enum, semaphore)
        tasks.append(task)
    
    # Run all language exports for this set concurrently
    await asyncio.gather(*tasks)
    print()  # Empty line after set completion

async def main():
    """Main function to export all sets in all languages"""
    
    print("Fetching all Pokémon card sets...")
    
    # Initialize SDK to get list of sets
    tcgdex = TCGdex(Language.EN)
    
    try:
        # Get all sets
        sets = await tcgdex.set.list()
        
        print(f"Found {len(sets)} sets. Starting export...\n")
        
        # Create main folder
        base_folder = Path("PokemonCardLists")
        base_folder.mkdir(exist_ok=True)
        print(f"Created main folder: {base_folder}\n")
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        # Process sets sequentially for clean console output
        for idx, card_set in enumerate(sets, 1):
            await process_set(card_set, idx, len(sets), semaphore)
        
        print(f"✓ Export completed! All files saved in '{base_folder}' folder")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())