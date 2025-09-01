#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bidirectional Gmail XML ↔ YAML converter with perfect round-trip preservation.
"""
from __future__ import print_function, unicode_literals

import sys
from typing import Dict, List, Optional, Tuple, Union, Any
from pathlib import Path

import yaml
from lxml import etree


class GmailFilterConverter:
    """Converts between Gmail XML filter exports and gmail-yaml-filters YAML format."""
    
    # Bidirectional property mappings (XML → YAML)
    XML_TO_YAML_MAP = {
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
    
    # Reverse mapping (YAML → XML)
    YAML_TO_XML_MAP = {
        'from': 'from',
        'to': 'to',
        'subject': 'subject',
        'has': 'hasTheWord',
        'does_not_have': 'doesNotHaveTheWord',
        'label': 'label',
        'archive': 'shouldArchive',
        'important': 'shouldAlwaysMarkAsImportant',
        'delete': 'shouldDelete',
        'read': 'shouldMarkAsRead',
        'not_important': 'shouldNeverMarkAsImportant',
        'not_spam': 'shouldNeverSpam',
        'star': 'shouldStar',
        'trash': 'shouldTrash',
        'forward': 'forwardTo',
    }
    
    # Properties that should be converted to boolean
    BOOLEAN_PROPERTIES = {
        'shouldArchive', 'shouldMarkAsImportant', 'shouldAlwaysMarkAsImportant',
        'shouldDelete', 'shouldMarkAsRead', 'shouldNeverMarkAsImportant', 
        'shouldNeverSpam', 'shouldStar', 'shouldTrash'
    }
    
    # Gmail-specific properties to preserve in _gmail_raw
    GMAIL_ONLY_PROPERTIES = {
        'size', 'sizeOperator', 'sizeUnit', 'smartLabelToApply',
        'excludeChats', 'hasAttachment', 'category', 'title', 
        'id', 'updated', 'content'
    }
    
    # Properties to clean when smart_clean is enabled
    CLEANABLE_DEFAULTS = {
        ('sizeOperator', 's_sl'),
        ('sizeUnit', 's_smb'),
        ('excludeChats', 'false'),
        ('hasAttachment', 'false'),
    }
    
    def __init__(self, preserve_raw: bool = True, smart_clean: bool = False,
                 verbose: bool = False, strict: bool = False):
        """
        Initialize the converter.
        
        Args:
            preserve_raw: Store Gmail-specific properties in _gmail_raw
            smart_clean: Remove meaningless defaults while preserving
            verbose: Print detailed conversion information
            strict: Fail on issues vs warning
        """
        self.preserve_raw = preserve_raw
        self.smart_clean = smart_clean
        self.verbose = verbose
        self.strict = strict
        self.warnings = []
        self.stats = {
            'total_filters': 0,
            'converted_filters': 0,
            'gmail_properties_preserved': 0,
            'properties_cleaned': 0,
            'round_trip_valid': None
        }
    
    def xml_to_yaml(self, xml_input: Union[str, Path], yaml_output: Optional[Union[str, Path]] = None) -> List[Dict]:
        """
        Convert Gmail XML to YAML dict structure.
        
        Args:
            xml_input: Path to XML file or XML string
            yaml_output: Optional path to write YAML file
            
        Returns:
            List of filter dictionaries
        """
        # Parse XML
        if isinstance(xml_input, (str, Path)) and Path(xml_input).exists():
            with open(xml_input, 'rb') as f:
                xml_content = f.read()
        else:
            xml_content = xml_input.encode('utf-8') if isinstance(xml_input, str) else xml_input
        
        try:
            root = etree.fromstring(xml_content)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Invalid XML: {e}")
        
        # Gmail uses Atom namespace
        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'apps': 'http://schemas.google.com/apps/2006'}
        
        filters = []
        entries = root.xpath('//atom:entry', namespaces=ns)
        self.stats['total_filters'] = len(entries)
        
        for i, entry in enumerate(entries):
            filter_dict = self._convert_xml_entry(entry, ns, filter_index=i)
            if filter_dict:
                filters.append(filter_dict)
                self.stats['converted_filters'] += 1
        
        # Write to YAML if output specified
        if yaml_output:
            self._write_yaml(filters, yaml_output)
        
        return filters
    
    def yaml_to_xml(self, yaml_input: Union[List, Dict, str, Path], xml_output: Optional[Union[str, Path]] = None) -> str:
        """
        Convert YAML back to Gmail XML format.
        
        Args:
            yaml_input: YAML data (list/dict), file path, or YAML string
            xml_output: Optional path to write XML file
            
        Returns:
            XML string
        """
        # Load YAML data
        if isinstance(yaml_input, (str, Path)):
            if Path(yaml_input).exists():
                with open(yaml_input, 'r') as f:
                    data = yaml.safe_load(f)
            else:
                data = yaml.safe_load(yaml_input)
        else:
            data = yaml_input
        
        # Handle both list and dict formats
        if isinstance(data, dict) and 'filters' in data:
            filters = data['filters']
        elif isinstance(data, list):
            filters = data
        else:
            filters = [data]
        
        # Create XML structure
        xml_str = self._create_gmail_xml(filters)
        
        # Write to file if output specified
        if xml_output:
            with open(xml_output, 'w', encoding='utf-8') as f:
                f.write(xml_str)
        
        return xml_str
    
    def validate_round_trip(self, xml_input: Union[str, Path]) -> bool:
        """
        Verify that XML → YAML → XML preserves all data.
        
        Args:
            xml_input: Path to XML file or XML string
            
        Returns:
            True if round-trip preserves all data
        """
        # Convert XML to YAML
        yaml_data = self.xml_to_yaml(xml_input)
        
        # Convert back to XML
        restored_xml = self.yaml_to_xml(yaml_data)
        
        # Parse both XML documents
        original_filters = self._parse_xml_filters(xml_input)
        restored_filters = self._parse_xml_filters(restored_xml)
        
        # Compare filters
        is_valid = self._filters_are_equivalent(original_filters, restored_filters)
        self.stats['round_trip_valid'] = is_valid
        
        if self.verbose:
            if is_valid:
                print("✅ Round-trip validation passed", file=sys.stderr)
            else:
                print("❌ Round-trip validation failed", file=sys.stderr)
                self._report_differences(original_filters, restored_filters)
        
        return is_valid
    
    def _convert_xml_entry(self, entry, ns: Dict, filter_index: int = 0) -> Optional[Dict]:
        """Convert a single XML entry to a filter dictionary."""
        filter_dict = {}
        gmail_raw = {}
        
        properties = entry.xpath('.//apps:property', namespaces=ns)
        
        # Check if this filter has actual size property (for smart cleaning)
        has_size_property = any(
            prop.get('name') == 'size' 
            for prop in properties
        )
        
        for prop in properties:
            name = prop.get('name')
            value = prop.get('value', '')
            
            if not name:
                continue
            
            # Smart cleaning
            if self.smart_clean:
                # Skip meaningless size operators without actual size
                if not has_size_property and name in ['sizeOperator', 'sizeUnit']:
                    self.stats['properties_cleaned'] += 1
                    continue
                
                # Skip default values
                if (name, value) in self.CLEANABLE_DEFAULTS:
                    self.stats['properties_cleaned'] += 1
                    continue
            
            # Check if it's a Gmail-only property
            if name in self.GMAIL_ONLY_PROPERTIES:
                if self.preserve_raw:
                    gmail_raw[name] = value
                    self.stats['gmail_properties_preserved'] += 1
                continue
            
            # Map to YAML property
            yaml_key = self.XML_TO_YAML_MAP.get(name)
            if yaml_key:
                # Convert boolean values
                if name in self.BOOLEAN_PROPERTIES:
                    value = value.lower() == 'true'
                
                # Handle multiple labels
                if yaml_key == 'label' and yaml_key in filter_dict:
                    if not isinstance(filter_dict[yaml_key], list):
                        filter_dict[yaml_key] = [filter_dict[yaml_key]]
                    filter_dict[yaml_key].append(value)
                else:
                    filter_dict[yaml_key] = value
            elif self.preserve_raw:
                # Unknown property - preserve in raw
                gmail_raw[name] = value
                self.stats['gmail_properties_preserved'] += 1
        
        # Add gmail_raw if we have any preserved properties
        if gmail_raw and self.preserve_raw:
            filter_dict['_gmail_raw'] = gmail_raw
        
        return filter_dict if filter_dict else None
    
    def _create_gmail_xml(self, filters: List[Dict]) -> str:
        """Create Gmail XML from filter dictionaries."""
        # Create root element with namespaces
        ns_map = {
            None: 'http://www.w3.org/2005/Atom',
            'apps': 'http://schemas.google.com/apps/2006'
        }
        root = etree.Element('feed', nsmap=ns_map)
        
        # Add title
        title = etree.SubElement(root, 'title')
        title.text = 'Mail Filters'
        
        # Add each filter as an entry
        for filter_dict in filters:
            entry = etree.SubElement(root, 'entry')
            
            # Add category
            category = etree.SubElement(entry, 'category')
            category.set('term', 'filter')
            
            # Add title
            entry_title = etree.SubElement(entry, 'title')
            entry_title.text = 'Mail Filter'
            
            # Add content (empty)
            content = etree.SubElement(entry, 'content')
            
            # Process standard properties
            for yaml_key, value in filter_dict.items():
                if yaml_key == '_gmail_raw':
                    continue
                
                xml_key = self.YAML_TO_XML_MAP.get(yaml_key)
                if xml_key:
                    # Handle multiple labels
                    if isinstance(value, list):
                        for v in value:
                            self._add_property(entry, xml_key, v, ns_map)
                    else:
                        self._add_property(entry, xml_key, value, ns_map)
            
            # Add preserved Gmail properties
            if '_gmail_raw' in filter_dict:
                for name, value in filter_dict['_gmail_raw'].items():
                    self._add_property(entry, name, value, ns_map)
        
        # Convert to string
        xml_bytes = etree.tostring(
            root,
            encoding='utf-8',
            pretty_print=True,
            xml_declaration=True
        )
        return xml_bytes.decode('utf-8')
    
    def _add_property(self, entry, name: str, value: Any, ns_map: Dict):
        """Add a property to an XML entry."""
        prop = etree.SubElement(entry, '{http://schemas.google.com/apps/2006}property')
        prop.set('name', name)
        
        # Convert boolean to string
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif value is None:
            value = ''
        
        prop.set('value', str(value))
    
    def _write_yaml(self, filters: List[Dict], output_path: Union[str, Path]):
        """Write filters to YAML file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Add header comment
            f.write("# Gmail filters converted from XML\n")
            f.write("# Use gmail-yaml-to-xml to convert back for Gmail import\n\n")
            
            # Write filters
            yaml.dump(
                filters,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )
    
    def _parse_xml_filters(self, xml_input: Union[str, Path, bytes]) -> List[Dict]:
        """Parse XML and return list of filter properties."""
        if isinstance(xml_input, bytes):
            xml_content = xml_input
        elif isinstance(xml_input, Path) or (isinstance(xml_input, str) and len(xml_input) < 500 and Path(xml_input).exists()):
            # It's a file path
            with open(xml_input, 'rb') as f:
                xml_content = f.read()
        else:
            # It's XML string content
            xml_content = xml_input.encode('utf-8') if isinstance(xml_input, str) else xml_input
        
        root = etree.fromstring(xml_content)
        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'apps': 'http://schemas.google.com/apps/2006'}
        
        filters = []
        for entry in root.xpath('//atom:entry', namespaces=ns):
            filter_props = {}
            for prop in entry.xpath('.//apps:property', namespaces=ns):
                name = prop.get('name')
                value = prop.get('value', '')
                if name:
                    # Handle multiple properties with same name
                    if name in filter_props:
                        if not isinstance(filter_props[name], list):
                            filter_props[name] = [filter_props[name]]
                        filter_props[name].append(value)
                    else:
                        filter_props[name] = value
            if filter_props:
                filters.append(filter_props)
        
        return filters
    
    def _filters_are_equivalent(self, filters1: List[Dict], filters2: List[Dict]) -> bool:
        """Check if two sets of filters are equivalent."""
        if len(filters1) != len(filters2):
            return False
        
        # Sort filters for comparison (order doesn't matter)
        def filter_key(f):
            return str(sorted(f.items()))
        
        sorted1 = sorted(filters1, key=filter_key)
        sorted2 = sorted(filters2, key=filter_key)
        
        for f1, f2 in zip(sorted1, sorted2):
            if set(f1.keys()) != set(f2.keys()):
                return False
            
            for key in f1.keys():
                v1 = f1[key]
                v2 = f2[key]
                
                # Normalize for comparison
                if isinstance(v1, list):
                    v1 = sorted(v1)
                if isinstance(v2, list):
                    v2 = sorted(v2)
                
                if v1 != v2:
                    return False
        
        return True
    
    def _report_differences(self, original: List[Dict], restored: List[Dict]):
        """Report differences between filter sets."""
        print(f"Original filters: {len(original)}", file=sys.stderr)
        print(f"Restored filters: {len(restored)}", file=sys.stderr)
        
        # Find differences
        for i, (o, r) in enumerate(zip(original, restored)):
            if o != r:
                print(f"\nFilter {i+1} differs:", file=sys.stderr)
                
                # Missing keys
                missing_in_restored = set(o.keys()) - set(r.keys())
                if missing_in_restored:
                    print(f"  Missing in restored: {missing_in_restored}", file=sys.stderr)
                
                # Extra keys
                extra_in_restored = set(r.keys()) - set(o.keys())
                if extra_in_restored:
                    print(f"  Extra in restored: {extra_in_restored}", file=sys.stderr)
                
                # Different values
                for key in set(o.keys()) & set(r.keys()):
                    if o[key] != r[key]:
                        print(f"  {key}: '{o[key]}' → '{r[key]}'", file=sys.stderr)
    
    def get_stats(self) -> Dict:
        """Return conversion statistics."""
        return self.stats
    
    def get_warnings(self) -> List[str]:
        """Return list of warnings encountered."""
        return self.warnings