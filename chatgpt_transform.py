import csv
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

# Your Cropink source feed
DEFAULT_CROPINK_FEED_URL = (
    "https://backend.ballzy.eu/et/amfeed/feed/download"
    "?id=102&file=cropink_et.xml"
)

# IMPORTANT:
# This should be the merchant/store name customers see.
# Change this if necessary.
DEFAULT_SELLER_NAME = "Ballzy"

# Output files
DEFAULT_OUTPUT_BASE = "chatgpt_ads_feed"


# ============================================================
# HELPERS
# ============================================================

def clean_text(text):
    """
    Remove HTML and normalize whitespace.
    """
    if not text:
        return ""

    clean = re.sub(r"<[^>]+>", " ", text)
    return " ".join(clean.split())


def parse_price_value(price_element):
    """
    Convert Google-style price such as:
        120.00 EUR

    into:
        120.00 EUR
    """
    if price_element is None or not price_element.text:
        return ""

    price_text = price_element.text.strip()

    match = re.match(
        r"([\d.,]+)\s*([A-Z]{3})$",
        price_text,
        re.IGNORECASE
    )

    if match:
        value = match.group(1)
        currency = match.group(2).upper()

        return f"{value} {currency}"

    return price_text


def parse_availability(availability_element):
    """
    Convert Google-style availability values to the
    OpenAI product feed values.
    """

    if availability_element is None:
        return "in_stock"

    if not availability_element.text:
        return "in_stock"

    value = availability_element.text.strip().lower()

    mapping = {
        "in stock": "in_stock",
        "in_stock": "in_stock",

        "out of stock": "out_of_stock",
        "out_of_stock": "out_of_stock",

        "preorder": "pre_order",
        "pre_order": "pre_order",

        "backorder": "backorder",
        "back_order": "backorder",
    }

    return mapping.get(value, "in_stock")


def get_text(item, xpath, namespaces=None):
    """
    Safely get XML element text.
    """
    element = item.find(xpath, namespaces=namespaces)

    if element is not None and element.text:
        return element.text.strip()

    return ""


# ============================================================
# MAIN TRANSFORMATION
# ============================================================

