#!/usr/bin/env python
"""
Verify XML equivalence using xmldiff, ignoring element order.

Usage:
    python verify_xml.py original.xml converted.xml
"""

import sys
from pathlib import Path

try:
    from xmldiff import main as xmldiff_main
    from xmldiff.actions import MoveNode
except ImportError:
    print("Error: xmldiff not installed. Install with: pip install xmldiff")
    sys.exit(1)


def verify_xml_files(original_file, converted_file, verbose=False):
    """Compare two XML files, ignoring element order."""
    
    # Read files
    with open(original_file, 'rb') as f:
        original_xml = f.read()
    
    with open(converted_file, 'rb') as f:
        converted_xml = f.read()
    
    # Get differences
    all_diffs = xmldiff_main.diff_texts(original_xml, converted_xml)
    
    # Separate order changes from semantic changes
    order_diffs = [d for d in all_diffs if isinstance(d, MoveNode)]
    semantic_diffs = [d for d in all_diffs if not isinstance(d, MoveNode)]
    
    # Report results
    print(f"Comparing: {original_file} vs {converted_file}")
    print(f"  Total differences: {len(all_diffs)}")
    print(f"  Order differences (ignored): {len(order_diffs)}")
    print(f"  Semantic differences: {len(semantic_diffs)}")
    
    if semantic_diffs:
        print("\n❌ FILES DIFFER - Semantic changes found:")
        for i, diff in enumerate(semantic_diffs[:10], 1):
            print(f"  {i}. {diff}")
        if len(semantic_diffs) > 10:
            print(f"  ... and {len(semantic_diffs) - 10} more differences")
        return False
    else:
        if order_diffs:
            print(f"\n✅ FILES ARE EQUIVALENT (ignoring {len(order_diffs)} order changes)")
        else:
            print("\n✅ FILES ARE IDENTICAL")
        return True


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_xml.py original.xml converted.xml")
        sys.exit(1)
    
    original_file = Path(sys.argv[1])
    converted_file = Path(sys.argv[2])
    
    if not original_file.exists():
        print(f"Error: File not found: {original_file}")
        sys.exit(1)
    
    if not converted_file.exists():
        print(f"Error: File not found: {converted_file}")
        sys.exit(1)
    
    # Verify equivalence
    is_equivalent = verify_xml_files(original_file, converted_file, verbose=True)
    
    # Exit with appropriate code
    sys.exit(0 if is_equivalent else 1)


if __name__ == "__main__":
    main()