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

REQUEST_TIMEOUT = 120

SELLER_NAME = "Streetbrand OÜ"
SELLER_URL = "https://ballzy.eu"
RETURN_POLICY_URL = (
    "https://ballzy.eu/et/shopping-help#returning"
)

TARGET_COUNTRY = "EE"
STORE_COUNTRY = "EE"


# ============================================================
# OPENAI NATIVE ADS SCHEMA
# ============================================================

COLUMNS = [
    "item_id",
    "title",
    "description",
    "url",
    "brand",
    "image_url",
    "price",
    "availability",
    "seller_name",
    "seller_url",
    "is_eligible_search",
    "is_eligible_checkout",
    "return_policy",
    "target_countries",
    "store_country",
    "is_ads_eligible",
]


# ============================================================
# HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text,
    )

    return " ".join(
        text.split()
    ).strip()


def force_https(url):
    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


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
    value = get_text(
        item,
        f"custom_label_{index}",
    )

    if value:
        return clean_text(value)

    return clean_text(
        get_text(
            item,
            f"g:custom_label_{index}",
            namespaces,
        )
    )


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
# DOWNLOAD
# ============================================================

def download_feed(url):

    print()
    print("=" * 70)
    print("DOWNLOADING SOURCE FEED")
    print("=" * 70)

    print(f"URL: {url}")

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": (
                "Ballzy-OpenAI-Ads-Feed/4.0"
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
# BUILD PRODUCTS
# ============================================================

def build_products(xml_data):

    root = ET.fromstring(
        xml_data
    )

    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    products = {
        "lifestyle": [],
        "basketball": [],
    }

    seen_ids = set()

    total = 0
    ignored = 0
    invalid = 0
    duplicates = 0

    for item in root.findall(
        ".//item"
    ):

        total += 1

        business_line = get_business_line(
            item,
            namespaces,
        )

        if business_line is None:
            ignored += 1
            continue

        item_id = clean_text(
            get_text(
                item,
                "g:id",
                namespaces,
            )
        )

        if item_id in seen_ids:
            duplicates += 1
            continue

        product = {
            "item_id": item_id,

            "title": clean_text(
                get_text(
                    item,
                    "g:title",
                    namespaces,
                )
            ),

            "description": clean_text(
                get_text(
                    item,
                    "g:description",
                    namespaces,
                )
            ),

            "url": force_https(
                get_text(
                    item,
                    "g:link",
                    namespaces,
                )
            ),

            "brand": clean_text(
                get_text(
                    item,
                    "g:brand",
                    namespaces,
                )
            ),

            "image_url": force_https(
                get_text(
                    item,
                    "g:image_link",
                    namespaces,
                )
            ),

            "price": parse_price(
                item.find(
                    "g:price",
                    namespaces,
                )
            ),

            "availability": (
                parse_availability(
                    item.find(
                        "g:availability",
                        namespaces,
                    )
                )
            ),

            "seller_name": SELLER_NAME,
            "seller_url": SELLER_URL,

            "is_eligible_search": "true",
            "is_eligible_checkout": "false",

            "return_policy": (
                RETURN_POLICY_URL
            ),

            "target_countries": (
                TARGET_COUNTRY
            ),

            "store_country": (
                STORE_COUNTRY
            ),

            "is_ads_eligible": "true",
        }

        # All fields required for this feed version.
        if not all(
            str(
                product[column]
            ).strip()
            for column in COLUMNS
        ):
            invalid += 1
            continue

        if not product[
            "url"
        ].startswith("https://"):
            invalid += 1
            continue

        if not product[
            "image_url"
        ].startswith("https://"):
            invalid += 1
            continue

        seen_ids.add(
            item_id
        )

        products[
            business_line
        ].append(
            product
        )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"Total items:          {total:,}"
    )

    print(
        f"Ignored:              {ignored:,}"
    )

    print(
        f"Invalid:              {invalid:,}"
    )

    print(
        f"Duplicates:           {duplicates:,}"
    )

    print(
        f"Lifestyle:            "
        f"{len(products['lifestyle']):,}"
    )

    print(
        f"Basketball:           "
        f"{len(products['basketball']):,}"
    )

    return products


# ============================================================
# SAVE TAB-DELIMITED TXT
# ============================================================

def save_txt(
    products,
    filename,
):

    df = pd.DataFrame(
        products,
        columns=COLUMNS,
    )

    # IMPORTANT:
    # OpenAI native feed diagnostic:
    # UTF-8 + TAB-DELIMITED TXT
    df.to_csv(
        filename,
        index=False,
        encoding="utf-8",
        sep="\t",
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
    )

    print()
    print("=" * 70)
    print(f"SAVED {filename}")
    print("=" * 70)

    print(
        f"Rows: "
        f"{len(df):,}"
    )

    print(
        f"Size: "
        f"{os.path.getsize(filename):,} bytes"
    )

    print()
    print(
        "HEADER:"
    )

    print(
        "\t".join(
            df.columns
        )
    )


# ============================================================
# VERIFY TXT
# ============================================================

def verify_txt(filename):

    df = pd.read_csv(
        filename,
        sep="\t",
        dtype=str,
        keep_default_na=False,
    )

    if list(
        df.columns
    ) != COLUMNS:

        raise RuntimeError(
            f"{filename}: "
            "header mismatch"
        )

    if len(df) == 0:

        raise RuntimeError(
            f"{filename}: zero rows"
        )

    if (
        df["item_id"]
        .duplicated()
        .any()
    ):

        raise RuntimeError(
            f"{filename}: duplicate IDs"
        )

    print(
        f"Verified: {filename}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("OPENAI ADS NATIVE TSV FEED")
    print("=" * 70)

    feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    data = download_feed(
        feed_url
    )

    products = build_products(
        data
    )

    # Brand-new filenames = no old feed cache.
    lifestyle_file = (
        "openai_native_lifestyle.txt"
    )

    basketball_file = (
        "openai_native_basketball.txt"
    )

    save_txt(
        products[
            "lifestyle"
        ],
        lifestyle_file,
    )

    save_txt(
        products[
            "basketball"
        ],
        basketball_file,
    )

    print()
    print("=" * 70)
    print("VERIFY")
    print("=" * 70)

    verify_txt(
        lifestyle_file
    )

    verify_txt(
        basketball_file
    )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    base = (
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
    )

    print()
    print(
        base
        + lifestyle_file
    )

    print(
        base
        + basketball_file
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
