import requests
import xml.etree.ElementTree as ET
import os # To read environment variables for the URL

# --- Configuration ---
# IMPORTANT: Use an environment variable for the URL in GitHub Actions
XML_FEED_URL = os.environ.get("FEED_URL", "FALLBACK_URL_IF_NOT_SET") 
OUTPUT_FILENAME = "street_shoes_product_names.txt"
TARGET_CATEGORY_PART = "Street Shoes"

# Define the Google Merchant Center Namespace
NAMESPACES = {'g': 'http://base.google.com/ns/1.0'}

def fetch_xml_data(url):
    """Fetches the XML data from the given URL."""
    if url == "FALLBACK_URL_IF_NOT_SET":
        print("ERROR: FEED_URL environment variable is not set. Cannot fetch data.")
        return None
        
    print(f"Fetching XML feed from: {url}")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def extract_street_shoes_list(xml_content):
    """Parses XML and extracts brand and title for products matching the category."""
    if not xml_content:
        return []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return []

    # Use a SET to store results, automatically preventing duplicates
    unique_product_list = set()
    items = root.findall('.//item') 
    
    print(f"Found {len(items)} total items to process.")

    for item in items:
        # 1. Get the Google Product Category (using namespace 'g')
        category_element = item.find('g:google_product_category', NAMESPACES)
        
        # 2. Check for the TARGET_CATEGORY_PART substring 
        #    (This correctly matches "Men's Street Shoes", "Women's Street Shoes", etc.)
        if category_element is not None and TARGET_CATEGORY_PART in category_element.text:
            
            # 3. Extract Title and Custom label 3 (Brand)
            title_element = item.find('g:title', NAMESPACES)
            brand_element = item.find('g:custom_label_3', NAMESPACES)

            title = title_element.text if title_element is not None else ""
            brand = brand_element.text if brand_element is not None else ""
            
            # 4. Format and Clean Output (e.g., "adidas samba og")
            if title and brand:
                # Clean and lowercase the text for better consistency and comparison
                clean_title = ' '.join(title.strip().lower().split())
                clean_brand = ' '.join(brand.strip().lower().split())
                
                output_string = f"{clean_brand} {clean_title}"
                
                # Add to the SET. Duplicates are ignored automatically.
                unique_product_list.add(output_string)
    
    return sorted(list(unique_product_list)) # Convert back to a sorted list for final output

def write_product_list(data_list, filename):
    """Writes the list of unique products to the specified file."""
    print(f"Writing {len(data_list)} unique product names to {filename}...")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for line in data_list:
                f.write(line + '\n')
        print("Done. File created successfully.")
    except IOError as e:
        print(f"Error writing file: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    xml_data = fetch_xml_data(XML_FEED_URL)
    
    if xml_data:
        extracted_products = extract_street_shoes_list(xml_data)
        write_product_list(extracted_products, OUTPUT_FILENAME)
