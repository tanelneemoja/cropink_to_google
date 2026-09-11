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
    "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4"
)

DEFAULT_SELLER_NAME = "Ballzy"
DEFAULT_OUTPUT_CSV_BASE = "chatgpt_ads_feed"

REQUEST_TIMEOUT = 120

# Number of products in the diagnostic test feed
TEST_PRODUCT_COUNT = 5

# ============================================================
# OPENAI ADS FEED COLUMNS
# ============================================================

CHATGPT_COLUMNS = [
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


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """
    Remove HTML tags, control characters and normalize whitespace.
    """

    if not text:
        return ""

    text = str(text)

    # Remove HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove problematic control characters
    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text,
    )

    # Normalize whitespace
    text = " ".join(text.split())

    return text.strip()


# ============================================================
# URL
# ============================================================

def force_https(url):
    """
    Convert HTTP URLs to HTTPS.
    """

    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


def is_valid_https_url(url):
    """
    Check that URL is HTTPS.
    """

    if not url:
        return False

    return url.lower().startswith("https://")


# ============================================================
# XML HELPERS
# ============================================================

def get_text(item, xpath, namespaces=None):
    """
    Safely retrieve XML element text.
    """

    element = item.find(
        xpath,
        namespaces=namespaces,
    )

    if element is not None and element.text:
        return element.text.strip()

    return ""


# ============================================================
# PRICE
# ============================================================

def parse_price_value(price_element):
    """
    Convert price into:

        17.00 EUR

    No thousands separators.
    ISO 4217 currency code.
    """

    if price_element is None:
        return ""

    if not price_element.text:
        return ""

    price_text = " ".join(
        price_element.text.strip().split()
    )

    # Accept:
    # 17 EUR
    # 17.00 EUR
    # 17.5 EUR

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})$",
        price_text,
    )

    if not match:
        print(
            f"WARNING: Could not parse price: "
            f"{price_text}"
        )
        return ""

    amount = match.group(1)
    currency = match.group(2).upper()

    return f"{amount} {currency}"


# ============================================================
# AVAILABILITY
# ============================================================

def parse_availability(availability_element):
    """
    Convert Google availability to standard values.
    """

    if availability_element is None:
        return "in_stock"

    if not availability_element.text:
        return "in_stock"

    value = (
        availability_element.text
        .strip()
        .lower()
    )

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

    return mapping.get(
        value,
        "in_stock",
    )


# ============================================================
# DOWNLOAD
# ============================================================

def download_cropink_feed(url):

    print()
    print("=" * 70)
    print("DOWNLOADING CROPINK FEED")
    print("=" * 70)

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
            f"Download successful: "
            f"{len(data):,} bytes"
        )

        return data

    except requests.exceptions.RequestException as error:

        print()
        print(
            "ERROR: Failed to download Cropink feed."
        )

        print(error)

        return None


# ============================================================
# XML PARSER
# ============================================================

def parse_cropink_xml(data):

    print()
    print("=" * 70)
    print("PARSING XML")
    print("=" * 70)

    try:

        root = ET.fromstring(data)

        print(
            "XML parsed successfully."
        )

        return root

    except ET.ParseError as error:

        print()
        print(
            "ERROR: Invalid XML."
        )

        print(error)

        return None


# ============================================================
# CATEGORY
# ============================================================

def get_product_category(item):

    custom_label_0 = item.find(
        "custom_label_0"
    )

    if (
        custom_label_0 is None
        or not custom_label_0.text
    ):
        return None

    label = (
        custom_label_0.text
        .strip()
        .lower()
    )

    if "basketball" in label:
        return "basketball"

    if "lifestyle" in label:
        return "lifestyle"

    return None


# ============================================================
# CREATE PRODUCT
# ============================================================

def create_product(
    item,
    namespaces,
    seller_name,
    category,
):

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

    url = force_https(
        get_text(
            item,
            "g:link",
            namespaces,
        )
    )

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

    availability_element = item.find(
        "g:availability",
        namespaces,
    )

    availability = parse_availability(
        availability_element
    )

    price_element = item.find(
        "g:price",
        namespaces,
    )

    price = parse_price_value(
        price_element
    )

    sale_price_element = item.find(
        "g:sale_price",
        namespaces,
    )

    sale_price = parse_price_value(
        sale_price_element
    )

    # --------------------------------------------------------
    # COLOR
    # --------------------------------------------------------

    color = clean_text(
        get_text(
            item,
            "g:color",
            namespaces,
        )
    )

    # --------------------------------------------------------
    # SIMPLE METADATA
    #
    # For this diagnostic test we deliberately keep
    # metadata simple.
    # --------------------------------------------------------

    metadata_parts = []

    if brand:
        metadata_parts.append(
            f"brand:{brand}"
        )

    if category:
        metadata_parts.append(
            f"category:{category}"
        )

    if color:
        metadata_parts.append(
            f"color:{color}"
        )

    ads_metadata = ";".join(
        metadata_parts
    )

    # --------------------------------------------------------
    # PRODUCT
    # --------------------------------------------------------

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
# VALIDATION
# ============================================================

