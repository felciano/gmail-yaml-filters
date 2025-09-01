#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Gmail YAML Filters CLI with organized subcommands.

Commands:
  export    Generate Gmail XML from YAML (default if no command given)
  convert   Convert between Gmail XML and YAML formats
  validate  Validate round-trip conversion (XML → YAML → XML)
  sync      Sync filters with Gmail (upload + prune)
  upload    Upload filters to Gmail
  prune     Remove filters from Gmail not in YAML
"""
from __future__ import print_function, unicode_literals

import argparse
import os
import re
import sys
from pathlib import Path

import yaml
from lxml import etree

from .ruleset import RuleSet, ruleset_to_etree
from .upload import (
    get_gmail_credentials,
    get_gmail_service,
    prune_filters_not_in_ruleset,
    prune_labels_not_in_ruleset,
    upload_ruleset,
)
from .xml_converter import GmailFilterConverter


def ruleset_to_xml(ruleset, pretty_print=True, encoding="utf8"):
    """Convert a RuleSet to Gmail XML format."""
    dom = ruleset_to_etree(ruleset)
    chars = etree.tostring(
        dom,
        encoding=encoding,
        pretty_print=pretty_print,
        xml_declaration=True,
    )
    return chars.decode(encoding)


def detect_file_format(filepath):
    """Detect if file is XML or YAML based on extension and content."""
    path = Path(filepath)
    
    # Check extension first
    if path.suffix.lower() in ['.xml']:
        return 'xml'
    elif path.suffix.lower() in ['.yaml', '.yml']:
        return 'yaml'
    
    # Try to detect from content
    try:
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
            if first_line.startswith('<?xml'):
                return 'xml'
            elif first_line.startswith('---') or first_line.startswith('-'):
                return 'yaml'
    except:
        pass
    
    # Default guess based on trying to parse as YAML
    try:
        with open(filepath, 'r') as f:
            yaml.safe_load(f)
        return 'yaml'
    except:
        return 'xml'


def create_parser():
    """Create the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog='gmail-yaml-filters',
        description='Manage Gmail filters with YAML configuration files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Gmail XML from YAML (original behavior)
  gmail-yaml-filters my-filters.yaml > filters.xml
  gmail-yaml-filters export my-filters.yaml -o filters.xml
  
  # Convert between formats
  gmail-yaml-filters convert mailFilters.xml -o my-filters.yaml
  gmail-yaml-filters convert my-filters.yaml -o filters.xml
  
  # Validate round-trip conversion
  gmail-yaml-filters validate mailFilters.xml
  
  # Sync with Gmail
  gmail-yaml-filters sync my-filters.yaml
  gmail-yaml-filters sync --dry-run my-filters.yaml
  
  # Upload or prune individually
  gmail-yaml-filters upload my-filters.yaml
  gmail-yaml-filters prune my-filters.yaml
        """
    )
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to execute'
    )
    
    # ========== EXPORT command (generate XML from YAML) ==========
    export_parser = subparsers.add_parser(
        'export',
        help='Generate Gmail XML from YAML filters',
        description='Convert YAML filter definitions to Gmail-compatible XML'
    )
    export_parser.add_argument(
        'yaml_file',
        help='YAML filter file to convert'
    )
    export_parser.add_argument(
        '-o', '--output',
        help='Output XML file (default: stdout)'
    )
    
    # ========== CONVERT command (bidirectional conversion) ==========
    convert_parser = subparsers.add_parser(
        'convert',
        help='Convert between Gmail XML and YAML formats',
        description='Automatically detects input format and converts to the other'
    )
    convert_parser.add_argument(
        'input_file',
        help='Input file (XML or YAML, auto-detected)'
    )
    convert_parser.add_argument(
        '-o', '--output',
        help='Output file (default: stdout)'
    )
    convert_parser.add_argument(
        '--to',
        choices=['xml', 'yaml'],
        help='Force output format (default: auto-detect opposite)'
    )
    convert_parser.add_argument(
        '--smart-clean',
        action='store_true',
        help='Remove meaningless Gmail defaults from output'
    )
    convert_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed conversion information'
    )
    convert_parser.add_argument(
        '--fail-on-unsupported-properties',
        action='store_true',
        help='Fail when encountering Gmail properties that cannot be converted'
    )
    
    # ========== VALIDATE command (round-trip validation) ==========
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate round-trip conversion preserves all data',
        description='Test that XML → YAML → XML conversion preserves all filter data'
    )
    validate_parser.add_argument(
        'xml_file',
        help='Gmail XML export file to validate'
    )
    validate_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed validation information'
    )
    
    # ========== SYNC command (upload + prune) ==========
    sync_parser = subparsers.add_parser(
        'sync',
        help='Sync YAML filters with Gmail (upload + prune)',
        description='Upload filters from YAML and remove any not in the file'
    )
    sync_parser.add_argument(
        'yaml_file',
        help='YAML filter file to sync'
    )
    sync_parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Preview changes without making API calls'
    )
    sync_parser.add_argument(
        '--prune-labels',
        action='store_true',
        help='Also remove unused Gmail labels'
    )
    sync_parser.add_argument(
        '--label-pattern',
        default=r'.*',
        help='Only prune labels matching this regex pattern'
    )
    sync_parser.add_argument(
        '--client-secret',
        help='Path to client_secret.json (default: same dir as YAML file)'
    )
    sync_parser.add_argument(
        '--credential-store',
        default=os.path.join(
            os.path.expanduser("~"), ".credentials", "gmail_yaml_filters.json"
        ),
        help='Path to credential cache'
    )
    
    # ========== UPLOAD command ==========
    upload_parser = subparsers.add_parser(
        'upload',
        help='Upload filters to Gmail',
        description='Create filters and labels in Gmail from YAML file'
    )
    upload_parser.add_argument(
        'yaml_file',
        help='YAML filter file to upload'
    )
    upload_parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Preview changes without making API calls'
    )
    upload_parser.add_argument(
        '--client-secret',
        help='Path to client_secret.json (default: same dir as YAML file)'
    )
    upload_parser.add_argument(
        '--credential-store',
        default=os.path.join(
            os.path.expanduser("~"), ".credentials", "gmail_yaml_filters.json"
        ),
        help='Path to credential cache'
    )
    
    # ========== PRUNE command ==========
    prune_parser = subparsers.add_parser(
        'prune',
        help='Remove Gmail filters not in YAML file',
        description='Delete filters from Gmail that are not defined in the YAML file'
    )
    prune_parser.add_argument(
        'yaml_file',
        help='YAML filter file defining filters to keep'
    )
    prune_parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Preview changes without making API calls'
    )
    prune_parser.add_argument(
        '--prune-labels',
        action='store_true',
        help='Also remove unused Gmail labels'
    )
    prune_parser.add_argument(
        '--label-pattern',
        default=r'.*',
        help='Only prune labels matching this regex pattern'
    )
    prune_parser.add_argument(
        '--client-secret',
        help='Path to client_secret.json (default: same dir as YAML file)'
    )
    prune_parser.add_argument(
        '--credential-store',
        default=os.path.join(
            os.path.expanduser("~"), ".credentials", "gmail_yaml_filters.json"
        ),
        help='Path to credential cache'
    )
    
    return parser


def load_yaml_filters(yaml_file):
    """Load and parse YAML filter file."""
    if yaml_file == '-':
        data = yaml.safe_load(sys.stdin)
    else:
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
    
    if not isinstance(data, list):
        data = [data]
    
    return RuleSet.from_object(rule for rule in data if not rule.get("ignore"))


def get_gmail_service_for_file(yaml_file, client_secret, credential_store, dry_run=False):
    """Get Gmail service, looking for client_secret in appropriate location."""
    if not client_secret:
        # Look for client_secret.json in same directory as YAML file
        if yaml_file != '-':
            config_dir = os.path.dirname(os.path.abspath(yaml_file))
            client_secret = os.path.join(config_dir, "client_secret.json")
        else:
            client_secret = "client_secret.json"
    
    credentials = get_gmail_credentials(client_secret, credential_store)
    return get_gmail_service(credentials, dry_run=dry_run)


def cmd_export(args):
    """Handle the export command (YAML to XML)."""
    ruleset = load_yaml_filters(args.yaml_file)
    xml_output = ruleset_to_xml(ruleset)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(xml_output)
        print(f"Exported {len(ruleset.rules)} filters to {args.output}", file=sys.stderr)
    else:
        print(xml_output)


def cmd_convert(args):
    """Handle the convert command (bidirectional)."""
    # Detect input format
    input_format = detect_file_format(args.input_file)
    
    # Determine output format
    if args.to:
        output_format = args.to
    else:
        output_format = 'yaml' if input_format == 'xml' else 'xml'
    
    if input_format == output_format:
        print(f"Error: Input and output formats are both {input_format}", file=sys.stderr)
        sys.exit(1)
    
    # Create converter
    converter = GmailFilterConverter(
        preserve_raw=True,  # Always preserve Gmail-specific properties
        smart_clean=args.smart_clean,
        verbose=args.verbose,
        strict=args.fail_on_unsupported_properties
    )
    
    # Perform conversion
    try:
        if input_format == 'xml' and output_format == 'yaml':
            # XML to YAML
            result = converter.xml_to_yaml(args.input_file, args.output)
            if not args.output:
                print(result)
        else:
            # YAML to XML
            result = converter.yaml_to_xml(args.input_file, args.output)
            if not args.output:
                print(result)
        
        if args.verbose and args.output:
            stats = converter.get_stats()
            print(f"✅ Converted {stats.get('total_filters', 0)} filters", file=sys.stderr)
            print(f"   {args.input_file} ({input_format}) → {args.output} ({output_format})", file=sys.stderr)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_validate(args):
    """Handle the validate command (round-trip validation)."""
    converter = GmailFilterConverter(
        preserve_raw=True,
        verbose=args.verbose or True  # Always show some output for validation
    )
    
    try:
        print(f"🔄 Validating round-trip conversion for {args.xml_file}...", file=sys.stderr)
        is_valid = converter.validate_round_trip(args.xml_file)
        stats = converter.get_stats()
        
        if is_valid:
            print(f"✅ SUCCESS: All {stats['total_filters']} filters preserved correctly", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"❌ FAILED: Round-trip validation failed", file=sys.stderr)
            sys.exit(1)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_sync(args):
    """Handle the sync command (upload + prune)."""
    ruleset = load_yaml_filters(args.yaml_file)
    service = get_gmail_service_for_file(
        args.yaml_file, args.client_secret, args.credential_store, args.dry_run
    )
    
    # Upload filters
    upload_ruleset(ruleset, service=service, dry_run=args.dry_run)
    
    # Prune filters not in ruleset
    prune_filters_not_in_ruleset(ruleset, service=service, dry_run=args.dry_run)
    
    # Optionally prune labels
    if args.prune_labels:
        match = re.compile(args.label_pattern).match
        prune_labels_not_in_ruleset(
            ruleset, 
            service=service, 
            dry_run=args.dry_run,
            only_matching=match,
            ignore_errors=False
        )


def cmd_upload(args):
    """Handle the upload command."""
    ruleset = load_yaml_filters(args.yaml_file)
    service = get_gmail_service_for_file(
        args.yaml_file, args.client_secret, args.credential_store, args.dry_run
    )
    
    upload_ruleset(ruleset, service=service, dry_run=args.dry_run)


def cmd_prune(args):
    """Handle the prune command."""
    ruleset = load_yaml_filters(args.yaml_file)
    service = get_gmail_service_for_file(
        args.yaml_file, args.client_secret, args.credential_store, args.dry_run
    )
    
    prune_filters_not_in_ruleset(ruleset, service=service, dry_run=args.dry_run)
    
    # Optionally prune labels
    if args.prune_labels:
        match = re.compile(args.label_pattern).match
        prune_labels_not_in_ruleset(
            ruleset,
            service=service,
            dry_run=args.dry_run,
            only_matching=match,
            ignore_errors=False
        )


def main():
    """Main entry point."""
    # Check for backward compatibility mode (no subcommand, just a file)
    if len(sys.argv) > 1 and sys.argv[1] not in ['export', 'convert', 'validate', 'sync', 'upload', 'prune', '-h', '--help'] and not sys.argv[1].startswith('-'):
        # This looks like backward compatibility mode: gmail-yaml-filters file.yaml
        yaml_file_path = sys.argv[1]
        class ExportArgs:
            yaml_file = yaml_file_path
            output = None
        cmd_export(ExportArgs())
        return
    
    parser = create_parser()
    args = parser.parse_args()
    
    # If no command, show help
    if not args.command:
        parser.print_help()
        sys.exit(1)
        return
    
    # Execute the appropriate command
    commands = {
        'export': cmd_export,
        'convert': cmd_convert,
        'validate': cmd_validate,
        'sync': cmd_sync,
        'upload': cmd_upload,
        'prune': cmd_prune,
    }
    
    command_func = commands.get(args.command)
    if command_func:
        try:
            command_func(args)
        except KeyboardInterrupt:
            print("\nInterrupted", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            if hasattr(args, 'verbose') and args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()