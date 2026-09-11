import csv
import os
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_CROPINK_FEED_URL = (
    "https://backend.ballzy.eu/et/amfeed/feed/download"
    "?id=102&file=cropink_et.xml"
)

DEFAULT_SELLER_NAME = "Ballzy"
DEFAULT_OUTPUT_CSV_BASE = "chatgpt_ads_feed"

REQUEST_TIMEOUT = 120


# ============================================================
# HELPERS
# ============================================================

def clean_text(text):
    """
    Remove HTML tags and normalize whitespace.
    """

    if not text:
        return ""

    text = str(text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace
    text = " ".join(text.split())

    return text.strip()


def force_https(url):
    """
    Convert HTTP URLs to HTTPS.

    Example:
        http://ballzy.eu/product/123
    becomes:
        https://ballzy.eu/product/123
    """

    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


def parse_price_value(price_element):
    """
    Read Google-style price values.

    Examples:

        120.00 EUR
        120 EUR
        1,299.99 EUR

    Returns the original normalized price string.
    """

    if price_element is None:
        return ""

    if not price_element.text:
        return ""

    price_text = price_element.text.strip()

    # Normalize whitespace
    price_text = " ".join(price_text.split())

    # Match amount + ISO currency
    match = re.match(
        r"^([\d.,]+)\s*([A-Za-z]{3})$",
        price_text,
    )

    if match:
        amount = match.group(1)
        currency = match.group(2).upper()

        return f"{amount} {currency}"

    return price_text


def parse_availability(availability_element):
    """
    Convert Google availability values into the
    OpenAI-style availability values.
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
    Safely extract text from an XML element.
    """

    element = item.find(
        xpath,
        namespaces=namespaces,
    )

    if element is not None and element.text:
        return element.text.strip()

    return ""


def is_valid_https_url(url):
    """
    Check whether a URL is HTTPS.
    """

    if not url:
        return False

    return url.lower().startswith("https://")


# ============================================================
# DOWNLOAD CROPINK FEED
# ============================================================

def download_cropink_feed(url):
    """
    Download Cropink XML feed.
    """

    print("=" * 70)
    print("DOWNLOADING CROPINK FEED")
    print("=" * 70)

    print()
    print(f"URL: {url}")

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Ballzy-ChatGPT-Ads-Feed/1.0"
                )
            },
        )

        response.raise_for_status()

        data = response.content

        print(
            f"Download successful: {len(data):,} bytes"
        )

        return data

    except requests.exceptions.RequestException as error:

        print()
        print("ERROR: Failed to download Cropink feed.")
        print(error)

        return None


# ============================================================
# PARSE XML
# ============================================================

def parse_cropink_xml(data):
    """
    Parse downloaded XML.
    """

    print()
    print("=" * 70)
    print("PARSING XML")
    print("=" * 70)

    try:

        root = ET.fromstring(data)

        print("XML parsed successfully.")

        return root

    except ET.ParseError as error:

        print()
        print("ERROR: Invalid XML.")
        print(error)

        return None


# ============================================================
# CREATE PRODUCT
# ============================================================

