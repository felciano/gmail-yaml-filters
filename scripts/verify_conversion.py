#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verify XML to YAML conversion preserves all important data.
"""
from collections import defaultdict
import yaml
from lxml import etree
from gmail_yaml_filters.xml_converter import GmailFilterConverter

def analyze_xml(xml_path):
    """Extract all filter data from XML."""
    with open(xml_path, 'rb') as f:
        root = etree.fromstring(f.read())
    
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'apps': 'http://schemas.google.com/apps/2006'}
    
    entries = root.xpath('//atom:entry', namespaces=ns)
    xml_filters = []
    all_properties = defaultdict(int)
    
    for entry in entries:
        filter_data = {}
        properties = entry.xpath('.//apps:property', namespaces=ns)
        
        for prop in properties:
            name = prop.get('name')
            value = prop.get('value')
            if name and name not in ['category', 'title', 'id', 'updated', 'content']:
                filter_data[name] = value
                all_properties[name] += 1
        
        if filter_data:
            xml_filters.append(filter_data)
    
    return xml_filters, dict(all_properties)

def analyze_yaml(yaml_path):
    """Extract all filter data from YAML."""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    yaml_filters = []
    all_properties = defaultdict(int)
    
    for filter_dict in data:
        yaml_filters.append(filter_dict)
        for key in filter_dict:
            all_properties[key] += 1
    
    return yaml_filters, dict(all_properties)

def compare_filters():
    """Compare original XML with converted YAML."""
    print("=" * 70)
    print("XML TO YAML CONVERSION VERIFICATION")
    print("=" * 70)
    
    # Analyze XML
    xml_filters, xml_props = analyze_xml('mailFilters.xml')
    print(f"\n📄 XML Analysis:")
    print(f"   Total filters: {len(xml_filters)}")
    print(f"   Unique properties: {len(xml_props)}")
    print(f"   Property usage:")
    for prop, count in sorted(xml_props.items(), key=lambda x: -x[1])[:15]:
        print(f"      {prop:30} : {count:3} occurrences")
    
    # Analyze YAML
    yaml_filters, yaml_props = analyze_yaml('test_output.yaml')
    print(f"\n📝 YAML Analysis:")
    print(f"   Total filters: {len(yaml_filters)}")
    print(f"   Unique properties: {len(yaml_props)}")
    print(f"   Property usage:")
    for prop, count in sorted(yaml_props.items(), key=lambda x: -x[1])[:15]:
        print(f"      {prop:30} : {count:3} occurrences")
    
    # Check filter count
    print(f"\n✅ Filter Count Check:")
    if len(xml_filters) == len(yaml_filters):
        print(f"   ✓ Both have {len(xml_filters)} filters")
    else:
        print(f"   ✗ XML has {len(xml_filters)}, YAML has {len(yaml_filters)}")
    
    # Map XML properties to YAML properties
    converter = GmailFilterConverter()
    property_mapping = {
        'from': 'from',
        'to': 'to',
        'subject': 'subject',
        'hasTheWord': 'has',
        'doesNotHaveTheWord': 'does_not_have',
        'label': 'label',
        'shouldArchive': 'archive',
        'shouldMarkAsImportant': 'important',
        'shouldAlwaysMarkAsImportant': 'important',
        'shouldDelete': 'delete',
        'shouldMarkAsRead': 'read',
        'shouldNeverMarkAsImportant': 'not_important',
        'shouldNeverSpam': 'not_spam',
        'shouldStar': 'star',
        'shouldTrash': 'trash',
        'forwardTo': 'forward',
    }
    
    # Check for data preservation
    print(f"\n🔍 Data Preservation Check:")
    preserved_count = 0
    ignored_props = {'sizeOperator', 'sizeUnit', 'smartLabelToApply'}
    
    for xml_prop in xml_props:
        if xml_prop in ignored_props:
            continue
        if xml_prop in property_mapping:
            yaml_prop = property_mapping[xml_prop]
            if yaml_prop in yaml_props:
                preserved_count += 1
                print(f"   ✓ {xml_prop:30} → {yaml_prop:30}")
            else:
                print(f"   ✗ {xml_prop:30} → NOT FOUND IN YAML")
        else:
            print(f"   ⚠ {xml_prop:30} → UNMAPPED PROPERTY")
    
    # Check specific filter examples
    print(f"\n📋 Sample Filter Verification:")
    for i in range(min(3, len(xml_filters))):
        print(f"\n   Filter #{i+1}:")
        xml_filter = xml_filters[i]
        yaml_filter = yaml_filters[i]
        
        # Check key conversions
        for xml_key, xml_value in xml_filter.items():
            if xml_key in ignored_props:
                continue
            yaml_key = property_mapping.get(xml_key)
            if yaml_key:
                yaml_value = yaml_filter.get(yaml_key)
                if yaml_value is not None:
                    # Check value conversion
                    if xml_key in converter.BOOLEAN_PROPERTIES:
                        expected = xml_value.lower() == 'true'
                        if yaml_value == expected:
                            print(f"      ✓ {xml_key}: '{xml_value}' → {yaml_key}: {yaml_value}")
                        else:
                            print(f"      ✗ {xml_key}: '{xml_value}' → {yaml_key}: {yaml_value} (expected {expected})")
                    else:
                        if str(yaml_value) == xml_value:
                            print(f"      ✓ {xml_key}: '{xml_value}' → {yaml_key}: '{yaml_value}'")
                        else:
                            print(f"      ⚠ {xml_key}: '{xml_value}' → {yaml_key}: '{yaml_value}' (value changed)")
                else:
                    print(f"      ✗ {xml_key}: '{xml_value}' → {yaml_key}: MISSING")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"   Total XML properties: {sum(xml_props.values())}")
    print(f"   Total YAML properties: {sum(yaml_props.values())}")
    print(f"   Unsupported properties (sizeOperator, sizeUnit, smartLabelToApply): {xml_props.get('sizeOperator', 0) + xml_props.get('sizeUnit', 0) + xml_props.get('smartLabelToApply', 0)}")
    print(f"   Successfully converted properties: {preserved_count}/{len([p for p in xml_props if p not in ignored_props])}")

if __name__ == '__main__':
    compare_filters()