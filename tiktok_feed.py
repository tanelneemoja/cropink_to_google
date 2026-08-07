import sys
import xml.etree.ElementTree as ET
import csv
import re
import requests

FEED_URL = "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4/tt"
OUTPUT_FILE = "tiktok_catalog_feed.csv"

# Official TikTok Catalog CSV Standard Headers
HEADERS = [
    "sku", "title", "description", "availability", "condition", "price", "landing_url", 
    "image_url", "brand", "video_url", "additional_image_url", "age_group", "color", 
    "gender", "item_group_id", "google_product_category", "material", "pattern", 
    "product_type", "sale_price", "sale_price_effective_date", "shipping", "shipping_weight", 
    "gtin", "mpn", "size", "tax", "ios_url", "ios_app_store_id", "ios_app_name", 
    "iphone_url", "iphone_app_store_id", "iphone_app_name", "ipad_url", "ipad_app_store_id", 
    "ipad_app_name", "android_url", "android_package", "android_app_name", 
    "custom_label_0", "custom_label_1", "custom_label_2", "custom_label_3", "custom_label_4"
]

NS = {
    'g': 'http://base.google.com/ns/1.0',
    'content': 'http://purl.org/rss/1.0/modules/content/'
}

def clean_text(val):
    if not val:
        return ""
    val = re.sub(r'<!\[CDATA\[([\s\S]*?)\]\]>', r'\1', val)
    val = re.sub(r'[\r\n\t]+', ' ', val)
    val = re.sub(r'\s+', ' ', val)
    return val.strip()

def get_field(item, tag_names):
    if isinstance(tag_names, str):
        tag_names = [tag_names]

    for tag in tag_names:
        elem = item.find(f'g:{tag}', NS)
        if elem is not None and elem.text:
            return clean_text(elem.text)
        
        elem = item.find(tag)
        if elem is not None and elem.text:
            return clean_text(elem.text)
            
    return ""

def main():
    print(f"Downloading feed from {FEED_URL}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(FEED_URL, headers=headers, timeout=60)
    
    if response.status_code != 200:
        print(f"Error fetching feed: Status code {response.status_code}")
        sys.exit(1)

    print("Parsing XML data...")
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"XML Parsing failed: {e}")
        sys.exit(1)

    channel = root.find('channel')
    items = channel.findall('item') if channel is not None else root.findall('item')

    print(f"Found {len(items)} items. Mapping to TikTok Catalog format...")

    rows = []
    for item in items:
        # Pull essential attributes mapping Google RSS -> TikTok standard names
        sku = get_field(item, ["sku_id", "id", "sku", "mpn"])
        title = get_field(item, "title")
        landing_url = get_field(item, ["link", "landing_url"])
        image_url = get_field(item, ["image_link", "image_url"])
        price = get_field(item, "price")

        # Skip rows missing absolute minimum requirements
        if not (sku and title and landing_url and price):
            continue

        availability = get_field(item, "availability") or "in stock"
        condition = get_field(item, "condition") or "new"

        row = [
            sku,
            title,
            get_field(item, "description") or title,
            availability,
            condition,
            price,
            landing_url,
            image_url,
            get_field(item, "brand"),
            get_field(item, ["video_link", "video_url"]),
            get_field(item, ["additional_image_link", "additional_image_url"]),
            get_field(item, "age_group"),
            get_field(item, "color"),
            get_field(item, "gender"),
            get_field(item, ["item_group_id", "group_id"]),
            get_field(item, "google_product_category"),
            get_field(item, "material"),
            get_field(item, "pattern"),
            get_field(item, "product_type"),
            get_field(item, "sale_price"),
            get_field(item, "sale_price_effective_date"),
            get_field(item, "shipping"),
            get_field(item, "shipping_weight"),
            get_field(item, "gtin"),
            get_field(item, "mpn"),
            get_field(item, "size"),
            get_field(item, "tax"),
            get_field(item, "ios_url"),
            get_field(item, "ios_app_store_id"),
            get_field(item, "ios_app_name"),
            get_field(item, ["iPhone_url", "iphone_url"]),
            get_field(item, ["iPhone_app_store_id", "iphone_app_store_id"]),
            get_field(item, ["iPhone_app_name", "iphone_app_name"]),
            get_field(item, ["iPad_url", "ipad_url"]),
            get_field(item, ["iPad_app_store_id", "ipad_app_store_id"]),
            get_field(item, ["iPad_app_name", "ipad_app_name"]),
            get_field(item, "android_url"),
            get_field(item, "android_package"),
            get_field(item, "android_app_name"),
            get_field(item, "custom_label_0"),
            get_field(item, "custom_label_1"),
            get_field(item, "custom_label_2"),
            get_field(item, "custom_label_3"),
            get_field(item, "custom_label_4")
        ]
        rows.append(row)

    print(f"Writing {len(rows)} products to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    print("TikTok feed script complete.")

if __name__ == "__main__":
    main()
