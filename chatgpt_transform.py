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
    "item_id", "title", "description", "url", "image_url", "brand", "price",
    "availability", "seller_name", "target_countries", "is_eligible_search",
    "is_eligible_checkout", "is_ads_eligible",
]
LIFESTYLE_SIZES = [1, 10, 50, 100, 250, 500, 1000]
BASKETBALL_SIZES = [1, 10, 50, 100, 250]

# Exact product types observed in the Ballzy XML. No title/description guessing.
ALLOWED_FOOTWEAR = {
    "lifestyle": {"street shoes", "boots"},
    "basketball": {"basketball shoes"},
}


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
        "in stock": "in_stock", "in_stock": "in_stock",
        "out of stock": "out_of_stock", "out_of_stock": "out_of_stock",
        "preorder": "pre_order", "pre_order": "pre_order",
        "backorder": "backorder", "back_order": "backorder",
    }
    return mapping.get(value, "in_stock")


def get_business_line(item, namespaces):
    label = get_custom_label(item, 0, namespaces).lower()
    if "lifestyle" in label:
        return "lifestyle"
    if "basketball" in label:
        return "basketball"
    return None


def is_target_footwear(item, line, namespaces):
