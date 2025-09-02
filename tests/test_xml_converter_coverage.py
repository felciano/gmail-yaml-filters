#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Additional tests to improve xml_converter.py coverage."""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml
from lxml import etree

from gmail_yaml_filters.xml_converter import GmailFilterConverter


class TestXMLConverterCoverage:
    """Additional tests for XML converter to improve coverage."""
    
    def test_xml_to_yaml_with_file_output(self):
        """Test XML to YAML conversion with file output."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='test@example.com'/>
        <apps:property name='label' value='Test'/>
        <apps:property name='shouldArchive' value='true'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as xml_file:
            xml_file.write(xml_content)
            xml_path = xml_file.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as yaml_file:
            yaml_path = yaml_file.name
        
        try:
            converter = GmailFilterConverter()
            converter.xml_to_yaml(xml_path, yaml_path)
            
            # Verify the YAML file was created
            with open(yaml_path) as f:
                filters = yaml.safe_load(f)
            
            assert len(filters) == 1
            assert filters[0]['from'] == 'test@example.com'
            assert filters[0]['label'] == 'Test'
            assert filters[0]['archive'] is True
        finally:
            os.unlink(xml_path)
            if os.path.exists(yaml_path):
                os.unlink(yaml_path)
    
    def test_convert_with_size_properties(self):
        """Test conversion of size-related properties."""
        converter = GmailFilterConverter(preserve_raw=True)
        
        # Create an XML entry with size properties
        ns_map = {
            None: 'http://www.w3.org/2005/Atom',
            'apps': 'http://schemas.google.com/apps/2006'
        }
        
        entry = etree.Element('entry', nsmap=ns_map)
        category = etree.SubElement(entry, 'category')
        category.set('term', 'filter')
        
        # Add size properties
        props = [
            ('from', 'test@example.com'),
            ('size', '5'),
            ('sizeOperator', 's_sl'),
            ('sizeUnit', 's_smb'),
            ('label', 'Large')
        ]
        
        for name, value in props:
            prop = etree.SubElement(entry, '{http://schemas.google.com/apps/2006}property')
            prop.set('name', name)
            prop.set('value', value)
        
        filter_dict = converter._convert_xml_entry(entry, {'apps': 'http://schemas.google.com/apps/2006'}, 0)
        
        assert filter_dict['from'] == 'test@example.com'
        assert filter_dict['label'] == 'Large'
        assert '_gmail_raw' in filter_dict
        assert filter_dict['_gmail_raw']['size'] == '5'
    
    def test_convert_with_forward_property(self):
        """Test conversion with forward property."""
        converter = GmailFilterConverter()
        
        ns_map = {
            None: 'http://www.w3.org/2005/Atom',
            'apps': 'http://schemas.google.com/apps/2006'
        }
        
        entry = etree.Element('entry', nsmap=ns_map)
        category = etree.SubElement(entry, 'category')
        category.set('term', 'filter')
        
        props = [
            ('from', 'test@example.com'),
            ('forwardTo', 'backup@example.com')
        ]
        
        for name, value in props:
            prop = etree.SubElement(entry, '{http://schemas.google.com/apps/2006}property')
            prop.set('name', name)
            prop.set('value', value)
        
        filter_dict = converter._convert_xml_entry(entry, {'apps': 'http://schemas.google.com/apps/2006'}, 0)
        
        assert filter_dict['from'] == 'test@example.com'
        assert filter_dict['forward'] == 'backup@example.com'
    
    def test_interactive_merge_user_responses(self):
        """Test interactive merge with different user responses."""
        converter = GmailFilterConverter(infer_more=True, infer_strategy='interactive')
        
        parent = {'from': 'test@example.com', 'label': 'Parent'}
        child = {'from': 'test@example.com', 'has': 'important', 'label': 'Child'}
        
        # Test 'yes' response
        with patch('builtins.input', return_value='y'):
            result = converter._interactive_merge_decision(parent, child, False, False)
            assert result is True
        
        # Test 'no' response
        with patch('builtins.input', return_value='n'):
            result = converter._interactive_merge_decision(parent, child, False, False)
            assert result is False
        
        # Test 'skip all' response
        with patch('builtins.input', return_value='s'):
            result = converter._interactive_merge_decision(parent, child, False, False)
            assert result == 'skip_all'
        
        # Test 'accept all' response
        with patch('builtins.input', return_value='a'):
            result = converter._interactive_merge_decision(parent, child, False, False)
            assert result == 'accept_all'
        
        # Test when skip_all is already set
        result = converter._interactive_merge_decision(parent, child, True, False)
        assert result is False
        
        # Test when accept_all is already set
        result = converter._interactive_merge_decision(parent, child, False, True)
        assert result is True
    
    def test_get_filter_conditions(self):
        """Test extraction of filter conditions."""
        converter = GmailFilterConverter()
        
        filter_dict = {
            'from': 'test@example.com',
            'subject': 'Important',
            'has': 'attachment',
            'label': 'Work',  # Not a condition
            'archive': True,  # Not a condition
            '_gmail_raw': {'id': '123'}  # Not a condition
        }
        
        conditions = converter._get_filter_conditions(filter_dict)
        
        assert 'from' in conditions
        assert 'subject' in conditions
        assert 'has' in conditions
        assert 'label' not in conditions
        assert 'archive' not in conditions
        assert '_gmail_raw' not in conditions
    
    def test_is_child_of_with_safety_analysis(self):
        """Test _is_child_of with safety analysis."""
        converter = GmailFilterConverter(infer_more=True, infer_strategy='conservative')
        
        parent = {'from': 'test@example.com', 'label': 'Parent'}
        parent_conditions = {'from': 'test@example.com'}
        
        # Test safe child
        safe_child = {'from': 'test@example.com', 'has': 'meeting', 'label': 'Meetings'}
        safe_child_conditions = {'from': 'test@example.com', 'has': 'meeting'}
        
        result = converter._is_child_of(parent, safe_child, parent_conditions, safe_child_conditions)
        assert result is True
        
        # Test unsafe child (action conflict)
        unsafe_child = {'from': 'test@example.com', 'archive': False, 'label': 'NoArchive'}
        parent['archive'] = True
        unsafe_child_conditions = {'from': 'test@example.com'}
        
        result = converter._is_child_of(parent, unsafe_child, parent_conditions, unsafe_child_conditions)
        assert result is False
    
    def test_validate_round_trip_with_invalid_xml(self):
        """Test round-trip validation with invalid XML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("Not valid XML content")
            xml_file = f.name
        
        try:
            converter = GmailFilterConverter()
            result = converter.validate_round_trip(xml_file)
            assert result is False
        finally:
            os.unlink(xml_file)
    
    def test_xml_to_yaml_with_verbose(self):
        """Test XML to YAML conversion with verbose output."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='verbose@example.com'/>
        <apps:property name='label' value='Verbose'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            xml_file = f.name
        
        try:
            converter = GmailFilterConverter(verbose=True)
            
            with patch('builtins.print') as mock_print:
                filters = converter.xml_to_yaml(xml_file)
                
            # Verbose mode should print processing information
            assert mock_print.called
            assert len(filters) == 1
            assert filters[0]['from'] == 'verbose@example.com'
        finally:
            os.unlink(xml_file)
    
    def test_merge_with_operator_inference(self):
        """Test merging with operator inference enabled."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='alice@example.com OR bob@example.com'/>
        <apps:property name='label' value='Team'/>
    </entry>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='alice@example.com OR bob@example.com'/>
        <apps:property name='label' value='Important'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            xml_file = f.name
        
        try:
            converter = GmailFilterConverter(
                merge_filters=True,
                infer_operators=True
            )
            
            filters = converter.xml_to_yaml(xml_file)
            
            # Should merge and convert OR pattern
            assert len(filters) == 1
            assert 'from' in filters[0]
            assert 'any' in filters[0]['from']
            assert set(filters[0]['label']) == {'Team', 'Important'}
        finally:
            os.unlink(xml_file)
    
    def test_clean_filter_dict_with_empty_gmail_raw(self):
        """Test cleaning filter dict with empty _gmail_raw."""
        converter = GmailFilterConverter()
        
        filter_dict = {
            'from': 'test@example.com',
            'label': 'Test',
            '_gmail_raw': {}  # Empty raw section
        }
        
        cleaned = converter._clean_filter_dict(filter_dict.copy())
        
        # Empty _gmail_raw should be removed
        assert '_gmail_raw' not in cleaned
    
    def test_clean_filter_dict_with_defaults(self):
        """Test cleaning filter dict removes default values."""
        converter = GmailFilterConverter(smart_clean=True)
        
        filter_dict = {
            'from': 'test@example.com',
            'label': 'Test',
            '_gmail_raw': {
                'sizeOperator': 's_sl',  # Default value
                'sizeUnit': 's_smb',  # Default value
                'excludeChats': 'false',  # Default value
                'id': '123'  # Should be kept
            }
        }
        
        cleaned = converter._clean_filter_dict(filter_dict.copy())
        
        # Defaults should be removed, id should remain
        assert '_gmail_raw' in cleaned
        assert 'id' in cleaned['_gmail_raw']
        assert 'sizeOperator' not in cleaned['_gmail_raw']
        assert 'sizeUnit' not in cleaned['_gmail_raw']
        assert 'excludeChats' not in cleaned['_gmail_raw']
    
    def test_build_more_with_empty_children(self):
        """Test building more structures handles empty children list."""
        converter = GmailFilterConverter(infer_more=True)
        
        # Hierarchy with empty children list (edge case)
        hierarchies = [{'parent': 0, 'children': []}]
        filters = [
            {'from': 'test@example.com', 'label': 'Parent'}
        ]
        
        result = converter._build_more_structures(hierarchies, filters)
        
        # Should handle gracefully
        assert len(result) >= 1
    
    def test_special_gmail_properties(self):
        """Test conversion of special Gmail properties."""
        converter = GmailFilterConverter()
        
        ns_map = {
            None: 'http://www.w3.org/2005/Atom',
            'apps': 'http://schemas.google.com/apps/2006'
        }
        
        entry = etree.Element('entry', nsmap=ns_map)
        category = etree.SubElement(entry, 'category')
        category.set('term', 'filter')
        
        # Test various special properties
        props = [
            ('hasTheWord', 'important'),
            ('doesNotHaveTheWord', 'spam'),
            ('hasAttachment', 'true'),
            ('excludeChats', 'true'),
            ('shouldAlwaysMarkAsImportant', 'true'),
            ('shouldNeverMarkAsImportant', 'true'),
            ('shouldSpam', 'true'),
            ('shouldNeverSpam', 'true'),
            ('shouldStar', 'true'),
            ('shouldTrash', 'true')
        ]
        
        for name, value in props:
            prop = etree.SubElement(entry, '{http://schemas.google.com/apps/2006}property')
            prop.set('name', name)
            prop.set('value', value)
        
        filter_dict = converter._convert_xml_entry(entry, {'apps': 'http://schemas.google.com/apps/2006'}, 0)
        
        assert filter_dict['has'] == 'important'
        assert filter_dict['does_not_have'] == 'spam'
        assert filter_dict['has_attachment'] is True
        assert filter_dict['exclude_chats'] is True
        assert filter_dict['important'] is True
        assert filter_dict['not_important'] is True
        assert filter_dict['spam'] is True
        assert filter_dict['not_spam'] is True
        assert filter_dict['star'] is True
        assert filter_dict['trash'] is True