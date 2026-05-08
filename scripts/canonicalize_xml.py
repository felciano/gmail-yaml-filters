#!/usr/bin/env python
"""
Canonicalize Gmail filter XML files for order-insensitive comparison.

This tool sorts XML elements deterministically and applies C14N canonicalization,
allowing byte-for-byte comparison of semantically equivalent XML files.

Usage:
    python canonicalize_xml.py input.xml output.xml
    python canonicalize_xml.py file1.xml file2.xml --compare
"""

import sys
import hashlib
from pathlib import Path
from lxml import etree


def sort_key_gmail(elem):
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


def sort_children(elem):
    """Recursively sort all children of an element."""
    # First recurse into children
    for child in list(elem):
        if isinstance(child.tag, str):  # Skip comments, PIs
            sort_children(child)
    
    # Get all element children (skip comments/PIs/text)
    kids = [c for c in elem if isinstance(c.tag, str)]
    
    # Sort them
    kids_sorted = sorted(kids, key=sort_key_gmail)
    
    # If order changed, reattach in sorted order
    if kids != kids_sorted:
        for k in kids:
            elem.remove(k)
        for k in kids_sorted:
            elem.append(k)


def normalize_boolean_expressions(tree):
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


def canonicalize_gmail_xml(xml_input, remove_feed_metadata=False):
    """
    Canonicalize Gmail filter XML for comparison.
    
    Args:
        xml_input: Path to XML file or XML bytes/string
        remove_feed_metadata: If True, remove feed-level id, updated, author
        
    Returns:
        Canonicalized XML as bytes
    """
    # Parse XML
    if isinstance(xml_input, (str, Path)):
        if Path(xml_input).exists():
            with open(xml_input, 'rb') as f:
                xml_content = f.read()
        else:
            xml_content = xml_input.encode('utf-8') if isinstance(xml_input, str) else xml_input
    else:
        xml_content = xml_input
    
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
    normalize_boolean_expressions(tree)
    
    # Sort all children recursively
    sort_children(tree)
    
    # Apply C14N canonicalization
    canonical = etree.tostring(tree, method="c14n", with_comments=False, exclusive=False)
    
    return canonical


def compare_canonical(file1, file2, remove_feed_metadata=False, verbose=False):
    """
    Compare two XML files after canonicalization.
    
    Args:
        file1: Path to first XML file
        file2: Path to second XML file
        remove_feed_metadata: If True, ignore feed-level metadata
        verbose: If True, show details
        
    Returns:
        True if files are equivalent after canonicalization
    """
    if verbose:
        print(f"Canonicalizing {file1}...")
    canon1 = canonicalize_gmail_xml(file1, remove_feed_metadata)
    hash1 = hashlib.sha256(canon1).hexdigest()
    
    if verbose:
        print(f"Canonicalizing {file2}...")
    canon2 = canonicalize_gmail_xml(file2, remove_feed_metadata)
    hash2 = hashlib.sha256(canon2).hexdigest()
    
    if verbose:
        print(f"\nFile 1 SHA256: {hash1}")
        print(f"File 2 SHA256: {hash2}")
        print(f"Canonical size 1: {len(canon1)} bytes")
        print(f"Canonical size 2: {len(canon2)} bytes")
    
    is_equal = canon1 == canon2
    
    # ALWAYS show the result (not just in verbose mode)
    if is_equal:
        print("✅ Files are IDENTICAL after canonicalization")
    else:
        print("❌ Files DIFFER after canonicalization")
        
        if verbose:
            # In verbose mode, show where they differ
            for i, (b1, b2) in enumerate(zip(canon1, canon2)):
                if b1 != b2:
                    print(f"First difference at byte {i}")
                    context = 100
                    start = max(0, i - context)
                    end = min(len(canon1), i + context)
                    print(f"Context 1: ...{canon1[start:end].decode('utf-8', errors='ignore')}...")
                    print(f"Context 2: ...{canon2[start:end].decode('utf-8', errors='ignore')}...")
                    break
    
    return is_equal


def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Canonicalize Gmail XML for order-insensitive comparison'
    )
    parser.add_argument('file1', help='First XML file')
    parser.add_argument('file2', nargs='?', help='Second XML file (for comparison) or output file')
    parser.add_argument('--compare', '-c', action='store_true',
                      help='Compare two files instead of canonicalizing')
    parser.add_argument('--ignore-feed-metadata', '-i', action='store_true',
                      help='Ignore feed-level id, updated, author elements')
    parser.add_argument('--verbose', '-v', action='store_true',
                      help='Show detailed information')
    
    args = parser.parse_args()
    
    if args.compare:
        # Compare mode
        if not args.file2:
            print("Error: Two files required for comparison")
            sys.exit(1)
        
        is_equal = compare_canonical(
            args.file1, 
            args.file2,
            remove_feed_metadata=args.ignore_feed_metadata,
            verbose=args.verbose
        )
        sys.exit(0 if is_equal else 1)
    
    else:
        # Canonicalize mode
        canonical = canonicalize_gmail_xml(
            args.file1,
            remove_feed_metadata=args.ignore_feed_metadata
        )
        
        if args.file2:
            # Write to output file
            with open(args.file2, 'wb') as f:
                f.write(canonical)
            print(f"✅ Canonicalized XML written to {args.file2}")
        else:
            # Write to stdout
            sys.stdout.buffer.write(canonical)


if __name__ == "__main__":
    main()