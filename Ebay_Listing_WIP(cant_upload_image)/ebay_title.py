import csv

def generate_ebay_title(row):
    """
    Generate eBay title in format:
    Carte Pokemon - French Name - Card Number - NM - Set Name - Fr
    """
    french_name = row['nameFR']
    card_number = row['cn']
    condition = row['condition']
    set_name = row['set']
    
    # Remove attack names in brackets from French name
    # e.g., "Capumain [Astonish]" becomes "Capumain"
    if '[' in french_name:
        french_name = french_name.split('[')[0].strip()
    
    # Create the title
    title = f"Carte Pokemon - {french_name} - {card_number} - {condition} - {set_name} - Fr"
    
    return title

def process_csv(input_file, output_file=None):
    """
    Process the CSV file and generate eBay titles
    """
    titles = []
    
    with open(input_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            title = generate_ebay_title(row)
            titles.append({
                'original_name': row['name'],
                'quantity': row['quantity'],
                'ebay_title': title
            })
            print(title)
    
    # Optionally save to output file
    if output_file:
        with open(output_file, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['original_name', 'quantity', 'ebay_title'])
            writer.writeheader()
            writer.writerows(titles)
        print(f"\nTitles saved to {output_file}")
    
    return titles

# Usage
if __name__ == "__main__":
    # Use raw string (r"") or forward slashes for Windows paths
    input_csv = r"D:\02-Travaille\04-Coding\03-Projects\05-Rename_Pokemon_Photo\stock.csv"
    output_csv = "ebay_titles.csv"   # Optional: output file for titles
    
    # Process the CSV
    titles = process_csv(input_csv, output_csv)
    
    print(f"\nTotal titles generated: {len(titles)}")