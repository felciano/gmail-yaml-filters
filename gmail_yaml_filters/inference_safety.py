#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Safety rules and analysis for Gmail filter inference.

Provides detection of security-sensitive filters and action conflicts
to prevent inappropriate merging of filters during inference.
"""
from typing import Dict, List, Tuple, Optional, Any


class InferenceSafety:
    """Safety rules and analysis for filter inference."""
    
    # Security-related keywords that suggest a filter shouldn't be merged
    SECURITY_KEYWORDS = [
        'password', 'reset', 'verification', 'verify', 'verified',
        '2fa', 'two-factor', 'two factor', 'otp', 'one-time',
        'code', 'token', 'security', 'secure', 'confirm', 'confirmation',
        'activate', 'activation', 'recover', 'recovery', 'authenticate',
        'authorization', 'account', 'signin', 'sign-in', 'login', 'log-in'
    ]
    
    # Action pairs that conflict with each other
    CONFLICTING_ACTION_PAIRS = [
        ('archive', 'not_archive'),
        ('important', 'not_important'),
        ('mark_as_important', 'never_mark_as_important'),
        ('spam', 'not_spam'),
        ('read', 'unread'),
        ('star', 'unstar'),
    ]
    
    # Actions that shouldn't be inherited for security reasons
    DANGEROUS_TO_INHERIT = [
        'archive',  # Security emails should stay in inbox
        'delete',   # Never auto-delete security emails
        'trash',    # Never auto-trash security emails
        'read',     # Security emails should be noticed
    ]
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the safety analyzer.
        
        Args:
            verbose: Whether to print detailed analysis
        """
        self.verbose = verbose
        self.decision_memory = {}  # Remember user decisions for similar patterns
    
    def analyze_merge_safety(self, parent: Dict, child: Dict) -> Dict:
        """
        Analyze the safety of merging two filters.
        
        Args:
            parent: Parent filter dict
            child: Child filter dict that would inherit from parent
            
        Returns:
            Dictionary with safety analysis:
                - safe: Boolean indicating if merge is safe
                - confidence: Confidence score (0-100)
                - warnings: List of warning messages
                - severity: 'low', 'medium', 'high', 'critical'
        """
        warnings = []
        confidence = 100
        severity = 'low'
        
        # Check if child is security-sensitive
        if self._is_security_sensitive(child):
            warnings.append("⚠️  Security-sensitive: Contains security-related keywords")
            confidence -= 40
            severity = 'high'
            
            # Check if parent has dangerous actions for security emails
            dangerous_inherited = self._get_dangerous_inherited_actions(parent)
            if dangerous_inherited:
                warnings.append(f"⛔ Would inherit dangerous actions for security email: {', '.join(dangerous_inherited)}")
                confidence -= 30
                severity = 'critical'
        
        # Check for action conflicts
        conflicts = self._get_action_conflicts(parent, child)
        if conflicts:
            conflict_strs = []
            has_archive_conflict = False
            
            for p, c in conflicts:
                # Check if this is an archive-related conflict
                if 'archive' in p.lower() or 'archive' in c.lower():
                    has_archive_conflict = True
                    conflict_strs.append(f"**{p} vs {c}**")  # Emphasize archive conflicts
                else:
                    conflict_strs.append(f"{p} vs {c}")
            
            warnings.append(f"⚠️  Action conflicts: {', '.join(conflict_strs)}")
            
            # Archive conflicts are more serious
            if has_archive_conflict:
                warnings.append("⛔ CRITICAL: Different archive states - messages would end up in different places!")
                confidence -= 40  # Larger penalty for archive conflicts
                severity = 'critical'  # Archive conflicts are always critical
            else:
                confidence -= 20 * len(conflicts)
                if severity == 'low':
                    severity = 'medium'
        
        # Check forwarding conflicts
        forward_conflict = self._check_forwarding_conflict(parent, child)
        if forward_conflict:
            warnings.append(f"⚠️  Forwarding conflict: {forward_conflict}")
            confidence -= 50
            severity = 'critical'
        
        # Check label compatibility
        label_warning = self._check_label_compatibility(parent, child)
        if label_warning:
            warnings.append(f"ℹ️  Label mismatch: {label_warning}")
            confidence -= 10
        
        # Determine overall safety
        safe = confidence > 50 and severity != 'critical'
        
        return {
            'safe': safe,
            'confidence': max(0, confidence),
            'warnings': warnings,
            'severity': severity
        }
    
    def _is_security_sensitive(self, filter_dict: Dict) -> bool:
        """
        Check if a filter contains security-sensitive content.
        
        Args:
            filter_dict: Filter dictionary to check
            
        Returns:
            True if filter appears security-related
        """
        # Fields to check for security keywords
        text_fields = ['subject', 'has', 'from', 'to', 'label']
        
        for field in text_fields:
            if field in filter_dict:
                value = filter_dict[field]
                # Handle both string and list values
                values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
                
                for val in values:
                    val_lower = str(val).lower()
                    for keyword in self.SECURITY_KEYWORDS:
                        if keyword in val_lower:
                            if self.verbose:
                                print(f"  Security keyword '{keyword}' found in {field}: {val}")
                            return True
        
        return False
    
    def _get_action_conflicts(self, parent: Dict, child: Dict) -> List[Tuple[str, str]]:
        """
        Find conflicting actions between parent and child.
        
        Args:
            parent: Parent filter dict
            child: Child filter dict
            
        Returns:
            List of tuples (parent_action, child_action) that conflict
        """
        conflicts = []
        
        for action1, action2 in self.CONFLICTING_ACTION_PAIRS:
            # Check both directions
            if action1 in parent and action2 in child:
                if parent[action1] and child[action2]:  # Both are true/set
                    conflicts.append((action1, action2))
            elif action2 in parent and action1 in child:
                if parent[action2] and child[action1]:
                    conflicts.append((action2, action1))
        
        # Special case: archive in parent but important in child
        if parent.get('archive') and child.get('important'):
            conflicts.append(('archive', 'important'))
        
        # Special case: delete/trash in parent but star in child
        if (parent.get('delete') or parent.get('trash')) and child.get('star'):
            conflicts.append(('delete/trash', 'star'))
        
        # Special case: Different archive states
        # This is critical because it fundamentally changes where messages end up
        parent_archives = parent.get('archive', False)
        child_archives = child.get('archive', False)
        
        # Check if they have explicitly different archive behaviors
        # (one archives, one doesn't, and it's not just a missing value)
        if 'archive' in parent and 'archive' in child:
            if parent_archives != child_archives:
                if parent_archives:
                    conflicts.append(('archive=true', 'archive=false'))
                else:
                    conflicts.append(('archive=false', 'archive=true'))
        elif parent_archives and 'archive' not in child:
            # Parent archives but child doesn't specify - child might be intended to stay in inbox
            # This is a warning-level conflict, not critical
            conflicts.append(('archive', 'no-archive-specified'))
        elif not parent_archives and child.get('archive'):
            # Parent doesn't archive but child does - conflicting intent
            conflicts.append(('no-archive', 'archive'))
        
        return conflicts
    
    def _get_dangerous_inherited_actions(self, parent: Dict) -> List[str]:
        """
        Get list of dangerous actions that parent has which shouldn't be inherited.
        
        Args:
            parent: Parent filter dict
            
        Returns:
            List of dangerous actions present in parent
        """
        dangerous = []
        for action in self.DANGEROUS_TO_INHERIT:
            if parent.get(action):
                dangerous.append(action)
        return dangerous
    
    def _check_forwarding_conflict(self, parent: Dict, child: Dict) -> Optional[str]:
        """
        Check if parent and child have conflicting forwarding.
        
        Args:
            parent: Parent filter dict
            child: Child filter dict
            
        Returns:
            Warning message if conflict found, None otherwise
        """
        parent_forward = parent.get('forward')
        child_forward = child.get('forward')
        
        if parent_forward and child_forward:
            if parent_forward != child_forward:
                return f"Parent forwards to {parent_forward}, child to {child_forward}"
        elif parent_forward and not child_forward:
            # Child would inherit forwarding - might not be intended
            if self._is_security_sensitive(child):
                return f"Security-sensitive email would be forwarded to {parent_forward}"
        
        return None
    
    def _check_label_compatibility(self, parent: Dict, child: Dict) -> Optional[str]:
        """
        Check if parent and child labels suggest they shouldn't be merged.
        
        Args:
            parent: Parent filter dict
            child: Child filter dict
            
        Returns:
            Warning message if labels suggest different purposes
        """
        parent_label = parent.get('label', '')
        child_label = child.get('label', '')
        
        if not parent_label or not child_label:
            return None
        
        # Normalize to lists for comparison
        parent_labels = [parent_label] if isinstance(parent_label, str) else parent_label
        child_labels = [child_label] if isinstance(child_label, str) else child_label
        
        # Check for semantic differences
        security_labels = ['security', 'auth', 'verification', 'important', 'urgent']
        automated_labels = ['automated', 'notification', 'no-reply', 'newsletter', 'marketing']
        
        parent_is_security = any(any(sec in str(label).lower() for sec in security_labels) 
                                 for label in parent_labels)
        child_is_security = any(any(sec in str(label).lower() for sec in security_labels) 
                               for label in child_labels)
        
        parent_is_automated = any(any(auto in str(label).lower() for auto in automated_labels) 
                                  for label in parent_labels)
        child_is_automated = any(any(auto in str(label).lower() for auto in automated_labels) 
                                 for label in child_labels)
        
        if parent_is_automated and child_is_security:
            return "Parent appears automated, child appears security-related"
        elif parent_is_security and child_is_automated:
            return "Parent appears security-related, child appears automated"
        elif parent_label != child_label and not any(p in child_labels for p in parent_labels):
            # Different labels with no overlap
            return f"Different labels suggest different purposes"
        
        return None
    
    def format_filter_summary(self, filter_dict: Dict, indent: str = "") -> str:
        """
        Format a filter dict for display.
        
        Args:
            filter_dict: Filter to format
            indent: Indentation prefix
            
        Returns:
            Formatted string representation
        """
        lines = []
        
        # Show conditions first
        condition_keys = ['from', 'to', 'subject', 'has', 'does_not_have', 'list']
        for key in condition_keys:
            if key in filter_dict:
                value = filter_dict[key]
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                lines.append(f"{indent}{key}: {value}")
        
        # Show actions
        action_keys = ['label', 'archive', 'delete', 'star', 'important', 'not_important', 
                      'forward', 'read', 'trash']
        for key in action_keys:
            if key in filter_dict and filter_dict[key]:
                value = filter_dict[key]
                if isinstance(value, bool):
                    lines.append(f"{indent}{key}: yes")
                elif isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                    lines.append(f"{indent}{key}: {value}")
                else:
                    lines.append(f"{indent}{key}: {value}")
        
        return '\n'.join(lines)
    
    def remember_decision(self, pattern_key: str, decision: str):
        """
        Remember a user's decision for a pattern.
        
        Args:
            pattern_key: Key identifying the pattern
            decision: User's decision ('yes', 'no', etc.)
        """
        self.decision_memory[pattern_key] = decision
    
    def get_remembered_decision(self, pattern_key: str) -> Optional[str]:
        """
        Get a remembered decision for a pattern.
        
        Args:
            pattern_key: Key identifying the pattern
            
        Returns:
            Remembered decision or None
        """
        return self.decision_memory.get(pattern_key)
    
    def create_pattern_key(self, parent: Dict, child: Dict) -> str:
        """
        Create a key for remembering decisions about similar patterns.
        
        Args:
            parent: Parent filter
            child: Child filter
            
        Returns:
            Pattern key string
        """
        # Create a key based on the presence of certain conditions/actions
        parent_keys = set(parent.keys())
        child_keys = set(child.keys())
        
        # Include security sensitivity in the key
        is_security = 'sec' if self._is_security_sensitive(child) else 'nosec'
        
        # Include presence of key actions
        has_conflicts = 'conflict' if self._get_action_conflicts(parent, child) else 'noconflict'
        
        return f"{sorted(parent_keys)}_{sorted(child_keys)}_{is_security}_{has_conflicts}"