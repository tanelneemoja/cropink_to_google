import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_CROPINK_FEED_URL = (
    "https://backend.ballzy.eu/et/amfeed/feed/download"
    "?id=102&file=cropink_et.xml"
)

# New filename to avoid any possible cache / stale preview issue
DEFAULT_OUTPUT_CSV_BASE = "openai_ads_feed_v2"

REQUEST_TIMEOUT = 120

SELLER_NAME = "Streetbrand OÜ"
TARGET_COUNTRY = "EE"


# ============================================================
# OUTPUT COLUMNS
# ============================================================

# Keep the 13 fields that already worked,
# then add only ads_metadata.
COLUMNS = [
    "item_id",
    "title",
    "description",
    "url",
    "image_url",
    "brand",
    "price",
    "availability",
    "seller_name",
    "target_countries",
    "is_eligible_search",
    "is_eligible_checkout",
    "is_ads_eligible",
    "ads_metadata",
]


# ============================================================
# FIELD LIMITS
# ============================================================

MAX_ITEM_ID = 100
MAX_TITLE = 150
MAX_DESCRIPTION = 5000
MAX_BRAND = 70
MAX_SELLER_NAME = 70


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)

    # Remove HTML
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    # Remove control characters
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


def truncate_text(text, max_length):
    text = clean_text(text)

    if len(text) <= max_length:
        return text

    return text[:max_length].rstrip()


# ============================================================
# URL HELPERS
# ============================================================

def force_https(url):
    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


def valid_https_url(url):
    return bool(
        url
        and url.lower().startswith("https://")
    )


# ============================================================
# XML HELPERS
# ============================================================

def get_text(
    item,
    xpath,
    namespaces=None,
):
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
    # Unnamespaced
    value = get_text(
        item,
        f"custom_label_{index}",
    )

    if value:
        return clean_text(value)

    # Google namespaced fallback
    value = get_text(
        item,
        f"g:custom_label_{index}",
        namespaces,
    )

    return clean_text(value)


# ============================================================
# PRICE
# ============================================================

def parse_price(element):
    if (
        element is None
        or not element.text
    ):
        return ""

    value = " ".join(
        element.text
        .strip()
        .split()
    )

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})$",
        value,
    )

    if not match:
        return ""

    amount = match.group(1)
    currency = match.group(2).upper()

    return f"{amount} {currency}"


def parse_money(value):
    if not value:
        return None

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)?) ([A-Z]{3})$",
        value.strip(),
    )

    if not match:
        return None

    return (
        float(match.group(1)),
        match.group(2),
    )


# ============================================================
# AVAILABILITY
# ============================================================

