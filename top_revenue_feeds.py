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

def get_xml_feed_map(url):
    """
    Downloads XML and maps g:title -> g:link.
    Uses .strip() to clean up CDATA newlines and spaces.
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        feed_map = {}
        ns = {'g': 'http://base.google.com/ns/1.0'}
        
        # This handles both <item> and CDATA structures
        for item in root.findall('.//item'):
            title_node = item.find('g:title', ns) or item.find('title')
            link_node = item.find('g:link', ns) or item.find('link')
                
            if title_node is not None and link_node is not None:
                # CRITICAL: .strip() removes the newlines inside <![CDATA[ ]]>
                clean_title = title_node.text.strip() if title_node.text else ""
                clean_link = link_node.text.strip() if link_node.text else ""
                
                if clean_title:
                    feed_map[clean_title] = clean_link
                    
        return feed_map
    except Exception as e:
        print(f"   [!] XML Error: {e}")
        return {}

def process_country_feed(country, gid):
    print(f"\n--- Processing {country} ---")
    
    # 1. Download Sheet data
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        print(f"   [!] Sheet Download failed: {e}")
        return

    # EXACT HEADERS from your previous logs
    col_name = 'Corrected name'
    col_rev = 'Item revenue'

    if col_name not in df.columns or col_rev not in df.columns:
        print(f"   [!] Headers not found. Found: {list(df.columns)}")
        return

    # 2. Revenue Aggregation (Handles duplicates)
    df[col_rev] = pd.to_numeric(df[col_rev], errors='coerce').fillna(0)
    df_summed = df.groupby(col_name)[col_rev].sum().reset_index()
    
    # 3. Get Top 50
    top_50_df = df_summed.sort_values(by=col_rev, ascending=False).head(50)
    
    # 4. Match against Feed (with CDATA cleaning)
    feed_map = get_xml_feed_map(FEED_URLS[country])
    page_feed_rows = []

    for _, row in top_50_df.iterrows():
        sheet_name = str(row[col_name]).strip()
        
        if sheet_name in feed_map:
            page_feed_rows.append({
                'Page URL': feed_map[sheet_name],
                'Custom label': f'Top50_{country}'
            })
    
    # 5. Export to CSV (Google Ads Format)
    if page_feed_rows:
        output_df = pd.DataFrame(page_feed_rows)
        filename = f"{country}_page_feed.csv"
        # Columns must be exactly: Page URL, Custom label
        output_df.to_csv(filename, index=False)
        print(f"   [Success] Created {filename} with {len(page_feed_rows)} matched items.")
    else:
        print(f"   [!] No matches. Top Sheet name: '{top_50_df.iloc[0][col_name] if not top_50_df.empty else 'N/A'}'")

def main():
    if SHEET_ID == 'PASTE_YOUR_DEFAULT_ID_HERE' and 'GOOGLE_SHEET_ID' not in os.environ:
        print("Error: No Google Sheet ID found in environment.")
        return

    for country, gid in COUNTRY_GIDS.items():
        process_country_feed(country, gid)

if __name__ == "__main__":
    main()