def create_product(
    item,
    namespaces,
    seller_name,
):
    """
    Convert one Cropink XML item into a ChatGPT Ads product.
    """

    item_id = get_text(
        item,
        "g:id",
        namespaces,
    )

    title = clean_text(
        get_text(
            item,
            "g:title",
            namespaces,
        )
    )

    description = clean_text(
        get_text(
            item,
            "g:description",
            namespaces,
        )
    )

    # Product URL
    url = force_https(
        get_text(
            item,
            "g:link",
            namespaces,
        )
    )

    # Product image URL
    image_url = force_https(
        get_text(
            item,
            "g:image_link",
            namespaces,
        )
    )

    brand = clean_text(
        get_text(
            item,
            "g:brand",
            namespaces,
        )
    )

    # Availability
    availability_element = item.find(
        "g:availability",
        namespaces,
    )

    availability = parse_availability(
        availability_element
    )

    # Price
    price_element = item.find(
        "g:price",
        namespaces,
    )

    price = parse_price_value(
        price_element
    )

    # Sale price
    sale_price_element = item.find(
        "g:sale_price",
        namespaces,
    )

    sale_price = parse_price_value(
        sale_price_element
    )

    # Google category
    google_product_category = clean_text(
        get_text(
            item,
            "g:google_product_category",
            namespaces,
        )
    )

    # Product type
    product_type = clean_text(
        get_text(
            item,
            "g:product_type",
            namespaces,
        )
    )

    # ========================================================
    # CATEGORY
    # ========================================================

    category = ""

    custom_label_0 = item.find(
        "custom_label_0"
    )

    if (
        custom_label_0 is not None
        and custom_label_0.text
    ):

        label = (
            custom_label_0.text
            .strip()
            .lower()
        )

        if "basketball" in label:

            category = "basketball"

        elif "lifestyle" in label:

            category = "lifestyle"

    # ========================================================
    # METADATA
    # ========================================================

    metadata = []

    if brand:
        metadata.append(
            f"brand:{brand}"
        )

    if category:
        metadata.append(
            f"category:{category}"
        )

    if google_product_category:
        metadata.append(
            f"google_product_category:{google_product_category}"
        )

    if product_type:
        metadata.append(
            f"product_type:{product_type}"
        )

    # Color
    color = clean_text(
        get_text(
            item,
            "g:color",
            namespaces,
        )
    )

    if color:
        metadata.append(
            f"color:{color}"
        )

    # Custom labels 0-4
    for index in range(5):

        label_element = item.find(
            f"custom_label_{index}"
        )

        if (
            label_element is not None
            and label_element.text
        ):

            label_value = clean_text(
                label_element.text
            )

            if label_value:
                metadata.append(
                    f"custom_label_{index}:{label_value}"
                )

    ads_metadata = ";".join(metadata)

    # ========================================================
    # PRODUCT OBJECT
    # ========================================================

    return {
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
        "ads_metadata": ads_metadata,
    }


# ============================================================
# VALIDATE PRODUCT
# ============================================================

def validate_product(product):
    """
    Validate the important product fields.

    Returns:
        list of errors
    """

    errors = []

    required_fields = [
        "item_id",
        "title",
        "description",
        "url",
        "seller_name",
        "image_url",
        "availability",
        "price",
    ]

    for field in required_fields:

        if not str(
            product.get(field, "")
        ).strip():

            errors.append(
                f"missing {field}"
            )

    # HTTPS product URL
    if product.get("url"):

        if not is_valid_https_url(
            product["url"]
        ):

            errors.append(
                "product URL is not HTTPS"
            )

    # HTTPS image URL
    if product.get("image_url"):

        if not is_valid_https_url(
            product["image_url"]
        ):

            errors.append(
                "image URL is not HTTPS"
            )

    # Availability
    valid_availability = {
        "in_stock",
        "out_of_stock",
        "pre_order",
        "backorder",
    }

    if (
        product.get("availability")
        not in valid_availability
    ):

        errors.append(
            "invalid availability"
        )

    # Ads eligibility
    if (
        product.get("is_ads_eligible")
        != "true"
    ):

        errors.append(
            "is_ads_eligible is not true"
        )

    return errors


# ============================================================
# PROCESS XML
# ============================================================

