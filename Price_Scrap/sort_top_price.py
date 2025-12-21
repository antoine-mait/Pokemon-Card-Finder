import json
import csv

# Charger le fichier JSON
with open('price_scrap/cardmarket_all_prices.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extraire et trier les cartes
cards_sorted = []

for result in data.get('results', []):
    if result.get('success') and 'prices' in result:
        card_info = result.get('card_info', {})
        prices = result.get('prices', {})
        
        # Extraire le prix de tendance
        tendance_str = prices.get('Tendance des prix', '0')
        # Convertir en float (gérer les virgules françaises)
        try:
            tendance = float(tendance_str.replace(',', '.'))
        except (ValueError, AttributeError):
            tendance = 0.0
        
        cards_sorted.append({
            'Nom': card_info.get('card_name', 'N/A'),
            'Extension': card_info.get('set_name', 'N/A'),
            'Prix': tendance
        })

# Trier par prix décroissant
cards_sorted.sort(key=lambda x: x['Prix'], reverse=True)

# Sauvegarder en TXT
with open('price_scrap/cartes_triees_par_prix.txt', 'w', encoding='utf-8') as f:
    for card in cards_sorted:
        f.write(f"{card['Nom']} - {card['Extension']} - {card['Prix']}€\n")

# Sauvegarder en CSV
with open('price_scrap/cartes_triees_par_prix.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Name', 'Extension', 'Price'])
    for card in cards_sorted:
        writer.writerow([card['Nom'], card['Extension'], card['Prix']])

print(f"✓ {len(cards_sorted)} cartes triées et sauvegardées dans 'price_scrap/'")
print("  - cartes_triees_par_prix.txt")
print("  - cartes_triees_par_prix.csv")

# Afficher les 10 premières cartes
print("\nTop 10 des cartes par tendance de prix :")
for i, card in enumerate(cards_sorted[:10], 1):
    print(f"{i}. {card['Nom']} - {card['Extension']} - {card['Prix']}€")