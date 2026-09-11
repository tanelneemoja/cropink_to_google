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

DEFAULT_OUTPUT_CSV_BASE = "chatgpt_ads_feed"
REQUEST_TIMEOUT = 120


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
    "target_countries",
    "is_eligible_search",
    "is_eligible_checkout",
    "is_ads_eligible",
    "product_type",
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
        element.text.strip().split()
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

    value = element.text.strip().lower()

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
# CATEGORY / BUSINESS LINE
# ============================================================

def get_business_line(item):
    """
    Reads custom_label_0 and splits products into:
    - lifestyle
    - basketball
    """

    element = item.find(
        "custom_label_0"
    )

    if (
        element is None
        or not element.text
    ):
        return None

    value = (
        element.text
        .strip()
        .lower()
    )

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
            "User-Agent": "Ballzy-OpenAI-Feed/1.0",
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

    products_by_category = {
        "lifestyle": [],
        "basketball": [],
    }

    total_items = 0
    ignored_items = 0
    invalid_items = 0

    for item in root.findall(
        ".//item"
    ):

        total_items += 1

        business_line = get_business_line(
            item
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

        # ---------------------------------------------
        # Product type comes from:
        #
        # <g:google_product_category>
        # <![CDATA[ Men's Socks ]]>
        # </g:google_product_category>
        # ---------------------------------------------

        product_type = clean_text(
            get_text(
                item,
                "g:google_product_category",
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

            "seller_name": "Streetbrand OÜ",
            "target_countries": "EE",
            "is_eligible_search": "true",
            "is_eligible_checkout": "false",
            "is_ads_eligible": "true",

            "product_type": product_type,
        }

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

        if not all(
            str(
                product[field]
            ).strip()
            for field in required_fields
        ):
            invalid_items += 1
            continue

        if not url.startswith(
            "https://"
        ):
            invalid_items += 1
            continue

        if not image_url.startswith(
            "https://"
        ):
            invalid_items += 1
            continue

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
        f"Total XML items:     "
        f"{total_items:,}"
    )

    print(
        f"Ignored categories:  "
        f"{ignored_items:,}"
    )

    print(
        f"Invalid products:    "
        f"{invalid_items:,}"
    )

    print(
        f"Lifestyle products:  "
        f"{len(products_by_category['lifestyle']):,}"
    )

    print(
        f"Basketball products: "
        f"{len(products_by_category['basketball']):,}"
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
        lineterminator="\n",
    )

    size = os.path.getsize(
        filename
    )

    print()
    print(
        f"Saved: {filename}"
    )

    print(
        f"Products: "
        f"{len(df):,}"
    )

    print(
        f"File size: "
        f"{size:,} bytes"
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

        print(
            df.iloc[0].to_dict()
        )


# ============================================================
# VERIFY CSV
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
            f"Column structure mismatch in {filename}"
        )

    if len(df) == 0:

        raise RuntimeError(
            f"No products in {filename}"
        )

    # Required columns must not be empty
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

        empty = (
            df[field]
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
        )

        if empty:

            raise RuntimeError(
                f"{filename}: "
                f"{field} has "
                f"{empty} empty values"
            )

    bad_urls = df[
        ~df["url"].str.startswith(
            "https://"
        )
    ]

    if len(
        bad_urls
    ) > 0:

        raise RuntimeError(
            f"{filename}: "
            f"{len(bad_urls)} "
            f"non-HTTPS URLs"
        )

    bad_images = df[
        ~df[
            "image_url"
        ].str.startswith(
            "https://"
        )
    ]

    if len(
        bad_images
    ) > 0:

        raise RuntimeError(
            f"{filename}: "
            f"{len(bad_images)} "
            f"non-HTTPS image URLs"
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
    print("OPENAI ADS FULL FEED GENERATOR")
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

    products_by_category = build_products(
        data
    )

    lifestyle_file = (
        f"{output_base}_lifestyle.csv"
    )

    basketball_file = (
        f"{output_base}_basketball.csv"
    )

    save_csv(
        products_by_category[
            "lifestyle"
        ],
        lifestyle_file,
    )

    save_csv(
        products_by_category[
            "basketball"
        ],
        basketball_file,
    )

    print()
    print("=" * 70)
    print("VERIFYING FEEDS")
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
        "Lifestyle feed:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "chatgpt_ads_feed_lifestyle.csv"
    )

    print()
    print(
        "Basketball feed:"
    )

    print(
        "https://tanelneemoja.github.io/"
        "cropink_to_google/"
        "chatgpt_ads_feed_basketball.csv"
    )

    return True


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print()
        print(
            f"ERROR: {error}"
        )

        sys.exit(1)
