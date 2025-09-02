#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for CLI commands in main.py."""

import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call
from io import StringIO
import argparse

from gmail_yaml_filters.main import (
    create_parser, cmd_export, cmd_convert, cmd_validate,
    cmd_sync, cmd_upload, cmd_prune, main, load_yaml_filters,
    ruleset_to_xml
)
from gmail_yaml_filters.ruleset import RuleSet
from gmail_yaml_filters.upload import upload_ruleset, prune_filters_not_in_ruleset


class TestCLICommands:
    """Test CLI command handlers."""
    
    def test_create_parser(self):
        """Test parser creation."""
        parser = create_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        
        # Test parsing export command
        args = parser.parse_args(['export', 'test.yaml'])
        assert args.command == 'export'
        assert args.yaml_file == 'test.yaml'
        
        # Test parsing convert command
        args = parser.parse_args(['convert', 'test.xml', '-o', 'output.yaml'])
        assert args.command == 'convert'
        assert args.input_file == 'test.xml'
        assert args.output == 'output.yaml'
    
    def test_cmd_export_to_stdout(self):
        """Test export command output to stdout."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
- from: alice@example.com
  label: Alice
- has: attachment
  archive: true
""")
            yaml_file = f.name
        
        try:
            args = MagicMock()
            args.yaml_file = yaml_file
            args.output = None  # stdout
            
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                cmd_export(args)
                output = mock_stdout.getvalue()
                
            assert '<?xml version' in output
            assert 'alice@example.com' in output
            assert 'attachment' in output
        finally:
            os.unlink(yaml_file)
    
    def test_cmd_export_to_file(self):
        """Test export command output to file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
- from: bob@example.com
  label: Bob
""")
            yaml_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            xml_file = f.name
        
        try:
            args = MagicMock()
            args.yaml_file = yaml_file
            args.output = xml_file
            
            cmd_export(args)
            
            with open(xml_file) as f:
                content = f.read()
            
            assert '<?xml version' in content
            assert 'bob@example.com' in content
        finally:
            os.unlink(yaml_file)
            if os.path.exists(xml_file):
                os.unlink(xml_file)
    
    def test_cmd_convert_xml_to_yaml(self):
        """Test convert command from XML to YAML."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='test@example.com'/>
        <apps:property name='label' value='Test'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            xml_file = f.name
        
        try:
            args = MagicMock()
            args.input_file = xml_file
            args.output = None  # stdout
            args.to = None  # auto-detect
            args.filter_merging = 'none'
            args.preserve_raw = False
            args.smart_clean = False
            args.verbose = False
            
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                cmd_convert(args)
                output = mock_stdout.getvalue()
                
            assert 'from: test@example.com' in output
            assert 'label: Test' in output
        finally:
            os.unlink(xml_file)
    
    def test_cmd_convert_yaml_to_xml(self):
        """Test convert command from YAML to XML."""
        yaml_content = """
- from: alice@example.com
  label: Alice
  archive: true
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            args = MagicMock()
            args.input_file = yaml_file
            args.output = None  # stdout
            args.to = None  # auto-detect
            args.filter_merging = 'none'
            args.preserve_raw = False
            args.smart_clean = False
            args.verbose = False
            
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                cmd_convert(args)
                output = mock_stdout.getvalue()
                
            assert '<?xml version' in output
            assert 'alice@example.com' in output
            assert 'shouldArchive' in output
        finally:
            os.unlink(yaml_file)
    
    def test_cmd_convert_with_merging(self):
        """Test convert command with filter merging enabled."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='test@example.com'/>
        <apps:property name='label' value='Test1'/>
    </entry>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='test@example.com'/>
        <apps:property name='label' value='Test2'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            xml_file = f.name
        
        try:
            args = MagicMock()
            args.input_file = xml_file
            args.output = None
            args.to = None  # auto-detect
            args.filter_merging = 'conservative'  # Enable merging
            args.preserve_raw = False
            args.smart_clean = False
            args.verbose = False
            
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                cmd_convert(args)
                output = mock_stdout.getvalue()
                
            # Should merge the two filters
            assert 'from: test@example.com' in output
            assert 'Test1' in output
            assert 'Test2' in output
        finally:
            os.unlink(xml_file)
    
    def test_cmd_validate_valid_roundtrip(self):
        """Test validate command with valid roundtrip."""
        xml_content = '''<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
    <title>Mail Filters</title>
    <entry>
        <category term='filter'></category>
        <apps:property name='from' value='test@example.com'/>
        <apps:property name='label' value='Test'/>
    </entry>
</feed>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            xml_file = f.name
        
        try:
            args = MagicMock()
            args.xml_file = xml_file
            args.verbose = False
            
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                cmd_validate(args)
                output = mock_stdout.getvalue()
            assert 'valid' in output.lower()
        finally:
            os.unlink(xml_file)
    
    @patch('gmail_yaml_filters.main.get_gmail_service_for_file')
    @patch('gmail_yaml_filters.main.prune_filters_not_in_ruleset')
    @patch('gmail_yaml_filters.main.upload_ruleset')
    def test_cmd_sync(self, mock_upload, mock_prune, mock_get_service):
        """Test sync command."""
        yaml_content = """
