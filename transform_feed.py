import requests
import xml.etree.ElementTree as ET
import pandas as pd
import os

def transform_ballzy_feeds():
    url = "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4"
    print(f"Fetching feed from {url}...")
    
    response = requests.get(url)
    root = ET.fromstring(response.content)
    
    # Standard Google Merchant Center namespace
    namespaces = {'g': 'http://base.google.com/ns/1.0'}
    items = root.findall('.//item')
    
    data = []
    # Identify all tags present in the first item to keep headers exact
    all_tags = [child.tag for child in items[0]]

    for item in items:
        row = {}
        for child in item:
            # Keep the tag name exactly as is (e.g., {namespace}id)
            # We will clean the header names later for the CSV
            row[child.tag] = child.text or ""
        data.append(row)

    df = pd.DataFrame(data)

    # Clean headers: remove the {url} part but keep the 'g:' prefix for compatibility
    df.columns = [col.replace('{http://base.google.com/ns/1.0}', 'g:') for col in df.columns]

    # The column we need to target is 'g:link'
    link_col = 'g:link'
    
    markets = ['lv', 'lt', 'fi']
    for lang in markets:
        df_market = df.copy()
        # Transform the link column only
        df_market[link_col] = df_market[link_col].str.replace('/et/', f'/{lang}/', regex=False)
        
        output_file = f"ballzy_{lang}_catalogue.csv"
        df_market.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Generated {output_file} with {len(df_market)} products.")

if __name__ == "__main__":
    transform_ballzy_feeds()