def parse_availability(element):
    if (
        element is None
        or not element.text
    ):
        return "in_stock"

    value = (
        element.text
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
# BUSINESS LINE
# ============================================================

def get_business_line(
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

    value = label.lower()

    if "lifestyle" in value:
        return "lifestyle"

    if "basketball" in value:
        return "basketball"

    return None


# ============================================================
# ADS METADATA
# ============================================================

def build_ads_metadata(
    business_line,
    product_category,
):
    """
    Keep this intentionally simple.

    Example:
    {
        "business_line": "lifestyle",
        "product_category": "Men's Socks"
    }
    """

    metadata = {}

    if business_line:
        metadata["business_line"] = (
            business_line
        )

    if product_category:
        metadata["product_category"] = (
            product_category
        )

    return json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ============================================================
# DOWNLOAD
# ============================================================

def download_feed(url):

    print()
    print("=" * 70)
    print("DOWNLOADING SOURCE FEED")
    print("=" * 70)

    print(
        f"URL: {url}"
    )

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": (
                "Ballzy-OpenAI-Feed/2.0"
            ),
        },
    )

    response.raise_for_status()

    print(
        f"Downloaded: "
        f"{len(response.content):,} bytes"
    )

    return response.content


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
        "image_url",
        "brand",
        "price",
        "availability",
        "seller_name",
        "target_countries",
        "is_eligible_search",
        "is_eligible_checkout",
        "is_ads_eligible",
    ]

    for field in required_fields:

        if not str(
            product.get(
                field,
                "",
            )
        ).strip():

            errors.append(
                f"missing_{field}"
            )

    if len(
        product["item_id"]
    ) > MAX_ITEM_ID:

        errors.append(
            "item_id_too_long"
        )

    if len(
        product["title"]
    ) > MAX_TITLE:

        errors.append(
            "title_too_long"
        )

    if len(
        product["description"]
    ) > MAX_DESCRIPTION:

        errors.append(
            "description_too_long"
        )

    if len(
        product["brand"]
    ) > MAX_BRAND:

        errors.append(
            "brand_too_long"
        )

    if len(
        product["seller_name"]
    ) > MAX_SELLER_NAME:

        errors.append(
            "seller_name_too_long"
        )

    if not valid_https_url(
        product["url"]
    ):

        errors.append(
            "invalid_url"
        )

    if not valid_https_url(
        product["image_url"]
    ):

        errors.append(
            "invalid_image_url"
        )

    valid_availability = {
        "in_stock",
        "out_of_stock",
        "pre_order",
        "backorder",
    }

    if (
        product["availability"]
        not in valid_availability
    ):

        errors.append(
            "invalid_availability"
        )

    money = parse_money(
        product["price"]
    )

    if not money:

        errors.append(
            "invalid_price"
        )

    else:

        amount, _ = money

        if amount <= 0:

            errors.append(
                "price_not_positive"
            )

    if (
        product["target_countries"]
        != TARGET_COUNTRY
    ):

        errors.append(
            "invalid_target_country"
        )

    if (
        product["is_eligible_search"]
        != "true"
    ):

        errors.append(
            "invalid_search_flag"
        )

    if (
        product["is_eligible_checkout"]
        != "false"
    ):

        errors.append(
            "invalid_checkout_flag"
        )

    if (
        product["is_ads_eligible"]
        != "true"
    ):

        errors.append(
            "invalid_ads_flag"
        )

    # Validate metadata JSON
    try:

        metadata = json.loads(
            product["ads_metadata"]
        )

        if not isinstance(
            metadata,
            dict,
        ):

            errors.append(
                "ads_metadata_not_object"
            )

        else:

            for key, value in metadata.items():

                if not isinstance(
                    key,
                    str,
                ):

                    errors.append(
                        "metadata_key_not_string"
                    )

                if not isinstance(
                    value,
                    str,
                ):

                    errors.append(
                        "metadata_value_not_string"
                    )

    except Exception:

        errors.append(
            "invalid_ads_metadata"
        )

    return errors


# ============================================================
# BUILD PRODUCTS
# ============================================================

