import csv
import json
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

# Number of products in diagnostic feed
TEST_PRODUCT_COUNT = 5


# ============================================================
# OPENAI ADS FEED COLUMNS
# ============================================================

# Minimal diagnostic schema.
# Use this first to isolate any OpenAI validation problem.
TEST_COLUMNS = [
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

# Full feed schema after the minimal test is accepted.
FULL_COLUMNS = [
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
    Remove HTML, invalid control characters and normalize whitespace.
    """
    if not text:
        return ""

    text = str(text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove control characters not allowed in normal text
    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text,
    )

    # Normalize whitespace
    text = " ".join(text.split())

    return text.strip()


# ============================================================
# URL HELPERS
# ============================================================

def force_https(url):
    """
    Convert HTTP URL to HTTPS.
    """
    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


def is_valid_https_url(url):
    """
    Check whether the URL uses HTTPS.
    """
    if not url:
        return False

    return url.lower().startswith("https://")


# ============================================================
# XML HELPERS
# ============================================================

def get_text(item, xpath, namespaces=None):
    """
    Safely return text from an XML element.
    """
    element = item.find(xpath, namespaces=namespaces)

    if element is not None and element.text:
        return element.text.strip()

    return ""


# ============================================================
# PRICE HELPERS
# ============================================================

def parse_price_value(price_element):
    """
    Convert source price to:
        17.00 EUR

    Accepts:
        17 EUR
        17.00 EUR
        17.5 EUR
    """
    if price_element is None or not price_element.text:
        return ""

    price_text = " ".join(price_element.text.strip().split())

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})$",
        price_text,
    )

    if not match:
        print(f"WARNING: Could not parse price: {price_text}")
        return ""

    amount = match.group(1)
    currency = match.group(2).upper()

    return f"{amount} {currency}"


def parse_money(price_string):
    """
    Parse:
        99.99 EUR

    Returns:
        (99.99, "EUR")

    or None if invalid.
    """
    if not price_string:
        return None

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?) ([A-Z]{3})$",
        price_string.strip(),
    )

    if not match:
        return None

    return float(match.group(1)), match.group(2)


def validate_sale_price(price, sale_price):
    """
    Return a valid sale_price or blank.

    Sale price must:
    - be positive
    - use same currency
    - be strictly lower than regular price
    """
    if not sale_price:
        return ""

    regular = parse_money(price)
    sale = parse_money(sale_price)

    if not regular or not sale:
        return ""

    regular_amount, regular_currency = regular
    sale_amount, sale_currency = sale

    if regular_amount <= 0:
        return ""

    if sale_amount <= 0:
        return ""

    if regular_currency != sale_currency:
        return ""

    if sale_amount >= regular_amount:
        return ""

    return sale_price


# ============================================================
# AVAILABILITY
# ============================================================

def parse_availability(availability_element):
    """
    Map source availability values to OpenAI-native values.
    """
    if availability_element is None or not availability_element.text:
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
                "User-Agent": "Ballzy-ChatGPT-Ads-Feed/1.0",
                "Accept": "application/xml,text/xml,*/*",
            },
        )

        response.raise_for_status()

        data = response.content

        print(f"Download successful: {len(data):,} bytes")

        return data

    except requests.exceptions.RequestException as error:
        print()
        print("ERROR: Failed to download Cropink feed.")
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
        print("XML parsed successfully.")
        return root

    except ET.ParseError as error:
        print()
        print("ERROR: Invalid XML.")
        print(error)
        return None


# ============================================================
# CATEGORY
# ============================================================

def get_product_category(item):
    """
    Determine whether product belongs to Basketball or Lifestyle.

    Supports both:
        <custom_label_0>
    and
        <g:custom_label_0>
    """

    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    label = get_text(item, "custom_label_0")

    if not label:
        label = get_text(
            item,
            "g:custom_label_0",
            namespaces,
        )

    label = label.strip().lower()

    if "basketball" in label:
        return "basketball"

    if "lifestyle" in label:
        return "lifestyle"

    return None


# ============================================================
# CUSTOM LABEL HELPER
# ============================================================

def get_custom_label(item, index, namespaces):
    """
    Try both unnamespaced and Google-namespaced custom labels.
    """

    value = get_text(
        item,
        f"custom_label_{index}",
    )

    if value:
        return clean_text(value)

    value = get_text(
        item,
        f"g:custom_label_{index}",
        namespaces,
    )

    return clean_text(value)


# ============================================================
# CREATE PRODUCT
# ============================================================

def create_product(
    item,
    namespaces,
    seller_name,
    category,
):

    item_id = clean_text(
        get_text(
            item,
            "g:id",
            namespaces,
        )
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

    raw_sale_price = parse_price_value(
        sale_price_element
    )

    sale_price = validate_sale_price(
        price,
        raw_sale_price,
    )

    # --------------------------------------------------------
    # OPTIONAL ATTRIBUTES FOR ADS METADATA
    # --------------------------------------------------------

    color = clean_text(
        get_text(
            item,
            "g:color",
            namespaces,
        )
    )

    product_type = clean_text(
        get_text(
            item,
            "g:product_type",
            namespaces,
        )
    )

    google_product_category = clean_text(
        get_text(
            item,
            "g:google_product_category",
            namespaces,
        )
    )

    custom_labels = {}

    for i in range(5):
        value = get_custom_label(
            item,
            i,
            namespaces,
        )

        if value:
            custom_labels[f"custom_label_{i}"] = value

    # --------------------------------------------------------
    # ADS METADATA
    # --------------------------------------------------------
    #
    # IMPORTANT:
    # This must be valid JSON inside the CSV cell.
    #
    # Example:
    # {"business_line":"lifestyle","brand":"adidas"}
    #
    # pandas will quote it correctly in the final CSV.
    # --------------------------------------------------------

    metadata = {}

    if category:
        metadata["business_line"] = category

    if brand:
        metadata["brand"] = brand

    if color:
        metadata["color"] = color

    if product_type:
        metadata["product_type"] = product_type

    if google_product_category:
        metadata["google_product_category"] = google_product_category

    for key, value in custom_labels.items():
        metadata[key] = value

    ads_metadata = json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
    )

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
# PRODUCT VALIDATION
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
        value = product.get(field, "")

        if not str(value).strip():
            errors.append(f"missing {field}")

    # --------------------------------------------------------
    # HTTPS
    # --------------------------------------------------------

    if product.get("url"):
        if not is_valid_https_url(product["url"]):
            errors.append("url is not HTTPS")

    if product.get("image_url"):
        if not is_valid_https_url(product["image_url"]):
            errors.append("image_url is not HTTPS")

    # --------------------------------------------------------
    # AVAILABILITY
    # --------------------------------------------------------

    valid_availability = {
        "in_stock",
        "out_of_stock",
        "pre_order",
        "backorder",
    }

    if product.get("availability") not in valid_availability:
        errors.append("invalid availability")

    # --------------------------------------------------------
    # SELLER
    # --------------------------------------------------------

    if product.get("seller_name") != "Ballzy":
        errors.append("seller_name is not Ballzy")

    # --------------------------------------------------------
    # ADS ELIGIBILITY
    # --------------------------------------------------------

    if product.get("is_ads_eligible") != "true":
        errors.append("is_ads_eligible is not true")

    # --------------------------------------------------------
    # REGULAR PRICE
    # --------------------------------------------------------

    price = product.get("price", "")

    price_info = parse_money(price)

    if not price_info:
        errors.append("invalid price format")
    else:
        amount, _ = price_info

        if amount <= 0:
            errors.append("price must be greater than zero")

    # --------------------------------------------------------
    # SALE PRICE
    # --------------------------------------------------------

    sale_price = product.get("sale_price", "")

    if sale_price:
        regular = parse_money(price)
        sale = parse_money(sale_price)

        if not regular or not sale:
            errors.append("invalid sale_price format")

        else:
            regular_amount, regular_currency = regular
            sale_amount, sale_currency = sale

            if sale_currency != regular_currency:
                errors.append(
                    "sale_price currency differs from price"
                )

            if sale_amount <= 0:
                errors.append(
                    "sale_price must be greater than zero"
                )

            if sale_amount >= regular_amount:
                errors.append(
                    "sale_price must be below price"
                )

    # --------------------------------------------------------
    # JSON METADATA
    # --------------------------------------------------------

    ads_metadata = product.get(
        "ads_metadata",
        "",
    )

    if ads_metadata:
        try:
            parsed = json.loads(
                ads_metadata
            )

            if not isinstance(parsed, dict):
                errors.append(
                    "ads_metadata is not a JSON object"
                )

            else:
                for key, value in parsed.items():

                    if not isinstance(key, str):
                        errors.append(
                            "ads_metadata key is not string"
                        )

                    if not isinstance(value, str):
                        errors.append(
                            f"ads_metadata value for {key} "
                            "is not string"
                        )

        except json.JSONDecodeError:
            errors.append(
                "ads_metadata contains invalid JSON"
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

    for item in root.findall(".//item"):

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

            if len(validation_examples) < 20:
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
    columns,
):

    print()
    print(f"Saving {filename}...")

    df = pd.DataFrame(
        products
    )

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
            doublequote=True,
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
# CREATE MINIMAL TEST FEED
# ============================================================

def save_test_feed(
    products,
    filename="chatgpt_ads_test.csv",
):

    print()
    print("=" * 70)
    print("CREATING MINIMAL OPENAI ADS TEST FEED")
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

    # Deliberately only use minimal required fields.
    minimal_products = []

    for product in test_products:

        minimal_product = {
            column: product.get(
                column,
                "",
            )
            for column in TEST_COLUMNS
        }

        minimal_products.append(
            minimal_product
        )

    result = save_csv(
        products=minimal_products,
        filename=filename,
        columns=TEST_COLUMNS,
    )

    if not result:
        return False

    print()
    print(
        f"TEST FEED CONTAINS "
        f"{len(minimal_products)} PRODUCTS"
    )

    for number, product in enumerate(
        minimal_products,
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
    expected_columns,
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

    if list(df.columns) != expected_columns:

        print()
        print(
            "ERROR: CSV columns are not "
            "exactly as expected."
        )

        return False

    # --------------------------------------------------------
    # Required values
    # --------------------------------------------------------

    required_columns = [
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

    for column in required_columns:

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

    # --------------------------------------------------------
    # Seller
    # --------------------------------------------------------

    sellers = (
        df["seller_name"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Seller names: "
        f"{sellers}"
    )

    if sellers != ["Ballzy"]:

        print(
            "ERROR: Seller name check failed."
        )

        return False

    # --------------------------------------------------------
    # Eligibility
    # --------------------------------------------------------

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
            "ERROR: is_ads_eligible "
            "check failed."
        )

        return False

    # --------------------------------------------------------
    # HTTPS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    invalid_price_count = 0

    for value in df["price"]:

        info = parse_money(
            value
        )

        if not info:
            invalid_price_count += 1
            continue

        amount, _ = info

        if amount <= 0:
            invalid_price_count += 1

    if invalid_price_count:

        print(
            f"ERROR: {invalid_price_count} "
            "invalid prices."
        )

        return False

    # --------------------------------------------------------
    # OPTIONAL FULL-FEED CHECKS
    # --------------------------------------------------------

    if "sale_price" in df.columns:

        invalid_sale_count = 0

        for _, row in df.iterrows():

            sale_price = row[
                "sale_price"
            ].strip()

            if not sale_price:
                continue

            regular = parse_money(
                row["price"]
            )

            sale = parse_money(
                sale_price
            )

            if not regular or not sale:
                invalid_sale_count += 1
                continue

            regular_amount, regular_currency = regular
            sale_amount, sale_currency = sale

            if (
                sale_currency != regular_currency
                or sale_amount <= 0
                or sale_amount >= regular_amount
            ):
                invalid_sale_count += 1

        if invalid_sale_count:

            print(
                f"ERROR: {invalid_sale_count} "
                "invalid sale prices."
            )

            return False

    if "ads_metadata" in df.columns:

        metadata_errors = 0

        for value in df[
            "ads_metadata"
        ]:

            if not value:
                continue

            try:
                parsed = json.loads(
                    value
                )

                if not isinstance(
                    parsed,
                    dict,
                ):
                    metadata_errors += 1
                    continue

                if not all(
                    isinstance(k, str)
                    and isinstance(v, str)
                    for k, v in parsed.items()
                ):
                    metadata_errors += 1

            except json.JSONDecodeError:
                metadata_errors += 1

        if metadata_errors:

            print(
                f"ERROR: {metadata_errors} "
                "invalid ads_metadata values."
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
        print("HEADER:")
        print(
            ",".join(df.columns)
        )

        print()
        print("FIRST PRODUCT:")

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
        f"Seller name: "
        f"{seller_name}"
    )

    print(
        f"Output base: "
        f"{output_csv_base}"
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

    success = True

    generated_files = []

    # --------------------------------------------------------
    # FULL FEEDS
    # --------------------------------------------------------

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
                f"WARNING: No valid "
                f"{category} products found."
            )

            continue

        filename = (
            f"{output_csv_base}_"
            f"{category}.csv"
        )

        if save_csv(
            products=products,
            filename=filename,
            columns=FULL_COLUMNS,
        ):

            generated_files.append(
                (
                    filename,
                    FULL_COLUMNS,
                )
            )

        else:
            success = False

    # --------------------------------------------------------
    # MINIMAL 5-PRODUCT TEST FEED
    # --------------------------------------------------------

    test_filename = (
        "chatgpt_ads_test.csv"
    )

    if save_test_feed(
        products_by_category[
            "lifestyle"
        ],
        test_filename,
    ):

        generated_files.append(
            (
                test_filename,
                TEST_COLUMNS,
            )
        )

    else:
        success = False

    # --------------------------------------------------------
    # VERIFY EVERYTHING
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "FINAL CSV VERIFICATION"
    )
    print("=" * 70)

    for filename, columns in generated_files:

        if not verify_csv(
            filename,
            columns,
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
            "CHATGPT ADS FEED "
            "GENERATION COMPLETE"
        )

        print("=" * 70)

        print()
        print("Generated files:")

        for filename, _ in generated_files:

            if os.path.exists(
                filename
            ):

                size = os.path.getsize(
                    filename
                )

                print(
                    f"  {filename} "
                    f"({size:,} bytes)"
                )

        print()
        print(
            "TEST THIS URL FIRST:"
        )

        print(
            "https://tanelneemoja.github.io/"
            "cropink_to_google/"
            "chatgpt_ads_test.csv"
        )

        print()
        print(
            "If the 5-product test imports "
            "successfully, then test:"
        )

        print(
            "https://tanelneemoja.github.io/"
            "cropink_to_google/"
            "chatgpt_ads_feed_lifestyle.csv"
        )

    else:

        print(
            "CHATGPT ADS FEED "
            "GENERATION FAILED"
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
