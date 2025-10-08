import requests
import xml.etree.ElementTree as ET
import os
import re # <-- Added to handle dynamic namespace extraction

# --- Configuration ---
# FIX: Hardcoded the URL to bypass environment variable errors as requested.
XML_FEED_URL = "https://f.cropink.com/feed/11e9623b-ed98-4a61-a9f6-445782c38aa4"
OUTPUT_FILENAME = "street_shoes_product_names.txt"
TARGET_CATEGORY_PART = "Street Shoes"

# Define the Google Merchant Center Namespace (for g: elements)
NAMESPACES = {'g': 'http://base.google.com/ns/1.0'}
ET.register_namespace('g', NAMESPACES['g']) 

def fetch_xml_data(url):
    """Fetches the XML data from the given URL and prints debug info."""
    # The URL check is removed since the URL is hardcoded.
    print(f"DEBUG: Attempting to fetch XML feed from: {url}")
    try:
        response = requests.get(url, timeout=45) 
        response.raise_for_status() 
        print(f"DEBUG: Fetch successful. Content length: {len(response.content)} bytes.")
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"FATAL ERROR: Failed to fetch data: {e}")
        return None

def extract_street_shoes_list(xml_content):
    """Parses XML and extracts brand and title for products matching the category."""
    if not xml_content:
        return []

    try:
        root = ET.fromstring(xml_content)
        print(f"DEBUG: XML Parsed successfully. Root tag is: {root.tag}")
    except ET.ParseError as e:
        print(f"FATAL ERROR: Error parsing XML: {e}")
        return []

    # --- Namespace Discovery for Product Items (RSS/Atom) ---
    product_tag_name = 'item' 
    namespace_match = re.match(r'\{(.+)\}', root.tag)
    
    if namespace_match:
        default_namespace = namespace_match.group(1)
        qualified_item = f"{{{default_namespace}}}item"
        qualified_entry = f"{{{default_namespace}}}entry"
        
        items = root.findall(f'.//{qualified_item}') 
        if not items:
            items = root.findall(f'.//{qualified_entry}')
        
        print(f"DEBUG: Using qualified search. Default namespace: {default_namespace}. Found {len(items)} items.")
    else:
        # Fallback to simple find (no namespaces)
        items = root.findall('.//item') or root.findall('.//entry')
        print(f"DEBUG: Using simple search (no namespace prefix). Found {len(items)} items.")

    # --- Check for successful item discovery ---
    if not items:
        print("WARNING: Could not find any product items using common paths (./item, ./entry, or qualified names).")
        print("DEBUG: Root Element Children (Snippet):")
        for i, child in enumerate(root):
            if i < 5:
                print(f"  Child {i+1} Tag: {child.tag}")
            else:
                break
        return []
        
    print(f"DEBUG: Found {len(items)} product items to process.")
    
    unique_product_list = set()
    matched_count = 0
    
    for item in items:
        # Attributes should still use the 'g:' namespace
        category_element = item.find('g:google_product_category', NAMESPACES)
        
        if category_element is not None and category_element.text and TARGET_CATEGORY_PART in category_element.text:
            
            matched_count += 1
            
            title_element = item.find('g:title', NAMESPACES)
            brand_element = item.find('g:custom_label_3', NAMESPACES)

            title = title_element.text if title_element is not None else None
            brand = brand_element.text if brand_element is not None else None
            
            if title is None or brand is None:
                # Log if required data is missing, but skip product
                print(f"WARNING: Skipping item {matched_count}. Title ({title}) or Brand ({brand}) is missing.")
                continue
                
            # Format and Clean Output 
            clean_title = ' '.join(title.strip().lower().split())
            clean_brand = ' '.join(brand.strip().lower().split())
            
            output_string = f"{clean_brand} {clean_title}"
            unique_product_list.add(output_string)

    print(f"DEBUG: Finished processing. Total items matched by category: {matched_count}.")
    print(f"DEBUG: Final unique products extracted: {len(unique_product_list)}")
    
    return sorted(list(unique_product_list))

def write_product_list(data_list, filename):
    """Writes the list of unique products to the specified file."""
    print(f"Writing {len(data_list)} unique product names to {filename}...")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for line in data_list:
                f.write(line + '\n')
        print("SUCCESS: File created successfully.")
    except IOError as e:
        print(f"FATAL ERROR: Error writing file: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    if 'requests' not in os.environ.get('PIP_PACKAGES', ''):
        try:
            pass 
        except ImportError:
            pass 

    xml_data = fetch_xml_data(XML_FEED_URL)
    
    if xml_data:
        extracted_products = extract_street_shoes_list(xml_data)
        if extracted_products:
            write_product_list(extracted_products, OUTPUT_FILENAME)
        else:
            print("INFO: No products matched the filter, or extraction failed. Output file is empty.")
