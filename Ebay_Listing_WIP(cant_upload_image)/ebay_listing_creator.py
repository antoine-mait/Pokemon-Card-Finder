import os
import csv
import base64
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import re
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

# Load environment variables
load_dotenv()

class EbayListingCreator:
    """Create eBay listings for Pokemon cards using CardMarket data and Cloudinary for images"""
    
    def __init__(self, production_mode=False):
        self.app_id = os.getenv('EBAY_APP_ID')
        self.dev_id = os.getenv('EBAY_DEV_ID')
        self.cert_id = os.getenv('EBAY_CERT_ID')
        self.user_token = os.getenv('EBAY_USER_TOKEN')
        
        # Cloudinary configuration
        self.cloudinary_cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
        self.cloudinary_api_key = os.getenv('CLOUDINARY_API_KEY')
        self.cloudinary_api_secret = os.getenv('CLOUDINARY_API_SECRET')
        
        self.production_mode = production_mode
        
        if production_mode:
            self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"
            self.trading_url = "https://api.ebay.com/ws/api.dll"
            print("🚀 PRODUCTION MODE - Real listings will be created!")
        else:
            self.auth_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
            self.trading_url = "https://api.sandbox.ebay.com/ws/api.dll"
            print("🧪 SANDBOX MODE - Test environment")
        
        self.access_token = None
        
        if not all([self.app_id, self.dev_id, self.cert_id]):
            raise ValueError("Missing eBay API credentials in .env file")
        
        if production_mode and not self.user_token:
            raise ValueError("EBAY_USER_TOKEN required for production mode!")
        
        # Configure Cloudinary
        if not all([self.cloudinary_cloud_name, self.cloudinary_api_key, self.cloudinary_api_secret]):
            raise ValueError("Missing Cloudinary credentials in .env file! Need: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET")
        
        cloudinary.config(
            cloud_name=self.cloudinary_cloud_name,
            api_key=self.cloudinary_api_key,
            api_secret=self.cloudinary_api_secret,
            secure=True
        )
        
        print(f"✓ Cloudinary configured: {self.cloudinary_cloud_name}")
        
        # Debug: Print token status
        if self.user_token:
            print(f"✓ User token loaded: {self.user_token[:30]}...")
        else:
            print("⚠️  No user token found")
    
    def upload_to_cloudinary(self, image_path, card_info):
        """Upload image to Cloudinary and return public HTTPS URL"""
        print(f"  📤 Uploading to Cloudinary: {os.path.basename(image_path)}")
        
        try:
            # Create a unique public_id based on card info
            filename = os.path.basename(image_path)
            public_id = f"pokemon_cards/{card_info['setCode']}/{card_info['cn']}/{filename}"
            public_id = public_id.replace('/', '_').replace(' ', '_')
            
            # Upload to Cloudinary with optimization
            result = cloudinary.uploader.upload(
                image_path,
                public_id=public_id,
                folder="ebay_pokemon_cards",
                overwrite=True,
                resource_type="image",
                format="jpg",  # Convert to JPG
                quality="auto:good",  # Auto optimize quality
                fetch_format="auto",  # Auto format selection
                width=1600,  # Max width for eBay
                height=1600,  # Max height for eBay
                crop="limit"  # Only resize if larger
            )
            
            image_url = result['secure_url']
            print(f"    ✓ Uploaded to Cloudinary: {image_url}")
            return image_url
            
        except Exception as e:
            print(f"    ✗ Error uploading to Cloudinary: {e}")
            return None
    
    def find_card_images_by_number(self, card_number, set_code, images_folder):
        """Find front and back images for a card using card number"""
        card_num_normalized = card_number.replace('/', '-')
        
        front_image = None
        back_image = None
        
        if not os.path.exists(images_folder):
            print(f"  ⚠️  Images folder doesn't exist: {images_folder}")
            return None, None
        
        all_files = os.listdir(images_folder)
        print(f"  🔍 Searching for card #{card_num_normalized} in set {set_code}")
        
        for filename in all_files:
            if set_code in filename and card_num_normalized in filename:
                full_path = os.path.join(images_folder, filename)
                if "_FRONT" in filename:
                    front_image = full_path
                    print(f"  ✓ Found FRONT: {filename}")
                elif "_BACK" in filename:
                    back_image = full_path
                    print(f"  ✓ Found BACK: {filename}")
        
        if not front_image:
            card_num_short = card_number.split('/')[0] if '/' in card_number else card_number
            print(f"  🔍 Trying alternative search with: {card_num_short}")
            
            for filename in all_files:
                if set_code in filename and card_num_short in filename:
                    full_path = os.path.join(images_folder, filename)
                    if "_FRONT" in filename:
                        front_image = full_path
                        print(f"  ✓ Found FRONT (alt): {filename}")
                    elif "_BACK" in filename:
                        back_image = full_path
                        print(f"  ✓ Found BACK (alt): {filename}")
        
        return front_image, back_image
    
    def create_listing_title(self, card_name, set_name, card_number, language, condition):
        """Create eBay listing title (80 char max)"""
        # Format: Pokemon [Card Name] [Set] [Number] [Language] [Condition]
        title = f"Pokemon {card_name} {set_name} #{card_number} {language} {condition}"
        
        if len(title) > 80:
            # Try shorter version
            title = f"Pokemon {card_name} {set_name} #{card_number} {condition}"
            if len(title) > 80:
                title = title[:77] + "..."
        
        return title
    
    def create_listing_description(self, card_data):
        """Create HTML description for the listing"""
        description = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <h1 style="color: #0654ba;">Pokemon Card - {card_data['name']}</h1>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <h2>Card Details</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Card Name:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['name']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Set:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['set']} ({card_data['setCode']})</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Card Number:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['cn']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Language:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['language']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Condition:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['condition']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Rarity:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{card_data['rarity']}</td>
                    </tr>
                </table>
            </div>
            
            <div style="margin-bottom: 20px;">
                <h2>Description</h2>
                <p>This is an authentic Pokemon Trading Card Game card in {card_data['condition']} condition.</p>
                <p><em>{card_data['comment']}</em></p>
                <p><strong>What you see in the photos is what you get!</strong></p>
            </div>
            
            <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px;">
                <h2>Shipping & Handling</h2>
                <ul>
                    <li>Card will be shipped in a protective sleeve</li>
                    <li>Carefully packaged to prevent damage during transit</li>
                    <li>Fast and reliable shipping from France</li>
                </ul>
            </div>
        </body>
        </html>
        """
        return description
    
    def create_ebay_listing(self, card_data, front_image_path, back_image_path):
        """Create an eBay listing using Trading API with Cloudinary-hosted images"""
        print(f"\n📝 Creating listing for: {card_data['name']}")
        
        # Upload images to Cloudinary
        image_urls = []
        
        if front_image_path:
            front_url = self.upload_to_cloudinary(front_image_path, card_data)
            if front_url:
                image_urls.append(front_url)
        
        if back_image_path:
            back_url = self.upload_to_cloudinary(back_image_path, card_data)
            if back_url:
                image_urls.append(back_url)
        
        if not image_urls:
            print("  ✗ No images available, skipping listing")
            return False
        
        print(f"  📸 Using {len(image_urls)} image(s)")
        for i, url in enumerate(image_urls, 1):
            print(f"    {i}. {url}")
        
        # Create listing title
        title = self.create_listing_title(
            card_data['name'],
            card_data['set'],
            card_data['cn'],
            card_data['language'],
            card_data['condition']
        )
        
        # Create description
        description = self.create_listing_description(card_data)
        
        # Calculate price (CardMarket price + markup)
        base_price = float(card_data.get('price', '0.02'))
        listing_price = max(base_price * 1.5, 0.99)  # 50% markup, minimum €0.99
        
        # Map condition to eBay condition ID
        condition_map = {
            'NM': 3000,  # Used
            'MT': 1000,  # New
            'EX': 3000,  # Used
            'GD': 3000,  # Used
            'LP': 3000,  # Used
            'PL': 4000,  # Very Good
            'PO': 5000   # Good
        }
        condition_id = condition_map.get(card_data['condition'], 3000)
        
        # Build picture URLs XML
        picture_urls_xml = '\n                    '.join([f'<PictureURL>{url}</PictureURL>' for url in image_urls])
        
        # Escape XML special characters in title
        title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # Prepare AddFixedPriceItem XML request
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
        <AddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
            <RequesterCredentials>
                <eBayAuthToken>{self.user_token}</eBayAuthToken>
            </RequesterCredentials>
            <Item>
                <Title>{title}</Title>
                <Description><![CDATA[{description}]]></Description>
                <PrimaryCategory>
                    <CategoryID>183454</CategoryID>
                </PrimaryCategory>
                <StartPrice>{listing_price:.2f}</StartPrice>
                <ConditionID>{condition_id}</ConditionID>
                <Country>FR</Country>
                <Currency>EUR</Currency>
                <DispatchTimeMax>3</DispatchTimeMax>
                <ListingDuration>GTC</ListingDuration>
                <ListingType>FixedPriceItem</ListingType>
                <Location>Paris, France</Location>
                <Quantity>{card_data['quantity']}</Quantity>
                <PictureDetails>
                    {picture_urls_xml}
                </PictureDetails>
                <PostalCode>75001</PostalCode>
                <ShippingDetails>
                    <ShippingType>Flat</ShippingType>
                    <ShippingServiceOptions>
                        <ShippingServicePriority>1</ShippingServicePriority>
                        <ShippingService>FR_Chronopost</ShippingService>
                        <ShippingServiceCost>2.50</ShippingServiceCost>
                        <ShippingServiceAdditionalCost>0.00</ShippingServiceAdditionalCost>
                    </ShippingServiceOptions>
                    <InsuranceDetails>
                        <InsuranceOption>NotOffered</InsuranceOption>
                    </InsuranceDetails>
                </ShippingDetails>
                <ReturnPolicy>
                    <ReturnsAcceptedOption>ReturnsNotAccepted</ReturnsAcceptedOption>
                </ReturnPolicy>

            </Item>
        </AddFixedPriceItemRequest>"""
        
        headers = {
            'X-EBAY-API-SITEID': '71',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '967',
            'X-EBAY-API-CALL-NAME': 'AddFixedPriceItem',
            'X-EBAY-API-APP-NAME': self.app_id,
            'X-EBAY-API-DEV-NAME': self.dev_id,
            'X-EBAY-API-CERT-NAME': self.cert_id,
            'Content-Type': 'text/xml'
        }
        
        try:
            print("  📤 Sending listing to eBay...")
            print(f"  💰 Price: €{listing_price:.2f}")
            print(f"  📦 Quantity: {card_data['quantity']}")
            
            if self.production_mode:
                print("\n===== FULL XML REQUEST SENT TO EBAY =====")
                print(xml_request)
                print("==========================================\n")
                response = requests.post(self.trading_url, data=xml_request.encode('utf-8'), headers=headers)
                
                if '<Ack>Success</Ack>' in response.text:
                    item_id_match = re.search(r'<ItemID>(\d+)</ItemID>', response.text)
                    item_id = item_id_match.group(1) if item_id_match else 'Unknown'
                    print(f"  ✓ Listing created successfully! Item ID: {item_id}")
                    print(f"  🔗 View at: https://www.ebay.fr/itm/{item_id}")
                    return True
                else:
                    print(f"  ✗ Error creating listing")
                    error_match = re.search(r'<ShortMessage>(.*?)</ShortMessage>', response.text)
                    if error_match:
                        print(f"  ✗ Error: {error_match.group(1)}")
                    long_error = re.search(r'<LongMessage>(.*?)</LongMessage>', response.text)
                    if long_error:
                        print(f"  ✗ Details: {long_error.group(1)}")
                    # Save full response for debugging
                    with open('ebay_error_response.xml', 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    print(f"  ℹ️  Full error saved to ebay_error_response.xml")
                    return False
            else:
                print("  ⚠️  SANDBOX MODE: Would create listing here")
                print("  ✓ Listing validated (sandbox simulation)")
                return True
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def process_cardmarket_csv(self, csv_path, images_folder, test_mode=False):
        """Process CardMarket CSV and create eBay listings"""
        print("="*70)
        print("EBAY LISTING CREATOR WITH CLOUDINARY")
        print("="*70)
        
        if not os.path.exists(csv_path):
            print(f"\n✗ CSV file not found: {csv_path}")
            return
        
        if not os.path.exists(images_folder):
            print(f"\n✗ Images folder not found: {images_folder}")
            return
        
        print(f"\n📄 Reading CSV: {csv_path}")
        print(f"🖼️ Images folder: {images_folder}")
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            cards = list(reader)
        
        if test_mode:
            print(f"\n⚠️  TEST MODE: Processing only the FIRST card out of {len(cards)} total")
            cards = cards[:1]
        else:
            print(f"\n✓ Found {len(cards)} cards to list")
        
        successful = 0
        failed = 0
        
        for i, card_data in enumerate(cards, 1):
            print(f"\n{'='*70}")
            print(f"[{i}/{len(cards)}] Processing: {card_data['name']} (#{card_data['cn']})")
            print('='*70)
            
            # Find images using card number
            front_image, back_image = self.find_card_images_by_number(
                card_data['cn'],
                card_data['setCode'],
                images_folder
            )
            
            if front_image:
                if self.create_ebay_listing(card_data, front_image, back_image):
                    successful += 1
                else:
                    failed += 1
            else:
                print("  ✗ Skipping - no images found")
                failed += 1
        
        print("\n" + "="*70)
        print("LISTING SUMMARY")
        print("="*70)
        print(f"Total cards: {len(cards)}")
        print(f"✓ Successfully listed: {successful}")
        print(f"✗ Failed: {failed}")
        print("="*70)


def main():
    """Main execution"""
    print("="*70)
    print("POKEMON CARD EBAY LISTING CREATOR WITH CLOUDINARY")
    print("="*70)
    
    # print("\nSelect environment:")
    # print("1. Sandbox (test environment)")
    # print("2. Production (REAL listings!)")
    #env_choice = input("Enter choice (1 or 2): ").strip()
    
    production_mode = True #(env_choice == "2")
    
    # if production_mode:
    #     print("\n" + "!"*70)
    #     print("⚠️  PRODUCTION MODE - REAL LISTINGS WILL BE CREATED!")
    #     print("!"*70)
    #     confirm = input("\nAre you ready to create real listings? (y/n): ").strip().lower()
    #     if confirm not in ['yes', 'y']:
    #         print("Cancelled.")
    #         return
    
    csv_path = input("\nEnter path to CSV file: ").strip().strip('"')
    images_folder = input("Enter path to images folder: ").strip().strip('"')
    
    print("\nProcessing mode:")
    print("1. Test mode (first card only)")
    print("2. Process ALL cards")
    mode_choice = input("Enter choice (1 or 2): ").strip()
    
    test_mode = (mode_choice == "1")
    
    if not test_mode and production_mode:
        print("\n🚨 THIS WILL CREATE REAL LISTINGS ON EBAY! 🚨")
    
    confirm = input("\nContinue? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Cancelled.")
        return
    
    try:
        creator = EbayListingCreator(production_mode=production_mode)
        creator.process_cardmarket_csv(csv_path, images_folder, test_mode=test_mode)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()