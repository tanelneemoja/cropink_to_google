import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
import os
import csv # Ensure csv module is imported for quoting in to_csv

def transform_cropink_to_google_ads_csv(cropink_url, output_csv_file="google_ads_feed.csv"):
    """
    Fetches the Cropink XML feed, transforms it into a Google Ads Business Data
    compatible CSV, and saves it to a file.
    """
    print(f"Attempting to fetch Cropink feed from: {cropink_url}")
    try:
        response = requests.get(cropink_url)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        cropink_data = response.text
        print("Successfully fetched Cropink feed.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Cropink feed: {e}")
        return False # Indicate failure

    print("Attempting to parse Cropink XML.")
    try:
        # Parse the XML data
        root = ET.fromstring(cropink_data)
        print("Successfully parsed Cropink XML.")
    except ET.ParseError as e:
        print(f"Error parsing Cropink XML: {e}")
        return False # Indicate failure

    products_for_google_ads = []

    # Iterate through each <item> element in the XML feed
    for item in root.findall(".//item"):
        # Initialize a dictionary for the current product's Google Ads data
        product_data = {
            'ID': '',
            'ID2': '',
            'Item title': '',
            'Final URL': '',
            'Image URL': '',
            'Item subtitle': '',
            'Item description': '',
            'Item category': '',
            'Price': '',
            'Sale price': '', # Now explicitly included for extraction
            'Contextual keywords': '',
            'Item address': '',
            'Tracking template': '',
            'Custom parameter': '',
            'Final mobile URL': '',
            'Android app link': '',
            'iOS app link': '',
            'iOS app store ID': '',
            'Formatted price': '',
            'Formatted sale price': ''
        }

        # --- Mapping Logic ---
        # All finds use the 'g' namespace
        namespaces = {'g': 'http://base.google.com/ns/1.0'}

        # g:id (Required)
        g_id = item.find('g:id', namespaces=namespaces)
        if g_id is not None and g_id.text:
            product_data['ID'] = g_id.text.strip()

        # g:title (Required for Item title)
        g_title = item.find('g:title', namespaces=namespaces)
        if g_title is not None and g_title.text:
            product_data['Item title'] = g_title.text.strip()

        # g:link (Required for Final URL)
        g_link = item.find('g:link', namespaces=namespaces)
        if g_link is not None and g_link.text:
            product_data['Final URL'] = g_link.text.strip()

        # g:image_link (Recommended for Image URL)
        g_image_link = item.find('g:image_link', namespaces=namespaces)
        if g_image_link is not None and g_image_link.text:
            product_data['Image URL'] = g_image_link.text.strip()

        # g:description (Recommended for Item description)
        g_description = item.find('g:description', namespaces=namespaces)
        if g_description is not None and g_description.text:
            product_data['Item description'] = g_description.text.strip()

        # g:google_product_category or g:product_type (Recommended for Item category)
        g_product_category = item.find('g:google_product_category', namespaces=namespaces)
        g_product_type = item.find('g:product_type', namespaces=namespaces)
        if g_product_category is not None and g_product_category.text:
            product_data['Item category'] = g_product_category.text.strip()
        elif g_product_type is not None and g_product_type.text:
            product_data['Item category'] = g_product_type.text.strip()

        # Helper function to parse price/sale price with currency
        def parse_price(price_element):
            if price_element is not None and price_element.text:
                price_text = price_element.text.strip()
                match = re.match(r'([\d.]+)\s*([A-Z]{3})$', price_text, re.IGNORECASE)
                if match:
                    price_value = match.group(1)
                    currency_code = match.group(2).upper()
                    return f"{price_value} {currency_code}"
                else:
                    # Fallback if regex doesn't match expected "NUMBER CURRENCY_CODE" format
                    print(f"Warning: Price format '{price_text}' not exactly 'NUMBER CURRENCY_CODE'. Using raw.")
                    return price_text
            return ''

        # g:price (Recommended for Price)
        g_price = item.find('g:price', namespaces=namespaces)
        product_data['Price'] = parse_price(g_price)

        # g:sale_price (New addition for Sale price)
        g_sale_price = item.find('g:sale_price', namespaces=namespaces)
        product_data['Sale price'] = parse_price(g_sale_price)

        # Contextual keywords (mapping from multiple fields like brand, color, custom labels)
        keywords = []
        g_brand = item.find('g:brand', namespaces=namespaces)
        if g_brand is not None and g_brand.text:
            keywords.append(g_brand.text.strip())

        g_color = item.find('g:color', namespaces=namespaces)
        if g_color is not None and g_color.text:
            keywords.append(g_color.text.strip())

        for i in range(5): # Iterate custom_label_0 to custom_label_4
            # Note: custom_label_x elements are NOT in the 'g' namespace
            custom_label = item.find(f'custom_label_{i}')
            if custom_label is not None and custom_label.text:
                keywords.append(custom_label.text.strip())

        if keywords:
            product_data['Contextual keywords'] = ";".join(filter(None, keywords)) # Filter out empty strings


        products_for_google_ads.append(product_data)

    # Create a Pandas DataFrame
    df = pd.DataFrame(products_for_google_ads)

    # Ensure column order matches the Google Ads template exactly
    google_ads_columns_order = [
        'ID', 'ID2', 'Item title', 'Final URL', 'Image URL', 'Item subtitle',
        'Item description', 'Item category', 'Price', 'Sale price', # Sale price included here
        'Contextual keywords', 'Item address', 'Tracking template',
        'Custom parameter', 'Final mobile URL', 'Android app link',
        'iOS app link', 'iOS app store ID', 'Formatted price', 'Formatted sale price'
    ]

    # Reindex the DataFrame to ensure correct column order
    df = df.reindex(columns=google_ads_columns_order)

    # Save to CSV
    print(f"Attempting to save transformed data to {output_csv_file}")
    try:
        df.to_csv(output_csv_file, index=False, encoding='utf-8', sep=',', doublequote=True, quoting=csv.QUOTE_ALL)
        print(f"Successfully transformed feed and saved to {output_csv_file}")
        return True # Indicate success
    except IOError as e:
        print(f"Error saving CSV file: {e}")
        return False # Indicate failure

if __name__ == "__main__":
    cropink_feed_url = os.environ.get('CROPINK_FEED_URL', "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4")
    output_csv_file = os.environ.get('OUTPUT_CSV_FILE', "google_ads_feed.csv")

    success = transform_cropink_to_google_ads_csv(cropink_feed_url, output_csv_file)
    if success:
        print(f"CSV generation process completed successfully. Check '{output_csv_file}'.")
    else:
        print("CSV generation process failed.")
