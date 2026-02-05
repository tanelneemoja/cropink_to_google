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

def clean_name(text):
    """Normalize text for matching."""
    if not text: return ""
    return str(text).lower().strip().replace('´', "'").replace('’', "'")

def force_https_clean(url_text):
    """Aggressively strips whitespace and forces https."""
    if not url_text: return ""
    # Strip whitespace, newlines, and tabs often hidden in CDATA
    clean_url = str(url_text).strip()
    if clean_url.startswith("http://"):
        return clean_url.replace("http://", "https://", 1)
    elif not clean_url.startswith("https://") and "://" not in clean_url:
        # Fallback for protocol-relative links
        return "https://" + clean_url.lstrip("/")
    return clean_url

def get_xml_feed_map(url):
    """Parses XML and maps cleaned g:title -> forced https g:link."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        feed_map = {}
        # Google Merchant Center namespace
        ns = {'g': 'http://base.google.com/ns/1.0'}
        
        items = root.findall('.//item')
        print(f"    [Debug] Found {len(items)} items in XML feed.")

        for item in items:
            # FIX: Use 'is not None' to avoid DeprecationWarning
            title_node = item.find('g:title', ns)
            if title_node is None:
                title_node = item.find('title')
                
            link_node = item.find('g:link', ns)
            if link_node is None:
                link_node = item.find('link')
                
            if title_node is not None and link_node is not None:
                title_key = clean_name(title_node.text)
                secure_link = force_https_clean(link_node.text)
                
                if title_key and title_key not in feed_map:
                    feed_map[title_key] = secure_link
        
        print(f"    [Debug] Mapped {len(feed_map)} unique titles from feed.")
        return feed_map
    except Exception as e:
        print(f"    [!] XML Error: {e}")
        return {}

def process_country_feed(country, gid):
    print(f"\n--- Processing {country} ---")
    
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        print(f"   [!] Sheet Download failed: {e}")
        return

    name_col = 'Corrected name'
    rev_col = 'Item revenue'

    if name_col not in df.columns or rev_col not in df.columns:
        print(f"   [!] Headers missing. Found: {list(df.columns)}")
        return

    df[rev_col] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
    unique_products = df.groupby(name_col)[rev_col].sum().reset_index()
    unique_products = unique_products.sort_values(by=rev_col, ascending=False)
    
    feed_map = get_xml_feed_map(FEED_URLS[country])
    page_feed_results = []
    seen_urls = set()

    for _, row in unique_products.iterrows():
        if len(page_feed_results) >= 50:
            break
            
        sheet_name_clean = clean_name(row[name_col])
        if sheet_name_clean in feed_map:
            match_url = feed_map[sheet_name_clean]
            if match_url not in seen_urls:
                page_feed_results.append({
                    'Page URL': match_url,
                    'Custom label': f'Top50_{country}'
                })
                seen_urls.add(match_url)

    if page_feed_results:
        # LOGGING CHECK: Print the first URL to verify HTTPS in GitHub logs
        print(f"   [Log Check] First URL: {page_feed_results[0]['Page URL']}")
        
        final_df = pd.DataFrame(page_feed_results)
        filename = f"{country}_page_feed.csv"
        final_df.to_csv(filename, index=False)
        print(f"   [Done] {filename} saved with {len(page_feed_results)} items.")
    else:
        print(f"   [!] No matches found for {country}.")

def main():
    if SHEET_ID == 'PASTE_YOUR_DEFAULT_ID_HERE' and 'GOOGLE_SHEET_ID' not in os.environ:
        print("Error: Missing GOOGLE_SHEET_ID.")
        return
        
    for country, gid in COUNTRY_GIDS.items():
        process_country_feed(country, gid)

if __name__ == "__main__":
    main()
