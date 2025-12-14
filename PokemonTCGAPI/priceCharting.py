import csv
import re

def extract_card_info(row):
    """Extract card information from the detailed CSV row"""
    card_name = row['card_name']
    card_id = row['card_id']
    set_folder = row['set_folder']
    
    # Extract card number from card_id (e.g., "neo1-1" -> "1")
    card_num = card_id.split('-')[-1]
    
    # Extract set name from set_folder
    # Remove everything after the last underscore (the set code)
    # "Neo_Genesis_NEO1" -> "Neo_Genesis" -> "Neo Genesis"
    # "Phantasmal_Flames_me02" -> "Phantasmal_Flames" -> "Phantasmal Flames"
    set_name = set_folder.rsplit('_', 1)[0]  # Remove last part after underscore
    set_name = set_name.replace('_', ' ')  # Replace remaining underscores with spaces
    
    # Type is always "Pokemon" for now (can be extended)
    type_card = "Pokemon"
    
    # Format: "Ampharos Pokemon Neo Genesis set #1"
    return f"{card_name} {type_card} {set_name} set #{card_num}"

def transform_csv(input_file, output_file):
    """Transform the detailed CSV to text format for pricing website"""
    with open(input_file, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        # Collect formatted lines
        formatted_lines = []
        for row in reader:
            formatted_lines.append(extract_card_info(row))
        
        # Write to output file (plain text, one per line)
        with open(output_file, 'w', encoding='utf-8') as outfile:
            outfile.write('\n'.join(formatted_lines))
    
    print(f"Transformation complete! Output saved to {output_file}")
    print(f"Processed {len(formatted_lines)} cards")
    print(f"\nFirst few lines:")
    for line in formatted_lines[:3]:
        print(f"  {line}")

if __name__ == "__main__":
    input_file = "./PokemonTCGAPI/collection_detailed.csv"
    output_file = "./PokemonTCGAPI/collection_list.txt"
    
    try:
        transform_csv(input_file, output_file)
    except FileNotFoundError:
        print(f"Error: {input_file} not found. Please ensure the file exists in the same directory.")
    except Exception as e:
        print(f"An error occurred: {e}")