import sys
import xml.etree.ElementTree as ET
import csv
import re
import requests

FEED_URL = "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4/tt"
OUTPUT_FILE = "tiktok_catalog_feed.csv"

# 44 Required TikTok Catalog CSV Headers
HEADERS = [
    "sku_id", "title", "description", "availability", "condition", "price", "link", 
    "image_link", "brand", "video_link", "additional_image_link", "age_group", "color", 
    "gender", "item_group_id", "google_product_category", "material", "pattern", 
    "product_type", "sale_price", "sale_price_effective_date", "shipping", "shipping_weight", 
    "gtin", "mpn", "size", "tax", "ios_url", "ios_app_store_id", "ios_app_name", 
    "iPhone_url", "iPhone_app_store_id", "iPhone_app_name", "iPad_url", "iPad_app_store_id", 
    "iPad_app_name", "android_url", "android_package", "android_app_name", 
    "custom_label_0", "custom_label_1", "custom_label_2", "custom_label_3", "custom_label_4"
]

# XML Namespaces
NS = {'g': 'http://base.google.com/ns/1.0'}

def clean_text(val):
    if not val:
        return ""
    # Strip CDATA tags if present
    val = re.sub(r'<!\[CDATA\[([\s\S]*?)\]\]>', r'\1', val)
    # Remove newlines, carriage returns, tabs, and normalize curly quotes
    val = re.sub(r'[\r\n\t]+', ' ', val)
    val = val.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return val.strip()

def get_tag_value(item, tag_name):
    # Search for <g:tag_name> first
    elem = item.find(f'g:{tag_name}', NS)
    if elem is not None and elem.text:
        return clean_text(elem.text)
    
    # Fallback to standard <tag_name>
    elem = item.find(tag_name)
    if elem is not None and elem.text:
        return clean_text(elem.text)
        
    return ""

def main():
    print(f"Fetching XML feed from: {FEED_URL}")
    response = requests.get(FEED_URL, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
    if response.status_code != 200:
        print(f"Failed to fetch feed. HTTP Status: {response.status_code}")
        sys.exit(1)

    print("Parsing XML payload...")
    # Parse XML directly from response stream
    root = ET.fromstring(response.content)
    channel = root.find('channel')
    
    if channel is None:
        print("Error: Invalid RSS feed structure (missing <channel>).")
        sys.exit(1)

    items = channel.findall('item')
    print(f"Found {len(items)} items. Extracting fields...")

    rows = []
    for item in items:
        price = get_tag_value(item, "price")
        currency = get_tag_value(item, "currency")
        
        # Ensure price format includes currency (e.g. 14.00 EUR)
        if price and currency and currency not in price:
            price = f"{price} {currency}"

        row = [
            get_tag_value(item, "sku_id"),
            get_tag_value(item, "title"),
            get_tag_value(item, "description"),
            get_tag_value(item, "availability"),
            get_tag_value(item, "condition"),
            price,
            get_tag_value(item, "link"),
            get_tag_value(item, "image_link"),
            get_tag_value(item, "brand"),
            get_tag_value(item, "video_link"),
            get_tag_value(item, "additional_image_link"),
            get_tag_value(item, "age_group"),
            get_tag_value(item, "color"),
            get_tag_value(item, "gender"),
            get_tag_value(item, "item_group_id"),
            get_tag_value(item, "google_product_category"),
            get_tag_value(item, "material"),
            get_tag_value(item, "pattern"),
            get_tag_value(item, "product_type"),
            get_tag_value(item, "sale_price"),
            get_tag_value(item, "sale_price_effective_date"),
            get_tag_value(item, "shipping"),
            get_tag_value(item, "shipping_weight"),
            get_tag_value(item, "gtin"),
            get_tag_value(item, "mpn"),
            get_tag_value(item, "size"),
            get_tag_value(item, "tax"),
            get_tag_value(item, "ios_url"),
            get_tag_value(item, "ios_app_store_id"),
            get_tag_value(item, "ios_app_name"),
            get_tag_value(item, "iPhone_url"),
            get_tag_value(item, "iPhone_app_store_id"),
            get_tag_value(item, "iPhone_app_name"),
            get_tag_value(item, "iPad_url"),
            get_tag_value(item, "iPad_app_store_id"),
            get_tag_value(item, "iPad_app_name"),
            get_tag_value(item, "android_url"),
            get_tag_value(item, "android_package"),
            get_tag_value(item, "android_app_name"),
            get_tag_value(item, "custom_label_0"),
            get_tag_value(item, "custom_label_1"),
            get_tag_value(item, "custom_label_2"),
            get_tag_value(item, "custom_label_3"),
            get_tag_value(item, "custom_label_4"),
        ]
        rows.append(row)

    print(f"Writing {len(rows)} product rows to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    print("TikTok Catalog CSV feed generated successfully.")

if __name__ == "__main__":
    main()
