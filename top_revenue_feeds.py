Here is the complete, production-ready Python script (top_revenue_feeds.py).

This version is optimized for your GitHub Actions workflow: it uses environment variables for the Sheet ID, handles deduplication by summing revenue, and generates four separate CSV files formatted for Google Ads Page Feeds.

Python

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
    Downloads XML and maps Title -> Link. 
    Handles both standard and Google-namespaced tags.
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        feed_map = {}
        # Namespaces often used in Google Merchant feeds
        namespaces = {'g': 'http://base.google.com/ns/1.0'}
        
        for item in root.findall('.//item'):
            # Try standard <title> first, then <g:title>
            title_node = item.find('title')
            if title_node is None:
                title_node = item.find('g:title', namespaces)
            
            link_node = item.find('link')
            if link_node is None:
                link_node = item.find('g:link', namespaces)
                
            if title_node is not None and link_node is not None:
                feed_map[title_node.text.strip()] = link_node.text.strip()
        return feed_map
    except Exception as e:
        print(f"   [!] XML Error: {e}")
        return {}

def process_country_feed(country, gid):
    print(f"--- Processing {country} ---")
    
    # 1. Download Sheet data as CSV
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        print(f"   [!] Download failed: {e}")
        return

    # 2. Revenue Aggregation & Deduplication
    # Use 'Item Revenue' and 'Corrected Name' per your requirement
    if 'Corrected Name' not in df.columns or 'Item Revenue' not in df.columns:
        print(f"   [!] Headers missing. Found: {list(df.columns)}")
        return

    # Convert revenue to number, ignoring text errors
    df['Item Revenue'] = pd.to_numeric(df['Item Revenue'], errors='coerce').fillna(0)
    
    # SUM revenue for duplicates found in 'Corrected Name'
    df_summed = df.groupby('Corrected Name')['Item Revenue'].sum().reset_index()
    
    # 3. Get Top 50 by Summed Revenue
    top_50 = df_summed.sort_values(by='Item Revenue', ascending=False).head(50)
    
    # 4. Match against XML Feed
    feed_map = get_xml_feed_map(FEED_URLS[country])
    page_feed_rows = []
    
    for _, row in top_50.iterrows():
        name = str(row['Corrected Name']).strip()
        if name in feed_map:
            page_feed_rows.append({
                'Page URL': feed_map[name],
                'Custom label': f'Top50_{country}'
            })
    
    # 5. Export Individual CSV for Google Ads
    if page_feed_rows:
        output_df = pd.DataFrame(page_feed_rows)
        filename = f"{country}_page_feed.csv"
        # Output headers: Page URL, Custom label
        output_df.to_csv(filename, index=False)
        print(f"   [Success] Created {filename} with {len(page_feed_rows)} items.")
    else:
        print(f"   [!] No matches found for {country}. Check if 'Corrected Name' matches XML titles.")

def main():
    if SHEET_ID == 'PASTE_YOUR_DEFAULT_ID_HERE':
        print("Error: GOOGLE_SHEET_ID environment variable is missing.")
        return

    for country, gid in COUNTRY_GIDS.items():
        process_country_feed(country, gid)

if __name__ == "__main__":
    main()
