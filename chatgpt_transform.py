import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

import pandas as pd
import requests

SOURCE_FEED_URL = "https://backend.ballzy.eu/et/amfeed/feed/download?id=102&file=cropink_et.xml"
REQUEST_TIMEOUT = 120

SELLER_NAME = "Streetbrand OÜ"
SELLER_URL = "https://ballzy.eu/et"
RETURN_POLICY = "https://ballzy.eu/et/shopping-help#returning"
TARGET_COUNTRIES = "EE"
STORE_COUNTRY = "EE"

LIFESTYLE_FILE = "openai_ads_native_lifestyle.csv"
BASKETBALL_FILE = "openai_ads_native_basketball.csv"

COLUMNS = [
    "item_id","title","description","url","brand","image_url","price","availability",
    "seller_name","seller_url","is_eligible_search","is_eligible_checkout",
    "return_policy","target_countries","store_country","is_ads_eligible",
]

def clean_text(value):
    if not value:
        return ""
    value = str(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", value)
    return " ".join(value.split()).strip()

def force_https(url):
    if not url:
        return ""
    url = url.strip()
    return "https://" + url[7:] if url.lower().startswith("http://") else url

def get_text(item, xpath, namespaces=None):
    element = item.find(xpath, namespaces=namespaces)
    return element.text.strip() if element is not None and element.text else ""

def get_custom_label(item, index, namespaces):
    value = get_text(item, f"custom_label_{index}")
    if value:
        return clean_text(value)
    return clean_text(get_text(item, f"g:custom_label_{index}", namespaces))

def parse_price(element):
    if element is None or not element.text:
        return ""
    raw = " ".join(element.text.strip().split())
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})", raw)
    return f"{m.group(1)} {m.group(2).upper()}" if m else ""

def parse_availability(element):
    if element is None or not element.text:
        return ""
    value = element.text.strip().lower()
    return {
        "in stock":"in_stock","in_stock":"in_stock",
        "out of stock":"out_of_stock","out_of_stock":"out_of_stock",
        "preorder":"pre_order","pre_order":"pre_order",
        "backorder":"backorder","back_order":"backorder",
    }.get(value, "")

def get_business_line(item, namespaces):
    label = get_custom_label(item, 0, namespaces).lower()
    if "lifestyle" in label:
        return "lifestyle"
    if "basketball" in label:
        return "basketball"
    return None

def validate_product(product):
    errors = []
    for field in COLUMNS:
        if not str(product.get(field, "")).strip():
            errors.append(f"missing_{field}")
    if product["url"] and not product["url"].startswith("https://"):
        errors.append("url_not_https")
    if product["image_url"] and not product["image_url"].startswith("https://"):
        errors.append("image_url_not_https")
    if product["availability"] not in {"in_stock","out_of_stock","pre_order","backorder"}:
        errors.append("invalid_availability")
    if product["availability"] in {"pre_order","backorder"}:
        errors.append("needs_availability_date")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)? [A-Z]{3}", product["price"]):
        errors.append("invalid_price")
    return errors

def download_source_feed(url):
    print("=" * 72)
    print("DOWNLOADING BALLZY SOURCE FEED")
    print("=" * 72)
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent":"Streetbrand-OpenAI-Ads-Feed/1.0","Accept":"application/xml,text/xml,*/*"},
    )
    response.raise_for_status()
    print(f"Downloaded {len(response.content):,} bytes")
    return response.content

def build_feeds(xml_data):
    root = ET.fromstring(xml_data)
    ns = {"g":"http://base.google.com/ns/1.0"}
    feeds = {"lifestyle":[], "basketball":[]}
    seen_ids = set()
    rejection_counts = Counter()
    total = ignored = duplicates = 0

    for item in root.findall(".//item"):
        total += 1
        line = get_business_line(item, ns)
        if line is None:
            ignored += 1
            continue

        item_id = clean_text(get_text(item, "g:id", ns))
        if item_id in seen_ids:
            duplicates += 1
            continue

        product = {
            "item_id": item_id,
            "title": clean_text(get_text(item, "g:title", ns)),
            "description": clean_text(get_text(item, "g:description", ns)),
            "url": force_https(get_text(item, "g:link", ns)),
            "brand": clean_text(get_text(item, "g:brand", ns)),
            "image_url": force_https(get_text(item, "g:image_link", ns)),
            "price": parse_price(item.find("g:price", ns)),
            "availability": parse_availability(item.find("g:availability", ns)),
            "seller_name": SELLER_NAME,
            "seller_url": SELLER_URL,
            "is_eligible_search": "true",
            "is_eligible_checkout": "false",
            "return_policy": RETURN_POLICY,
            "target_countries": TARGET_COUNTRIES,
            "store_country": STORE_COUNTRY,
            "is_ads_eligible": "true",
        }

        errors = validate_product(product)
        if errors:
            for e in errors:
                rejection_counts[e] += 1
            continue

        seen_ids.add(item_id)
        feeds[line].append(product)

    print("\nBUILD SUMMARY")
    print(f"Total XML items:    {total:,}")
    print(f"Ignored categories: {ignored:,}")
    print(f"Duplicate IDs:      {duplicates:,}")
    print(f"Lifestyle rows:     {len(feeds['lifestyle']):,}")
    print(f"Basketball rows:    {len(feeds['basketball']):,}")
    print("Rejected rows by reason:")
    if rejection_counts:
        for reason, count in rejection_counts.most_common():
            print(f"  {reason}: {count:,}")
    else:
        print("  none")
    return feeds

def save_csv(products, filename):
    df = pd.DataFrame(products, columns=COLUMNS)
    df.to_csv(filename, index=False, encoding="utf-8", sep=",",
              quoting=csv.QUOTE_MINIMAL, doublequote=True, lineterminator="\n")
    print(f"Saved {filename}: {len(df):,} rows / {os.path.getsize(filename):,} bytes")

def verify_csv(filename):
    df = pd.read_csv(filename, dtype=str, keep_default_na=False)
    if list(df.columns) != COLUMNS:
        raise RuntimeError(f"{filename}: header mismatch")
    if df.empty:
        raise RuntimeError(f"{filename}: zero rows")
    if df["item_id"].duplicated().any():
        raise RuntimeError(f"{filename}: duplicate item IDs")
    for col in COLUMNS:
        if df[col].str.strip().eq("").any():
            raise RuntimeError(f"{filename}: empty values in {col}")
    print(f"Verified {filename}: {len(df):,} valid rows")

def main():
    source_url = os.environ.get("CROPINK_FEED_URL", SOURCE_FEED_URL)
    data = download_source_feed(source_url)
    feeds = build_feeds(data)
    save_csv(feeds["lifestyle"], LIFESTYLE_FILE)
    save_csv(feeds["basketball"], BASKETBALL_FILE)
    verify_csv(LIFESTYLE_FILE)
    verify_csv(BASKETBALL_FILE)
    base = "https://tanelneemoja.github.io/cropink_to_google/"
    print(base + LIFESTYLE_FILE)
    print(base + BASKETBALL_FILE)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FATAL ERROR: {error}")
        sys.exit(1)
