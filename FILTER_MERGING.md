# Filter Merging and Inference

## Overview

The `--filter-merging` option provides intelligent conversion from Gmail's flat XML filter format to more structured and maintainable YAML. It combines multiple inference features:

1. **Label merging**: Combines filters that differ only in labels
2. **Hierarchy inference**: Detects parent-child relationships to create "more" structures  
3. **Operator inference**: Converts Gmail's OR/AND/NOT patterns to YAML operators

## Usage

```bash
gmail-yaml-filters convert mailFilters.xml --filter-merging <level> -o filters.yaml
```

## Merging Levels

### `none` (default)
No merging or inference. Direct 1:1 conversion from XML to YAML.

```bash
gmail-yaml-filters convert mailFilters.xml --filter-merging none -o filters.yaml
```

### `conservative`
Safe merging and inference:
- Merges filters that differ only in labels
- Infers hierarchies when conditions match exactly
- Converts OR/AND/NOT patterns to operators
- Never merges security-sensitive filters
- Avoids merging filters with conflicting actions

```bash
gmail-yaml-filters convert mailFilters.xml --filter-merging conservative -o filters.yaml
```

### `aggressive`
More aggressive merging:
- All conservative features plus:
- Detects subset relationships (child has all parent conditions plus more)
- May suggest merging filters with minor differences
- Still respects safety rules for security filters

```bash
gmail-yaml-filters convert mailFilters.xml --filter-merging aggressive -o filters.yaml
```

### `interactive`
User-guided merging:
- Shows detailed safety analysis for each potential merge
- Prompts for confirmation on ambiguous cases
- Provides warnings about conflicts and security concerns
- Remembers decisions for similar patterns

```bash
gmail-yaml-filters convert mailFilters.xml --filter-merging interactive -o filters.yaml
```

## Examples

### Before (Gmail XML export)
```xml
<!-- Multiple filters for different team members -->
<entry>
  <apps:property name='from' value='alice@example.com'/>
  <apps:property name='label' value='Team'/>
  <apps:property name='label' value='Alice'/>
</entry>
<entry>
  <apps:property name='from' value='bob@example.com'/>
  <apps:property name='label' value='Team'/>
  <apps:property name='label' value='Bob'/>
</entry>

<!-- Filters with OR patterns -->
<entry>
  <apps:property name='subject' value='{urgent important critical}'/>
  <apps:property name='label' value='Priority'/>
</entry>

<!-- Hierarchical filters -->
<entry>
  <apps:property name='from' value='notifications@github.com'/>
  <apps:property name='label' value='GitHub'/>
</entry>
<entry>
  <apps:property name='from' value='notifications@github.com'/>
  <apps:property name='subject' value='pull request'/>
  <apps:property name='label' value='GitHub/PR'/>
</entry>
```

### After with `conservative` merging
```yaml
# Merged team member filters
- from:
    any:
      - alice@example.com
      - bob@example.com
  label:
    - Team
    - for_each:
        - [alice@example.com, Alice]
        - [bob@example.com, Bob]

# Converted operators
- subject:
    any:
      - urgent
      - important
      - critical
  label: Priority

# Inferred hierarchy
- from: notifications@github.com
  label: GitHub
  more:
    - subject: pull request
      label: GitHub/PR
```

## Safety Features

The merging system includes built-in safety checks:

### Security Detection
Filters containing security-related keywords are handled carefully:
- Password resets
- Two-factor authentication
- Account verification
- Login notifications

### Action Conflict Detection
Warns about conflicting actions:
- `archive` vs `not_archive`
- `important` vs `not_important`
- Different forwarding addresses
- Archive state conflicts (critical)

### Interactive Mode Prompts

In interactive mode, you'll see detailed analysis:

```
Potential merge detected:
  Parent: from=notifications@github.com, label=GitHub
  Child: from=notifications@github.com, subject=PR, label=GitHub/PR

Safety Analysis:
  ✓ No security keywords detected
  ✓ No action conflicts
  ✓ Compatible labels suggest hierarchy
  Confidence: 95%

Merge these filters? (y/n/skip-all/accept-all):
```

## Combining with Other Options

```bash
# Full conversion with smart cleaning and verbose output
gmail-yaml-filters convert mailFilters.xml \
  --filter-merging interactive \
  --smart-clean \
  --verbose \
  -o filters.yaml
```

## When to Use Each Level

- **`none`**: When you want exact preservation of Gmail's structure
- **`conservative`**: For most users - safe, predictable improvements
- **`aggressive`**: When you have many similar filters and want maximum consolidation
- **`interactive`**: When you want full control over the merging process

## Limitations

- Only works when converting from XML to YAML
- Cannot infer relationships that don't exist in the original filters
- Some complex Gmail search patterns may not be perfectly converted
- Merged filters must still be valid according to Gmail's rules