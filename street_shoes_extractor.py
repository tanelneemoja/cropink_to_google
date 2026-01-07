import requests
import xml.etree.ElementTree as ET
import os
import re

# --- Configuration ---
# FIX: Hardcoded the URL to bypass environment variable errors as requested.
XML_FEED_URL = "https://backend.ballzy.eu/et/amfeed/feed/download?id=102&file=cropink_et.xml"
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
    """Parses XML and extracts brand, title, and G:LINK for products matching the category."""
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
    
    # Stores {product_string: raw_link}
    unique_product_data = {} 
    matched_count = 0
    
    # Define prefixes/suffixes to strip from titles to reduce duplicates (case-insensitive)
    GENDER_STRIPPERS = [
        r'\bw\b',       # 'w ' (e.g., nike w air max)
        r'\bwmns\b',    # 'wmns ' (e.g., jordan wmns air force 1)
        r"women's\b",
        r"womens\b",
        r"gs\b",        # Grade School / Youth sizing often appears as a redundant suffix
    ]
    # Compile a regex pattern to efficiently check and replace these prefixes/suffixes
    GENDER_PREFIX_PATTERN = re.compile(r'^\s*(' + '|'.join(GENDER_STRIPPERS) + r')\s*', re.IGNORECASE)
    GENDER_SUFFIX_PATTERN = re.compile(r'\s+(' + '|'.join(GENDER_STRIPPERS) + r')\s*$', re.IGNORECASE)


    for item in items:
        # 1. Get required elements (Category, Title, Brand, Lifestyle, and Link)
        category_element = item.find('g:google_product_category', NAMESPACES)
        lifestyle_element = item.find('custom_label_0', NAMESPACES)
        brand_element = item.find('custom_label_3', NAMESPACES)
        title_element = item.find('g:title', NAMESPACES)
        # Note: g:link is used here, assuming the feed structure is consistent
        link_element = item.find('g:link', NAMESPACES) 
        
        # Helper to safely retrieve text, accounting for None and CDATA
        get_text = lambda elem: (elem.text or "").strip() if elem is not None else ""

        raw_category = get_text(category_element)
        raw_lifestyle = get_text(lifestyle_element)
        raw_brand = get_text(brand_element)
        raw_title = get_text(title_element)
        raw_link = get_text(link_element) 
        
        # 2. Apply Filtering Conditions
        # A. Must contain "Street Shoes" in category
        # B. Must be exactly "Lifestyle" in custom_label_0 (case insensitive)
        is_street_shoe = TARGET_CATEGORY_PART in raw_category
        is_lifestyle = raw_lifestyle.lower() == "lifestyle"
        has_data = bool(raw_title) and bool(raw_brand) and bool(raw_link) 
        
        if is_street_shoe and is_lifestyle and has_data:
            
            matched_count += 1
            
            # --- 3. Normalization and Deduplication ---
            
            # A. Brand Normalization: 'adidas originals' -> 'adidas'
            normalized_brand = raw_brand.lower()
            if normalized_brand == "adidas originals":
                normalized_brand = "adidas"
            
            # B. Title Cleaning (lowercase, single spaces)
            clean_title = ' '.join(raw_title.lower().split())

            # C. Gender Prefix/Suffix Removal
            final_title = GENDER_PREFIX_PATTERN.sub('', clean_title)
            final_title = GENDER_SUFFIX_PATTERN.sub('', final_title).strip()
            
            # Re-clean to remove any double spaces left by stripping
            final_title = ' '.join(final_title.split())
            
            
            # D. Brand Redundancy Check 
            
            # 1. Check for standard redundant brand prefix (e.g., 'nike nike air max')
            brand_prefix = normalized_brand + ' '
            if final_title.startswith(brand_prefix):
                final_title = final_title[len(brand_prefix):].strip()
            
            # 2. Re-clean to remove any double spaces left by stripping
            final_title = ' '.join(final_title.split())

            # --- 4. Final Output String Creation ---
            
            if normalized_brand == 'jordan' and 'air jordan' in final_title:
                output_string = final_title
            else:
                output_string = f"{normalized_brand} {final_title}"
            
            # Use the final product string as the key to enforce uniqueness, storing the link
            unique_product_data[output_string] = raw_link

        elif is_street_shoe and has_data:
             # This block logs items that meet the old criteria but fail the new 'Lifestyle' filter
             pass 

    # Print the links in the requested "product [space] link" format
    print("\n=======================================================")
    print("Webpage Links for Filtered Street Shoes Products:")
    print("(Product Name [space] Link)")
    print("=======================================================")
    
    # Sort and prepare the final results list
    sorted_product_strings = sorted(unique_product_data.keys())
    final_output_list = []
    
    for product_string in sorted_product_strings:
        link = unique_product_data[product_string]
        # CHANGE HERE: Print the combined string
        combined_output = f" {link}"
        print(combined_output)
        
        # Keep only the product name for the file writing function
        final_output_list.append(product_string)


    print(f"\nDEBUG: Finished processing. Total items matched by category and lifestyle: {matched_count}.")
    print(f"DEBUG: Final unique products extracted: {len(unique_product_data)}")
    
    # Return the product names for the file writing function
    return final_output_list

def write_product_list(data_list, filename):
    """Writes the list of unique products to the specified file."""
    print(f"\nWriting {len(data_list)} unique product names to {filename}...")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for line in data_list:
                f.write(line + '\n')
        print("SUCCESS: File created successfully.")
    except IOError as e:
        print(f"FATAL ERROR: Error writing file: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    xml_data = fetch_xml_data(XML_FEED_URL)
    
    if xml_data:
        extracted_products = extract_street_shoes_list(xml_data)
        if extracted_products:
            write_product_list(extracted_products, OUTPUT_FILENAME)
        else:
            print("INFO: No products matched the filter, or extraction failed. Output file is empty.")
