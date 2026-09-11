import csv
import os
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd
import requests


DEFAULT_CROPINK_FEED_URL = (
    "https://backend.ballzy.eu/et/amfeed/feed/download"
    "?id=102&file=cropink_et.xml"
)

OUTPUT_FILE = "chatgpt_ads_test.csv"
TEST_PRODUCT_COUNT = 5
REQUEST_TIMEOUT = 120

COLUMNS = [
    "item_id",
    "title",
    "description",
    "url",
    "image_url",
    "brand",
    "price",
    "availability",
]


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


def download_feed(url):
    print(f"Downloading: {url}")

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "Ballzy-OpenAI-Feed-Test/1.0",
        },
    )

    response.raise_for_status()

    print(
        f"Downloaded: "
        f"{len(response.content):,} bytes"
    )

    return response.content


def build_test_feed(xml_data):
    root = ET.fromstring(
        xml_data
    )

    namespaces = {
        "g": "http://base.google.com/ns/1.0"
    }

    products = []

    for item in root.findall(
        ".//item"
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
        }

        if not all(
            str(product[field]).strip()
            for field in COLUMNS
        ):
            continue

        if not url.startswith(
            "https://"
        ):
            continue

        if not image_url.startswith(
            "https://"
        ):
            continue

        products.append(
            product
        )

        if len(products) >= TEST_PRODUCT_COUNT:
            break

    if not products:
        raise RuntimeError(
            "No valid products found."
        )

    return products


def save_csv(products):
    df = pd.DataFrame(
        products,
        columns=COLUMNS,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    print()
    print(
        f"Saved {len(df)} products "
        f"to {OUTPUT_FILE}"
    )

    print()
    print("HEADER:")
    print(
        ",".join(df.columns)
    )

    print()
    print("FIRST ROW:")
    print(
        df.iloc[0].to_dict()
    )


def main():
    feed_url = os.environ.get(
        "CROPINK_FEED_URL",
        DEFAULT_CROPINK_FEED_URL,
    )

    data = download_feed(
        feed_url
    )

    products = build_test_feed(
        data
    )

    save_csv(
        products
    )

    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERROR: {error}"
        )
        sys.exit(1)