def process_products(
    root,
    seller_name,
):
    """
    Process all XML products and split them
    into lifestyle and basketball feeds.
    """

    print()
    print("=" * 70)
    print("PROCESSING PRODUCTS")
    print("=" * 70)

    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    products_by_category = {
        "basketball": [],
        "lifestyle": [],
    }

    total_items = 0
    ignored_items = 0

    invalid_products = 0

    validation_examples = []

    for item in root.findall(".//item"):

        total_items += 1

        # Determine category
        custom_label_0 = item.find(
            "custom_label_0"
        )

        category = None

        if (
            custom_label_0 is not None
            and custom_label_0.text
        ):

            label = (
                custom_label_0.text
                .strip()
                .lower()
            )

            if "basketball" in label:

                category = "basketball"

            elif "lifestyle" in label:

                category = "lifestyle"

        # Skip unknown categories
        if category is None:

            ignored_items += 1

            continue

        # Create product
        product = create_product(
            item=item,
            namespaces=namespaces,
            seller_name=seller_name,
        )

        # Validate
        errors = validate_product(
            product
        )

        if errors:

            invalid_products += 1

            if len(validation_examples) < 10:

                validation_examples.append(
                    (
                        product.get(
                            "item_id",
                            "UNKNOWN",
                        ),
                        errors,
                    )
                )

            # Do not include invalid products
            continue

        products_by_category[
            category
        ].append(product)

    print()
    print(
        f"Total XML items:       {total_items:,}"
    )

    print(
        f"Ignored categories:    {ignored_items:,}"
    )

    print(
        f"Invalid products:      {invalid_products:,}"
    )

    print(
        f"Valid basketball:      "
        f"{len(products_by_category['basketball']):,}"
    )

    print(
        f"Valid lifestyle:       "
        f"{len(products_by_category['lifestyle']):,}"
    )

    # Print validation examples
    if validation_examples:

        print()
        print("First validation errors:")

        for item_id, errors in validation_examples:

            print(
                f"  {item_id}: "
                f"{', '.join(errors)}"
            )

    return products_by_category


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    products,
    filename,
):
    """
    Save product list as UTF-8 CSV.
    """

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

    print()
    print(
        f"Saving {filename}..."
    )

    df = pd.DataFrame(
        products,
        columns=columns,
    )

    # Force exact column order
    df = df.reindex(
        columns=columns
    )

    try:

        df.to_csv(
            filename,
            index=False,
            encoding="utf-8",
            sep=",",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

    except Exception as error:

        print()
        print(
            f"ERROR writing {filename}"
        )

        print(error)

        return False

    file_size = os.path.getsize(
        filename
    )

    print(
        f"Saved successfully: {filename}"
    )

    print(
        f"Products: {len(df):,}"
    )

    print(
        f"File size: {file_size:,} bytes"
    )

    # Print header
    print()
    print("CSV header:")

    print(
        ",".join(columns)
    )

    # Print first product
    if len(df) > 0:

        print()
        print("First product:")

        first = df.iloc[0]

        print(
            f"item_id:       {first['item_id']}"
        )

        print(
            f"title:         {first['title']}"
        )

        print(
            f"url:           {first['url']}"
        )

        print(
            f"brand:         {first['brand']}"
        )

        print(
            f"seller_name:   {first['seller_name']}"
        )

        print(
            f"image_url:     {first['image_url']}"
        )

        print(
            f"availability:  {first['availability']}"
        )

        print(
            f"price:         {first['price']}"
        )

        print(
            f"sale_price:    {first['sale_price']}"
        )

        print(
            f"ads_eligible:  {first['is_ads_eligible']}"
        )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("CHATGPT ADS PRODUCT FEED GENERATOR")
    print("=" * 70)

    # Environment variables
    cropink_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    seller_name = os.environ.get(
        "SELLER_NAME",
        DEFAULT_SELLER_NAME,
    )

    output_csv_base = os.environ.get(
        "OUTPUT_CSV_BASE",
        DEFAULT_OUTPUT_CSV_BASE,
    )

    print()
    print(
        f"Seller name: {seller_name}"
    )

    print(
        f"Output base: {output_csv_base}"
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    data = download_cropink_feed(
        cropink_url
    )

    if data is None:

        print()
        print("FEED GENERATION FAILED.")

        return False

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    root = parse_cropink_xml(
        data
    )

    if root is None:

        print()
        print("FEED GENERATION FAILED.")

        return False

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    products_by_category = process_products(
        root=root,
        seller_name=seller_name,
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    success = True

    for category in [
        "lifestyle",
        "basketball",
    ]:

        products = products_by_category[
            category
        ]

        if not products:

            print()
            print(
                f"WARNING: No valid {category} "
                f"products found."
            )

            continue

        filename = (
            f"{output_csv_base}_{category}.csv"
        )

        result = save_csv(
            products=products,
            filename=filename,
        )

        if not result:

            success = False

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print()
    print("=" * 70)

    if success:

        print("CHATGPT ADS FEED GENERATION COMPLETE")

        print("=" * 70)

        print()
        print(
            "Generated files:"
        )

        for category in [
            "lifestyle",
            "basketball",
        ]:

            filename = (
                f"{output_csv_base}_{category}.csv"
            )

            if os.path.exists(filename):

                print(
                    f"  {filename}"
                )

    else:

        print(
            "CHATGPT ADS FEED GENERATION FAILED"
        )

        print("=" * 70)

    print()

    return success


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    success = main()

    if not success:

        sys.exit(1)
