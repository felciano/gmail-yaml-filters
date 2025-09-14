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

from .inference_safety import InferenceSafety
from .operator_inference import OperatorInference

# Import xmldiff validation if available
try:
    from .xml_validator import validate_round_trip_with_xmldiff, XMLDIFF_AVAILABLE
except ImportError:
    XMLDIFF_AVAILABLE = False
    validate_round_trip_with_xmldiff = None

import hashlib


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
                 verbose: bool = False, strict: bool = False, merge_filters: bool = False,
                 infer_more: bool = False, infer_strategy: str = 'conservative',
                 infer_operators: bool = False):
        """
        Initialize the converter.
        
        Args:
            preserve_raw: Store Gmail-specific properties in _gmail_raw
            smart_clean: Remove meaningless defaults while preserving
            verbose: Print detailed conversion information
            strict: Fail on issues vs warning
            merge_filters: Merge filters that differ only in labels when converting XML to YAML
            infer_more: Attempt to infer hierarchical "more" structures from flat filters
            infer_strategy: Strategy for inference ('conservative', 'aggressive', or 'interactive')
            infer_operators: Infer YAML operators (any, all, not) from Gmail search patterns
        """
        self.preserve_raw = preserve_raw
        self.smart_clean = smart_clean
        self.verbose = verbose
        self.strict = strict
        self.merge_filters = merge_filters
        self.infer_more = infer_more
        self.infer_strategy = infer_strategy
        self.infer_operators = infer_operators
        self.safety_analyzer = InferenceSafety(verbose=verbose) if infer_more else None
        self.operator_inference = OperatorInference(verbose=verbose) if infer_operators else None
        self.warnings = []
        self.stats = {
            'total_filters': 0,
            'converted_filters': 0,
            'gmail_properties_preserved': 0,
            'properties_cleaned': 0,
            'filters_merged': 0,
            'hierarchies_inferred': 0,
            'hierarchies_skipped_safety': 0,
            'round_trip_valid': None
        }
    
    def _pre_check_expressions(self, root, ns: Dict) -> List[Dict]:
        """
        Pre-check all filters for malformed expressions.
        Returns a list of issues found.
        
        Args:
            root: XML root element
            ns: Namespace dictionary
            
        Returns:
            List of error dictionaries with filter info
        """
        issues = []
        entries = root.xpath('//atom:entry', namespaces=ns)
        
        for i, entry in enumerate(entries):
            # Get filter ID if available for better reporting
            filter_id = None
            id_element = entry.find('{http://www.w3.org/2005/Atom}id')
            if id_element is not None and id_element.text:
                if 'filter:' in id_element.text:
                    filter_id = id_element.text.split('filter:')[-1]
            
            # Check all properties
            properties = entry.xpath('.//apps:property', namespaces=ns)
            for prop in properties:
                name = prop.get('name')
                value = prop.get('value', '')
                
                if not name or not value:
                    continue
                
                # Check if this is a searchable field that might have expressions
                yaml_key = self.XML_TO_YAML_MAP.get(name)
                if yaml_key in ['from', 'to', 'subject', 'has', 'does_not_have']:
                    # Check for boolean operators or parentheses/brackets
                    if any(op in value for op in [' OR ', ' AND ', '(', ')', '[', ']', '{', '}']):
                        try:
                            self._validate_expression_balance(value, f"{yaml_key} (XML property: {name})")
                        except ValueError as e:
                            # Extract a sample of the filter for context
                            filter_sample = self._get_filter_sample(entry, ns)
                            issues.append({
                                'filter_index': i + 1,
                                'filter_id': filter_id,
                                'field': yaml_key,
                                'value': value,
                                'error': str(e).split('\n')[0],  # First line of error
                                'sample': filter_sample
                            })
        
        return issues
    
    def _get_filter_sample(self, entry, ns: Dict) -> str:
        """
        Get a brief sample of the filter for error reporting.
        
        Args:
            entry: XML entry element
            ns: Namespace dictionary
            
        Returns:
            Brief description of the filter
        """
        sample_parts = []
        properties = entry.xpath('.//apps:property', namespaces=ns)
        
        # Get a few key properties for context
        for prop in properties[:3]:  # Just first 3 properties
            name = prop.get('name')
            value = prop.get('value', '')
            if name and value:
                yaml_key = self.XML_TO_YAML_MAP.get(name, name)
                if len(value) > 50:
                    value = value[:50] + '...'
                sample_parts.append(f"{yaml_key}={value}")
        
        return ', '.join(sample_parts) if sample_parts else 'No properties found'
    
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
        
        # Pre-check all expressions for balance issues
        issues = self._pre_check_expressions(root, ns)
        if issues:
            # Format comprehensive error message
            error_msg = self._format_expression_issues(issues)
            raise ValueError(error_msg)
        
        filters = []
        entries = root.xpath('//atom:entry', namespaces=ns)
        self.stats['total_filters'] = len(entries)
        
        for i, entry in enumerate(entries):
            filter_dict = self._convert_xml_entry(entry, ns, filter_index=i)
            if filter_dict:
                filters.append(filter_dict)
                self.stats['converted_filters'] += 1
        
        # Merge filters if requested
        if self.merge_filters:
            filters = self._merge_identical_filters(filters)
        
        # Infer "more" structures if requested
        if self.infer_more:
            filters = self._infer_more_structures(filters)
        
        # Write to YAML if output specified
        if yaml_output:
            self._write_yaml(filters, yaml_output)
        
        return filters
    
    def _format_expression_issues(self, issues: List[Dict]) -> str:
        """
        Format a comprehensive error message for all expression issues found.
        
        Args:
            issues: List of issue dictionaries
            
        Returns:
            Formatted error message
        """
        lines = [
            "Found malformed expressions in Gmail filters:",
            "=" * 60,
            ""
        ]
        
        for issue in issues:
            filter_desc = f"Filter #{issue['filter_index']}"
            if issue['filter_id']:
                filter_desc += f" (ID: {issue['filter_id']})"
            
            lines.append(filter_desc)
            lines.append(f"  Field: {issue['field']}")
            lines.append(f"  Value: {issue['value'][:100]}{'...' if len(issue['value']) > 100 else ''}")
            lines.append(f"  Problem: {issue['error']}")
            lines.append(f"  Filter sample: {issue['sample']}")
            lines.append("")
        
        lines.append("=" * 60)
        lines.append(f"Total filters with issues: {len(issues)}")
        lines.append("")
        lines.append("Please fix these filters in Gmail before converting.")
        lines.append("The expressions have unbalanced or mismatched parentheses/brackets.")
        
        return '\n'.join(lines)
    
    def _pre_check_yaml_expressions(self, filters: List[Dict]) -> List[Dict]:
        """
        Pre-check all YAML filters for malformed expressions.
        Returns a list of issues found.
        
        Args:
            filters: List of filter dictionaries
            
        Returns:
            List of error dictionaries with filter info
        """
        issues = []
        
        def check_value(value: Any, field: str, filter_index: int, filter_dict: Dict):
            """Recursively check values including nested structures."""
            if isinstance(value, str):
                if any(op in value for op in [' OR ', ' AND ', '(', ')', '[', ']', '{', '}']):
                    try:
                        self._validate_expression_balance(value, field)
                    except ValueError as e:
                        # Get filter sample
                        sample_parts = []
                        for k, v in list(filter_dict.items())[:3]:
                            if k != '_gmail_raw':
                                v_str = str(v)[:50]
                                if len(str(v)) > 50:
                                    v_str += '...'
                                sample_parts.append(f"{k}={v_str}")
                        
                        issues.append({
                            'filter_index': filter_index + 1,
                            'filter_id': filter_dict.get('_gmail_raw', {}).get('id'),
                            'field': field,
                            'value': value,
                            'error': str(e).split('\n')[0],
                            'sample': ', '.join(sample_parts)
                        })
            elif isinstance(value, list):
                for item in value:
                    check_value(item, field, filter_index, filter_dict)
            elif isinstance(value, dict):
                # Handle operator dictionaries
                for op_key, op_value in value.items():
                    if op_key in ['any', 'all', 'not']:
                        check_value(op_value, field, filter_index, filter_dict)
        
        # Check each filter
        for i, filter_dict in enumerate(filters):
            # Check searchable fields
            for field in ['from', 'to', 'subject', 'has', 'does_not_have']:
                if field in filter_dict:
                    check_value(filter_dict[field], field, i, filter_dict)
        
        return issues
    
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
        
        # Pre-check all expressions for balance issues
        issues = self._pre_check_yaml_expressions(filters)
        if issues:
            # Format comprehensive error message
            error_msg = self._format_expression_issues(issues)
            raise ValueError(error_msg)
        
        # Create XML structure
        xml_str = self._create_gmail_xml(filters)
        
        # Write to file if output specified
        if xml_output:
            with open(xml_output, 'w', encoding='utf-8') as f:
                f.write(xml_str)
        
        return xml_str
    
    def _canonicalize_xml(self, xml_content: bytes, remove_feed_metadata: bool = True) -> bytes:
        """
        Canonicalize XML for order-insensitive comparison.
        
        Args:
            xml_content: XML content as bytes
            remove_feed_metadata: If True, remove feed-level id, updated, author
            
        Returns:
            Canonicalized XML as bytes
        """
        # Parse with blank text removal
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml_content, parser)
        
        # Optionally remove feed-level metadata that's not preserved in roundtrip
        if remove_feed_metadata:
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            # Remove feed-level id, updated, author elements
            for elem_name in ['id', 'updated', 'author']:
                for elem in tree.xpath(f'/atom:feed/atom:{elem_name}', namespaces=ns):
                    elem.getparent().remove(elem)
        
        # Normalize boolean expressions by adding outer parentheses where missing
        self._normalize_boolean_expressions(tree)
        
        # Sort all children recursively
        self._sort_xml_children(tree)
        
        # Apply C14N canonicalization
        canonical = etree.tostring(tree, method="c14n", with_comments=False, exclusive=False)
        
        return canonical
    
    def _normalize_boolean_expressions(self, tree):
        """
        Normalize boolean expressions by adding outer parentheses where missing.
        
        This ensures that 'A OR B' and '(A OR B)' are treated as equivalent,
        since adding outer parentheses doesn't change the meaning in Gmail's search syntax.
        
        Args:
            tree: XML tree to normalize in-place
        """
        ns = {'apps': 'http://schemas.google.com/apps/2006'}
        
        # Find all property elements
        for prop in tree.xpath('//apps:property', namespaces=ns):
            value = prop.get('value', '')
            
            # Skip empty values
            if not value:
                continue
                
            # Check if value contains OR or AND operators (case-sensitive as Gmail uses)
            if ' OR ' in value or ' AND ' in value:
                # Skip if already wrapped in outer parentheses
                if value.startswith('(') and value.endswith(')'):
                    # Verify these are balanced outer parentheses
                    # Simple check: remove outer parens and count remaining
                    inner = value[1:-1]
                    open_count = inner.count('(')
                    close_count = inner.count(')')
                    if open_count == close_count:
                        # Already has outer parentheses, skip
                        continue
                
                # Add outer parentheses
                prop.set('value', f'({value})')
    
    def _sort_xml_children(self, elem):
        """Recursively sort all children of an XML element."""
        # First recurse into children
        for child in list(elem):
            if isinstance(child.tag, str):  # Skip comments, PIs
                self._sort_xml_children(child)
        
        # Get all element children (skip comments/PIs/text)
        kids = [c for c in elem if isinstance(c.tag, str)]
        
        # Sort them
        kids_sorted = sorted(kids, key=self._gmail_sort_key)
        
        # If order changed, reattach in sorted order
        if kids != kids_sorted:
            for k in kids:
                elem.remove(k)
            for k in kids_sorted:
                elem.append(k)
    
    def _gmail_sort_key(self, elem):
        """
        Build a deterministic sort key for Gmail filter elements.
        
        For Gmail filters, we prioritize:
        1. Tag name (localname without namespace)
        2. For <property> elements: the 'name' attribute value
        3. For <entry> elements: the filter ID if present
        4. Other attributes alphabetically
        5. Text content
        """
        tag = etree.QName(elem).localname
        
        # Special handling for Gmail property elements
        if tag == 'property':
            # Sort properties by their 'name' attribute
            name_attr = elem.get('name', '')
            return (tag, name_attr, elem.get('value', ''))
        
        # Special handling for entry elements - sort by ID
        if tag == 'entry':
            # Find the ID child element
            id_text = ''
            for child in elem:
                if etree.QName(child).localname == 'id' and child.text:
                    id_text = child.text.split(':')[-1]  # Extract just the filter ID
                    break
            return (tag, id_text)
        
        # For other elements, use tag + sorted attributes + text
        attrs = tuple(sorted((k, v) for k, v in elem.attrib.items()))
        text = (elem.text or "").strip()
        return (tag, attrs, text)
    
    def validate_round_trip(self, xml_input: Union[str, Path], use_xmldiff: bool = False, use_canonical: bool = True) -> bool:
        """
        Verify that XML → YAML → XML preserves all data.
        
        Args:
            xml_input: Path to XML file or XML string
            use_xmldiff: If True and available, use xmldiff for comparison (deprecated)
            use_canonical: If True, use canonical XML comparison (recommended)
            
        Returns:
            True if round-trip preserves all data (or successfully converts when merging)
        """
        # Convert XML to YAML
        yaml_data = self.xml_to_yaml(xml_input)
        
        # Merging MUST be lossless - we expect perfect round-trip even with merging
        if self.merge_filters or self.infer_more:
            if self.verbose:
                print("Validating lossless round-trip with merging/inference...", file=sys.stderr)
            
            try:
                # Convert back to XML
                restored_xml = self.yaml_to_xml(yaml_data)
                
                # Parse to count filters
                restored_filters = self._parse_xml_filters(restored_xml)
                original_filters = self._parse_xml_filters(xml_input)
                
                if self.verbose:
                    print(f"  Filter count: {len(original_filters)} → {len(yaml_data)} YAML entries → {len(restored_filters)} filters", file=sys.stderr)
                    if len(yaml_data) < len(original_filters):
                        print(f"  Merged {len(original_filters) - len(yaml_data)} filters into hierarchies", file=sys.stderr)
                
                # Check filter count first
                if len(original_filters) != len(restored_filters):
                    if self.verbose:
                        print(f"❌ Filter count mismatch: {len(original_filters)} original vs {len(restored_filters)} restored", file=sys.stderr)
                    return False
                
                # Perform canonical comparison to ensure PERFECT round-trip
                if use_canonical:
                    if self.verbose:
                        print("  Verifying perfect round-trip with canonical comparison...", file=sys.stderr)
                    
                    # Read original XML
                    if isinstance(xml_input, (str, Path)) and Path(xml_input).exists():
                        with open(xml_input, 'rb') as f:
                            original_xml_bytes = f.read()
                    else:
                        original_xml_bytes = xml_input.encode('utf-8') if isinstance(xml_input, str) else xml_input
                    
                    # Convert restored XML to bytes
                    restored_xml_bytes = restored_xml.encode('utf-8') if isinstance(restored_xml, str) else restored_xml
                    
                    # Canonicalize both
                    original_canonical = self._canonicalize_xml(original_xml_bytes, remove_feed_metadata=True)
                    restored_canonical = self._canonicalize_xml(restored_xml_bytes, remove_feed_metadata=True)
                    
                    # Compare - MUST be identical for lossless round-trip
                    is_identical = original_canonical == restored_canonical
                    
                    if self.verbose:
                        if is_identical:
                            print(f"  ✅ Perfect round-trip achieved (canonical match)", file=sys.stderr)
                            original_hash = hashlib.sha256(original_canonical).hexdigest()
                            print(f"     SHA256: {original_hash}", file=sys.stderr)
                        else:
                            print(f"  ❌ Round-trip NOT lossless - canonical comparison failed", file=sys.stderr)
                            original_hash = hashlib.sha256(original_canonical).hexdigest()
                            restored_hash = hashlib.sha256(restored_canonical).hexdigest()
                            print(f"     Original SHA256: {original_hash}", file=sys.stderr)
                            print(f"     Restored SHA256: {restored_hash}", file=sys.stderr)
                    
                    return is_identical  # CRITICAL: Return the actual comparison result
                else:
                    # Fall back to dictionary comparison
                    is_valid = self._filters_are_equivalent(original_filters, restored_filters)
                    if self.verbose:
                        if is_valid:
                            print(f"  ✅ All filters preserved (dictionary comparison)", file=sys.stderr)
                        else:
                            print(f"  ❌ Filters differ", file=sys.stderr)
                    return is_valid
                    
            except Exception as e:
                if self.verbose:
                    print(f"❌ Conversion failed: {e}", file=sys.stderr)
                return False
        
        # Normal round-trip validation without merging
        # Convert back to XML
        restored_xml = self.yaml_to_xml(yaml_data)
        
        # Try canonical comparison first (recommended)
        if use_canonical:
            if self.verbose:
                print("Using canonical XML comparison (order-insensitive)...", file=sys.stderr)
            
            # Read original XML
            if isinstance(xml_input, (str, Path)) and Path(xml_input).exists():
                with open(xml_input, 'rb') as f:
                    original_xml_bytes = f.read()
            else:
                original_xml_bytes = xml_input.encode('utf-8') if isinstance(xml_input, str) else xml_input
            
            # Convert restored XML to bytes
            restored_xml_bytes = restored_xml.encode('utf-8') if isinstance(restored_xml, str) else restored_xml
            
            # Canonicalize both
            original_canonical = self._canonicalize_xml(original_xml_bytes, remove_feed_metadata=True)
            restored_canonical = self._canonicalize_xml(restored_xml_bytes, remove_feed_metadata=True)
            
            # Compare
            is_valid = original_canonical == restored_canonical
            
            if self.verbose:
                original_hash = hashlib.sha256(original_canonical).hexdigest()
                restored_hash = hashlib.sha256(restored_canonical).hexdigest()
                
                if is_valid:
                    print(f"  ✅ XMLs are identical after canonicalization", file=sys.stderr)
                    print(f"     SHA256: {original_hash}", file=sys.stderr)
                else:
                    print(f"  ❌ XMLs differ after canonicalization", file=sys.stderr)
                    print(f"     Original SHA256: {original_hash}", file=sys.stderr)
                    print(f"     Restored SHA256: {restored_hash}", file=sys.stderr)
                    
                    # Show first difference
                    for i, (b1, b2) in enumerate(zip(original_canonical, restored_canonical)):
                        if b1 != b2:
                            print(f"     First difference at byte {i}", file=sys.stderr)
                            break
            
            self.stats['round_trip_valid'] = is_valid
            return is_valid
        
        # Try xmldiff validation if requested (deprecated)
        if use_xmldiff and XMLDIFF_AVAILABLE and validate_round_trip_with_xmldiff:
            if self.verbose:
                print("Using xmldiff for order-insensitive validation...", file=sys.stderr)
            
            # Convert restored_xml to bytes if it's a string
            if isinstance(restored_xml, str):
                restored_xml_bytes = restored_xml.encode('utf-8')
            else:
                restored_xml_bytes = restored_xml
            
            # Use xmldiff for comparison (ignores order differences)
            xmldiff_result = validate_round_trip_with_xmldiff(
                Path(xml_input) if isinstance(xml_input, str) else xml_input,
                restored_xml_bytes,
                ignore_order=True,
                verbose=self.verbose
            )
            
            if xmldiff_result is not None:
                self.stats['round_trip_valid'] = xmldiff_result
                return xmldiff_result
        
        # Fall back to original dictionary comparison
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
    
    def _validate_expression_balance(self, value: str, field: str) -> None:
        """
        Validate that parentheses and brackets are properly balanced.
        Raises ValueError if unbalanced.
        
        Args:
            value: Expression to validate
            field: Field name for error reporting
        """
        stack = []
        pairs = {'(': ')', '[': ']', '{': '}'}
        
        for i, char in enumerate(value):
            if char in pairs:
                stack.append((char, i))
            elif char in pairs.values():
                if not stack:
                    raise ValueError(
                        f"Unbalanced parentheses/brackets in expression: '{value}'\n"
                        f"Field: {field}\n"
                        f"Character '{char}' at position {i} has no matching opening\n"
                        f"This is likely a malformed Gmail filter expression.\n"
                        f"Please fix the filter in Gmail before converting"
                    )
                last_open, pos = stack.pop()
                if pairs[last_open] != char:
                    raise ValueError(
                        f"Mismatched parentheses/brackets in expression: '{value}'\n"
                        f"Field: {field}\n"
                        f"Opening '{last_open}' at position {pos} doesn't match closing '{char}' at position {i}\n"
                        f"This is likely a malformed Gmail filter expression.\n"
                        f"Please fix the filter in Gmail before converting"
                    )
        
        if stack:
            unmatched = ', '.join(f"'{char}' at position {pos}" for char, pos in stack)
            raise ValueError(
                f"Unbalanced parentheses/brackets in expression: '{value}'\n"
                f"Field: {field}\n"
                f"Unclosed opening characters: {unmatched}\n"
                f"This is likely a malformed Gmail filter expression.\n"
                f"Please fix the filter in Gmail before converting"
            )
    
    def _convert_xml_entry(self, entry, ns: Dict, filter_index: int = 0) -> Optional[Dict]:
        """Convert a single XML entry to a filter dictionary."""
        filter_dict = {}
        gmail_raw = {}
        
        # Preserve Gmail metadata (id and updated timestamps)
        id_element = entry.find('{http://www.w3.org/2005/Atom}id')
        if id_element is not None and id_element.text:
            # Extract just the filter ID number from the full tag URI
            # Format: tag:mail.google.com,2008:filter:1746353375264
            id_text = id_element.text
            if 'filter:' in id_text:
                filter_id = id_text.split('filter:')[-1]
                gmail_raw['id'] = filter_id
            else:
                gmail_raw['id'] = id_text
        
        updated_element = entry.find('{http://www.w3.org/2005/Atom}updated')
        if updated_element is not None and updated_element.text:
            gmail_raw['updated'] = updated_element.text
        
        # Preserve title element
        title_element = entry.find('{http://www.w3.org/2005/Atom}title')
        if title_element is not None and title_element.text:
            gmail_raw['title'] = title_element.text
        
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
                # Note: Expression validation is now done in pre-check phase
                # This ensures all errors are reported at once
                
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
        
        # Apply operator inference if enabled
        if self.operator_inference and filter_dict:
            filter_dict = self.operator_inference.infer_operators(filter_dict)
        
        return filter_dict if filter_dict else None
    
    def _flatten_filters_for_xml(self, filters: List[Dict]) -> List[Dict]:
        """
        Flatten filters for XML export:
        1. Expand filters with multiple labels into separate filters
        2. Flatten "more" structures into individual filters
        """
        flattened = []
        
        for filter_dict in filters:
            # Handle "more" structures first
            if 'more' in filter_dict:
                # Process parent and children
                parent = filter_dict.copy()
                children = parent.pop('more')
                
                # Add parent filter (might still have multiple labels)
                self._expand_filter_labels(parent, flattened)
                
                # Process each child filter
                for child in children:
                    # Child inherits all parent conditions
                    merged_child = parent.copy()
                    # Remove parent's action properties, keep only conditions
                    for key in ['label', 'archive', 'delete', 'forward', 'important', 
                               'not_important', 'not_spam', 'read', 'spam', 'star', 
                               'trash', 'unread', '_gmail_raw']:  # Also remove _gmail_raw
                        if key in merged_child:
                            del merged_child[key]
                    
                    # Handle _gmail_raw specially - merge parent and child
                    if '_gmail_raw' in parent and '_gmail_raw' in child:
                        # Merge parent and child _gmail_raw, child takes precedence
                        merged_raw = parent['_gmail_raw'].copy()
                        merged_raw.update(child['_gmail_raw'])
                        child_with_merged_raw = child.copy()
                        child_with_merged_raw['_gmail_raw'] = merged_raw
                        merged_child.update(child_with_merged_raw)
                    elif '_gmail_raw' in parent and '_gmail_raw' not in child:
                        # Child has no _gmail_raw, inherit parent's
                        child_with_parent_raw = child.copy()
                        child_with_parent_raw['_gmail_raw'] = parent['_gmail_raw'].copy()
                        merged_child.update(child_with_parent_raw)
                    else:
                        # Add child's properties as-is
                        merged_child.update(child)
                    
                    # Expand labels if needed
                    self._expand_filter_labels(merged_child, flattened)
            else:
                # No "more" structure, just expand labels if needed
                self._expand_filter_labels(filter_dict, flattened)
        
        return flattened
    
    def _expand_filter_labels(self, filter_dict: Dict, flattened: List[Dict]):
        """
        If a filter has multiple labels, create separate filters for each label.
        Gmail doesn't support multiple labels in a single filter.
        """
        if 'label' in filter_dict and isinstance(filter_dict['label'], list):
            # Multiple labels - create separate filters
            labels = filter_dict['label']
            for label in labels:
                filter_copy = filter_dict.copy()
                filter_copy['label'] = label
                flattened.append(filter_copy)
        else:
            # Single label or no label - add as is
            flattened.append(filter_dict)
    
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
        
        # First, flatten any "more" structures and expand multiple labels
        flattened_filters = self._flatten_filters_for_xml(filters)
        
        # Add each filter as an entry
        for filter_dict in flattened_filters:
            entry = etree.SubElement(root, 'entry')
            
            # Add category
            category = etree.SubElement(entry, 'category')
            category.set('term', 'filter')
            
            # Add title - use preserved value if available, otherwise default
            entry_title = etree.SubElement(entry, 'title')
            if '_gmail_raw' in filter_dict and 'title' in filter_dict['_gmail_raw']:
                entry_title.text = filter_dict['_gmail_raw']['title']
            else:
                entry_title.text = 'Mail Filter'
            
            # Add Gmail metadata if present
            if '_gmail_raw' in filter_dict:
                # Add id if present
                if 'id' in filter_dict['_gmail_raw']:
                    id_element = etree.SubElement(entry, 'id')
                    filter_id = filter_dict['_gmail_raw']['id']
                    # Reconstruct full Gmail filter ID if it's just the number
                    if filter_id.isdigit() or not filter_id.startswith('tag:'):
                        id_element.text = f'tag:mail.google.com,2008:filter:{filter_id}'
                    else:
                        id_element.text = filter_id
                
                # Add updated timestamp if present
                if 'updated' in filter_dict['_gmail_raw']:
                    updated_element = etree.SubElement(entry, 'updated')
                    updated_element.text = filter_dict['_gmail_raw']['updated']
            
            # Add content (empty)
            content = etree.SubElement(entry, 'content')
            
            # Process standard properties
            for yaml_key, value in filter_dict.items():
                if yaml_key == '_gmail_raw' or yaml_key == 'more':
                    continue
                
                xml_key = self.YAML_TO_XML_MAP.get(yaml_key)
                if xml_key:
                    # Labels should already be single values after flattening
                    self._add_property(entry, xml_key, value, ns_map)
            
            # Add preserved Gmail properties (except id, updated, and title which are handled as elements)
            if '_gmail_raw' in filter_dict:
                for name, value in filter_dict['_gmail_raw'].items():
                    if name not in ['id', 'updated', 'title']:  # Skip metadata fields that are elements, not properties
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
        elif isinstance(value, dict):
            # Handle operator dictionaries - convert back to Gmail search syntax
            value = self._operator_dict_to_string(value)
        
        # Note: Expression validation is now done in pre-check phase
        # This ensures all errors are reported at once
        
        prop.set('value', str(value))
    
    def _operator_dict_to_string(self, op_dict: Dict) -> str:
        """
        Convert operator dictionary back to Gmail search string.
        Examples:
            {'any': ['A', 'B', 'C']} -> '(A OR B OR C)'
            {'all': ['A', 'B']} -> '(A AND B)'
            {'not': 'A'} -> '-A'
            {'not': {'any': ['A', 'B']}} -> '-(A OR B)'
        """
        if 'any' in op_dict:
            # OR pattern - always wrap in parentheses for safety
            terms = op_dict['any']
            if isinstance(terms, list):
                # Quote terms if they contain spaces
                quoted_terms = []
                for term in terms:
                    if isinstance(term, dict):
                        # Nested operator - recurse
                        quoted_terms.append(self._operator_dict_to_string(term))
                    elif ' ' in str(term) and not (str(term).startswith('"') and str(term).endswith('"')):
                        quoted_terms.append(f'"{term}"')
                    else:
                        quoted_terms.append(str(term))
                return f"({' OR '.join(quoted_terms)})"
            else:
                return str(terms)
        
        elif 'all' in op_dict:
            # AND pattern - wrap in parentheses
            terms = op_dict['all']
            if isinstance(terms, list):
                # Quote terms if they contain spaces
                quoted_terms = []
                for term in terms:
                    if isinstance(term, dict):
                        # Nested operator
                        quoted_terms.append(self._operator_dict_to_string(term))
                    elif ' ' in str(term) and not (str(term).startswith('"') and str(term).endswith('"')):
                        quoted_terms.append(f'"{term}"')
                    else:
                        quoted_terms.append(str(term))
                return f"({' AND '.join(quoted_terms)})"
            else:
                return str(terms)
        
        elif 'not' in op_dict:
            # NOT pattern
            value = op_dict['not']
            if isinstance(value, dict):
                # Nested operator like {'not': {'any': ['A', 'B']}}
                return f"-{self._operator_dict_to_string(value)}"
            else:
                # Simple negation
                if ' ' in str(value) and not (str(value).startswith('"') and str(value).endswith('"')):
                    return f'-"{value}"'
                else:
                    return f'-{value}'
        
        else:
            # Unknown operator, return as string
            return str(op_dict)
    
    def _infer_more_structures(self, filters: List[Dict]) -> List[Dict]:
        """
        Attempt to infer hierarchical "more" structures from flat filters.
        
        Args:
            filters: List of flat filter dictionaries
            
        Returns:
            List of filters with inferred "more" structures where applicable
        """
        if not filters:
            return filters
        
        # Find potential parent-child relationships
        hierarchies = self._detect_hierarchies(filters)
        
        if not hierarchies:
            return filters
        
        # Build the new structure with "more" constructs
        structured_filters = self._build_more_structures(hierarchies, filters)
        
        if self.verbose:
            print(f"✅ Inferred {len(hierarchies)} hierarchical structures", file=sys.stderr)
            print(f"   Reduced from {len(filters)} to {len(structured_filters)} top-level filters", file=sys.stderr)
        
        self.stats['hierarchies_inferred'] = len(hierarchies)
        
        return structured_filters
    
    def _detect_hierarchies(self, filters: List[Dict]) -> List[Dict]:
        """
        Detect potential parent-child relationships between filters.
        
        Returns:
            List of hierarchy dictionaries with 'parent' and 'children' indices
        """
        hierarchies = []
        used_indices = set()
        
        # Sort filters by number of conditions (fewer conditions first, likely parents)
        indexed_filters = [(i, f, self._get_filter_conditions(f)) for i, f in enumerate(filters)]
        indexed_filters.sort(key=lambda x: len(x[2]))
        
        # For interactive mode, we need to handle user decisions
        skip_all_similar = False
        accept_all_similar = False
        
        for i, (parent_idx, parent_filter, parent_conditions) in enumerate(indexed_filters):
            if parent_idx in used_indices:
                continue
            
            children = []
            
            # Look for potential children (filters that have all parent conditions plus more)
            for child_idx, child_filter, child_conditions in indexed_filters[i+1:]:
                if child_idx in used_indices:
                    continue
                
                # Check basic conditions for parent-child relationship
                if not self._basic_child_check(parent_filter, child_filter, parent_conditions, child_conditions):
                    continue
                
                # In interactive mode, ask user about each potential merge
                if self.infer_strategy == 'interactive':
                    should_merge = self._interactive_merge_decision(
                        parent_filter, child_filter, 
                        skip_all_similar, accept_all_similar
                    )
                    
                    if should_merge == 'skip_all':
                        skip_all_similar = True
                        continue
                    elif should_merge == 'accept_all':
                        accept_all_similar = True
                        should_merge = True
                    
                    if should_merge:
                        children.append(child_idx)
                        used_indices.add(child_idx)
                else:
                    # Non-interactive modes use _is_child_of which includes safety checks
                    if self._is_child_of(parent_filter, child_filter, parent_conditions, child_conditions):
                        children.append(child_idx)
                        if self.infer_strategy == 'aggressive':
                            used_indices.add(child_idx)
            
            # Only create hierarchy if we found children
            if children:
                hierarchies.append({
                    'parent': parent_idx,
                    'children': children
                })
                used_indices.add(parent_idx)
                if self.infer_strategy in ['conservative', 'interactive']:
                    # In conservative/interactive mode, only use each filter once
                    used_indices.update(children)
        
        return hierarchies
    
    def _basic_child_check(self, parent: Dict, child: Dict, parent_conditions: Dict, child_conditions: Dict) -> bool:
        """
        Basic check if child could be a child of parent (without safety analysis).
        """
        # Child must have all parent conditions
        for key, parent_value in parent_conditions.items():
            if key not in child_conditions:
                return False
            
            child_value = child_conditions[key]
            
            # For 'has' fields, check if child extends parent
            if key == 'has':
                if not self._has_value_extends(parent_value, child_value):
                    return False
            # For other fields, must be identical
            elif parent_value != child_value:
                return False
        
        # Child must have at least one additional condition
        if len(child_conditions) <= len(parent_conditions):
            return False
        
        return True
    
    def _interactive_merge_decision(self, parent: Dict, child: Dict, 
                                   skip_all: bool, accept_all: bool) -> Union[bool, str]:
        """
        Interactively ask user about merging two filters.
        
        Returns:
            True/False for merge decision, or 'skip_all'/'accept_all' for batch decisions
        """
        # Check if we have a batch decision
        if skip_all or accept_all:
            pattern_key = self.safety_analyzer.create_pattern_key(parent, child)
            remembered = self.safety_analyzer.get_remembered_decision(pattern_key)
            if remembered == 'skip_all' or skip_all:
                return False
            elif remembered == 'accept_all' or accept_all:
                return True
        
        # Perform safety analysis
        safety_analysis = self.safety_analyzer.analyze_merge_safety(parent, child)
        
        # Display the analysis to user
        print("\n" + "═" * 70, file=sys.stderr)
        print("Potential hierarchy detected:\n", file=sys.stderr)
        
        print("PARENT FILTER:", file=sys.stderr)
        print(self.safety_analyzer.format_filter_summary(parent, "  "), file=sys.stderr)
        
        print("\nCHILD FILTER (would inherit parent conditions):", file=sys.stderr)
        print(self.safety_analyzer.format_filter_summary(child, "  "), file=sys.stderr)
        
        # Show warnings if any
        if safety_analysis['warnings']:
            print("\n⚠️  WARNINGS:", file=sys.stderr)
            for warning in safety_analysis['warnings']:
                print(f"  {warning}", file=sys.stderr)
        
        # Show confidence
        confidence = safety_analysis['confidence']
        severity = safety_analysis['severity']
        print(f"\nConfidence: {confidence}% | Severity: {severity}", file=sys.stderr)
        
        # Show what would be inherited
        print("\nIf merged, the child would inherit:", file=sys.stderr)
        parent_conditions = self._get_filter_conditions(parent)
        for key, value in parent_conditions.items():
            print(f"  ✓ {key}: {value}", file=sys.stderr)
        
        # Also show inherited actions that might be problematic
        dangerous_actions = ['archive', 'delete', 'trash', 'forward']
        for action in dangerous_actions:
            if parent.get(action):
                warning = " ⚠️" if safety_analysis['severity'] in ['high', 'critical'] else ""
                print(f"  ✓ {action}: {parent[action]}{warning}", file=sys.stderr)
        
        # Get user decision
        print("\nMerge these filters into a hierarchy?", file=sys.stderr)
        print("[y]es / [N]o / [a]ll similar / [s]kip all similar / [h]elp: ", end="", file=sys.stderr)
        
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSkipping...", file=sys.stderr)
            return False
        
        if response == 'h':
            print("\nHelp:", file=sys.stderr)
            print("  y/yes     - Merge these two filters", file=sys.stderr)
            print("  n/no      - Keep filters separate (default)", file=sys.stderr)
            print("  a/all     - Merge all similar patterns automatically", file=sys.stderr)
            print("  s/skip    - Skip all similar patterns automatically", file=sys.stderr)
            print("  h/help    - Show this help", file=sys.stderr)
            print("\nPress Enter to repeat the question...", file=sys.stderr)
            input()
            return self._interactive_merge_decision(parent, child, skip_all, accept_all)
        
        # Remember the decision for similar patterns
        pattern_key = self.safety_analyzer.create_pattern_key(parent, child)
        
        if response in ['y', 'yes']:
            self.safety_analyzer.remember_decision(pattern_key, 'yes')
            return True
        elif response in ['a', 'all']:
            self.safety_analyzer.remember_decision(pattern_key, 'accept_all')
            return 'accept_all'
        elif response in ['s', 'skip']:
            self.safety_analyzer.remember_decision(pattern_key, 'skip_all')
            return 'skip_all'
        else:  # Default to 'no'
            self.safety_analyzer.remember_decision(pattern_key, 'no')
            return False
    
    def _format_filter_summary(self, filter_dict: Dict, max_value_len: int = 50) -> str:
        """
        Format a concise summary of a filter for logging.
        
        Args:
            filter_dict: Filter dictionary
            max_value_len: Maximum length for each value display
            
        Returns:
            Formatted filter summary string
        """
        summary_parts = []
        
        # Priority order for fields to show
        priority_fields = ['from', 'to', 'subject', 'has', 'label', 'archive', 'delete']
        
        # First add priority fields if present
        for field in priority_fields:
            if field in filter_dict:
                value = filter_dict[field]
                if isinstance(value, str) and len(value) > max_value_len:
                    value = value[:max_value_len] + '...'
                elif isinstance(value, list):
                    value = f"[{', '.join(str(v)[:20] for v in value[:2])}{'...' if len(value) > 2 else ''}]"
                elif isinstance(value, dict):
                    # Handle operator dicts
                    if 'any' in value:
                        value = f"any({len(value['any'])} items)"
                    elif 'all' in value:
                        value = f"all({len(value['all'])} items)"
                    elif 'not' in value:
                        value = f"not(...)"
                summary_parts.append(f"{field}={value}")
                
                # Stop after we have 3-4 parts for brevity
                if len(summary_parts) >= 4:
                    break
        
        # If we don't have enough, add any other fields
        if len(summary_parts) < 3:
            for field, value in filter_dict.items():
                if field not in priority_fields and field != '_gmail_raw':
                    if isinstance(value, str) and len(value) > max_value_len:
                        value = value[:max_value_len] + '...'
                    summary_parts.append(f"{field}={value}")
                    if len(summary_parts) >= 3:
                        break
        
        # Add filter ID if available
        if '_gmail_raw' in filter_dict and 'id' in filter_dict['_gmail_raw']:
            filter_id = filter_dict['_gmail_raw']['id']
            return f"Filter ID {filter_id}: {', '.join(summary_parts)}"
        
        return ', '.join(summary_parts) if summary_parts else 'Empty filter'
    
    def _get_filter_conditions(self, filter_dict: Dict) -> Dict:
        """
        Extract only the condition fields from a filter (not actions).
        """
        # Conditions are fields that filter emails
        condition_keys = {'from', 'to', 'cc', 'bcc', 'subject', 'has', 'does_not_have', 
                         'list', 'has_attachment', 'filename', 'category', 'size',
                         'larger', 'smaller', 'rfc822msgid', 'deliveredto', 'is'}
        
        conditions = {}
        for key, value in filter_dict.items():
            if key in condition_keys or key in self.XML_TO_YAML_MAP.values():
                # Check if it's a condition by checking against known conditions
                if key not in {'label', 'archive', 'delete', 'read', 'star', 'important',
                              'not_important', 'not_spam', 'trash', 'forward', '_gmail_raw'}:
                    conditions[key] = value
        
        return conditions
    
    def _is_child_of(self, parent: Dict, child: Dict, parent_conditions: Dict, child_conditions: Dict) -> bool:
        """
        Determine if child filter could be a child of parent filter in a "more" structure.
        """
        # Child must have all parent conditions
        for key, parent_value in parent_conditions.items():
            if key not in child_conditions:
                return False
            
            child_value = child_conditions[key]
            
            # For 'has' fields, check if child extends parent
            if key == 'has':
                if not self._has_value_extends(parent_value, child_value):
                    return False
            # For other fields, must be identical
            elif parent_value != child_value:
                return False
        
        # Child must have at least one additional condition
        if len(child_conditions) <= len(parent_conditions):
            return False
        
        # Apply safety analysis if we have a safety analyzer
        if self.safety_analyzer and self.infer_strategy != 'interactive':
            safety_analysis = self.safety_analyzer.analyze_merge_safety(parent, child)
            
            if self.infer_strategy == 'conservative':
                # Conservative: Skip if any safety warnings
                if not safety_analysis['safe'] or safety_analysis['warnings']:
                    # Always show basic info about skipped filter, even in non-verbose mode
                    parent_summary = self._format_filter_summary(parent)
                    child_summary = self._format_filter_summary(child)
                    
                    # Extract the primary warning for display
                    primary_reason = "Safety concern detected"
                    if safety_analysis['warnings']:
                        # Clean up the first warning for display
                        primary_reason = safety_analysis['warnings'][0].replace('⛔', '').replace('⚠️', '').replace('ℹ️', '').strip()
                    
                    if self.verbose:
                        print(f"  Skipping filter merge due to safety concerns:", file=sys.stderr)
                        print(f"    Parent: {parent_summary}", file=sys.stderr)
                        print(f"    Child:  {child_summary}", file=sys.stderr)
                        if safety_analysis['warnings']:
                            print(f"    Reason: {'; '.join(safety_analysis['warnings'])}", file=sys.stderr)
                    else:
                        # Non-verbose: Show concise but informative message
                        print(f"  ⚠️  Skipping filter merge: {primary_reason}", file=sys.stderr)
                        print(f"      Child filter: {child_summary}", file=sys.stderr)
                    
                    self.stats['hierarchies_skipped_safety'] += 1
                    return False
                
                # Also check label compatibility as before
                parent_label = parent.get('label')
                child_label = child.get('label')
                
                if parent_label and child_label and parent_label != child_label:
                    if not isinstance(child_label, list) or parent_label not in child_label:
                        if not (isinstance(parent_label, str) and isinstance(child_label, str) and 
                               (parent_label in child_label or child_label.startswith(parent_label))):
                            return False
            
            elif self.infer_strategy == 'aggressive':
                # Aggressive: Only skip critical safety issues
                if safety_analysis['severity'] == 'critical':
                    # Always show basic info about skipped filter, even in non-verbose mode
                    parent_summary = self._format_filter_summary(parent)
                    child_summary = self._format_filter_summary(child)
                    
                    # Extract the most critical warning for display
                    critical_reason = "Safety conflict detected"
                    if safety_analysis['warnings']:
                        # Find the most critical warning (those with ⛔ symbol)
                        critical_warnings = [w for w in safety_analysis['warnings'] if '⛔' in w]
                        if critical_warnings:
                            # Clean up the warning for display
                            critical_reason = critical_warnings[0].replace('⛔', '').strip()
                        elif safety_analysis['warnings']:
                            critical_reason = safety_analysis['warnings'][0].replace('⚠️', '').strip()
                    
                    if self.verbose:
                        print(f"  Skipping filter merge due to critical safety issue:", file=sys.stderr)
                        print(f"    Parent: {parent_summary}", file=sys.stderr)
                        print(f"    Child:  {child_summary}", file=sys.stderr)
                        if safety_analysis['warnings']:
                            print(f"    Reason: {'; '.join(safety_analysis['warnings'])}", file=sys.stderr)
                    else:
                        # Non-verbose: Show concise but informative message
                        print(f"  ⚠️  Skipping filter merge: {critical_reason}", file=sys.stderr)
                        print(f"      Child filter: {child_summary}", file=sys.stderr)
                    
                    self.stats['hierarchies_skipped_safety'] += 1
                    return False
        
        return True
    
    def _has_value_extends(self, parent_value: Union[str, Dict], child_value: Union[str, Dict]) -> bool:
        """
        Check if child's 'has' value extends parent's (includes it as substring or AND condition).
        """
        # Handle dict values from operator inference
        if isinstance(parent_value, dict) or isinstance(child_value, dict):
            # Can't do simple string comparison with dicts
            # For now, consider them as not extending if either is a dict
            return False
        
        # Simple containment check
        if parent_value in child_value:
            return True
        
        # Check for AND pattern: (parent AND something)
        if child_value.startswith('(') and ' AND ' in child_value:
            # Remove parentheses and quotes
            child_clean = child_value.strip('()').replace('"', '')
            parent_clean = parent_value.replace('"', '')
            
            # Split by AND and check if parent is one of the parts
            parts = [p.strip() for p in child_clean.split(' AND ')]
            return parent_clean in parts
        
        return False
    
    def _build_more_structures(self, hierarchies: List[Dict], filters: List[Dict]) -> List[Dict]:
        """
        Build new filter list with "more" structures based on detected hierarchies.
        """
        used_indices = set()
        structured = []
        
        # Process each hierarchy
        for hierarchy in hierarchies:
            parent_idx = hierarchy['parent']
            children_indices = hierarchy['children']
            
            # Get parent filter
            parent = filters[parent_idx].copy()
            
            # Build "more" list from children
            more_list = []
            for child_idx in children_indices:
                child = filters[child_idx].copy()
                
                # Remove parent conditions from child (they're inherited)
                parent_conditions = self._get_filter_conditions(parent)
                for key in parent_conditions:
                    if key in child:
                        # For 'has', remove parent part if it's AND'd
                        if key == 'has':
                            child_has = child[key]
                            parent_has = parent[key]
                            if self._has_value_extends(parent_has, child_has):
                                # Try to extract just the additional part
                                simplified = self._simplify_has_condition(parent_has, child_has)
                                if simplified and simplified != child_has:
                                    child[key] = simplified
                                else:
                                    # If we can't simplify, keep the full condition
                                    pass
                        else:
                            # Remove identical conditions
                            if child[key] == parent_conditions[key]:
                                del child[key]
                
                # Also handle _gmail_raw inheritance
                if '_gmail_raw' in parent and '_gmail_raw' in child:
                    parent_raw = parent['_gmail_raw']
                    child_raw = child['_gmail_raw'].copy()
                    
                    # Remove any child _gmail_raw properties that are identical to parent
                    for raw_key, raw_value in list(child_raw.items()):
                        if raw_key in parent_raw and parent_raw[raw_key] == raw_value:
                            del child_raw[raw_key]
                    
                    # If all _gmail_raw properties were inherited, remove the whole section
                    if not child_raw:
                        del child['_gmail_raw']
                    else:
                        child['_gmail_raw'] = child_raw
                
                more_list.append(child)
                used_indices.add(child_idx)
            
            # Add "more" to parent
            if more_list:
                parent['more'] = more_list
            
            structured.append(parent)
            used_indices.add(parent_idx)
        
        # Add remaining filters that weren't part of any hierarchy
        for i, filter_dict in enumerate(filters):
            if i not in used_indices:
                structured.append(filter_dict)
        
        return structured
    
    def _simplify_has_condition(self, parent_has: Union[str, Dict], child_has: Union[str, Dict]) -> Optional[Union[str, Dict]]:
        """
        Try to simplify child's 'has' condition by removing parent's part.
        
        Example: 
            parent: "urgent"
            child: "(urgent AND meeting)" 
            returns: "meeting"
            
            parent: "pull request"
            child: "(pull request AND review requested)"
            returns: "review requested"
        """
        # Handle dict values from operator inference
        if isinstance(parent_has, dict) or isinstance(child_has, dict):
            # Can't simplify dicts, return child as-is
            return child_has
        
        # Handle AND pattern with parentheses
        if child_has.startswith('(') and ' AND ' in child_has:
            child_clean = child_has.strip('()')
            parts = [p.strip() for p in child_clean.split(' AND ')]
            
            # Remove parent part (handle both with and without quotes)
            parent_clean = parent_has.strip('"')
            remaining = []
            for part in parts:
                part_clean = part.strip('"')
                # Check if this part is the parent or contains the parent
                if part_clean != parent_clean:
                    # Also check if parent is a phrase that matches this part
                    if parent_clean not in part_clean or part_clean == parent_clean:
                        remaining.append(part)
            
            # If we removed something, return simplified version
            if len(remaining) < len(parts):
                if len(remaining) == 1:
                    return remaining[0]
                elif len(remaining) > 1:
                    return f"({' AND '.join(remaining)})"
        
        # Handle case where parent is a phrase without quotes
        # e.g., parent: "pull request", child: "(pull request AND review requested)"
        if ' ' in parent_has and parent_has in child_has:
            # Try to remove the parent phrase
            if child_has.startswith('(') and child_has.endswith(')'):
                inner = child_has[1:-1]
                parts = inner.split(' AND ')
                remaining = [p for p in parts if p.strip() != parent_has.strip()]
                if len(remaining) < len(parts):
                    if len(remaining) == 1:
                        return remaining[0].strip()
                    elif remaining:
                        return f"({' AND '.join(remaining)})"
        
        return None
    
    def _merge_identical_filters(self, filters: List[Dict]) -> List[Dict]:
        """
        Merge filters that are identical except for their labels.
        
        Args:
            filters: List of filter dictionaries
            
        Returns:
            List of merged filter dictionaries
        """
        merged = []
        seen_signatures = {}
        
        for filter_dict in filters:
            # Create a signature of the filter without the label
            signature_dict = {k: v for k, v in filter_dict.items() if k != 'label'}
            
            # Convert to a hashable signature
            # Sort items to ensure consistent ordering
            def make_hashable(obj):
                """Recursively convert an object to a hashable form."""
                if isinstance(obj, dict):
                    return tuple(sorted((k, make_hashable(v)) for k, v in obj.items()))
                elif isinstance(obj, list):
                    return tuple(make_hashable(item) for item in obj)
                else:
                    return obj
            
            signature_items = []
            for k, v in sorted(signature_dict.items()):
                signature_items.append((k, make_hashable(v)))
            signature = tuple(signature_items)
            
            # Check if we've seen this signature before
            if signature in seen_signatures:
                # Merge labels with existing filter
                existing_idx = seen_signatures[signature]
                existing_filter = merged[existing_idx]
                
                # Get labels from both filters
                existing_labels = existing_filter.get('label', [])
                new_labels = filter_dict.get('label', [])
                
                # Ensure labels are lists
                if not isinstance(existing_labels, list):
                    existing_labels = [existing_labels] if existing_labels else []
                if not isinstance(new_labels, list):
                    new_labels = [new_labels] if new_labels else []
                
                # Merge unique labels
                all_labels = existing_labels + new_labels
                unique_labels = []
                seen_labels = set()
                for label in all_labels:
                    if label not in seen_labels:
                        unique_labels.append(label)
                        seen_labels.add(label)
                
                # Update the existing filter with merged labels
                if unique_labels:
                    existing_filter['label'] = unique_labels if len(unique_labels) > 1 else unique_labels[0]
                
                self.stats['filters_merged'] += 1
                
                if self.verbose:
                    print(f"  Merged filter with labels: {new_labels} into existing filter", file=sys.stderr)
            else:
                # New unique filter
                seen_signatures[signature] = len(merged)
                merged.append(filter_dict)
        
        if self.verbose and self.stats['filters_merged'] > 0:
            print(f"✅ Merged {self.stats['filters_merged']} duplicate filters", file=sys.stderr)
            print(f"   Reduced from {len(filters)} to {len(merged)} filters", file=sys.stderr)
        
        return merged
    
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