def validate_product(product):

    errors = []

    required_fields = [
        "item_id",
        "title",
        "description",
        "url",
        "brand",
        "seller_name",
        "image_url",
        "availability",
        "price",
        "is_ads_eligible",
    ]

    for field in required_fields:

        value = product.get(
            field,
            "",
        )

        if not str(value).strip():

            errors.append(
                f"missing {field}"
            )

    # HTTPS product URL

    if product.get("url"):

        if not is_valid_https_url(
            product["url"]
        ):

            errors.append(
                "url is not HTTPS"
            )

    # HTTPS image URL

    if product.get("image_url"):

        if not is_valid_https_url(
            product["image_url"]
        ):

            errors.append(
                "image_url is not HTTPS"
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

    # Seller

    if product.get(
        "seller_name"
    ) != "Ballzy":

        errors.append(
            "seller_name is not Ballzy"
        )

    # Ads eligibility

    if (
        product.get(
            "is_ads_eligible"
        )
        != "true"
    ):

        errors.append(
            "is_ads_eligible is not true"
        )

    # Price format

    price = product.get(
        "price",
        "",
    )

    if price:

        if not re.match(
            r"^[0-9]+(?:\.[0-9]+)? [A-Z]{3}$",
            price,
        ):

            errors.append(
                "invalid price format"
            )

    return errors


# ============================================================
# PROCESS PRODUCTS
# ============================================================

def process_products(
    root,
    seller_name,
):

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

    for item in root.findall(
        ".//item"
    ):

        total_items += 1

        category = get_product_category(
            item
        )

        if category is None:

            ignored_items += 1

            continue

        product = create_product(
            item=item,
            namespaces=namespaces,
            seller_name=seller_name,
            category=category,
        )

        errors = validate_product(
            product
        )

        if errors:

            invalid_products += 1

            if len(
                validation_examples
            ) < 10:

                validation_examples.append(
                    (
                        product.get(
                            "item_id",
                            "UNKNOWN",
                        ),
                        errors,
                    )
                )

            continue

        products_by_category[
            category
        ].append(product)

    print()
    print(
        f"Total XML items:       "
        f"{total_items:,}"
    )

    print(
        f"Ignored categories:    "
        f"{ignored_items:,}"
    )

    print(
        f"Invalid products:      "
        f"{invalid_products:,}"
    )

    print(
        f"Valid basketball:      "
        f"{len(products_by_category['basketball']):,}"
    )

    print(
        f"Valid lifestyle:       "
        f"{len(products_by_category['lifestyle']):,}"
    )

    if validation_examples:

        print()
        print(
            "First validation errors:"
        )

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

    print()
    print(
        f"Saving {filename}..."
    )

    df = pd.DataFrame(
        products,
        columns=CHATGPT_COLUMNS,
    )

    df = df.reindex(
        columns=CHATGPT_COLUMNS
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
        f"Saved successfully: "
        f"{filename}"
    )

    print(
        f"Products: "
        f"{len(df):,}"
    )

    print(
        f"File size: "
        f"{file_size:,} bytes"
    )

    return True


# ============================================================
# CREATE 5-PRODUCT TEST FEED
# ============================================================

def save_test_feed(
    products,
    filename="chatgpt_ads_test.csv",
):

    print()
    print("=" * 70)
    print("CREATING OPENAI ADS TEST FEED")
    print("=" * 70)

    test_products = products[
        :TEST_PRODUCT_COUNT
    ]

    if not test_products:

        print(
            "ERROR: No products available "
            "for test feed."
        )

        return False

    result = save_csv(
        products=test_products,
        filename=filename,
    )

    if not result:
        return False

    print()
    print(
        f"TEST FEED CONTAINS "
        f"{len(test_products)} PRODUCTS"
    )

    print()
    print(
        "Test products:"
    )

    for number, product in enumerate(
        test_products,
        start=1,
    ):

        print()
        print(
            f"Product #{number}"
        )

        print(
            f"  item_id: "
            f"{product['item_id']}"
        )

        print(
            f"  title: "
            f"{product['title']}"
        )

        print(
            f"  brand: "
            f"{product['brand']}"
        )

        print(
            f"  seller_name: "
            f"{product['seller_name']}"
        )

        print(
            f"  price: "
            f"{product['price']}"
        )

        print(
            f"  availability: "
            f"{product['availability']}"
        )

        print(
            f"  is_ads_eligible: "
            f"{product['is_ads_eligible']}"
        )

        print(
            f"  url: "
            f"{product['url']}"
        )

        print(
            f"  image_url: "
            f"{product['image_url']}"
        )

    return True


# ============================================================
# VERIFY CSV
# ============================================================

def verify_csv(
    filename,
):

    print()
    print("=" * 70)
    print(
        f"VERIFYING {filename}"
    )
    print("=" * 70)

    if not os.path.exists(filename):

        print(
            f"ERROR: File does not exist: "
            f"{filename}"
        )

        return False

    try:

        df = pd.read_csv(
            filename,
            dtype=str,
            keep_default_na=False,
        )

    except Exception as error:

        print(
            "ERROR: Could not read CSV."
        )

        print(error)

        return False

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Columns: {list(df.columns)}"
    )

    # Exact columns

    if list(df.columns) != CHATGPT_COLUMNS:

        print()
        print(
            "ERROR: CSV columns are not "
            "exactly as expected."
        )

        return False

    # Seller

    sellers = (
        df["seller_name"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Seller names: {sellers}"
    )

    if sellers != ["Ballzy"]:

        print(
            "ERROR: Seller name check failed."
        )

        return False

    # Ads eligibility

    ads_values = (
        df["is_ads_eligible"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Ads eligibility values: "
        f"{ads_values}"
    )

    if ads_values != ["true"]:

        print(
            "ERROR: is_ads_eligible check failed."
        )

        return False

    # Availability

    availability_values = (
        df["availability"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Availability values: "
        f"{availability_values}"
    )

    # HTTPS URLs

    bad_urls = df[
        ~df["url"].str.startswith(
            "https://",
            na=False,
        )
    ]

    if len(bad_urls) > 0:

        print(
            f"ERROR: {len(bad_urls)} "
            f"product URLs are not HTTPS."
        )

        return False

    bad_images = df[
        ~df["image_url"].str.startswith(
            "https://",
            na=False,
        )
    ]

    if len(bad_images) > 0:

        print(
            f"ERROR: {len(bad_images)} "
            f"image URLs are not HTTPS."
        )

        return False

    # Required values

    for column in [
        "item_id",
        "title",
        "description",
        "url",
        "brand",
        "seller_name",
        "image_url",
        "availability",
        "price",
        "is_ads_eligible",
    ]:

        empty_count = (
            df[column]
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
        )

        if empty_count:

            print(
                f"ERROR: {column} has "
                f"{empty_count} empty values."
            )

            return False

    print()
    print(
        f"OK: {filename}"
    )

    return True


# ============================================================
# PRINT SAMPLE
# ============================================================

def print_sample(filename):

    print()
    print("=" * 70)
    print(
        f"SAMPLE FROM {filename}"
    )
    print("=" * 70)

    try:

        df = pd.read_csv(
            filename,
            dtype=str,
            keep_default_na=False,
        )

        print()
        print(
            "HEADER:"
        )

        print(
            ",".join(df.columns)
        )

        print()
        print(
            "FIRST PRODUCT:"
        )

        if len(df) > 0:

            print(
                df.iloc[0].to_string()
            )

    except Exception as error:

        print(
            f"Could not print sample: "
            f"{error}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "CHATGPT ADS PRODUCT FEED GENERATOR"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # ENVIRONMENT
    # --------------------------------------------------------

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

    print(
        f"Seller name: {seller_name}"
    )

    print(
        f"Output base: {output_csv_base}"
    )

    # --------------------------------------------------------
    # SELLER SAFETY CHECK
    # --------------------------------------------------------

    if seller_name != "Ballzy":

        print()
        print(
            "ERROR: SELLER_NAME must be Ballzy."
        )

        return False

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    data = download_cropink_feed(
        cropink_url
    )

    if data is None:
        return False

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

    root = parse_cropink_xml(
        data
    )

    if root is None:
        return False

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    products_by_category = process_products(
        root=root,
        seller_name=seller_name,
    )

    # --------------------------------------------------------
    # SAVE FULL FEEDS
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

        if not save_csv(
            products=products,
            filename=filename,
        ):

            success = False

    # --------------------------------------------------------
    # CREATE TEST FEED
    # --------------------------------------------------------

    if not save_test_feed(
        products_by_category["lifestyle"],
        "chatgpt_ads_test.csv",
    ):

        success = False

    # --------------------------------------------------------
    # VERIFY ALL FILES
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL CSV VERIFICATION")
    print("=" * 70)

    files_to_verify = [
        "chatgpt_ads_feed_lifestyle.csv",
        "chatgpt_ads_feed_basketball.csv",
        "chatgpt_ads_test.csv",
    ]

    for filename in files_to_verify:

        if os.path.exists(filename):

            if not verify_csv(
                filename
            ):

                success = False

            print_sample(
                filename
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()
    print("=" * 70)

    if success:

        print(
            "CHATGPT ADS FEED GENERATION COMPLETE"
        )

        print("=" * 70)

        print()
        print(
            "Generated files:"
        )

        for filename in files_to_verify:

            if os.path.exists(filename):

                size = os.path.getsize(
                    filename
                )

                print(
                    f"  {filename} "
                    f"({size:,} bytes)"
                )

        print()
        print(
            "IMPORTANT TEST URL:"
        )

        print(
            "https://tanelneemoja.github.io/"
            "cropink_to_google/"
            "chatgpt_ads_test.csv"
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
