import requests
import xml.etree.ElementTree as ET
import csv

def transform():
    url = "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4"
    response = requests.get(url)
    root = ET.fromstring(response.content)
    
    # Namespaces
    namespaces = {'g': 'http://base.google.com/ns/1.0'}
    items = root.findall('.//item')
    
    markets = ['lv', 'lt', 'fi']
    
    # Get all unique tags from the first item to define CSV headers
    if not items:
        print("No items found.")
        return
        
    headers = []
    for child in items[0]:
        tag = child.tag.replace('{http://base.google.com/ns/1.0}', 'g:')
        headers.append(tag)

    for lang in markets:
        filename = f"{lang}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            
            for item in items:
                row = []
                for child in item:
                    value = child.text or ""
                    # Check if this tag is the link tag (ignoring namespace for the check)
                    if child.tag.endswith('link') and not child.tag.endswith('image_link'):
                        value = value.replace("/et/", f"/{lang}/")
                    row.append(value)
                writer.writerow(row)
        print(f"Created {filename} with {len(items)} products.")

if __name__ == "__main__":
    transform()
