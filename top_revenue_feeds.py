import pandas as pd
import requests
import xml.etree.ElementTree as ET
import os

# --- CONFIGURATION ---
# This pulls from the 'env' section of your GitHub YAML
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', 'PASTE_YOUR_DEFAULT_ID_HERE')

# Replace these GIDs with the actual ID for each tab in your Google Sheet
# You find this at the end of the URL (gid=XXXXX) when you click each tab
COUNTRY_GIDS = {
    'EE': '584562652',        # Example GID for Estonia
    'LT': '1828770726', # Replace with actual LT tab GID
    'LV': '1414826085', # Replace with actual LV tab GID
    'FI': '321921273'  # Replace with actual FI tab GID
}

# Live XML Feed URLs for Weekend.ee
FEED_URLS = {
    'EE': 'https://backend.ballzy.eu/et/amfeed/feed/download?id=102&file=cropink_et.xml',
    'LT': 'https://backend.ballzy.eu/lt/amfeed/feed/download?id=105&file=cropink_lt.xml',
    'LV': 'https://backend.ballzy.eu/lv/amfeed/feed/download?id=104&file=cropink_lv.xml',
    'FI': 'https://backend.ballzy.eu/fi/amfeed/feed/download?id=103&file=cropink_fi.xml'
}

def clean_text(text):
    """Normalize text for matching (lowercase, strip, fix quotes)."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = text.replace('´', "'").replace('’', "'").replace('‘', "'")
    return text

def ensure_https(url):
    """Replaces http with https if present."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("http://"):
        return url.replace("http://", "https://", 1)
    return url

def get_xml_feed_map(url):
    """Parses XML and creates a dictionary of cleaned g:title -> forced https g:link."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        feed_map = {}
        ns = {'g': 'http://base.google.com/ns/1.0'}
        
        items = root.findall('.//item')
        for item in items:
            title_node = item.find('g:title', ns) or item.find('title')
            link_node = item.find('g:link', ns) or item.find('link')
                
            if title_node is not None and link_node is not None:
                raw_title = title_node.text if title_node.text else ""
                raw_link = link_node.text if link_node.text else ""
                
                if raw_title:
                    cleaned_title = clean_text(raw_title)
                    # Force HTTPS immediately
                    secure_link = ensure_https(raw_link)
                    
                    if cleaned_title not in feed_map:
                        feed_map[cleaned_title] = secure_link
                    
        return feed_map
    except Exception as e:
        print(f"   [!] XML Error: {e}")
        return {}

def find_best_url(sheet_name, feed_map):
    """Tries exact match, then checks if the sheet name is part of a feed title."""
    cleaned_sheet = clean_text(sheet_name)
    
    # 1. Exact match
    if cleaned_sheet in feed_map:
        return feed_map[cleaned_sheet]
    
    # 2. Partial match fallback
    for feed_title, url in feed_map.items():
        if cleaned_sheet in feed_title:
            return url
            
    return None

def process_country_feed(country, gid):
    print(f"\n--- Processing {country} ---")
    
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(url)
    except Exception as e:
        print(f"   [!] Failed to download sheet: {e}")
        return

    name_col = 'Corrected name'
    rev_col = 'Item revenue'

    if name_col not in df.columns or rev_col not in df.columns:
        print(f"   [!] Error: Headers '{name_col}' or '{rev_col}' missing.")
        return

    # 1. Deduplicate & Aggregate Revenue (Sum revenue for same 'Corrected name')
    df[rev_col] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
    unique_products = df.groupby(name_col)[rev_col].sum().reset_index()
    
    # 2. Sort by total revenue (Highest First)
    unique_products = unique_products.sort_values(by=rev_col, ascending=False)
    
    # 3. Load Feed
    feed_map = get_xml_feed_map(FEED_URLS[country])
    
    # 4. Find exactly 50 unique matching products
    page_feed_results = []
    seen_urls = set()

    for _, row in unique_products.iterrows():
        if len(page_feed_results) >= 50:
            break
            
        prod_name = row[name_col]
        match_url = find_best_url(prod_name, feed_map)
        
        # Double check match_url is https and not a duplicate
        if match_url:
            match_url = ensure_https(match_url)
            if match_url not in seen_urls:
                page_feed_results.append({
                    'Page URL': match_url,
                    'Custom label': f'Top50_{country}'
                })
                seen_urls.add(match_url)

    # 5. Save the CSV
    if page_feed_results:
        final_df = pd.DataFrame(page_feed_results)
        filename = f"{country}_page_feed.csv"
        # Headers: Page URL, Custom label
        final_df.to_csv(filename, index=False)
        print(f"   [Done] {filename} saved with {len(page_feed_results)} products (Forced HTTPS).")
    else:
        print(f"   [!] Warning: No matches found for {country}.")

def main():
    if SHEET_ID == 'PASTE_YOUR_DEFAULT_ID_HERE' and 'GOOGLE_SHEET_ID' not in os.environ:
        print("Error: Missing GOOGLE_SHEET_ID in environment variables.")
        return
        
    for country, gid in COUNTRY_GIDS.items():
        process_country_feed(country, gid)

if __name__ == "__main__":
    main()
