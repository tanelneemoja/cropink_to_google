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

REQUEST_TIMEOUT = 120
SELLER_NAME = "Streetbrand OÜ"
TARGET_COUNTRY = "EE"

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
]

LIFESTYLE_SIZES = [1, 10, 50, 100, 250, 500, 1000]
BASKETBALL_SIZES = [1, 10, 50, 100, 250]


def clean_text(text):
    if not text:
        return ""
    text = str(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", text)
    return " ".join(text.split()).strip()


def force_https(url):
    if not url:
        return ""
    url = url.strip()
    if url.lower().startswith("http://"):
        return "https://" + url[7:]
    return url


def get_text(item, xpath, namespaces=None):
    element = item.find(xpath, namespaces=namespaces)
    if element is not None and element.text:
        return element.text.strip()
    return ""


def get_custom_label(item, index, namespaces):
    value = get_text(item, f"custom_label_{index}")
    if value:
        return clean_text(value)
    return clean_text(get_text(item, f"g:custom_label_{index}", namespaces))


def parse_price(element):
    if element is None or not element.text:
        return ""
    value = " ".join(element.text.strip().split())
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})$", value)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2).upper()}"


def parse_availability(element):
    if element is None or not element.text:
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
    return mapping.get(value, "in_stock")


def get_business_line(item, namespaces):
    label = get_custom_label(item, 0, namespaces).lower()
    if "lifestyle" in label:
        return "lifestyle"
    if "basketball" in label:
        return "basketball"
    return None


def download_feed(url):
    print(f"Downloading: {url}")
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "Ballzy-OpenAI-Feed-Diagnostic/1.0"},
    )
    response.raise_for_status()
    print(f"Downloaded {len(response.content):,} bytes")
    return response.content


def build_products(xml_data):
    root = ET.fromstring(xml_data)
    ns = {"g": "http://base.google.com/ns/1.0"}

    out = {"lifestyle": [], "basketball": []}
    seen = set()

    total = ignored = invalid = dupes = 0

    for item in root.findall(".//item"):
        total += 1
        line = get_business_line(item, ns)
        if line is None:
            ignored += 1
            continue

        product = {
            "item_id": clean_text(get_text(item, "g:id", ns)),
            "title": clean_text(get_text(item, "g:title", ns)),
            "description": clean_text(get_text(item, "g:description", ns)),
            "url": force_https(get_text(item, "g:link", ns)),
            "image_url": force_https(get_text(item, "g:image_link", ns)),
            "brand": clean_text(get_text(item, "g:brand", ns)),
            "price": parse_price(item.find("g:price", ns)),
            "availability": parse_availability(item.find("g:availability", ns)),
            "seller_name": SELLER_NAME,
            "target_countries": TARGET_COUNTRY,
            "is_eligible_search": "true",
            "is_eligible_checkout": "false",
            "is_ads_eligible": "true",
        }

        if not all(str(product[c]).strip() for c in COLUMNS):
            invalid += 1
            continue

        if not product["url"].startswith("https://"):
            invalid += 1
            continue

        if not product["image_url"].startswith("https://"):
            invalid += 1
            continue

        if product["item_id"] in seen:
            dupes += 1
            continue

        seen.add(product["item_id"])
        out[line].append(product)

    print("\nSUMMARY")
    print(f"Total XML items:      {total:,}")
    print(f"Ignored categories:   {ignored:,}")
    print(f"Invalid rows:         {invalid:,}")
    print(f"Duplicate IDs:        {dupes:,}")
    print(f"Valid Lifestyle:      {len(out['lifestyle']):,}")
    print(f"Valid Basketball:     {len(out['basketball']):,}")

    return out


def save_file(products, filename):
    df = pd.DataFrame(products, columns=COLUMNS)
    df.to_csv(
        filename,
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
    )
    print(f"{filename}: {len(df):,} rows / {os.path.getsize(filename):,} bytes")


def make_slices(products, prefix, sizes):
    for n in sizes:
        if len(products) >= n:
            save_file(products[:n], f"{prefix}_{n}.csv")
    save_file(products, f"{prefix}_full.csv")


def main():
    feed_url = os.environ.get("CROPINK_FEED_URL", DEFAULT_CROPINK_FEED_URL)
    data = download_feed(feed_url)
    products = build_products(data)

    make_slices(products["lifestyle"], "openai_diag_lifestyle", LIFESTYLE_SIZES)
    make_slices(products["basketball"], "openai_diag_basketball", BASKETBALL_SIZES)

    save_file(products["lifestyle"], "chatgpt_ads_feed_lifestyle.csv")
    save_file(products["basketball"], "chatgpt_ads_feed_basketball.csv")

    print("\nTRY THESE IN THIS ORDER:")
    base = "https://tanelneemoja.github.io/cropink_to_google/"
    names = [
        "openai_diag_lifestyle_1.csv",
        "openai_diag_lifestyle_10.csv",
        "openai_diag_lifestyle_50.csv",
        "openai_diag_lifestyle_100.csv",
        "openai_diag_lifestyle_250.csv",
        "openai_diag_lifestyle_500.csv",
        "openai_diag_lifestyle_1000.csv",
        "openai_diag_lifestyle_full.csv",
        "openai_diag_basketball_1.csv",
        "openai_diag_basketball_10.csv",
        "openai_diag_basketball_50.csv",
        "openai_diag_basketball_100.csv",
        "openai_diag_basketball_250.csv",
        "openai_diag_basketball_full.csv",
    ]
    for name in names:
        print(base + name)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL ERROR: {exc}")
        sys.exit(1)