- from: alice@example.com
  label: Alice
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            args = MagicMock()
            args.yaml_file = yaml_file
            args.dry_run = True
            args.client_secret = None
            args.credential_store = None
            args.prune_labels = False
            
            cmd_sync(args)
            
            # Verify functions were called
            mock_upload.assert_called_once()
            mock_prune.assert_called_once()
        finally:
            os.unlink(yaml_file)
    
    @patch('gmail_yaml_filters.main.get_gmail_service_for_file')
    @patch('gmail_yaml_filters.main.upload_ruleset')
    def test_cmd_upload(self, mock_upload, mock_get_service):
        """Test upload command."""
        yaml_content = """
- from: bob@example.com
  label: Bob
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            args = MagicMock()
            args.yaml_file = yaml_file
            args.dry_run = False
            args.client_secret = None
            args.credential_store = None
            
            cmd_upload(args)
            
            # Verify upload was called
            mock_upload.assert_called_once()
        finally:
            os.unlink(yaml_file)
    
    @patch('gmail_yaml_filters.main.get_gmail_service_for_file')
    @patch('gmail_yaml_filters.main.prune_filters_not_in_ruleset')
    def test_cmd_prune(self, mock_prune, mock_get_service):
        """Test prune command."""
        yaml_content = """
- from: charlie@example.com
  label: Charlie
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            args = MagicMock()
            args.yaml_file = yaml_file
            args.dry_run = False
            args.client_secret = None
            args.credential_store = None
            
            cmd_prune(args)
            
            # Verify prune was called
            mock_prune.assert_called_once()
        finally:
            os.unlink(yaml_file)
    
    def test_main_backward_compatibility(self):
        """Test main function backward compatibility mode."""
        yaml_content = """
- from: dave@example.com
  label: Dave
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            # Simulate calling: gmail-yaml-filters file.yaml
            with patch('sys.argv', ['gmail-yaml-filters', yaml_file]):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    with patch('sys.exit') as mock_exit:
                        main()
                        
                output = mock_stdout.getvalue()
                assert '<?xml version' in output
                assert 'dave@example.com' in output
                mock_exit.assert_called_once_with(0)
        finally:
            os.unlink(yaml_file)
    
    def test_main_with_export_command(self):
        """Test main function with export command."""
        yaml_content = """
- from: eve@example.com
  label: Eve
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        
        try:
            with patch('sys.argv', ['gmail-yaml-filters', 'export', yaml_file]):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    with patch('sys.exit') as mock_exit:
                        main()
                        
                output = mock_stdout.getvalue()
                assert '<?xml version' in output
                assert 'eve@example.com' in output
                mock_exit.assert_called_once_with(0)
        finally:
            os.unlink(yaml_file)
    
    def test_main_help(self):
        """Test main function help output."""
        with patch('sys.argv', ['gmail-yaml-filters', '--help']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                assert exc_info.value.code == 0
                output = mock_stdout.getvalue()
                assert 'Manage Gmail filters' in output
    
    def test_cmd_export_with_invalid_file(self):
        """Test export with non-existent file."""
        args = MagicMock()
        args.yaml_file = '/nonexistent/file.yaml'
        args.output = None
        
        with patch('sys.stderr', new_callable=StringIO):
            with pytest.raises(SystemExit) as exc_info:
                cmd_export(args)
            assert exc_info.value.code == 1
    
    def test_cmd_convert_with_invalid_input(self):
        """Test convert with invalid input file."""
        args = MagicMock()
        args.input_file = '/nonexistent/file.xml'
        args.output = None
        args.to = None
        args.filter_merging = 'none'
        args.preserve_raw = False
        args.smart_clean = False
        args.verbose = False
        
        with patch('sys.stderr', new_callable=StringIO):
            with pytest.raises(SystemExit) as exc_info:
                cmd_convert(args)
            assert exc_info.value.code == 1