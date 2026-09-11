import csv
import os
import re
import xml.etree.ElementTree as ET
import pandas as pd
import requests


def clean_text(text):
    """Strips HTML tags and normalizes whitespace for conversational LLM matching."""
    if not text:
        return ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    clean = " ".join(clean.split())
    return clean


def parse_price_value(price_element):
    """Extracts price formatted as 'VALUE CURRENCY', e.g., '120.00 EUR'."""
    if price_element is not None and price_element.text:
        price_text = price_element.text.strip()
        match = re.match(r"([\d.]+)\s*([A-Z]{3})$", price_text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2).upper()}"
        return price_text
    return ""


def parse_availability(availability_element):
    """Maps standard Google availability to OpenAI schema values."""
    if availability_element is not None and availability_element.text:
        val = availability_element.text.strip().lower()
        if val in ["in stock", "in_stock"]:
            return "in_stock"
        elif val in ["out of stock", "out_of_stock"]:
            return "out_of_stock"
        elif val in ["preorder", "pre_order"]:
            return "pre_order"
        elif val in ["backorder", "back_order"]:
            return "backorder"
    return "in_stock"  # Default assumption if present in feed


def transform_cropink_to_chatgpt_ads_csv(
    cropink_url, output_csv_base="chatgpt_ads_feed"
):
    """Fetches Cropink XML feed and maps it into OpenAI/ChatGPT Ads CSV specifications."""
    print(f"Fetching Cropink feed from: {cropink_url}")
    try:
        response = requests.get(cropink_url)
        response.raise_for_status()
        cropink_data = response.text
        print("Successfully fetched Cropink feed.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Cropink feed: {e}")
        return False

    print("Parsing Cropink XML...")
    try:
        root = ET.fromstring(cropink_data)
        print("Successfully parsed XML.")
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return False

    products_by_category = {"basketball": [], "lifestyle": []}

    namespaces = {"g": "http://base.google.com/ns/1.0"}

    # Process XML items
    for item in root.findall(".//item"):
        # Check custom_label_0 for target categorization
        custom_label_0 = item.find("custom_label_0")
        category_key = None
        if custom_label_0 is not None and custom_label_0.text:
            label_text = custom_label_0.text.strip().lower()
            if "basketball" in label_text:
                category_key = "basketball"
            elif "lifestyle" in label_text:
                category_key = "lifestyle"

        if category_key:
            # Schema according to OpenAI Product Feed specifications
            product_data = {
                "item_id": "",
                "title": "",
                "description": "",
                "url": "",
                "image_url": "",
                "brand": "",
                "price": "",
                "sale_price": "",
                "availability": "in_stock",
                "google_product_category": "",
                "product_type": "",
                "is_ads_eligible": "true",  # Required flag for OpenAI Ads ingestion
                "enable_search": "true",  # Eligibility for ChatGPT Shopping search
                "ads_metadata": "",  # Contextual tags/keywords stringified
            }

            # Product ID
            g_id = item.find("g:id", namespaces=namespaces)
            if g_id is not None and g_id.text:
                product_data["item_id"] = g_id.text.strip()

            # Title
            g_title = item.find("g:title", namespaces=namespaces)
            if g_title is not None and g_title.text:
                product_data["title"] = clean_text(g_title.text)

            # URL / Link
            g_link = item.find("g:link", namespaces=namespaces)
            if g_link is not None and g_link.text:
                product_data["url"] = g_link.text.strip()

            # Main Image URL
            g_image_link = item.find("g:image_link", namespaces=namespaces)
            if g_image_link is not None and g_image_link.text:
                product_data["image_url"] = g_image_link.text.strip()

            # Description
            g_description = item.find("g:description", namespaces=namespaces)
            if g_description is not None and g_description.text:
                product_data["description"] = clean_text(g_description.text)

            # Brand
            g_brand = item.find("g:brand", namespaces=namespaces)
            if g_brand is not None and g_brand.text:
                product_data["brand"] = g_brand.text.strip()

            # Availability
            g_availability = item.find("g:availability", namespaces=namespaces)
            product_data["availability"] = parse_availability(g_availability)

            # Category / Types
            g_product_category = item.find(
                "g:google_product_category", namespaces=namespaces
            )
            if g_product_category is not None and g_product_category.text:
                product_data["google_product_category"] = (
                    g_product_category.text.strip()
                )

            g_product_type = item.find("g:product_type", namespaces=namespaces)
            if g_product_type is not None and g_product_type.text:
                product_data["product_type"] = g_product_type.text.strip()

            # Price & Sale Price
            g_price = item.find("g:price", namespaces=namespaces)
            product_data["price"] = parse_price_value(g_price)

            g_sale_price = item.find("g:sale_price", namespaces=namespaces)
            product_data["sale_price"] = parse_price_value(g_sale_price)

            # Collect contextual keywords into ads_metadata (useful for ChatGPT Ad targeting)
            meta_attributes = []
            if product_data["brand"]:
                meta_attributes.append(f"brand:{product_data['brand']}")

            g_color = item.find("g:color", namespaces=namespaces)
            if g_color is not None and g_color.text:
                meta_attributes.append(f"color:{g_color.text.strip()}")

            for i in range(5):
                custom_label = item.find(f"custom_label_{i}")
                if custom_label is not None and custom_label.text:
                    meta_attributes.append(custom_label.text.strip())

            product_data["ads_metadata"] = ";".join(meta_attributes)

            products_by_category[category_key].append(product_data)

    # Column ordering according to standard ChatGPT product feed specifications
    chatgpt_columns_order = [
        "item_id",
        "title",
        "description",
        "url",
        "image_url",
        "brand",
        "price",
        "sale_price",
        "availability",
        "google_product_category",
        "product_type",
        "is_ads_eligible",
        "enable_search",
        "ads_metadata",
    ]

    success = True
    for category, product_list in products_by_category.items():
        if product_list:
            output_csv_file = f"{output_csv_base}_{category}.csv"
            df = pd.DataFrame(product_list)
            df = df.reindex(columns=chatgpt_columns_order)

            print(
                f"Saving {len(product_list)} items for {category.capitalize()} to {output_csv_file}..."
            )
            try:
                # UTF-8 encoding without BOM is required for OpenAI feed ingestion
                df.to_csv(
                    output_csv_file,
                    index=False,
                    encoding="utf-8",
                    sep=",",
                    doublequote=True,
                    quoting=csv.QUOTE_MINIMAL,
                )
                print(f"Successfully generated: {output_csv_file}")
            except IOError as e:
                print(f"Error saving CSV: {e}")
                success = False
        else:
            print(f"No products found for '{category.capitalize()}'.")

    return success


if __name__ == "__main__":
    cropink_feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        "https://backend.ballzy.eu/et/amfeed/feed/download?id=102&file=cropink_et.xml",
    )
    output_csv_base = os.environ.get("OUTPUT_CSV_BASE", "chatgpt_ads_feed")

    if transform_cropink_to_chatgpt_ads_csv(cropink_feed_url, output_csv_base):
        print("ChatGPT Ads feed transformation completed successfully.")
    else:
        print("ChatGPT Ads feed transformation failed.")
