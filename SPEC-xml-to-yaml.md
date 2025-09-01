## SPEC.md - Gmail XML to YAML Filter Converter

### Project Overview
Create a converter tool for the `gmail-yaml-filters` project that transforms Gmail's exported XML filter format into the YAML format expected by gmail-yaml-filters. This will help users migrate their existing Gmail filters to the more maintainable YAML format.

### Background Context
- Gmail exports filters as XML files through Settings → Filters and Blocked Addresses → Export
- The `gmail-yaml-filters` project (https://github.com/mesozoic/gmail-yaml-filters) uses YAML for filter definitions
- Currently no automated conversion tool exists
- Users must manually recreate dozens or hundreds of filters

### Goals
1. Provide a reliable, well-tested converter from Gmail XML to gmail-yaml-filters YAML
2. Preserve all convertible filter properties
3. Clearly report any unsupported properties
4. Integrate seamlessly with the existing gmail-yaml-filters workflow
5. Include comprehensive tests and documentation

### Technical Requirements

#### Input Format
Gmail XML structure (simplified example):
```xml
<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>
	<entry>
		<apps:property name='from' value='example@gmail.com'/>
		<apps:property name='label' value='Important'/>
		<apps:property name='shouldMarkAsImportant' value='true'/>
	</entry>
</feed>
```

#### Output Format
gmail-yaml-filters YAML structure:
```yaml
filters:
  - from: example@gmail.com
	label: Important
	important: true
```

#### Property Mappings
Create a complete mapping between Gmail XML properties and YAML fields:

| Gmail XML Property | YAML Field | Type | Notes |
|-------------------|------------|------|-------|
| from | from | string | Direct mapping |
| to | to | string | Direct mapping |
| subject | subject | string | Direct mapping |
| hasTheWord | has | string | Search query |
| doesNotHaveTheWord | not | string | Negative search |
| label | label | string | Supports nested labels with `/` |
| shouldArchive | archive | boolean | Convert string to bool |
| shouldMarkAsImportant | important | boolean | Convert string to bool |
| shouldDelete | delete | boolean | Convert string to bool |
| shouldMarkAsRead | mark_read | boolean | Convert string to bool |
| shouldNeverMarkAsImportant | never_important | boolean | Convert string to bool |
| shouldNeverSpam | not_spam | boolean | Convert string to bool |
| shouldStar | star | boolean | Convert string to bool |
| shouldTrash | trash | boolean | Convert string to bool |
| forwardTo | forward | string | Email address |
| hasAttachment | - | - | Convert to `has: has:attachment` |
| size | - | - | Not supported, warn user |
| sizeOperator | - | - | Not supported, warn user |
| excludeChats | - | - | Not supported, warn user |

### Implementation Details

#### Core Converter Module
Create `gmail_xml_to_yaml.py` with:

```python
class GmailFilterConverter:
	def __init__(self, verbose=False, strict=False):
		"""
		Args:
			verbose: Print detailed conversion information
			strict: Fail on unsupported properties vs warning
		"""
		
	def convert_file(self, xml_path: str, yaml_path: str = None) -> dict:
		"""Convert XML file to YAML file or return dict"""
		
	def convert_string(self, xml_string: str) -> dict:
		"""Convert XML string to dict suitable for YAML output"""
		
	def get_stats(self) -> dict:
		"""Return conversion statistics"""
		
	def get_warnings(self) -> list:
		"""Return list of warnings encountered"""
```

#### CLI Interface
Create command-line interface:
```bash
# Basic usage
gmail-xml-to-yaml mailFilters.xml

# With options
gmail-xml-to-yaml mailFilters.xml -o my_filters.yaml --verbose

# Validate without writing
gmail-xml-to-yaml mailFilters.xml --dry-run

# Strict mode (fail on warnings)
gmail-xml-to-yaml mailFilters.xml --strict
```

#### Integration Points
- Add to existing CLI as subcommand: `gmail-yaml-filters convert-xml mailFilters.xml`
- Or standalone script in `tools/` directory
- Import functionality for use in Python scripts

### Special Cases to Handle

1. **Nested Labels**: Convert `parent/child` format correctly
2. **Boolean Values**: Convert "true"/"false" strings to Python booleans
3. **OR Conditions**: Preserve `OR` logic in from/to fields
4. **Complex Searches**: Maintain parentheses and quotes in `hasTheWord`
5. **hasAttachment**: Convert to `has: has:attachment` or append to existing `has` field
6. **Multiple Labels**: Some filters may have multiple label actions
7. **UTF-8 Handling**: Preserve international characters
8. **Empty Values**: Handle empty strings appropriately

### Testing Requirements

#### Unit Tests
Test file: `test_gmail_xml_to_yaml.py`

Required test cases:
1. Basic filter with single property
2. Complex filter with all supported properties
3. Filter with unsupported properties (should warn, not fail)
4. Nested labels
5. Boolean conversions
6. Special characters and UTF-8
7. Empty XML file
8. Malformed XML (should error gracefully)
9. hasAttachment special case
10. Multiple filters with different properties
11. OR conditions in from/to fields
12. Complex search queries with quotes and parentheses

#### Integration Tests
1. Round-trip test: XML → YAML → gmail-yaml-filters validation
2. Large file performance test (100+ filters)
3. Comparison with manual conversions

#### Test Data
Include `test_data/` directory with:
- `simple_filter.xml` - Single basic filter
- `complex_filters.xml` - Multiple filters with various properties
- `edge_cases.xml` - Unusual but valid configurations
- `expected_output/` - Corresponding expected YAML files

### Error Handling

1. **File Errors**: Clear messages for missing/unreadable files
2. **XML Parse Errors**: Show line number and context
3. **Unsupported Properties**: 
   - Default: Warn and continue
   - Strict mode: Fail with detailed report
4. **Value Conversion Errors**: Log and use original value
5. **Namespace Issues**: Handle missing or different XML namespaces

### Documentation Requirements

#### README Addition
Add section to main README:
```markdown
## Converting from Gmail XML

Export your filters from Gmail and convert them:

```bash
gmail-xml-to-yaml mailFilters.xml -o my_filters.yaml
gmail-yaml-filters my_filters.yaml
```

See [Converting from Gmail](docs/converting-from-gmail.md) for details.
```

#### Dedicated Documentation
Create `docs/converting-from-gmail.md` with:
1. Step-by-step Gmail export instructions
2. Conversion command examples
3. Property mapping table
4. Handling unsupported properties
5. Common patterns and solutions
6. Troubleshooting guide

#### Code Documentation
- Docstrings for all public methods
- Type hints throughout
- Inline comments for complex logic

### Performance Requirements
- Handle 1000+ filters without memory issues
- Complete conversion in < 1 second for typical use (50-100 filters)
- Stream processing for very large files if needed

### Compatibility
- Python 3.6+ (match main project requirements)
- Use only standard library + existing project dependencies
- Cross-platform (Windows, Mac, Linux)

### Deliverables

1. **Core Files**:
   - `gmail_xml_to_yaml.py` - Main converter module
   - `test_gmail_xml_to_yaml.py` - Comprehensive tests
   - `test_data/` - Test fixtures

2. **Documentation**:
   - `docs/converting-from-gmail.md` - User guide
   - README.md updates
   - Inline code documentation

3. **Integration**:
   - CLI command addition
   - Setup.py / requirements.txt updates if needed

4. **Pull Request**:
   - Clear description of feature
   - Examples of usage
   - Test coverage report
   - No breaking changes to existing functionality

### Success Criteria
1. Converts 95%+ of common Gmail filter properties
2. Clear reporting of unsupported features
3. Zero data loss for supported properties
4. Comprehensive test coverage (>90%)
5. Clear documentation
6. Accepted by project maintainers

### Example Usage Session
```bash
$ gmail-xml-to-yaml mailFilters.xml --verbose
📧 Gmail XML to YAML Converter
Reading mailFilters.xml...
Found 47 filters to convert

Converting filters...
  ✓ Filter 1: from:'newsletter@example.com' → label:Newsletters
  ✓ Filter 2: subject:'Invoice' → label:Billing, mark_important
  ⚠ Filter 3: Unsupported property 'size' - skipped
  ...

Conversion complete!
  Converted: 45/47 filters
  Warnings: 2 (use --verbose for details)
  
Output written to: mailFilters.yaml

Next step: Run 'gmail-yaml-filters mailFilters.yaml' to apply filters
```

### Notes for Implementation
- Consider using `ruamel.yaml` if preserve comments/formatting needed
- Could add `--preserve-order` flag to maintain filter sequence
- Consider adding `--split` option to separate filters into multiple files
- Future enhancement: Two-way sync capability
- Consider detecting and suggesting variable extraction for repeated values