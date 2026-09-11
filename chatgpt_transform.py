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

DEFAULT_OUTPUT_CSV_BASE = "openai_ads_feed_v3"

REQUEST_TIMEOUT = 120

SELLER_NAME = "Streetbrand OÜ"
SELLER_URL = "https://ballzy.eu"
RETURN_POLICY_URL = "https://ballzy.eu/et/shopping-help#returning"

TARGET_COUNTRY = "EE"
STORE_COUNTRY = "EE"


# ============================================================
# OUTPUT COLUMNS
# ============================================================

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
    "seller_url",
    "return_policy",
    "target_countries",
    "store_country",
    "is_eligible_search",
    "is_eligible_checkout",
    "is_ads_eligible",
]


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
    return " ".join(
        text.split()
    ).strip()


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


def is_https(url):
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
    # Try without namespace first
    value = get_text(
        item,
        f"custom_label_{index}",
    )

    if value:
        return clean_text(value)

    # Google namespace fallback
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
# DOWNLOAD SOURCE FEED
# ============================================================

def download_feed(url):

    print()
    print("=" * 70)
    print("DOWNLOADING BALLZY SOURCE FEED")
    print("=" * 70)

    print(f"URL: {url}")

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "Ballzy-OpenAI-Ads-Feed/3.0",
            "Accept": "application/xml,text/xml,*/*",
        },
    )

    response.raise_for_status()

    print(
        f"Downloaded: "
        f"{len(response.content):,} bytes"
    )

    return response.content


# ============================================================
# PRODUCT VALIDATION
# ============================================================

def validate_product(product):

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
        "seller_url",
        "return_policy",
        "target_countries",
        "store_country",
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
            return False, f"missing_{field}"

    if not is_https(
        product["url"]
    ):
        return False, "bad_product_url"

    if not is_https(
        product["image_url"]
    ):
        return False, "bad_image_url"

    if not is_https(
        product["seller_url"]
    ):
        return False, "bad_seller_url"

    if not is_https(
        product["return_policy"]
    ):
        return False, "bad_return_policy"

    if (
        product["target_countries"]
        != "EE"
    ):
        return False, "bad_target_country"

    if (
        product["store_country"]
        != "EE"
    ):
        return False, "bad_store_country"

    if (
        product["is_eligible_search"]
        != "true"
    ):
        return False, "bad_search_flag"

    if (
        product["is_eligible_checkout"]
        != "false"
    ):
        return False, "bad_checkout_flag"

    if (
        product["is_ads_eligible"]
        != "true"
    ):
        return False, "bad_ads_flag"

    return True, ""


# ============================================================
# BUILD PRODUCTS
# ============================================================

def build_products(xml_data):

    root = ET.fromstring(
        xml_data
    )

    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    products_by_category = {
        "lifestyle": [],
        "basketball": [],
    }

    total_items = 0
    ignored_items = 0
    invalid_items = 0
    duplicate_ids = 0

    seen_ids = set()

    rejection_reasons = {}

    for item in root.findall(
        ".//item"
    ):

        total_items += 1

        business_line = get_business_line(
            item,
            namespaces,
        )

        if business_line is None:
            ignored_items += 1
            continue

        item_id = clean_text(
            get_text(
                item,
                "g:id",
                namespaces,
            )
        )

        if item_id in seen_ids:
            duplicate_ids += 1
            continue

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
            "seller_url": SELLER_URL,
            "return_policy": RETURN_POLICY_URL,

            "target_countries": TARGET_COUNTRY,
            "store_country": STORE_COUNTRY,

            "is_eligible_search": "true",
            "is_eligible_checkout": "false",
            "is_ads_eligible": "true",
        }

        valid, reason = validate_product(
            product
        )

        if not valid:
            invalid_items += 1

            rejection_reasons[
                reason
            ] = (
                rejection_reasons.get(
                    reason,
                    0,
                )
                + 1
            )

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
        f"{ignored_items:,}"
    )

    print(
        f"Duplicate item IDs:    "
        f"{duplicate_ids:,}"
    )

    print(
        f"Invalid products:      "
        f"{invalid_items:,}"
    )

    print(
        f"Valid Lifestyle:       "
        f"{len(products_by_category['lifestyle']):,}"
    )

    print(
        f"Valid Basketball:      "
        f"{len(products_by_category['basketball']):,}"
    )

    if rejection_reasons:

        print()
        print(
            "Rejection reasons:"
        )

        for reason, count in sorted(
            rejection_reasons.items(),
            key=lambda x: x[1],
            reverse=True,
        ):

            print(
                f"  {reason}: "
                f"{count:,}"
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
        f"{os.path.getsize(filename):,} bytes"
    )

    print()
    print("Header:")

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

        for column in COLUMNS:

            print(
                f"  {column}: "
                f"{df.iloc[0][column]}"
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
            f"feed contains zero products"
        )

    duplicate_count = (
        df["item_id"]
        .duplicated()
        .sum()
    )

    if duplicate_count:

        raise RuntimeError(
            f"{filename}: "
            f"{duplicate_count} duplicate IDs"
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
    print("OPENAI ADS BALLZY FEED V3")
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
    print("VERIFYING FILES")
    print("=" * 70)

    verify_csv(
        lifestyle_file
    )

    verify_csv(
        basketball_file
    )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print()
    print(
        "Lifestyle:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "openai_ads_feed_v3_lifestyle.csv"
    )

    print()
    print(
        "Basketball:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "openai_ads_feed_v3_basketball.csv"
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
