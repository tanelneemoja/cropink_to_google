import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

import pandas as pd
import requests


SOURCE_FEED_URL = (
    "https://backend.ballzy.eu/et/amfeed/feed/download"
    "?id=102&file=cropink_et.xml"
)

REQUEST_TIMEOUT = 120

LIFESTYLE_FILE = "openai_final_lifestyle.csv"
BASKETBALL_FILE = "openai_final_basketball.csv"


# ============================================================
# FEED COLUMNS
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
    "is_eligible_search",
    "is_eligible_checkout",
    "is_ads_eligible",
]


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = str(value)

    # Remove HTML
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    # Remove control characters
    value = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        value,
    )

    return " ".join(
        value.split()
    ).strip()


def truncate(value, max_chars):
    value = clean_text(value)

    if len(value) <= max_chars:
        return value

    return value[:max_chars].rstrip()


# ============================================================
# URL
# ============================================================

def force_https(url):
    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith("http://"):
        return "https://" + url[7:]

    return url


# ============================================================
# XML
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
    """
    Outputs exactly:
        17.00 EUR
        109.00 EUR
    """

    if (
        element is None
        or not element.text
    ):
        return ""

    raw = " ".join(
        element.text
        .strip()
        .split()
    )

    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})",
        raw,
    )

    if not match:
        return ""

    try:
        amount = Decimal(
            match.group(1)
        )

    except InvalidOperation:
        return ""

    if amount <= 0:
        return ""

    currency = (
        match
        .group(2)
        .upper()
    )

    return (
        f"{amount.quantize(Decimal('0.01'))} "
        f"{currency}"
    )


# ============================================================
# AVAILABILITY
# ============================================================

def parse_availability(element):
    if (
        element is None
        or not element.text
    ):
        return ""

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
        "",
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
    ).lower()

    if "lifestyle" in label:
        return "lifestyle"

    if "basketball" in label:
        return "basketball"

    return None


# ============================================================
# DOWNLOAD
# ============================================================

def download_feed(url):

    print("=" * 70)
    print("DOWNLOADING SOURCE FEED")
    print("=" * 70)

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": (
                "Streetbrand-OpenAI-Feed/1.0"
            ),
            "Accept": (
                "application/xml,text/xml,*/*"
            ),
        },
    )

    response.raise_for_status()

    print(
        f"Downloaded "
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
    preorders_skipped = 0

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

        item_id = truncate(
            get_text(
                item,
                "g:id",
                namespaces,
            ),
            100,
        )

        if not item_id:
            invalid += 1
            continue

        if item_id in seen_ids:
            continue

        availability = parse_availability(
            item.find(
                "g:availability",
                namespaces,
            )
        )

        # Skip preorder because we do not have availability_date
        if availability == "pre_order":
            preorders_skipped += 1
            continue

        product = {
            "item_id": item_id,

            "title": truncate(
                get_text(
                    item,
                    "g:title",
                    namespaces,
                ),
                150,
            ),

            "description": truncate(
                get_text(
                    item,
                    "g:description",
                    namespaces,
                ),
                5000,
            ),

            "url": force_https(
                get_text(
                    item,
                    "g:link",
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

            "brand": truncate(
                get_text(
                    item,
                    "g:brand",
                    namespaces,
                ),
                70,
            ),

            "price": parse_price(
                item.find(
                    "g:price",
                    namespaces,
                )
            ),

            "availability": availability,

            "is_eligible_search": "true",

            "is_eligible_checkout": "false",

            "is_ads_eligible": "true",
        }

        # All output values must exist
        if not all(
            str(
                product[field]
            ).strip()
            for field in COLUMNS
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
        f"Total:              "
        f"{total:,}"
    )

    print(
        f"Ignored category:   "
        f"{ignored:,}"
    )

    print(
        f"Invalid:            "
        f"{invalid:,}"
    )

    print(
        f"Preorders skipped:  "
        f"{preorders_skipped:,}"
    )

    print(
        f"Lifestyle:          "
        f"{len(products['lifestyle']):,}"
    )

    print(
        f"Basketball:         "
        f"{len(products['basketball']):,}"
    )

    return products


# ============================================================
# SAVE
# ============================================================

def save_csv(
    products,
    filename,
):

    df = pd.DataFrame(
        products,
        columns=COLUMNS,
    )

    # Use CRLF to stay close to manually-created Windows CSV
    df.to_csv(
        filename,
        index=False,
        encoding="utf-8",
        sep=",",
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\r\n",
    )

    print(
        f"Saved {filename}: "
        f"{len(df):,} rows / "
        f"{os.path.getsize(filename):,} bytes"
    )


# ============================================================
# VERIFY
# ============================================================

def verify(filename):

    df = pd.read_csv(
        filename,
        dtype=str,
        keep_default_na=False,
    )

    if list(
        df.columns
    ) != COLUMNS:

        raise RuntimeError(
            f"{filename}: header mismatch"
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

    for field in COLUMNS:

        empty_count = (
            df[field]
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
        )

        if empty_count:

            raise RuntimeError(
                f"{filename}: "
                f"{field} has "
                f"{empty_count} empty values"
            )

    bad_price = ~df[
        "price"
    ].str.match(
        r"^[0-9]+\.[0-9]{2} [A-Z]{3}$"
    )

    if bad_price.any():

        raise RuntimeError(
            f"{filename}: "
            f"{bad_price.sum()} invalid prices"
        )

    print(
        f"Verified {filename}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        SOURCE_FEED_URL,
    )

    data = download_feed(
        feed_url
    )

    products = build_products(
        data
    )

    save_csv(
        products[
            "lifestyle"
        ],
        LIFESTYLE_FILE,
    )

    save_csv(
        products[
            "basketball"
        ],
        BASKETBALL_FILE,
    )

    verify(
        LIFESTYLE_FILE
    )

    verify(
        BASKETBALL_FILE
    )

    base = (
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
    )

    print()
    print(
        base + LIFESTYLE_FILE
    )

    print(
        base + BASKETBALL_FILE
    )


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print(
            f"FATAL ERROR: {error}"
        )

        sys.exit(1)
