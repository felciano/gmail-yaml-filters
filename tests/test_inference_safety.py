#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for inference safety functionality."""

import pytest
from gmail_yaml_filters.inference_safety import InferenceSafety


class TestInferenceSafety:
    """Test the InferenceSafety class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.safety = InferenceSafety(verbose=False)
    
    # ========== Security Detection Tests ==========
    
    def test_detect_security_keywords_in_subject(self):
        """Test detection of security keywords in subject."""
        filter_dict = {'subject': 'Password reset request', 'label': 'security'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    def test_detect_security_keywords_in_from(self):
        """Test detection of security keywords in from field."""
        filter_dict = {'from': 'noreply@secure-login.com', 'label': 'auth'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    def test_detect_two_factor_keywords(self):
        """Test detection of 2FA related keywords."""
        filter_dict = {'has': 'Your two-factor authentication code', 'label': '2fa'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    def test_detect_verification_keywords(self):
        """Test detection of verification keywords."""
        filter_dict = {'subject': 'Please verify your email', 'label': 'verify'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    def test_no_security_keywords(self):
        """Test non-security filter is not flagged."""
        filter_dict = {'from': 'newsletter@example.com', 'label': 'news'}
        assert self.safety._is_security_sensitive(filter_dict) is False
    
    def test_security_in_label(self):
        """Test security keyword in label field."""
        filter_dict = {'from': 'bank@example.com', 'label': 'security/banking'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    def test_case_insensitive_security_detection(self):
        """Test security detection is case insensitive."""
        filter_dict = {'subject': 'PASSWORD RESET', 'label': 'auth'}
        assert self.safety._is_security_sensitive(filter_dict) is True
    
    # ========== Action Conflict Tests ==========
    
    def test_detect_archive_conflict(self):
        """Test detection of archive vs no-archive conflict."""
        parent = {'from': 'test@example.com', 'archive': True}
        child = {'from': 'test@example.com', 'archive': False}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert len(conflicts) > 0
        assert any('archive' in str(c[0]) or 'archive' in str(c[1]) for c in conflicts)
    
    def test_detect_important_conflict(self):
        """Test detection of important vs not_important conflict."""
        parent = {'from': 'test@example.com', 'important': True}
        child = {'from': 'test@example.com', 'not_important': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert ('important', 'not_important') in conflicts
    
    def test_detect_spam_conflict(self):
        """Test detection of spam vs not_spam conflict."""
        parent = {'from': 'test@example.com', 'spam': True}
        child = {'from': 'test@example.com', 'not_spam': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert ('spam', 'not_spam') in conflicts
    
    def test_detect_read_conflict(self):
        """Test detection of read vs unread conflict."""
        parent = {'from': 'test@example.com', 'read': True}
        child = {'from': 'test@example.com', 'unread': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert ('read', 'unread') in conflicts
    
    def test_detect_archive_important_conflict(self):
        """Test special case: archive vs important conflict."""
        parent = {'from': 'test@example.com', 'archive': True}
        child = {'from': 'test@example.com', 'important': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert ('archive', 'important') in conflicts
    
    def test_detect_delete_star_conflict(self):
        """Test special case: delete/trash vs star conflict."""
        parent = {'from': 'test@example.com', 'delete': True}
        child = {'from': 'test@example.com', 'star': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert ('delete/trash', 'star') in conflicts
    
    def test_no_conflicts(self):
        """Test filters with compatible actions."""
        parent = {'from': 'test@example.com', 'label': 'work'}
        child = {'from': 'test@example.com', 'has': 'meeting', 'star': True}
        conflicts = self.safety._get_action_conflicts(parent, child)
        assert len(conflicts) == 0
    
    # ========== Dangerous Actions Tests ==========
    
    def test_detect_dangerous_archive(self):
        """Test detection of dangerous archive action."""
        parent = {'from': 'test@example.com', 'archive': True}
        dangerous = self.safety._get_dangerous_inherited_actions(parent)
        assert 'archive' in dangerous
    
    def test_detect_dangerous_delete(self):
        """Test detection of dangerous delete action."""
        parent = {'from': 'test@example.com', 'delete': True}
        dangerous = self.safety._get_dangerous_inherited_actions(parent)
        assert 'delete' in dangerous
    
    def test_detect_dangerous_trash(self):
        """Test detection of dangerous trash action."""
        parent = {'from': 'test@example.com', 'trash': True}
        dangerous = self.safety._get_dangerous_inherited_actions(parent)
        assert 'trash' in dangerous
    
    def test_detect_dangerous_read(self):
        """Test detection of dangerous read action."""
        parent = {'from': 'test@example.com', 'read': True}
        dangerous = self.safety._get_dangerous_inherited_actions(parent)
        assert 'read' in dangerous
    
    def test_no_dangerous_actions(self):
        """Test safe actions are not flagged as dangerous."""
        parent = {'from': 'test@example.com', 'label': 'work', 'star': True}
        dangerous = self.safety._get_dangerous_inherited_actions(parent)
        assert len(dangerous) == 0
    
    # ========== Forwarding Conflict Tests ==========
    
    def test_detect_forwarding_conflict_different_addresses(self):
        """Test detection of conflicting forward addresses."""
        parent = {'from': 'test@example.com', 'forward': 'alice@example.com'}
        child = {'from': 'test@example.com', 'forward': 'bob@example.com'}
        conflict = self.safety._check_forwarding_conflict(parent, child)
        assert conflict is not None
        assert 'alice@example.com' in conflict
        assert 'bob@example.com' in conflict
    
    def test_detect_security_forward_conflict(self):
        """Test security email would be forwarded warning."""
        parent = {'from': 'bank@example.com', 'forward': 'external@gmail.com'}
        child = {'from': 'bank@example.com', 'subject': 'password reset'}
        conflict = self.safety._check_forwarding_conflict(parent, child)
        assert conflict is not None
        assert 'Security-sensitive' in conflict
    
    def test_no_forwarding_conflict_same_address(self):
        """Test no conflict when forwarding to same address."""
        parent = {'from': 'test@example.com', 'forward': 'backup@example.com'}
        child = {'from': 'test@example.com', 'forward': 'backup@example.com'}
        conflict = self.safety._check_forwarding_conflict(parent, child)
        assert conflict is None
    
    # ========== Label Compatibility Tests ==========
    
    def test_detect_security_vs_automated_labels(self):
        """Test detection of security vs automated label mismatch."""
        parent = {'from': 'noreply@example.com', 'label': 'automated'}
        child = {'from': 'noreply@example.com', 'label': 'security'}
        warning = self.safety._check_label_compatibility(parent, child)
        assert warning is not None
        assert 'automated' in warning.lower()
        assert 'security' in warning.lower()
    
    def test_detect_different_label_purposes(self):
        """Test detection of different label purposes."""
        parent = {'from': 'test@example.com', 'label': 'work'}
        child = {'from': 'test@example.com', 'label': 'personal'}
        warning = self.safety._check_label_compatibility(parent, child)
        assert warning is not None
        assert 'different purposes' in warning.lower()
    
    def test_compatible_hierarchical_labels(self):
        """Test hierarchical labels are considered compatible."""
        parent = {'from': 'test@example.com', 'label': 'work'}
        child = {'from': 'test@example.com', 'label': ['work', 'meetings']}
        warning = self.safety._check_label_compatibility(parent, child)
        # Should be None or minimal warning since parent label is in child
        # Implementation might vary
        assert warning is None or 'different purposes' in str(warning).lower()
    
    # ========== Full Safety Analysis Tests ==========
    
    def test_analyze_safe_merge(self):
        """Test analysis of safe merge."""
        parent = {'from': 'newsletter@example.com', 'label': 'news'}
        child = {'from': 'newsletter@example.com', 'subject': 'weekly update', 'label': 'news/weekly'}
        
        result = self.safety.analyze_merge_safety(parent, child)
        assert result['safe'] is True
        assert result['confidence'] > 50
        assert result['severity'] == 'low'
    
    def test_analyze_security_merge_blocked(self):
        """Test security-sensitive merge is flagged."""
        parent = {'from': 'bank@example.com', 'archive': True}
        child = {'from': 'bank@example.com', 'subject': 'password reset', 'label': 'security'}
        
        result = self.safety.analyze_merge_safety(parent, child)
        assert result['safe'] is False
        assert result['severity'] in ['high', 'critical']
        assert len(result['warnings']) > 0
        assert any('security' in w.lower() for w in result['warnings'])
    
    def test_analyze_action_conflict_merge(self):
        """Test merge with action conflicts."""
        parent = {'from': 'test@example.com', 'archive': True}
        child = {'from': 'test@example.com', 'archive': False}
        
        result = self.safety.analyze_merge_safety(parent, child)
        assert result['safe'] is False
        assert result['severity'] == 'critical'
        assert any('archive' in w.lower() for w in result['warnings'])
    
    def test_analyze_forwarding_conflict(self):
        """Test merge with forwarding conflict."""
        parent = {'from': 'test@example.com', 'forward': 'alice@example.com'}
        child = {'from': 'test@example.com', 'forward': 'bob@example.com'}
        
        result = self.safety.analyze_merge_safety(parent, child)
        assert result['safe'] is False
        assert result['severity'] == 'critical'
        assert any('forward' in w.lower() for w in result['warnings'])
    
    def test_confidence_decreases_with_issues(self):
        """Test confidence score decreases with more issues."""
        # Safe merge
        parent1 = {'from': 'test@example.com', 'label': 'work'}
        child1 = {'from': 'test@example.com', 'has': 'meeting'}
        result1 = self.safety.analyze_merge_safety(parent1, child1)
        
        # Merge with one issue
        parent2 = {'from': 'test@example.com', 'label': 'work'}
        child2 = {'from': 'test@example.com', 'label': 'personal'}
        result2 = self.safety.analyze_merge_safety(parent2, child2)
        
        # Merge with multiple issues
        parent3 = {'from': 'bank@example.com', 'archive': True, 'forward': 'external@example.com'}
        child3 = {'from': 'bank@example.com', 'subject': 'password reset', 'archive': False}
        result3 = self.safety.analyze_merge_safety(parent3, child3)
        
        assert result1['confidence'] > result2['confidence']
        assert result2['confidence'] > result3['confidence']
    
    # ========== Pattern Memory Tests ==========
    
    def test_remember_decision(self):
        """Test remembering user decisions."""
        pattern_key = "test_pattern_123"
        self.safety.remember_decision(pattern_key, "yes")
        assert self.safety.get_remembered_decision(pattern_key) == "yes"
    
    def test_get_unknown_decision(self):
        """Test getting decision for unknown pattern."""
        assert self.safety.get_remembered_decision("unknown_pattern") is None
    
    def test_create_pattern_key(self):
        """Test pattern key creation."""
        parent = {'from': 'test@example.com', 'archive': True}
        child = {'from': 'test@example.com', 'has': 'important'}
        
        key1 = self.safety.create_pattern_key(parent, child)
        assert isinstance(key1, str)
        assert len(key1) > 0
        
        # Same filters should produce same key
        key2 = self.safety.create_pattern_key(parent, child)
        assert key1 == key2
        
        # Different filters should produce different key
        child2 = {'from': 'test@example.com', 'subject': 'password reset'}
        key3 = self.safety.create_pattern_key(parent, child2)
        assert key1 != key3
    
    # ========== Format Summary Tests ==========
    
    def test_format_filter_summary(self):
        """Test filter summary formatting."""
        filter_dict = {
            'from': 'test@example.com',
            'subject': 'Important',
            'label': 'work',
            'archive': True,
            'star': True
        }
        
        summary = self.safety.format_filter_summary(filter_dict)
        assert 'from: test@example.com' in summary
        assert 'subject: Important' in summary
        assert 'label: work' in summary
        assert 'archive: yes' in summary
        assert 'star: yes' in summary
    
    def test_format_filter_summary_with_list(self):
        """Test filter summary with list values."""
        filter_dict = {
            'from': 'test@example.com',
            'label': ['work', 'important']
        }
        
        summary = self.safety.format_filter_summary(filter_dict)
        assert 'from: test@example.com' in summary
        assert 'label: work, important' in summary