def build_products(xml_data):

    root = ET.fromstring(
        xml_data
    )

    namespaces = {
        "g": (
            "http://base.google.com/ns/1.0"
        )
    }

    products_by_category = {
        "lifestyle": [],
        "basketball": [],
    }

    seen_ids = set()

    rejection_counts = Counter()

    total_items = 0
    ignored_categories = 0

    for item in root.findall(
        ".//item"
    ):

        total_items += 1

        business_line = get_business_line(
            item,
            namespaces,
        )

        if business_line is None:

            ignored_categories += 1

            continue

        item_id = truncate_text(
            get_text(
                item,
                "g:id",
                namespaces,
            ),
            MAX_ITEM_ID,
        )

        if item_id in seen_ids:

            rejection_counts[
                "duplicate_item_id"
            ] += 1

            continue

        title = truncate_text(
            get_text(
                item,
                "g:title",
                namespaces,
            ),
            MAX_TITLE,
        )

        description = truncate_text(
            get_text(
                item,
                "g:description",
                namespaces,
            ),
            MAX_DESCRIPTION,
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

        brand = truncate_text(
            get_text(
                item,
                "g:brand",
                namespaces,
            ),
            MAX_BRAND,
        )

        price = parse_price(
            item.find(
                "g:price",
                namespaces,
            )
        )

        availability = parse_availability(
            item.find(
                "g:availability",
                namespaces,
            )
        )

        # Used ONLY inside ads_metadata.
        product_category = clean_text(
            get_text(
                item,
                "g:google_product_category",
                namespaces,
            )
        )

        ads_metadata = (
            build_ads_metadata(
                business_line=(
                    business_line
                ),
                product_category=(
                    product_category
                ),
            )
        )

        product = {
            "item_id": item_id,
            "title": title,
            "description": description,
            "url": url,
            "image_url": image_url,
            "brand": brand,
            "price": price,
            "availability": availability,

            "seller_name": SELLER_NAME,
            "target_countries": TARGET_COUNTRY,

            "is_eligible_search": "true",
            "is_eligible_checkout": "false",
            "is_ads_eligible": "true",

            "ads_metadata": ads_metadata,
        }

        errors = validate_product(
            product
        )

        if errors:

            for error in errors:

                rejection_counts[
                    error
                ] += 1

            continue

        seen_ids.add(
            item_id
        )

        products_by_category[
            business_line
        ].append(
            product
        )

    print()
    print("=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)

    print(
        f"Total XML items:       "
        f"{total_items:,}"
    )

    print(
        f"Ignored categories:    "
        f"{ignored_categories:,}"
    )

    print(
        f"Valid Lifestyle:       "
        f"{len(products_by_category['lifestyle']):,}"
    )

    print(
        f"Valid Basketball:      "
        f"{len(products_by_category['basketball']):,}"
    )

    print()
    print("=" * 70)
    print("REJECTION SUMMARY")
    print("=" * 70)

    if rejection_counts:

        for reason, count in (
            rejection_counts
            .most_common()
        ):

            print(
                f"{reason}: "
                f"{count:,}"
            )

    else:

        print(
            "No rejected products."
        )

    return products_by_category


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    products,
    filename,
):

    df = pd.DataFrame(
        products,
        columns=COLUMNS,
    )

    df.to_csv(
        filename,
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
    )

    file_size = os.path.getsize(
        filename
    )

    print()
    print("=" * 70)
    print(
        f"SAVED {filename}"
    )
    print("=" * 70)

    print(
        f"Products: "
        f"{len(df):,}"
    )

    print(
        f"File size: "
        f"{file_size:,} bytes"
    )

    print()
    print(
        "Header:"
    )

    print(
        ",".join(
            df.columns
        )
    )

    if len(df) > 0:

        print()
        print(
            "First product:"
        )

        for key in COLUMNS:

            print(
                f"  {key}: "
                f"{df.iloc[0][key]}"
            )


# ============================================================
# VERIFY OUTPUT
# ============================================================

def verify_csv(filename):

    df = pd.read_csv(
        filename,
        dtype=str,
        keep_default_na=False,
    )

    if list(
        df.columns
    ) != COLUMNS:

        raise RuntimeError(
            f"{filename}: "
            f"column structure mismatch"
        )

    if len(df) == 0:

        raise RuntimeError(
            f"{filename}: "
            f"zero products"
        )

    duplicates = (
        df["item_id"]
        .duplicated()
        .sum()
    )

    if duplicates:

        raise RuntimeError(
            f"{filename}: "
            f"{duplicates} duplicate item IDs"
        )

    print(
        f"Verified: "
        f"{filename}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("OPENAI ADS FEED V2")
    print("=" * 70)

    feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    output_base = os.environ.get(
        "OUTPUT_CSV_BASE",
        DEFAULT_OUTPUT_CSV_BASE,
    )

    data = download_feed(
        feed_url
    )

    products = build_products(
        data
    )

    lifestyle_file = (
        f"{output_base}_lifestyle.csv"
    )

    basketball_file = (
        f"{output_base}_basketball.csv"
    )

    save_csv(
        products[
            "lifestyle"
        ],
        lifestyle_file,
    )

    save_csv(
        products[
            "basketball"
        ],
        basketball_file,
    )

    print()
    print("=" * 70)
    print("VERIFYING OUTPUT")
    print("=" * 70)

    verify_csv(
        lifestyle_file
    )

    verify_csv(
        basketball_file
    )

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)

    print()
    print(
        "NEW Lifestyle URL:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "openai_ads_feed_v2_lifestyle.csv"
    )

    print()
    print(
        "NEW Basketball URL:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "openai_ads_feed_v2_basketball.csv"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print()
        print(
            f"FATAL ERROR: {error}"
        )

        sys.exit(1)
