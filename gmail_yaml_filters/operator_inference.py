#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Operator inference for Gmail filter conversion.

Detects and converts Gmail's OR/AND/NOT patterns in search queries
to YAML operator constructs (any, all, not) for more readable filters.
"""
import re
from typing import Dict, List, Optional, Union, Any


class OperatorInference:
    """Infers YAML operators from Gmail search patterns."""
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the operator inference engine.
        
        Args:
            verbose: Whether to print detailed inference information
        """
        self.verbose = verbose
    
    def _strip_quotes(self, value: str) -> str:
        """
        Strip surrounding quotes from a string if present.
        Gmail uses quotes for exact phrase matching, but we don't need them in YAML.
        
        Args:
            value: String that may have surrounding quotes
            
        Returns:
            String with quotes removed if they were surrounding the entire value
        """
        if len(value) >= 2:
            # Check for matching quotes at start and end
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
        return value
        
    def infer_operators(self, filter_dict: Dict) -> Dict:
        """
        Infer operators from Gmail search patterns in a filter.
        
        Args:
            filter_dict: Filter dictionary to process
            
        Returns:
            Modified filter with inferred operators
        """
        # Fields that can contain search patterns
        search_fields = ['from', 'to', 'subject', 'has', 'does_not_have']
        
        modified = filter_dict.copy()
        
        for field in search_fields:
            if field in modified:
                value = modified[field]
                
                # Process string values
                if isinstance(value, str):
                    result = self._process_search_string(value, field)
                    if result != value:  # Something was inferred
                        modified[field] = result
                        if self.verbose:
                            print(f"  Inferred operators in {field}: {value} -> {result}")
                
                # Process list values (already partially processed)
                elif isinstance(value, list):
                    new_list = []
                    changed = False
                    for item in value:
                        if isinstance(item, str):
                            result = self._process_search_string(item, field)
                            new_list.append(result)
                            if result != item:
                                changed = True
                        else:
                            new_list.append(item)
                    
                    if changed:
                        modified[field] = new_list
                        if self.verbose:
                            print(f"  Inferred operators in {field} list")
        
        return modified
    
    def _process_search_string(self, value: str, field: str) -> Union[str, Dict]:
        """
        Process a search string to detect and convert operators.
        
        Args:
            value: The search string to process
            field: The field name (for context)
            
        Returns:
            Original string or operator structure
        """
        # Try to detect patterns in order of precedence
        # Complex patterns should be checked first to avoid partial matches
        
        # 1. Check for complex parenthetical expressions FIRST
        # This catches patterns like "-(error OR warning)" before the simpler patterns
        complex_result = self._detect_complex_pattern(value)
        if complex_result:
            return complex_result
        
        # 2. Check for NOT pattern (-term)
        not_result = self._detect_not_pattern(value)
        if not_result:
            return not_result
        
        # 3. Check for OR pattern (term1 OR term2)
        or_result = self._detect_or_pattern(value)
        if or_result:
            return or_result
        
        # 4. Check for AND pattern (term1 AND term2)
        and_result = self._detect_and_pattern(value)
        if and_result:
            return and_result
        
        # No patterns detected, strip quotes and return
        return self._strip_quotes(value)
    
    def _detect_or_pattern(self, value: str) -> Optional[Dict]:
        """
        Detect and convert OR patterns.
        
        Gmail uses 'OR' (case-sensitive) or '|' for OR operations.
        Also handles curly braces {term1 term2} as OR.
        
        Args:
            value: Search string to check
            
        Returns:
            'any' operator structure or None
        """
        # Check if the entire expression is wrapped in parentheses
        # e.g., "(term1 OR term2 OR term3)"
        stripped_value = value
        if value.startswith('(') and value.endswith(')'):
            # Check if these are matching outer parentheses (not part of terms)
            # by ensuring balanced parentheses when we remove them
            inner = value[1:-1]
            if ' OR ' in inner:
                # Use the inner content for OR processing
                stripped_value = inner
        
        # Pattern 1: Explicit OR
        # Examples: "alice OR bob", "alice@example.com OR bob@example.com"
        or_pattern = r'^(.+?)\s+OR\s+(.+)$'
        match = re.match(or_pattern, stripped_value)
        if match:
            terms = [match.group(1).strip(), match.group(2).strip()]
            # Check for additional ORs
            while ' OR ' in terms[-1]:
                parts = terms[-1].split(' OR ', 1)
                terms[-1] = parts[0].strip()
                terms.append(parts[1].strip())
            
            # Strip quotes from each term
            terms = [self._strip_quotes(t) for t in terms]
            
            # Process each term recursively
            processed_terms = [self._process_search_string(t, '') for t in terms]
            return {'any': processed_terms}
        
        # Pattern 2: Curly braces (Gmail's OR shorthand)
        # Example: "{alice bob charlie}"
        # Use original value, not stripped_value for other patterns
        curly_pattern = r'^\{([^}]+)\}$'
        match = re.match(curly_pattern, value)
        if match:
            # Split by whitespace, handling quoted strings
            content = match.group(1)
            terms = self._split_terms(content)
            if len(terms) > 1:
                return {'any': terms}
        
        # Pattern 3: Pipe separator
        # Example: "alice|bob|charlie"
        if '|' in value and not value.startswith('|') and not value.endswith('|'):
            terms = [t.strip() for t in value.split('|') if t.strip()]
            if len(terms) > 1:
                return {'any': terms}
        
        return None
    
    def _detect_and_pattern(self, value: str) -> Optional[Dict]:
        """
        Detect and convert AND patterns.
        
        Gmail uses 'AND' (case-sensitive) or implicit space for AND.
        
        Args:
            value: Search string to check
            
        Returns:
            'all' operator structure or None
        """
        # Check if the entire expression is wrapped in parentheses
        # e.g., "(term1 AND term2 AND term3)"
        stripped_value = value
        if value.startswith('(') and value.endswith(')'):
            # Check if these are matching outer parentheses (not part of terms)
            inner = value[1:-1]
            if ' AND ' in inner:
                # Use the inner content for AND processing
                stripped_value = inner
        
        # Pattern 1: Explicit AND
        # Example: "alice AND bob"
        and_pattern = r'^(.+?)\s+AND\s+(.+)$'
        match = re.match(and_pattern, stripped_value)
        if match:
            terms = [match.group(1).strip(), match.group(2).strip()]
            # Check for additional ANDs
            while ' AND ' in terms[-1]:
                parts = terms[-1].split(' AND ', 1)
                terms[-1] = parts[0].strip()
                terms.append(parts[1].strip())
            
            # Strip quotes from each term
            terms = [self._strip_quotes(t) for t in terms]
            
            # Process each term recursively
            processed_terms = [self._process_search_string(t, '') for t in terms]
            return {'all': processed_terms}
        
        # Pattern 2: Parentheses with implicit AND
        # Example: "(term1 term2 term3)" - all must match
        # Use original value, not stripped_value for this pattern
        paren_pattern = r'^\(([^)]+)\)$'
        match = re.match(paren_pattern, value)
        if match:
            content = match.group(1)
            # Only convert if there are multiple terms without OR
            if ' OR ' not in content and '{' not in content:
                terms = self._split_terms(content)
                if len(terms) > 1:
                    return {'all': terms}
        
        return None
    
    def _detect_not_pattern(self, value: str) -> Optional[Dict]:
        """
        Detect and convert NOT patterns.
        
        Gmail uses '-' prefix for NOT operations.
        
        Args:
            value: Search string to check
            
        Returns:
            'not' operator structure or None
        """
        # Pattern: Leading minus
        # Examples: "-alice", "-newsletter", "-{spam promotions}", '-"exact phrase"'
        if value.startswith('-') and len(value) > 1:
            negated_term = value[1:].strip()
            
            # Strip quotes from the negated term if it's not going to be further processed
            # Check if it's a simple negation (no operators)
            if not (' OR ' in negated_term or ' AND ' in negated_term or 
                    negated_term.startswith('{') or negated_term.startswith('(')):
                negated_term = self._strip_quotes(negated_term)
            
            # Process the negated term for nested operators
            processed = self._process_search_string(negated_term, '')
            
            return {'not': processed}
        
        return None
    
    def _detect_complex_pattern(self, value: str) -> Optional[Dict]:
        """
        Detect and convert complex nested patterns.
        
        Handles combinations like: "-(alice OR bob)" or "{term1 term2} AND term3"
        
        Args:
            value: Search string to check
            
        Returns:
            Nested operator structure or None
        """
        # Pattern 1: Negated parenthetical OR group
        # Example: "-(error OR warning OR failure)" -> not: {any: [error, warning, failure]}
        neg_paren_pattern = r'^-\((.+)\)$'
        match = re.match(neg_paren_pattern, value)
        if match:
            inner_content = match.group(1)
            # Check if it's an OR pattern
            if ' OR ' in inner_content:
                or_result = self._detect_or_pattern(inner_content)
                if or_result:
                    return {'not': or_result}
            # Otherwise just negate the content
            return {'not': inner_content}
        
        # Pattern 2: Negated curly braces
        # Example: "-{spam ads}" -> not: {any: [spam, ads]}
        neg_curly_pattern = r'^-\{([^}]+)\}$'
        match = re.match(neg_curly_pattern, value)
        if match:
            terms = self._split_terms(match.group(1))
            if len(terms) > 1:
                return {'not': {'any': terms}}
        
        # Pattern 3: Parenthetical OR followed by AND
        # Example: "(bug OR issue) AND fixed" -> all: [{any: [bug, issue]}, fixed]
        paren_or_and_pattern = r'^\((.+)\)\s+AND\s+(.+)$'
        match = re.match(paren_or_and_pattern, value)
        if match:
            paren_content = match.group(1)
            and_term = match.group(2).strip()
            
            # Process the parenthetical part
            if ' OR ' in paren_content:
                or_result = self._detect_or_pattern(paren_content)
                if or_result:
                    return {'all': [or_result, and_term]}
            
            # Just parentheses without OR, treat as single term
            return {'all': [paren_content, and_term]}
        
        return None
    
    def _split_terms(self, content: str) -> List[str]:
        """
        Split a string into terms, respecting quoted strings.
        
        Args:
            content: String to split
            
        Returns:
            List of terms
        """
        terms = []
        current_term = ''
        in_quotes = False
        quote_char = None
        
        for char in content:
            if char in '"\'':
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current_term += char
            elif char == ' ' and not in_quotes:
                if current_term:
                    terms.append(current_term)
                    current_term = ''
            else:
                current_term += char
        
        if current_term:
            terms.append(current_term)
        
        return terms
    
    def explain_inference(self, original: str, result: Union[str, Dict]) -> str:
        """
        Explain what was inferred from a pattern.
        
        Args:
            original: Original string
            result: Inference result
            
        Returns:
            Human-readable explanation
        """
        if isinstance(result, str):
            return f"No operators inferred, kept as: {result}"
        
        if isinstance(result, dict):
            if 'any' in result:
                items = result['any']
                return f"OR pattern detected: Any of {items}"
            elif 'all' in result:
                items = result['all']
                return f"AND pattern detected: All of {items}"
            elif 'not' in result:
                negated = result['not']
                if isinstance(negated, dict):
                    nested = self.explain_inference('', negated)
                    return f"NOT pattern with nested: {nested}"
                else:
                    return f"NOT pattern: Exclude {negated}"
        
        return "Unknown pattern"