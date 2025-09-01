#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Compare two Gmail XML files semantically (ignoring order and formatting).
"""
import sys
from lxml import etree
from collections import Counter

def normalize_filters(xml_file):
    """Extract and normalize filters from XML."""
    with open(xml_file, 'rb') as f:
        root = etree.fromstring(f.read())
    
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'apps': 'http://schemas.google.com/apps/2006'}
    
    filters = []
    for entry in root.xpath('//atom:entry', namespaces=ns):
        props = {}
        for prop in entry.xpath('.//apps:property', namespaces=ns):
            name = prop.get('name')
            value = prop.get('value', '')
            if name:
                if name in props:
                    # Handle multiple values
                    if not isinstance(props[name], list):
                        props[name] = [props[name]]
                    props[name].append(value)
                else:
                    props[name] = value
        
        # Sort properties for consistent comparison
        filter_str = str(sorted(props.items()))
        filters.append(filter_str)
    
    return sorted(filters)

def compare_xml_files(file1, file2):
    """Compare two XML files semantically."""
    print(f"Comparing {file1} vs {file2}")
    print("=" * 60)
    
    filters1 = normalize_filters(file1)
    filters2 = normalize_filters(file2)
    
    print(f"File 1: {len(filters1)} filters")
    print(f"File 2: {len(filters2)} filters")
    
    if filters1 == filters2:
        print("✅ Files are semantically IDENTICAL")
        return True
    
    # Find differences
    counter1 = Counter(filters1)
    counter2 = Counter(filters2)
    
    only_in_1 = counter1 - counter2
    only_in_2 = counter2 - counter1
    
    if only_in_1:
        print(f"\n❌ Filters only in {file1}: {sum(only_in_1.values())}")
        for f in list(only_in_1.elements())[:3]:  # Show first 3
            print(f"  {f[:100]}...")
    
    if only_in_2:
        print(f"\n❌ Filters only in {file2}: {sum(only_in_2.values())}")
        for f in list(only_in_2.elements())[:3]:  # Show first 3
            print(f"  {f[:100]}...")
    
    # Check which properties differ
    all_props1 = set()
    all_props2 = set()
    
    for f_str in filters1:
        filter_dict = eval(f_str)
        all_props1.update(k for k, v in filter_dict)
    
    for f_str in filters2:
        filter_dict = eval(f_str)
        all_props2.update(k for k, v in filter_dict)
    
    missing_props = all_props1 - all_props2
    extra_props = all_props2 - all_props1
    
    if missing_props:
        print(f"\n⚠️  Properties lost: {missing_props}")
    if extra_props:
        print(f"\n⚠️  Properties added: {extra_props}")
    
    return False

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python compare_xml.py file1.xml file2.xml")
        sys.exit(1)
    
    file1 = sys.argv[1]
    file2 = sys.argv[2]
    
    if compare_xml_files(file1, file2):
        sys.exit(0)
    else:
        sys.exit(1)