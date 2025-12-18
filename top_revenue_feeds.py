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
    """Normalizes text for better matching."""
    if not text:
        return ""
    # Convert to lowercase and strip whitespace
    text = str(text).lower().strip()
    # Normalize common tricky characters
    text = text.replace('´', "'").replace('’', "'").replace('‘', "'")
    return text

def get_xml_feed_map(url):
    """Downloads XML and maps cleaned g:title -> g:link."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        feed_map = {}
        ns = {'g': 'http://base.google.com/ns/1.0'}
        
        for item in root.findall('.//item'):
            # Fix for DeprecationWarning: explicitly check 'is not None'
            title_node = item.find('g:title', ns)
            if title_node is None:
                title_node = item.find('title')
            
            link_node = item.find('g:link', ns)
            if link_node is None:
                link_node = item.find('link')
                
            if title_node is not None and link_node is not None:
                raw_title = title_node.text if title_node.text else ""
                raw_link = link_node.text if link_node.text else ""
                
                # Clean the title for matching but keep link as is
                if raw_title:
                    feed_map[clean_text(raw_title)] = raw_link.strip()
                    
        return feed_map
    except Exception as e:
        print(f"   [!] XML Error: {e}")
        return {}

def process_country_feed(country, gid):
    print(f"\n--- Processing {country} ---")
    
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        print(f"   [!] Sheet Download failed: {e}")
        return

    col_name = 'Corrected name'
    col_rev = 'Item revenue'

    if col_name not in df.columns or col_rev not in df.columns:
        print(f"   [!] Headers not found. Found: {list(df.columns)}")
        return

    df[col_rev] = pd.to_numeric(df[col_rev], errors='coerce').fillna(0)
    df_summed = df.groupby(col_name)[col_rev].sum().reset_index()
    top_50_df = df_summed.sort_values(by=col_rev, ascending=False).head(50)
    
    feed_map = get_xml_feed_map(FEED_URLS[country])
    page_feed_rows = []

    for _, row in top_50_df.iterrows():
        # Clean the name from the sheet
        original_name = str(row[col_name])
        cleaned_sheet_name = clean_text(original_name)
        
        if cleaned_sheet_name in feed_map:
            page_feed_rows.append({
                'Page URL': feed_map[cleaned_sheet_name],
                'Custom label': f'Top50_{country}'
            })
    
    if page_feed_rows:
        output_df = pd.DataFrame(page_feed_rows)
        filename = f"{country}_page_feed.csv"
        output_df.to_csv(filename, index=False)
        print(f"   [Success] Created {filename} with {len(page_feed_rows)} items.")
    else:
        print(f"   [!] No matches for {country}.")
        # DIAGNOSTIC: Show why it's failing
        if not top_50_df.empty:
            print(f"   [Debug] Sheet example: '{clean_text(top_50_df.iloc[0][col_name])}'")
        if feed_map:
            print(f"   [Debug] Feed examples: {list(feed_map.keys())[:3]}")

def main():
    if SHEET_ID == 'PASTE_YOUR_DEFAULT_ID_HERE' and 'GOOGLE_SHEET_ID' not in os.environ:
        print("Error: No Google Sheet ID found.")
        return

    for country, gid in COUNTRY_GIDS.items():
        process_country_feed(country, gid)

if __name__ == "__main__":
    main()
