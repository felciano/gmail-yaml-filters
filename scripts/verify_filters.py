#!/usr/bin/env python
"""
Verify Gmail filter entries are equivalent, ignoring feed metadata and order.

Usage:
    python verify_filters.py original.xml converted.xml
"""

import sys
from pathlib import Path
from lxml import etree

def extract_entries(xml_file):
    """Extract just the entry elements for comparison."""
    tree = etree.parse(xml_file)
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'apps': 'http://schemas.google.com/apps/2006'}
    
    entries = []
    for entry in tree.xpath('//atom:entry', namespaces=ns):
        # Create a sortable key from the entry's properties
        props = {}
        
        # Get ID if present
        id_elem = entry.find('atom:id', ns)
        if id_elem is not None:
            props['_id'] = id_elem.text
        
        # Get all properties
        for prop in entry.xpath('.//apps:property', namespaces=ns):
            name = prop.get('name')
            value = prop.get('value', '')
            if name in props:
                # Handle multiple values
                if isinstance(props[name], list):
                    props[name].append(value)
                else:
                    props[name] = [props[name], value]
            else:
                props[name] = value
        
        entries.append(props)
    
    # Sort entries by ID (or by string representation if no ID)
    entries.sort(key=lambda e: e.get('_id', str(sorted(e.items()))))
    return entries


def compare_entries(original_entries, converted_entries):
    """Compare two sets of entries."""
    if len(original_entries) != len(converted_entries):
        return False, f"Different number of entries: {len(original_entries)} vs {len(converted_entries)}"
    
    differences = []
    for i, (orig, conv) in enumerate(zip(original_entries, converted_entries)):
        # Compare keys
        orig_keys = set(orig.keys())
        conv_keys = set(conv.keys())
        
        if orig_keys != conv_keys:
            differences.append(f"Entry {i}: Different properties - missing: {orig_keys - conv_keys}, extra: {conv_keys - orig_keys}")
            continue
        
        # Compare values
        for key in orig_keys:
            orig_val = orig[key]
            conv_val = conv[key]
            
            # Normalize lists for comparison
            if isinstance(orig_val, list):
                orig_val = sorted(orig_val)
            if isinstance(conv_val, list):
                conv_val = sorted(conv_val)
            
            if orig_val != conv_val:
                differences.append(f"Entry {i}: {key} differs")
    
    if differences:
        return False, differences
    return True, []


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_filters.py original.xml converted.xml")
        print("\nThis tool compares only the filter entries, ignoring:")
        print("  - Feed-level metadata (author, feed ID, etc.)")
        print("  - Element order within the XML")
        print("  - Namespace prefixes and formatting")
        sys.exit(1)
    
    original_file = Path(sys.argv[1])
    converted_file = Path(sys.argv[2])
    
    if not original_file.exists():
        print(f"Error: File not found: {original_file}")
        sys.exit(1)
    
    if not converted_file.exists():
        print(f"Error: File not found: {converted_file}")
        sys.exit(1)
    
    print(f"Comparing filter entries:")
    print(f"  Original: {original_file}")
    print(f"  Converted: {converted_file}")
    print()
    
    # Extract entries
    original_entries = extract_entries(original_file)
    converted_entries = extract_entries(converted_file)
    
    print(f"Found {len(original_entries)} filters in original")
    print(f"Found {len(converted_entries)} filters in converted")
    
    # Compare
    is_equivalent, differences = compare_entries(original_entries, converted_entries)
    
    if is_equivalent:
        print("\n✅ ALL FILTER ENTRIES ARE EQUIVALENT")
        print("   (ignoring feed metadata and element order)")
        sys.exit(0)
    else:
        print(f"\n❌ FILTER ENTRIES DIFFER:")
        for diff in differences[:10]:
            print(f"  - {diff}")
        if len(differences) > 10:
            print(f"  ... and {len(differences) - 10} more")
        sys.exit(1)


if __name__ == "__main__":
    main()