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

DEFAULT_OUTPUT_CSV_BASE = "chatgpt_ads_feed"

REQUEST_TIMEOUT = 120

# Small diagnostic feed
TEST_PRODUCT_COUNT = 5


# ============================================================
# OPENAI ADS FEED COLUMNS
# ============================================================

# Reconstructed structure based on the earlier likely-working feed.
COLUMNS = [
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
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    # Remove problematic control characters
    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text,
    )

    # Normalize whitespace
    text = " ".join(
        text.split()
    )

    return text.strip()


# ============================================================
# URL HELPERS
# ============================================================

def force_https(url):
    """
    Convert http:// URLs to https://.
    """

    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith(
        "http://"
    ):
        return (
            "https://"
            + url[7:]
        )

    return url


def is_valid_https_url(url):
    """
    Verify HTTPS URL.
    """

    if not url:
        return False

    return url.lower().startswith(
        "https://"
    )


# ============================================================
# XML HELPERS
# ============================================================

def get_text(
    item,
    xpath,
    namespaces=None,
):
    """
    Safely retrieve XML text.
    """

    element = item.find(
        xpath,
        namespaces=namespaces,
    )

    if (
        element is not None
        and element.text
    ):
        return element.text.strip()

    return ""


def get_custom_label(
    item,
    index,
    namespaces,
):
    """
    Support both:
        <custom_label_0>
    and:
        <g:custom_label_0>
    """

    value = get_text(
        item,
        f"custom_label_{index}",
    )

    if value:
        return clean_text(
            value
        )

    value = get_text(
        item,
        f"g:custom_label_{index}",
        namespaces,
    )

    return clean_text(
        value
    )


# ============================================================
# PRICE
# ============================================================

def parse_price_value(
    price_element,
):
    """
    Convert source price to:
        17.00 EUR

    Accepted:
        17 EUR
        17.00 EUR
        17.5 EUR
    """

    if price_element is None:
        return ""

    if not price_element.text:
        return ""

    price_text = " ".join(
        price_element
        .text
        .strip()
        .split()
    )

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
    currency = (
        match
        .group(2)
        .upper()
    )

    return (
        f"{amount} "
        f"{currency}"
    )


def parse_money(value):
    """
    Parse:
        89.00 EUR

    Returns:
        (89.0, "EUR")
    """

    if not value:
        return None

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?) ([A-Z]{3})$",
        value.strip(),
    )

    if not match:
        return None

    return (
        float(
            match.group(1)
        ),
        match.group(2),
    )


def validate_sale_price(
    price,
    sale_price,
):
    """
    Keep sale price only when:
    - > 0
    - same currency
    - lower than regular price
    """

    if not sale_price:
        return ""

    regular = parse_money(
        price
    )

    sale = parse_money(
        sale_price
    )

    if (
        not regular
        or not sale
    ):
        return ""

    regular_amount, regular_currency = (
        regular
    )

    sale_amount, sale_currency = (
        sale
    )

    if regular_amount <= 0:
        return ""

    if sale_amount <= 0:
        return ""

    if (
        regular_currency
        != sale_currency
    ):
        return ""

    if (
        sale_amount
        >= regular_amount
    ):
        return ""

    return sale_price


# ============================================================
# AVAILABILITY
# ============================================================

def parse_availability(
    availability_element,
):
    """
    Convert source availability values.
    """

    if availability_element is None:
        return "in_stock"

    if not availability_element.text:
        return "in_stock"

    value = (
        availability_element
        .text
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
# DOWNLOAD SOURCE FEED
# ============================================================

def download_cropink_feed(url):

    print()
    print(
        "=" * 70
    )
    print(
        "DOWNLOADING CROPINK FEED"
    )
    print(
        "=" * 70
    )

    print(
        f"URL: {url}"
    )

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Ballzy-OpenAI-Ads-Feed/1.0"
                ),
                "Accept": (
                    "application/xml,"
                    "text/xml,*/*"
                ),
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
            "ERROR: Failed to download source feed."
        )

        print(
            error
        )

        return None


# ============================================================
# PARSE XML
# ============================================================

def parse_cropink_xml(data):

    print()
    print(
        "=" * 70
    )
    print(
        "PARSING XML"
    )
    print(
        "=" * 70
    )

    try:

        root = ET.fromstring(
            data
        )

        print(
            "XML parsed successfully."
        )

        return root

    except ET.ParseError as error:

        print()
        print(
            "ERROR: Invalid XML."
        )

        print(
            error
        )

        return None


