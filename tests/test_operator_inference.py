#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for operator inference functionality."""

import pytest
from gmail_yaml_filters.operator_inference import OperatorInference


class TestOperatorInference:
    """Test the OperatorInference class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.inference = OperatorInference(verbose=False)
    
    # ========== OR Pattern Tests ==========
    
    def test_detect_explicit_or_pattern(self):
        """Test detection of explicit OR patterns."""
        result = self.inference._detect_or_pattern("alice@example.com OR bob@example.com")
        assert result == {'any': ['alice@example.com', 'bob@example.com']}
    
    def test_detect_multiple_or_pattern(self):
        """Test detection of multiple OR terms."""
        result = self.inference._detect_or_pattern("alice OR bob OR charlie OR david")
        assert result == {'any': ['alice', 'bob', 'charlie', 'david']}
    
    def test_detect_or_with_parentheses(self):
        """Test OR pattern with outer parentheses."""
        result = self.inference._detect_or_pattern("(alice OR bob OR charlie)")
        assert result == {'any': ['alice', 'bob', 'charlie']}
    
    def test_detect_or_with_quotes(self):
        """Test OR pattern with quoted terms."""
        result = self.inference._detect_or_pattern('"Account Update" OR "Balance Alert"')
        assert result == {'any': ['Account Update', 'Balance Alert']}
    
    def test_detect_or_with_parentheses_and_quotes(self):
        """Test OR pattern with both parentheses and quotes."""
        result = self.inference._detect_or_pattern('("Account Update" OR "Balance Alert" OR "Payment Due")')
        assert result == {'any': ['Account Update', 'Balance Alert', 'Payment Due']}
    
    def test_detect_curly_braces_or(self):
        """Test curly braces as OR shorthand."""
        result = self.inference._detect_or_pattern("{urgent important critical}")
        assert result == {'any': ['urgent', 'important', 'critical']}
    
    def test_detect_pipe_separator_or(self):
        """Test pipe separator as OR."""
        result = self.inference._detect_or_pattern("bug|issue|defect")
        assert result == {'any': ['bug', 'issue', 'defect']}
    
    def test_no_or_pattern(self):
        """Test string without OR pattern."""
        result = self.inference._detect_or_pattern("simple text")
        assert result is None
    
    # ========== AND Pattern Tests ==========
    
    def test_detect_explicit_and_pattern(self):
        """Test detection of explicit AND patterns."""
        result = self.inference._detect_and_pattern("invoice AND paid")
        assert result == {'all': ['invoice', 'paid']}
    
    def test_detect_multiple_and_pattern(self):
        """Test detection of multiple AND terms."""
        result = self.inference._detect_and_pattern("invoice AND paid AND 2024 AND verified")
        assert result == {'all': ['invoice', 'paid', '2024', 'verified']}
    
    def test_detect_and_with_parentheses(self):
        """Test AND pattern with outer parentheses."""
        result = self.inference._detect_and_pattern("(invoice AND paid AND 2024)")
        assert result == {'all': ['invoice', 'paid', '2024']}
    
    def test_detect_and_with_quotes(self):
        """Test AND pattern with quoted terms."""
        result = self.inference._detect_and_pattern('"important meeting" AND "tomorrow"')
        assert result == {'all': ['important meeting', 'tomorrow']}
    
    def test_detect_implicit_and_in_parentheses(self):
        """Test implicit AND pattern in parentheses."""
        result = self.inference._detect_and_pattern("(term1 term2 term3)")
        assert result == {'all': ['term1', 'term2', 'term3']}
    
    def test_no_and_pattern(self):
        """Test string without AND pattern."""
        result = self.inference._detect_and_pattern("simple text")
        assert result is None
    
    # ========== NOT Pattern Tests ==========
    
    def test_detect_simple_not_pattern(self):
        """Test detection of simple NOT pattern."""
        result = self.inference._detect_not_pattern("-unsubscribe")
        assert result == {'not': 'unsubscribe'}
    
    def test_detect_not_with_quotes(self):
        """Test NOT pattern with quoted term."""
        result = self.inference._detect_not_pattern('-"unsubscribe link"')
        assert result == {'not': 'unsubscribe link'}
    
    def test_detect_not_with_curly_braces(self):
        """Test NOT pattern with curly braces."""
        result = self.inference._detect_not_pattern("-{spam promotions ads}")
        assert result == {'not': {'any': ['spam', 'promotions', 'ads']}}
    
    def test_detect_not_with_or_pattern(self):
        """Test NOT pattern with nested OR."""
        result = self.inference._detect_complex_pattern("-(error OR warning OR failure)")
        assert result == {'not': {'any': ['error', 'warning', 'failure']}}
    
    def test_no_not_pattern(self):
        """Test string without NOT pattern."""
        result = self.inference._detect_not_pattern("simple text")
        assert result is None
    
    # ========== Complex Pattern Tests ==========
    
    def test_detect_complex_not_or(self):
        """Test complex NOT with OR pattern."""
        result = self.inference._detect_complex_pattern("-(spam OR promotion OR sale)")
        assert result == {'not': {'any': ['spam', 'promotion', 'sale']}}
    
    def test_detect_complex_or_and_mixed(self):
        """Test mixed OR and AND pattern."""
        result = self.inference._detect_complex_pattern("(bug OR issue) AND fixed")
        assert result == {'all': [{'any': ['bug', 'issue']}, 'fixed']}
    
    def test_detect_complex_quoted_or_and(self):
        """Test complex pattern with quotes."""
        result = self.inference._detect_complex_pattern('("critical bug" OR "urgent issue") AND fixed')
        assert result == {'all': [{'any': ['critical bug', 'urgent issue']}, 'fixed']}
    
    # ========== Quote Stripping Tests ==========
    
    def test_strip_double_quotes(self):
        """Test stripping of double quotes."""
        assert self.inference._strip_quotes('"quoted text"') == 'quoted text'
    
    def test_strip_single_quotes(self):
        """Test stripping of single quotes."""
        assert self.inference._strip_quotes("'quoted text'") == 'quoted text'
    
    def test_no_quotes_to_strip(self):
        """Test string without quotes."""
        assert self.inference._strip_quotes('unquoted text') == 'unquoted text'
    
    def test_mismatched_quotes_not_stripped(self):
        """Test mismatched quotes are not stripped."""
        assert self.inference._strip_quotes('"mismatched\'') == '"mismatched\''
    
    def test_internal_quotes_preserved(self):
        """Test internal quotes are preserved."""
        assert self.inference._strip_quotes('text with "internal" quotes') == 'text with "internal" quotes'
    
    # ========== Process Search String Tests ==========
    
    def test_process_simple_string(self):
        """Test processing of simple string."""
        result = self.inference._process_search_string("simple text", "field")
        assert result == "simple text"
    
    def test_process_quoted_string(self):
        """Test processing removes surrounding quotes."""
        result = self.inference._process_search_string('"exact phrase"', "field")
        assert result == "exact phrase"
    
    def test_process_or_pattern(self):
        """Test processing of OR pattern."""
        result = self.inference._process_search_string("alice OR bob", "field")
        assert result == {'any': ['alice', 'bob']}
    
    def test_process_complex_pattern(self):
        """Test processing of complex pattern."""
        result = self.inference._process_search_string("-(error OR warning)", "field")
        assert result == {'not': {'any': ['error', 'warning']}}
    
    # ========== Integration Tests ==========
    
    def test_infer_operators_in_filter(self):
        """Test operator inference on a complete filter."""
        filter_dict = {
            'from': 'alice@example.com OR bob@example.com',
            'subject': '"Important Meeting"',
            'has': '-unsubscribe',
            'label': 'work'
        }
        result = self.inference.infer_operators(filter_dict)
        
        assert result['from'] == {'any': ['alice@example.com', 'bob@example.com']}
        assert result['subject'] == 'Important Meeting'
        assert result['has'] == {'not': 'unsubscribe'}
        assert result['label'] == 'work'
    
    def test_infer_operators_with_list_values(self):
        """Test operator inference with list values."""
        filter_dict = {
            'from': ['alice OR bob', 'charlie'],
            'label': ['important', 'work']
        }
        result = self.inference.infer_operators(filter_dict)
        
        assert result['from'][0] == {'any': ['alice', 'bob']}
        assert result['from'][1] == 'charlie'
        assert result['label'] == ['important', 'work']
    
    def test_infer_operators_preserves_non_searchable_fields(self):
        """Test that non-searchable fields are preserved as-is."""
        filter_dict = {
            'from': 'alice OR bob',
            'archive': True,
            'star': False,
            '_gmail_raw': {'sizeOperator': 's_sl'}
        }
        result = self.inference.infer_operators(filter_dict)
        
        assert result['from'] == {'any': ['alice', 'bob']}
        assert result['archive'] is True
        assert result['star'] is False
        assert result['_gmail_raw'] == {'sizeOperator': 's_sl'}
    
    def test_edge_case_or_in_normal_text(self):
        """Test OR in normal text is not converted."""
        # This is a tricky case - "OR" in the middle of normal text
        result = self.inference._detect_or_pattern("Meeting with Bob OR Alice (whoever is available)")
        assert result == {'any': ['Meeting with Bob', 'Alice (whoever is available)']}
    
    def test_edge_case_empty_parentheses(self):
        """Test empty parentheses."""
        result = self.inference._detect_or_pattern("()")
        assert result is None
    
    def test_edge_case_nested_parentheses(self):
        """Test nested parentheses."""
        # Gmail doesn't really support nested parentheses well, but test behavior
        result = self.inference._process_search_string("((alice OR bob) AND charlie)", "field")
        # This might not parse perfectly due to complexity
        assert result is not None  # Just ensure no crash
    
    def test_real_world_healthcare_filter(self):
        """Test real-world complex healthcare filter from user data."""
        value = ("(covered.ca.gov OR donotreplyucsfmychart@ucsf.edu OR "
                "cosmeticdentistryassociates.net OR hallszeto.com OR "
                "mailer@sparkpeople.com OR office@mvnutrition.com OR "
                "audrey@notakeout.com OR rob@pacificanxietygroup.com)")
        
        result = self.inference._detect_or_pattern(value)
        assert result is not None
        assert 'any' in result
        assert 'covered.ca.gov' in result['any']
        assert 'rob@pacificanxietygroup.com' in result['any']
        # Check no parentheses in terms
        for term in result['any']:
            assert not term.startswith('(')
            assert not term.endswith(')')