import requests
import json
import csv
from datetime import datetime
import time
from dotenv import load_dotenv
import os
from pathlib import Path
import shutil

# Load environment variables from .env file
load_dotenv()

class PokemonTCGAPI:
    def __init__(self, api_key):
        """
        Initialize Pokemon TCG API client.
        
        Get your API key from: https://dev.pokemontcg.io/
        Includes CardMarket prices in Euros!
        """
        self.api_key = api_key
        self.base_url = "https://api.pokemontcg.io/v2"
        self.headers = {"X-Api-Key": api_key}
        
    def search_card(self, card_name, set_name=None, max_retries=3):
        """
        Search for a card by name.
        
        Args:
            card_name: Name of the card
            set_name: Optional set name to narrow search
            max_retries: Number of retries on timeout
        
        Returns:
            List of matching cards
        """
        url = f"{self.base_url}/cards"
        
        # Build search query - use wildcards for better matching
        query_parts = [f'name:{card_name}*']
        if set_name:
            query_parts.append(f'set.name:{set_name}*')
        
        params = {
            "q": " ".join(query_parts),
            "orderBy": "-set.releaseDate"  # Most recent first
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  Timeout, retrying in {wait_time} seconds... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"Error: API timed out after {max_retries} attempts")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Error searching card: {e}")
                if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 404:
                    print("Tip: Make sure your API key is valid and the card name is correct")
                return None
        
        return None
    
    def get_card_by_id(self, card_id):
        """
        Get detailed card information by ID.
        
        Args:
            card_id: Pokemon TCG API card ID
        
        Returns:
            Card details including CardMarket prices
        """
        url = f"{self.base_url}/cards/{card_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get('data')
        except requests.exceptions.RequestException as e:
            print(f"Error getting card: {e}")
            return None
    
    def display_card_price(self, card_data):
        """Display formatted price information for a card."""
        if not card_data:
            print("No card data available")
            return
        
        print(f"\n{'='*70}")
        print(f"Card: {card_data.get('name', 'N/A')}")
        print(f"Set: {card_data.get('set', {}).get('name', 'N/A')} "
              f"({card_data.get('set', {}).get('series', 'N/A')})")
        print(f"Number: {card_data.get('number', 'N/A')}/{card_data.get('set', {}).get('printedTotal', 'N/A')}")
        print(f"Rarity: {card_data.get('rarity', 'N/A')}")
        print(f"Card ID: {card_data.get('id', 'N/A')}")
        print(f"{'='*70}")
        
        # CardMarket prices (in Euros)
        cardmarket = card_data.get('cardmarket', {})
        prices = cardmarket.get('prices', {})
        
        if prices:
            print("\n💶 CardMarket Prices (EUR):")
            print(f"  Updated: {cardmarket.get('updatedAt', 'N/A')}")
            print(f"  URL: {cardmarket.get('url', 'N/A')}")
            print("\n  Prices by Grade/Condition:")
            
            price_labels = {
                'averageSellPrice': 'Average Sell',
                'lowPrice': 'Low',
                'trendPrice': 'Trend',
                'germanProLow': 'German Pro Low',
                'suggestedPrice': 'Suggested',
                'reverseHoloSell': 'Reverse Holo Sell',
                'reverseHoloLow': 'Reverse Holo Low',
                'reverseHoloTrend': 'Reverse Holo Trend',
                'lowPriceExPlus': 'Low (EX+)',
                'avg1': 'Average (Grade 1)',
                'avg7': 'Average (Grade 7)',
                'avg30': 'Average (Grade 30)',
                'reverseHoloAvg1': 'Reverse Holo (Grade 1)',
                'reverseHoloAvg7': 'Reverse Holo (Grade 7)',
                'reverseHoloAvg30': 'Reverse Holo (Grade 30)'
            }
            
            for key, label in price_labels.items():
                if key in prices and prices[key] is not None:
                    print(f"    {label:25} €{prices[key]:>8.2f}")
        else:
            print("\n⚠️  No CardMarket pricing available for this card")
        
        # TCGPlayer prices (in USD) for comparison
        tcgplayer = card_data.get('tcgplayer', {})
        if tcgplayer and 'prices' in tcgplayer:
            print("\n💵 TCGPlayer Prices (USD) - For Comparison:")
            tcg_prices = tcgplayer.get('prices', {})
            
            for price_type, values in tcg_prices.items():
                if values:
                    print(f"\n  {price_type.replace('_', ' ').title()}:")
                    for key, value in values.items():
                        if value is not None:
                            print(f"    {key:12} ${value:>8.2f}")
        
        print(f"\n{'='*70}\n")
    
    def load_existing_prices(self, report_file):
        """Load existing prices from a previous report."""
        if not os.path.exists(report_file):
            return {}
        
        price_cache = {}
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    card_id = row.get('card_id')
                    if card_id and row.get('unit_price_eur'):
                        price_cache[card_id] = {
                            'unit_price_eur': float(row['unit_price_eur']),
                            'updated': row.get('updated', 'N/A')
                        }
        except Exception as e:
            print(f"Warning: Could not load existing prices: {e}")
        
        return price_cache
    
    def track_collection(self, collection_file, output_file='collection_value.csv', refresh_mode='full'):
        """
        Track prices for a collection from a CSV file with incremental saving.
        
        Args:
            collection_file: Path to CSV with card collection
            output_file: Output report file
            refresh_mode: 'full' to refresh all prices, 'missing' to only fetch missing prices
        
        CSV format: card_name,card_id,quantity,condition,reverse_holo
        """
        results = []
        total_value_eur = 0
        
        # Load existing prices if in missing mode
        price_cache = {}
        if refresh_mode == 'missing':
            print(f"Loading existing prices from {output_file}...")
            price_cache = self.load_existing_prices(output_file)
            print(f"Found {len(price_cache)} cached prices\n")
        
        # Initialize output file with header
        fieldnames = ['card_name', 'set_name', 'number', 'rarity', 'quantity', 
                     'condition', 'reverse_holo', 'unit_price_eur', 'total_price_eur', 
                     'card_id', 'updated']
        
        try:
            with open(collection_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                collection_rows = list(reader)
            
            # Open output file for incremental writing
            with open(output_file, 'w', newline='', encoding='utf-8') as out_f:
                writer = csv.DictWriter(out_f, fieldnames=fieldnames)
                writer.writeheader()
                
                for idx, row in enumerate(collection_rows, 1):
                    card_name = row.get('card_name', '')
                    card_id = row.get('card_id', '')
                    quantity = int(row.get('quantity', 1))
                    condition = row.get('condition', 'nm').lower()
                    is_reverse_holo = row.get('reverse_holo', 'no').lower() == 'yes'
                    
                    if not card_id:
                        print(f"⚠️  [{idx}/{len(collection_rows)}] Skipping {card_name}: No card_id")
                        continue
                    
                    # Check if we can use cached price
                    use_cached = False
                    price_eur = None
                    updated = None
                    card = None
                    
                    if refresh_mode == 'missing' and card_id in price_cache:
                        use_cached = True
                        price_eur = price_cache[card_id]['unit_price_eur']
                        updated = price_cache[card_id]['updated']
                        print(f"[{idx}/{len(collection_rows)}] Using cached: {card_name} ({card_id}) - €{price_eur:.2f}")
                    else:
                        print(f"[{idx}/{len(collection_rows)}] Fetching: {card_name} ({card_id})...")
                        
                        # Get card directly by ID
                        card = self.get_card_by_id(card_id)
                        
                        if not card:
                            print(f"  ❌ Card ID not found: {card_id}")
                            continue
                        
                        # Get CardMarket prices
                        cardmarket = card.get('cardmarket', {})
                        prices = cardmarket.get('prices', {})
                        updated = cardmarket.get('updatedAt', 'N/A')
                        
                        # Select price based on condition
                        if is_reverse_holo:
                            price_eur = prices.get('reverseHoloTrend') or prices.get('reverseHoloSell')
                        else:
                            condition_map = {
                                'nm': 'trendPrice',
                                'lp': 'lowPrice',
                                'mp': 'lowPrice',
                                'hp': 'lowPrice',
                                'dmg': 'lowPrice'
                            }
                            price_key = condition_map.get(condition, 'trendPrice')
                            price_eur = prices.get(price_key) or prices.get('averageSellPrice')
                        
                        if not price_eur:
                            print(f"  ⚠️  No price data available")
                            continue
                        
                        print(f"  ✓ Found - €{price_eur:.2f}")
                        time.sleep(0.3)  # Rate limiting
                    
                    # Calculate totals
                    item_total = price_eur * quantity
                    total_value_eur += item_total
                    
                    # Prepare row data
                    result_row = {
                        'card_name': card.get('name') if card else card_name,
                        'set_name': card.get('set', {}).get('name') if card else 'N/A',
                        'number': card.get('number') if card else 'N/A',
                        'rarity': card.get('rarity') if card else 'N/A',
                        'quantity': quantity,
                        'condition': condition.upper(),
                        'reverse_holo': 'Yes' if is_reverse_holo else 'No',
                        'unit_price_eur': price_eur,
                        'total_price_eur': item_total,
                        'card_id': card_id,
                        'updated': updated
                    }
                    
                    # Write immediately to file
                    writer.writerow(result_row)
                    out_f.flush()  # Ensure it's written to disk
                    
                    results.append(result_row)
                    
                    print(f"  💾 Saved: {card_name if not card else card.get('name')} - €{price_eur:.2f} x {quantity} = €{item_total:.2f}\n")
        
        except FileNotFoundError:
            print(f"Error: File not found '{collection_file}'")
            return None
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        return {
            'items': results,
            'total_value_eur': total_value_eur,
            'date': datetime.now().isoformat(),
            'currency': 'EUR (CardMarket)'
        }
    
    def print_summary(self, results, output_file='collection_value.csv'):
        """Print summary of collection tracking."""
        if not results or not results['items']:
            print("No results to summarize")
            return
        
        print(f"\n{'='*70}")
        print(f"📊 Collection Report Summary")
        print(f"{'='*70}")
        print(f"📄 Report saved to: {output_file}")
        print(f"📦 Total Cards: {len(results['items'])}")
        print(f"💶 Total Collection Value: €{results['total_value_eur']:.2f} EUR")
        print(f"📅 Date: {results['date']}")
        print(f"{'='*70}\n")
    
    def compare_reports(self, old_report, new_report):
        """Compare two collection reports to see value changes."""
        try:
            with open(old_report, 'r', encoding='utf-8') as f:
                old_data = list(csv.DictReader(f))
            with open(new_report, 'r', encoding='utf-8') as f:
                new_data = list(csv.DictReader(f))
            
            old_total = sum(float(row['total_price_eur']) for row in old_data)
            new_total = sum(float(row['total_price_eur']) for row in new_data)
            
            change = new_total - old_total
            change_pct = (change / old_total * 100) if old_total > 0 else 0
            
            print(f"\n{'='*70}")
            print("📈 Collection Value Comparison")
            print(f"{'='*70}")
            print(f"Old Value: €{old_total:.2f}")
            print(f"New Value: €{new_total:.2f}")
            print(f"Change:    €{change:+.2f} ({change_pct:+.1f}%)")
            print(f"{'='*70}\n")
            
        except Exception as e:
            print(f"Error comparing reports: {e}")


def prompt_refresh_mode(output_file='PokemonTCGAPI/collection_value.csv'):
    """Prompt user for refresh mode and handle old report backup."""
    print("="*70)
    print("Pokemon TCG Collection Price Tracker")
    print("="*70)
    
    if os.path.exists(output_file):
        print(f"\n📄 Found existing report: {output_file}")
        print("\nRefresh Options:")
        print("  1. Full Refresh - Fetch ALL prices (updates all cards)")
        print("  2. Missing Only - Only fetch prices for cards without pricing")
        
        while True:
            choice = input("\nSelect option (1 or 2): ").strip()
            if choice in ['1', '2']:
                break
            print("Invalid choice. Please enter 1 or 2.")
        
        if choice == '1':
            # Backup old report
            old_report = 'PokemonTCGAPI/collection_value_old.csv'
            if os.path.exists(old_report):
                # If old backup exists, create timestamped backup
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                archive_name = f'PokemonTCGAPI/collection_value_backup_{timestamp}.csv'
                shutil.copy(output_file, archive_name)
                print(f"📦 Created timestamped backup: {archive_name}")
            else:
                shutil.copy(output_file, old_report)
                print(f"📦 Backed up existing report to: {old_report}")
            
            return 'full'
        else:
            print("📋 Using existing prices where available...")
            return 'missing'
    else:
        print(f"\n📄 No existing report found. Will create new report: {output_file}")
        return 'full'


# Example usage
if __name__ == "__main__":
    # Load API key from .env file
    API_KEY = os.getenv("POKEMON_TCG_API_KEY")
    
    if not API_KEY:
        print("Error: POKEMON_TCG_API_KEY not found in .env file")
        print("Create a .env file with: POKEMON_TCG_API_KEY=your_key_here")
        exit(1)
    
    api = PokemonTCGAPI(API_KEY)
    
    # Prompt user for refresh mode
    refresh_mode = prompt_refresh_mode()
    
    print("\n" + "="*70)
    print(f"Starting {'FULL' if refresh_mode == 'full' else 'MISSING ONLY'} price refresh...")
    print("="*70 + "\n")
    
    # Track collection with incremental saving
    results = api.track_collection(
        'PokemonTCGAPI/my_pokemon_collection.csv',
        output_file='PokemonTCGAPI/collection_value.csv',
        refresh_mode=refresh_mode
    )
    
    if results:
        api.print_summary(results, 'PokemonTCGAPI/collection_value.csv')
        
        # If there's an old report, show comparison
        if os.path.exists('PokemonTCGAPI/collection_value_old.csv'):
            api.compare_reports('PokemonTCGAPI/collection_value_old.csv', 'PokemonTCGAPI/collection_value.csv')
    
    print("\n💡 Tips:")
    print("  - Run with full refresh weekly/monthly to track value changes")
    print("  - Use 'missing only' mode to quickly update incomplete reports")
    print("  - Old reports are backed up automatically")
    print("="*70)