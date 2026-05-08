#!/usr/bin/env python
"""XML validation using xmldiff for order-insensitive comparison."""

from typing import List, Dict, Tuple, Optional
from pathlib import Path
import sys

try:
    from xmldiff import main as xmldiff_main
    from xmldiff.actions import MoveNode
    XMLDIFF_AVAILABLE = True
except ImportError:
    XMLDIFF_AVAILABLE = False


def validate_xml_equivalence(
    xml1: bytes, 
    xml2: bytes, 
    ignore_order: bool = True,
    verbose: bool = False
) -> Tuple[bool, List[Dict], List[Dict]]:
    """
    Validate that two XML documents are semantically equivalent.
    
    Args:
        xml1: First XML document as bytes
        xml2: Second XML document as bytes
        ignore_order: If True, ignore element order differences
        verbose: If True, print detailed diff information
        
    Returns:
        Tuple of (is_equivalent, semantic_differences, order_differences)
        - is_equivalent: True if XMLs are semantically equivalent
        - semantic_differences: List of non-order differences
        - order_differences: List of order-only differences (MoveNode actions)
    """
    if not XMLDIFF_AVAILABLE:
        raise ImportError("xmldiff package is required for XML validation. Install with: pip install xmldiff")
    
    # Get the full diff
    all_diffs = xmldiff_main.diff_texts(xml1, xml2)
    
    # Separate order changes from semantic changes
    order_diffs = [d for d in all_diffs if isinstance(d, MoveNode)]
    semantic_diffs = [d for d in all_diffs if not isinstance(d, MoveNode)]
    
    if verbose:
        if order_diffs:
            print(f"  Order differences: {len(order_diffs)} elements reordered", file=sys.stderr)
        if semantic_diffs:
            print(f"  Semantic differences: {len(semantic_diffs)} actual changes", file=sys.stderr)
            for diff in semantic_diffs[:5]:  # Show first 5 differences
                print(f"    - {diff}", file=sys.stderr)
            if len(semantic_diffs) > 5:
                print(f"    ... and {len(semantic_diffs) - 5} more", file=sys.stderr)
    
    # Determine equivalence based on ignore_order setting
    if ignore_order:
        is_equivalent = len(semantic_diffs) == 0
    else:
        is_equivalent = len(all_diffs) == 0
    
    return is_equivalent, semantic_diffs, order_diffs


def validate_round_trip_with_xmldiff(
    original_xml_path: Path,
    converted_xml: bytes,
    ignore_order: bool = True,
    verbose: bool = False
) -> bool:
    """
    Validate round-trip conversion using xmldiff.
    
    Args:
        original_xml_path: Path to original XML file
        converted_xml: Converted XML as bytes
        ignore_order: If True, ignore element order differences
        verbose: If True, print detailed comparison
        
    Returns:
        True if round-trip is valid (semantically equivalent)
    """
    if not XMLDIFF_AVAILABLE:
        if verbose:
            print("  Note: xmldiff not available, using basic validation", file=sys.stderr)
        return None  # Indicate xmldiff validation not available
    
    # Read original XML
    with open(original_xml_path, 'rb') as f:
        original_xml = f.read()
    
    # Validate equivalence
    is_equivalent, semantic_diffs, order_diffs = validate_xml_equivalence(
        original_xml, 
        converted_xml,
        ignore_order=ignore_order,
        verbose=verbose
    )
    
    if verbose:
        if is_equivalent:
            if order_diffs and ignore_order:
                print(f"  ✅ XMLs are semantically equivalent (ignoring {len(order_diffs)} order differences)", file=sys.stderr)
            else:
                print("  ✅ XMLs are identical", file=sys.stderr)
        else:
            print(f"  ❌ XMLs differ: {len(semantic_diffs)} semantic differences found", file=sys.stderr)
    
    return is_equivalent


def get_xml_diff_summary(
    xml1: bytes,
    xml2: bytes,
    max_diffs: int = 10
) -> str:
    """
    Get a human-readable summary of differences between two XMLs.
    
    Args:
        xml1: First XML document
        xml2: Second XML document
        max_diffs: Maximum number of differences to show
        
    Returns:
        String summary of differences
    """
    if not XMLDIFF_AVAILABLE:
        return "xmldiff not available for detailed comparison"
    
    all_diffs = xmldiff_main.diff_texts(xml1, xml2)
    
    if not all_diffs:
        return "XMLs are identical"
    
    order_diffs = [d for d in all_diffs if isinstance(d, MoveNode)]
    semantic_diffs = [d for d in all_diffs if not isinstance(d, MoveNode)]
    
    summary = []
    
    if order_diffs:
        summary.append(f"Order differences: {len(order_diffs)} elements reordered")
    
    if semantic_diffs:
        summary.append(f"Semantic differences: {len(semantic_diffs)} changes")
        for i, diff in enumerate(semantic_diffs[:max_diffs], 1):
            summary.append(f"  {i}. {diff}")
        if len(semantic_diffs) > max_diffs:
            summary.append(f"  ... and {len(semantic_diffs) - max_diffs} more")
    
    return "\n".join(summary)