# ============================================================
# CATEGORY
# ============================================================

def get_product_category(
    item,
    namespaces,
):

    label = get_custom_label(
        item,
        0,
        namespaces,
    )

    if not label:
        return None

    label_lower = (
        label
        .strip()
        .lower()
    )

    if (
        "basketball"
        in label_lower
    ):
        return "basketball"

    if (
        "lifestyle"
        in label_lower
    ):
        return "lifestyle"

    return None


# ============================================================
# CREATE ADS METADATA
# ============================================================

def create_ads_metadata(
    item,
    namespaces,
    brand,
    color,
):
    """
    Reproduce the old semicolon metadata structure.

    Example:
        brand:Nike;
        color:White;
        Lifestyle;
        in stock;
        No;
        Nike;
        Male|Female

    Output is a single semicolon-delimited string.
    """

    parts = []

    if brand:
        parts.append(
            f"brand:{brand}"
        )

    if color:
        parts.append(
            f"color:{color}"
        )

    # Keep custom labels as plain values,
    # matching the earlier working-looking feed.
    for i in range(5):

        value = get_custom_label(
            item,
            i,
            namespaces,
        )

        if value:
            parts.append(
                value
            )

    return ";".join(
        parts
    )


# ============================================================
# CREATE PRODUCT
# ============================================================

def create_product(
    item,
    namespaces,
):

    # --------------------------------------------------------
    # BASIC VALUES
    # --------------------------------------------------------

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

    # Force HTTPS
    url = force_https(
        get_text(
            item,
            "g:link",
            namespaces,
        )
    )

    # Force HTTPS
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

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

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
    # AVAILABILITY
    # --------------------------------------------------------

    availability_element = item.find(
        "g:availability",
        namespaces,
    )

    availability = parse_availability(
        availability_element
    )

    # --------------------------------------------------------
    # CATEGORY FIELDS
    # --------------------------------------------------------

    google_product_category = clean_text(
        get_text(
            item,
            "g:google_product_category",
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
    # ADS METADATA
    # --------------------------------------------------------

    ads_metadata = create_ads_metadata(
        item=item,
        namespaces=namespaces,
        brand=brand,
        color=color,
    )

    # --------------------------------------------------------
    # FINAL PRODUCT
    # --------------------------------------------------------

    return {
        "item_id": item_id,
        "title": title,
        "description": description,
        "url": url,
        "image_url": image_url,
        "brand": brand,
        "price": price,
        "sale_price": sale_price,
        "availability": availability,
        "google_product_category": (
            google_product_category
        ),
        "product_type": (
            product_type
        ),
        "is_ads_eligible": "true",
        "enable_search": "true",
        "ads_metadata": (
            ads_metadata
        ),
    }


# ============================================================
# VALIDATE PRODUCT
# ============================================================

def validate_product(product):

    errors = []

    required_fields = [
        "item_id",
        "title",
        "description",
        "url",
        "image_url",
        "brand",
        "price",
        "availability",
        "is_ads_eligible",
        "enable_search",
    ]

    # --------------------------------------------------------
    # REQUIRED FIELDS
    # --------------------------------------------------------

    for field in required_fields:

        value = product.get(
            field,
            "",
        )

        if not str(
            value
        ).strip():

            errors.append(
                f"missing {field}"
            )

    # --------------------------------------------------------
    # HTTPS
    # --------------------------------------------------------

    if product.get(
        "url"
    ):

        if not is_valid_https_url(
            product["url"]
        ):

            errors.append(
                "product URL is not HTTPS"
            )

    if product.get(
        "image_url"
    ):

        if not is_valid_https_url(
            product["image_url"]
        ):

            errors.append(
                "image URL is not HTTPS"
            )

    # --------------------------------------------------------
    # AVAILABILITY
    # --------------------------------------------------------

    valid_availability = {
        "in_stock",
        "out_of_stock",
        "pre_order",
        "backorder",
    }

    if (
        product.get(
            "availability"
        )
        not in valid_availability
    ):

        errors.append(
            "invalid availability"
        )

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    price = parse_money(
        product.get(
            "price",
            "",
        )
    )

    if not price:

        errors.append(
            "invalid price"
        )

    else:

        amount, _ = price

        if amount <= 0:

            errors.append(
                "price must be > 0"
            )

    # --------------------------------------------------------
    # SALE PRICE
    # --------------------------------------------------------

    sale_price = product.get(
        "sale_price",
        "",
    )

    if sale_price:

        regular = parse_money(
            product["price"]
        )

        sale = parse_money(
            sale_price
        )

        if (
            not regular
            or not sale
        ):

            errors.append(
                "invalid sale_price"
            )

        else:

            regular_amount, regular_currency = (
                regular
            )

            sale_amount, sale_currency = (
                sale
            )

            if (
                regular_currency
                != sale_currency
            ):

                errors.append(
                    "sale currency mismatch"
                )

            if (
                sale_amount <= 0
            ):

                errors.append(
                    "sale_price <= 0"
                )

            if (
                sale_amount
                >= regular_amount
            ):

                errors.append(
                    "sale_price >= price"
                )

    # --------------------------------------------------------
    # FLAGS
    # --------------------------------------------------------

    if (
        product.get(
            "is_ads_eligible"
        )
        != "true"
    ):

        errors.append(
            "is_ads_eligible is not true"
        )

    if (
        product.get(
            "enable_search"
        )
        != "true"
    ):

        errors.append(
            "enable_search is not true"
        )

    return errors


# ============================================================
# PROCESS PRODUCTS
# ============================================================

def process_products(root):

    print()
    print(
        "=" * 70
    )
    print(
        "PROCESSING PRODUCTS"
    )
    print(
        "=" * 70
    )

    namespaces = {
        "g": (
            "http://base.google.com/ns/1.0"
        )
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
            item,
            namespaces,
        )

        if category is None:

            ignored_items += 1

            continue

        product = create_product(
            item,
            namespaces,
        )

        errors = validate_product(
            product
        )

        if errors:

            invalid_products += 1

            if (
                len(
                    validation_examples
                )
                < 20
            ):

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
        ].append(
            product
        )

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
        products
    )

    df = df.reindex(
        columns=COLUMNS
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
            f"ERROR writing "
            f"{filename}"
        )

        print(
            error
        )

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
# TEST FEED
# ============================================================

