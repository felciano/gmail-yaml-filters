#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Compare original XML filters with round-trip converted filters.
"""
from lxml import etree
from collections import Counter

def extract_filters_from_xml(xml_path):
    """Extract filter properties from XML, ignoring metadata."""
    with open(xml_path, 'rb') as f:
        root = etree.fromstring(f.read())
    
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'apps': 'http://schemas.google.com/apps/2006'}
    
    entries = root.xpath('//atom:entry', namespaces=ns)
    filters = []
    
    for entry in entries:
        filter_props = {}
        properties = entry.xpath('.//apps:property', namespaces=ns)
        
        for prop in properties:
            name = prop.get('name')
            value = prop.get('value')
            if name:
                filter_props[name] = value
        
        if filter_props:
            # Create a normalized representation for comparison
            filters.append(tuple(sorted(filter_props.items())))
    
    return filters

def compare_xmls():
    print("=" * 70)
    print("ROUND-TRIP CONVERSION COMPARISON")
    print("=" * 70)
    
    # Extract filters from both XMLs
    original_filters = extract_filters_from_xml('mailFilters.xml')
    roundtrip_filters = extract_filters_from_xml('roundtrip.xml')
    
    print(f"\n📄 Original XML: {len(original_filters)} filters")
    print(f"🔄 Round-trip XML: {len(roundtrip_filters)} filters")
    
    # Count property occurrences
    orig_props = Counter()
    for f in original_filters:
        for key, _ in f:
            orig_props[key] += 1
    
    round_props = Counter()
    for f in roundtrip_filters:
        for key, _ in f:
            round_props[key] += 1
    
    print(f"\n📊 Property Comparison:")
    all_props = set(orig_props.keys()) | set(round_props.keys())
    
    preserved = []
    lost = []
    
    for prop in sorted(all_props):
        orig_count = orig_props.get(prop, 0)
        round_count = round_props.get(prop, 0)
        
        if orig_count > 0 and round_count > 0:
            preserved.append(prop)
            print(f"   ✓ {prop:30} : {orig_count:3} → {round_count:3}")
        elif orig_count > 0 and round_count == 0:
            lost.append(prop)
            print(f"   ✗ {prop:30} : {orig_count:3} → LOST")
        elif orig_count == 0 and round_count > 0:
            print(f"   + {prop:30} : NEW → {round_count:3}")
    
    print(f"\n🔍 Data Preservation Analysis:")
    print(f"   Preserved properties: {len(preserved)}")
    print(f"   Lost properties: {len(lost)}")
    
    if lost:
        print(f"\n   Lost properties detail:")
        for prop in lost:
            print(f"      - {prop} ({orig_props[prop]} occurrences)")
    
    # Sample some specific filters for detailed comparison
    print(f"\n📋 Sample Filter Details (first 3 filters):")
    
    for i in range(min(3, len(original_filters))):
        print(f"\n   Filter #{i+1}:")
        orig_filter = dict(original_filters[i])
        
        # Try to find corresponding filter in roundtrip
        # (This is approximate - filters might be reordered)
        if i < len(roundtrip_filters):
            round_filter = dict(roundtrip_filters[i])
            
            # Check what's preserved
            for key, value in orig_filter.items():
                if key in round_filter:
                    if round_filter[key] == value:
                        print(f"      ✓ {key}: '{value[:50]}...' preserved")
                    else:
                        print(f"      ⚠ {key}: value changed")
                        print(f"         Original:  '{value[:50]}...'")
                        print(f"         Roundtrip: '{round_filter[key][:50]}...'")
                else:
                    if key not in ['sizeOperator', 'sizeUnit', 'smartLabelToApply']:
                        print(f"      ✗ {key}: '{value[:50]}...' LOST")
    
    # Calculate preservation rate
    total_orig_props = sum(orig_props.values())
    lost_props_count = sum(orig_props[p] for p in lost)
    preserved_props_count = total_orig_props - lost_props_count
    
    preservation_rate = (preserved_props_count / total_orig_props * 100) if total_orig_props > 0 else 0
    
    print(f"\n📈 Overall Data Preservation Rate:")
    print(f"   Total original properties: {total_orig_props}")
    print(f"   Properties preserved: {preserved_props_count}")
    print(f"   Properties lost: {lost_props_count}")
    print(f"   Preservation rate: {preservation_rate:.1f}%")
    
    # Identify what was lost
    if lost:
        print(f"\n⚠️  Note: The following properties are not supported by gmail-yaml-filters:")
        for prop in lost:
            print(f"   - {prop}: This appears to be {'expected' if prop in ['sizeOperator', 'sizeUnit', 'smartLabelToApply'] else 'UNEXPECTED LOSS'}")

if __name__ == '__main__':
    compare_xmls()