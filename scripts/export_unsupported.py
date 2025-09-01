#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Export unsupported filters to a separate file for manual review.
"""
import sys
import yaml
from lxml import etree
from gmail_yaml_filters.xml_converter import GmailFilterConverter

def export_unsupported_filters(xml_path, output_prefix='unsupported'):
    """
    Export filters with unsupported properties to separate files.
    """
    print("=" * 70)
    print("EXPORTING UNSUPPORTED FILTERS")
    print("=" * 70)
    print()
    
    # Parse XML
    with open(xml_path, 'rb') as f:
        root = etree.fromstring(f.read())
    
    ns = {'atom': 'http://www.w3.org/2005/Atom',
          'apps': 'http://schemas.google.com/apps/2006'}
    
    entries = root.xpath('//atom:entry', namespaces=ns)
    
    # Categories of problematic filters
    size_filters = []
    smart_label_filters = []
    no_action_filters = []
    
    for i, entry in enumerate(entries):
        filter_data = {}
        properties = entry.xpath('.//apps:property', namespaces=ns)
        
        has_size = False
        has_smart_label = False
        has_actions = False
        
        for prop in properties:
            name = prop.get('name')
            value = prop.get('value')
            if name:
                filter_data[name] = value
                
                if name in ['sizeOperator', 'sizeUnit']:
                    has_size = True
                elif name == 'smartLabelToApply':
                    has_smart_label = True
                elif name in ['shouldArchive', 'shouldStar', 'shouldDelete', 
                             'shouldTrash', 'label', 'forwardTo', 'shouldMarkAsRead',
                             'shouldNeverSpam', 'shouldAlwaysMarkAsImportant',
                             'shouldNeverMarkAsImportant']:
                    has_actions = True
        
        # Categorize the filter
        if has_size:
            size_filters.append({
                'index': i + 1,
                'filter': filter_data,
                'description': f"Filter #{i+1}: Size-based filter"
            })
        
        if has_smart_label:
            smart_label_filters.append({
                'index': i + 1,
                'filter': filter_data,
                'description': f"Filter #{i+1}: Uses smart labels"
            })
        
        # Check for filters with only conditions
        conditions = ['from', 'to', 'subject', 'hasTheWord', 'doesNotHaveTheWord']
        has_conditions = any(c in filter_data for c in conditions)
        
        if has_conditions and not has_actions:
            no_action_filters.append({
                'index': i + 1,
                'filter': filter_data,
                'description': f"Filter #{i+1}: Has conditions but no actions"
            })
    
    # Export to files
    all_unsupported = {
        'size_based_filters': size_filters,
        'smart_label_filters': smart_label_filters,
        'no_action_filters': no_action_filters,
        'summary': {
            'total_filters': len(entries),
            'size_based': len(size_filters),
            'smart_labels': len(smart_label_filters),
            'no_actions': len(no_action_filters)
        }
    }
    
    # Save as YAML for easy review
    output_file = f"{output_prefix}_filters.yaml"
    with open(output_file, 'w') as f:
        f.write("# Filters with unsupported Gmail features\n")
        f.write("# These filters need manual review and adjustment\n\n")
        yaml.safe_dump(all_unsupported, f, default_flow_style=False, 
                      allow_unicode=True, sort_keys=False)
    
    print(f"📊 Summary:")
    print(f"  Total filters: {len(entries)}")
    print(f"  Size-based filters: {len(size_filters)}")
    print(f"  Smart label filters: {len(smart_label_filters)}")
    print(f"  Filters without actions: {len(no_action_filters)}")
    print()
    print(f"📄 Unsupported filters exported to: {output_file}")
    print()
    
    # Provide migration suggestions
    if size_filters:
        print("💡 Size Filter Migration Tips:")
        print("  Replace size filters with 'has' field:")
        print("  • For emails > 10MB: has: 'larger:10M'")
        print("  • For emails < 1MB: has: 'smaller:1M'")
        print()
    
    if smart_label_filters:
        print("💡 Smart Label Migration Tips:")
        print("  Smart labels (Social, Promotions, etc.) cannot be set via API.")
        print("  Consider:")
        print("  • Creating custom labels instead")
        print("  • Using Gmail's web interface for smart label filters")
        print()
    
    if no_action_filters:
        print("💡 No-Action Filter Fix:")
        print("  Add at least one action to each filter:")
        print("  • label: 'YourLabel'")
        print("  • archive: true")
        print("  • star: true")
        print()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python export_unsupported.py mailFilters.xml [output_prefix]")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    output_prefix = sys.argv[2] if len(sys.argv) > 2 else 'unsupported'
    
    export_unsupported_filters(xml_file, output_prefix)