def save_test_feed(
    products,
    filename=(
        "chatgpt_ads_test.csv"
    ),
):

    print()
    print(
        "=" * 70
    )
    print(
        "CREATING OPENAI ADS TEST FEED"
    )
    print(
        "=" * 70
    )

    test_products = products[
        :TEST_PRODUCT_COUNT
    ]

    if not test_products:

        print(
            "ERROR: No products "
            "available for test feed."
        )

        return False

    if not save_csv(
        test_products,
        filename,
    ):

        return False

    print()
    print(
        f"Test feed contains "
        f"{len(test_products)} products."
    )

    for number, product in enumerate(
        test_products,
        start=1,
    ):

        print()
        print(
            f"PRODUCT #{number}"
        )

        print(
            f"item_id: "
            f"{product['item_id']}"
        )

        print(
            f"title: "
            f"{product['title']}"
        )

        print(
            f"url: "
            f"{product['url']}"
        )

        print(
            f"image_url: "
            f"{product['image_url']}"
        )

        print(
            f"brand: "
            f"{product['brand']}"
        )

        print(
            f"price: "
            f"{product['price']}"
        )

        print(
            f"sale_price: "
            f"{product['sale_price']}"
        )

        print(
            f"availability: "
            f"{product['availability']}"
        )

        print(
            f"google_product_category: "
            f"{product['google_product_category']}"
        )

        print(
            f"product_type: "
            f"{product['product_type']}"
        )

        print(
            f"is_ads_eligible: "
            f"{product['is_ads_eligible']}"
        )

        print(
            f"enable_search: "
            f"{product['enable_search']}"
        )

        print(
            f"ads_metadata: "
            f"{product['ads_metadata']}"
        )

    return True


# ============================================================
# VERIFY GENERATED CSV
# ============================================================

