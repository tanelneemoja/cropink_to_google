import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
import os
import csv

def transform_cropink_to_google_ads_csv(cropink_url, output_csv_base="google_ads_feed"):
    """
    Fetches the Cropink XML feed, transforms it into Google Ads Business Data
    compatible CSVs for 'Basketball' and 'Lifestyle' categories, and saves them
    to separate files .
    """
    print(f"Attempting to fetch Cropink feed from: {cropink_url}")
    try:
        response = requests.get(cropink_url)
        response.raise_for_status()
        cropink_data = response.text
        print("Successfully fetched Cropink feed.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Cropink feed: {e}")
        return False

    print("Attempting to parse Cropink XML.")
    try:
        root = ET.fromstring(cropink_data)
        print("Successfully parsed Cropink XML.")
    except ET.ParseError as e:
        print(f"Error parsing Cropink XML: {e}")
        return False

    products_for_google_ads = {
        'basketball': [],
        'lifestyle': []
    }

    # Helper function to parse price/sale price with currency
    def parse_price(price_element):
        if price_element is not None and price_element.text:
            price_text = price_element.text.strip()
            # Simple check for a number followed by a currency code
            match = re.match(r'([\d.]+)\s*([A-Z]{3})$', price_text, re.IGNORECASE)
            if match:
                price_value = match.group(1)
                currency_code = match.group(2).upper()
                return f"{price_value} {currency_code}"
            return price_text
        return ''

    # Iterate through each <item> element
    namespaces = {'g': 'http://base.google.com/ns/1.0'}
    for item in root.findall(".//item"):
        # Check the custom_label_0 to determine the category
        custom_label_0 = item.find('custom_label_0')
        category_key = None
        if custom_label_0 is not None and custom_label_0.text:
            label_text = custom_label_0.text.strip().lower()
            if "basketball" in label_text:
                category_key = 'basketball'
            elif "lifestyle" in label_text:
                category_key = 'lifestyle'

        if category_key:
            # Initialize a dictionary for the current product's Google Ads data
            product_data = {
                'ID': '', 'ID2': '', 'Item title': '', 'Final URL': '', 'Image URL': '',
                'Item subtitle': '', 'Item description': '', 'Item category': '',
                'Price': '', 'Sale price': '', 'Contextual keywords': '',
                'Item address': '', 'Tracking template': '', 'Custom parameter': '',
                'Final mobile URL': '', 'Android app link': '', 'iOS app link': '',
                'iOS app store ID': '', 'Formatted price': '', 'Formatted sale price': ''
            }

            # --- Mapping Logic ---
            g_id = item.find('g:id', namespaces=namespaces)
            if g_id is not None and g_id.text:
                product_data['ID'] = g_id.text.strip()

            g_title = item.find('g:title', namespaces=namespaces)
            if g_title is not None and g_title.text:
                product_data['Item title'] = g_title.text.strip()

            g_link = item.find('g:link', namespaces=namespaces)
            if g_link is not None and g_link.text:
                product_data['Final URL'] = g_link.text.strip()

            g_image_link = item.find('g:image_link', namespaces=namespaces)
            if g_image_link is not None and g_image_link.text:
                product_data['Image URL'] = g_image_link.text.strip()

            g_description = item.find('g:description', namespaces=namespaces)
            if g_description is not None and g_description.text:
                product_data['Item description'] = g_description.text.strip()

            g_product_category = item.find('g:google_product_category', namespaces=namespaces)
            g_product_type = item.find('g:product_type', namespaces=namespaces)
            if g_product_category is not None and g_product_category.text:
                product_data['Item category'] = g_product_category.text.strip()
            elif g_product_type is not None and g_product_type.text:
                product_data['Item category'] = g_product_type.text.strip()

            g_price = item.find('g:price', namespaces=namespaces)
            product_data['Price'] = parse_price(g_price)

            g_sale_price = item.find('g:sale_price', namespaces=namespaces)
            product_data['Sale price'] = parse_price(g_sale_price)

            keywords = []
            g_brand = item.find('g:brand', namespaces=namespaces)
            if g_brand is not None and g_brand.text:
                keywords.append(g_brand.text.strip())

            g_color = item.find('g:color', namespaces=namespaces)
            if g_color is not None and g_color.text:
                keywords.append(g_color.text.strip())

            for i in range(5):
                custom_label = item.find(f'custom_label_{i}')
                if custom_label is not None and custom_label.text:
                    keywords.append(custom_label.text.strip())

            if keywords:
                product_data['Contextual keywords'] = ";".join(filter(None, keywords))

            products_for_google_ads[category_key].append(product_data)

    # --- Save to separate CSV files ---
    google_ads_columns_order = [
        'ID', 'ID2', 'Item title', 'Final URL', 'Image URL', 'Item subtitle',
        'Item description', 'Item category', 'Price', 'Sale price',
        'Contextual keywords', 'Item address', 'Tracking template',
        'Custom parameter', 'Final mobile URL', 'Android app link',
        'iOS app link', 'iOS app store ID', 'Formatted price', 'Formatted sale price'
    ]

    success = True
    for category, product_list in products_for_google_ads.items():
        if product_list:
            output_csv_file = f"{output_csv_base}_{category}.csv"
            df = pd.DataFrame(product_list)
            df = df.reindex(columns=google_ads_columns_order)

            print(f"Attempting to save {category.capitalize()} data to {output_csv_file}")
            try:
                df.to_csv(output_csv_file, index=False, encoding='utf-8', sep=',', doublequote=True, quoting=csv.QUOTE_ALL)
                print(f"Successfully transformed feed and saved to {output_csv_file}")
            except IOError as e:
                print(f"Error saving CSV file: {e}")
                success = False
        else:
            print(f"No products found for the '{category.capitalize()}' category. No CSV file will be created.")

    return success

if __name__ == "__main__":
    cropink_feed_url = os.environ.get('CROPINK_FEED_URL', "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4")
    output_csv_base = os.environ.get('OUTPUT_CSV_BASE', "google_ads_feed")

    success = transform_cropink_to_google_ads_csv(cropink_feed_url, output_csv_base)
    if success:
        print("CSV generation process completed successfully.")
    else:
        print("CSV generation process failed.")