def transform_cropink_to_chatgpt_ads_csv(
    cropink_url,
    output_csv_base="chatgpt_ads_feed",
    seller_name="Ballzy",
):
    print("=" * 70)
    print("CHATGPT ADS PRODUCT FEED GENERATOR")
    print("=" * 70)

    print()
    print(f"Source feed:")
    print(cropink_url)

    print()
    print(f"Seller name:")
    print(seller_name)

    # --------------------------------------------------------
    # DOWNLOAD CROPINK XML
    # --------------------------------------------------------

    print()
    print("Downloading Cropink feed...")

    try:
        response = requests.get(
            cropink_url,
            timeout=120,
            headers={
                "User-Agent": "ChatGPT-Ads-Feed-Generator/1.0"
            },
        )

        response.raise_for_status()

        cropink_data = response.content

        print(
            f"Download successful: {len(cropink_data):,} bytes"
        )

    except requests.exceptions.RequestException as e:
        print()
        print("ERROR: Could not download Cropink feed.")
        print(e)
        return False

    # --------------------------------------------------------
    # PARSE XML
    # --------------------------------------------------------

    print()
    print("Parsing XML...")

    try:
        root = ET.fromstring(cropink_data)

        print("XML parsed successfully.")

    except ET.ParseError as e:
        print()
        print("ERROR: Cropink XML is invalid.")
        print(e)
        return False

    # Google namespace
    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    # --------------------------------------------------------
    # PRODUCT GROUPS
    # --------------------------------------------------------

    products_by_category = {
        "basketball": [],
        "lifestyle": [],
    }

    total_items = 0
    ignored_items = 0

    # --------------------------------------------------------
    # PROCESS PRODUCTS
    # --------------------------------------------------------

    print()
    print("Processing products...")

    for item in root.findall(".//item"):

        total_items += 1

        # ----------------------------------------------------
        # Determine category from custom_label_0
        # ----------------------------------------------------

        custom_label_0 = item.find("custom_label_0")

        category_key = None

        if custom_label_0 is not None and custom_label_0.text:

            label_text = custom_label_0.text.strip().lower()

            if "basketball" in label_text:
                category_key = "basketball"

            elif "lifestyle" in label_text:
                category_key = "lifestyle"

        # Ignore products that aren't in our two categories
        if category_key is None:
            ignored_items += 1
            continue

        # ----------------------------------------------------
        # Read Google product fields
        # ----------------------------------------------------

        item_id = get_text(
            item,
            "g:id",
            namespaces
        )

        title = clean_text(
            get_text(
                item,
                "g:title",
                namespaces
            )
        )

        description = clean_text(
            get_text(
                item,
                "g:description",
                namespaces
            )
        )

        url = get_text(
            item,
            "g:link",
            namespaces
        )

        image_url = get_text(
            item,
            "g:image_link",
            namespaces
        )

        brand = get_text(
            item,
            "g:brand",
            namespaces
        )

        availability_element = item.find(
            "g:availability",
            namespaces
        )

        availability = parse_availability(
            availability_element
        )

        price_element = item.find(
            "g:price",
            namespaces
        )

        price = parse_price_value(
            price_element
        )

        sale_price_element = item.find(
            "g:sale_price",
            namespaces
        )

        sale_price = parse_price_value(
            sale_price_element
        )

        google_product_category = get_text(
            item,
            "g:google_product_category",
            namespaces
        )

        product_type = get_text(
            item,
            "g:product_type",
            namespaces
        )

        # ----------------------------------------------------
        # Additional labels for ads metadata
        # ----------------------------------------------------

        metadata = {}

        if brand:
            metadata["brand"] = brand

        metadata["category"] = category_key

        if google_product_category:
            metadata["google_product_category"] = (
                google_product_category
            )

        if product_type:
            metadata["product_type"] = product_type

        # Color
        color = get_text(
            item,
            "g:color",
            namespaces
        )

        if color:
            metadata["color"] = color

        # Custom labels
        for i in range(5):

            label = item.find(
                f"custom_label_{i}"
            )

            if label is not None and label.text:

                value = label.text.strip()

                if value:
                    metadata[
                        f"custom_label_{i}"
                    ] = value

        # ----------------------------------------------------
        # Create OpenAI Ads product
        # ----------------------------------------------------

        product_data = {
            "item_id": item_id,
            "title": title,
            "description": description,
            "url": url,
            "brand": brand,
            "seller_name": seller_name,
            "image_url": image_url,
            "availability": availability,
            "price": price,
            "sale_price": sale_price,
            "is_ads_eligible": "true",
            "ads_metadata": ";".join(
                f"{key}:{value}"
                for key, value in metadata.items()
            ),
        }

        products_by_category[
            category_key
        ].append(product_data)

    # --------------------------------------------------------
    # OUTPUT COLUMNS
    # --------------------------------------------------------

    columns = [
        "item_id",
        "title",
        "description",
        "url",
        "brand",
        "seller_name",
        "image_url",
        "availability",
        "price",
        "sale_price",
        "is_ads_eligible",
        "ads_metadata",
    ]

    # --------------------------------------------------------
    # SAVE FILES
    # --------------------------------------------------------

    success = True

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)

    print()
    print(f"Total XML items: {total_items:,}")
    print(f"Ignored items:   {ignored_items:,}")

    for category, product_list in products_by_category.items():

        if not product_list:

            print()
            print(
                f"No products found for: {category}"
            )

            continue

        output_file = (
            f"{output_csv_base}_{category}.csv"
        )

        print()
        print(
            f"{category.upper()}: "
            f"{len(product_list):,} products"
        )

        df = pd.DataFrame(product_list)

        df = df.reindex(
            columns=columns
        )

        try:

            df.to_csv(
                output_file,
                index=False,
                encoding="utf-8",
                sep=",",
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\n",
            )

            file_size = os.path.getsize(
                output_file
            )

            print(
                f"Saved: {output_file}"
            )

            print(
                f"Size:  {file_size:,} bytes"
            )

        except IOError as e:

            print(
                f"ERROR saving {output_file}: {e}"
            )

            success = False

    print()

    if success:

        print("=" * 70)
        print("SUCCESS")
        print("=" * 70)

    else:

        print("=" * 70)
        print("FAILED")
        print("=" * 70)

    return success


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    cropink_feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    seller_name = os.environ.get(
        "SELLER_NAME",
        DEFAULT_SELLER_NAME,
    )

    output_csv_base = os.environ.get(
        "OUTPUT_CSV_BASE",
        DEFAULT_OUTPUT_BASE,
    )

    success = transform_cropink_to_chatgpt_ads_csv(
        cropink_url=cropink_feed_url,
        output_csv_base=output_csv_base,
        seller_name=seller_name,
    )

    if not success:
        raise SystemExit(1)