def verify_csv(filename):

    print()
    print(
        "=" * 70
    )
    print(
        f"VERIFYING {filename}"
    )
    print(
        "=" * 70
    )

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

        print(
            error
        )

        return False

    print(
        f"Rows: "
        f"{len(df):,}"
    )

    print(
        f"Columns: "
        f"{list(df.columns)}"
    )

    if list(
        df.columns
    ) != COLUMNS:

        print(
            "ERROR: Column structure mismatch."
        )

        return False

    # --------------------------------------------------------
    # REQUIRED VALUES
    # --------------------------------------------------------

    for column in [
        "item_id",
        "title",
        "description",
        "url",
        "image_url",
        "brand",
        "price",
        "availability",
        "is_ads_eligible",
        "enable_search",
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
                f"ERROR: "
                f"{column} has "
                f"{empty_count} empty values."
            )

            return False

    # --------------------------------------------------------
    # HTTPS
    # --------------------------------------------------------

    bad_urls = df[
        ~df[
            "url"
        ].str.startswith(
            "https://",
            na=False,
        )
    ]

    if len(
        bad_urls
    ) > 0:

        print(
            f"ERROR: "
            f"{len(bad_urls)} "
            f"non-HTTPS product URLs."
        )

        return False

    bad_images = df[
        ~df[
            "image_url"
        ].str.startswith(
            "https://",
            na=False,
        )
    ]

    if len(
        bad_images
    ) > 0:

        print(
            f"ERROR: "
            f"{len(bad_images)} "
            f"non-HTTPS image URLs."
        )

        return False

    # --------------------------------------------------------
    # FLAGS
    # --------------------------------------------------------

    if (
        df[
            "is_ads_eligible"
        ]
        .drop_duplicates()
        .tolist()
        != ["true"]
    ):

        print(
            "ERROR: Unexpected "
            "is_ads_eligible values."
        )

        return False

    if (
        df[
            "enable_search"
        ]
        .drop_duplicates()
        .tolist()
        != ["true"]
    ):

        print(
            "ERROR: Unexpected "
            "enable_search values."
        )

        return False

    print()
    print(
        f"OK: {filename}"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=" * 70
    )
    print(
        "OPENAI ADS FEED GENERATOR "
        "- RECONSTRUCTED OLD FORMAT"
    )
    print(
        "=" * 70
    )

    cropink_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    output_csv_base = os.environ.get(
        "OUTPUT_CSV_BASE",
        DEFAULT_OUTPUT_CSV_BASE,
    )

    print(
        f"Source feed: "
        f"{cropink_url}"
    )

    print(
        f"Output base: "
        f"{output_csv_base}"
    )

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
        root
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

        products = (
            products_by_category[
                category
            ]
        )

        if not products:

            print()
            print(
                f"WARNING: No valid "
                f"{category} products."
            )

            continue

        filename = (
            f"{output_csv_base}_"
            f"{category}.csv"
        )

        if save_csv(
            products,
            filename,
        ):

            generated_files.append(
                filename
            )

        else:

            success = False

    # --------------------------------------------------------
    # 5-PRODUCT TEST FEED
    # --------------------------------------------------------

    test_filename = (
        "chatgpt_ads_test.csv"
    )

    lifestyle_products = (
        products_by_category[
            "lifestyle"
        ]
    )

    if save_test_feed(
        lifestyle_products,
        test_filename,
    ):

        generated_files.append(
            test_filename
        )

    else:

        success = False

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )
    print(
        "FINAL CSV VERIFICATION"
    )
    print(
        "=" * 70
    )

    for filename in generated_files:

        if not verify_csv(
            filename
        ):

            success = False

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    if success:

        print(
            "OPENAI ADS FEED "
            "GENERATION COMPLETE"
        )

        print(
            "=" * 70
        )

        print()
        print(
            "Generated files:"
        )

        for filename in generated_files:

            size = os.path.getsize(
                filename
            )

            print(
                f"  {filename} "
                f"({size:,} bytes)"
            )

        print()
        print(
            "TEST THIS FIRST:"
        )

        print(
            "https://tanelneemoja.github.io/"
            "cropink_to_google/"
            "chatgpt_ads_test.csv"
        )

        print()
        print(
            "THEN TEST:"
        )

        print(
            "https://tanelneemoja.github.io/"
            "cropink_to_google/"
            "chatgpt_ads_feed_lifestyle.csv"
        )

    else:

        print(
            "OPENAI ADS FEED "
            "GENERATION FAILED"
        )

        print(
            "=" * 70
        )

    return success


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    success = main()

    if not success:
        sys.exit(1)
