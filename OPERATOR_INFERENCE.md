# Operator Inference Documentation

## Overview

The operator inference feature automatically converts Gmail's search patterns (OR, AND, NOT) into cleaner YAML operator structures when converting from XML to YAML format. This feature is now integrated into the `--filter-merging` option.

## Usage

Operator inference is automatically enabled with any filter merging level except `none`:

```bash
# Convert XML to YAML with operator inference (and other merging features)
gmail-yaml-filters convert mailFilters.xml --filter-merging conservative -o filters.yaml

# Export YAML with operators back to Gmail-compatible XML
gmail-yaml-filters export filters.yaml -o filters.xml
```

**Note**: Use the `export` command (not `convert`) when going from YAML to XML if your YAML contains operators. The `export` command properly converts operators back to Gmail search syntax.

## Supported Patterns

### OR Patterns (`any` operator)

Gmail supports several ways to express OR logic:

1. **Explicit OR**: `alice@example.com OR bob@example.com`
   ```yaml
   from:
     any:
       - alice@example.com
       - bob@example.com
   ```

2. **Curly braces**: `{urgent important critical}`
   ```yaml
   subject:
     any:
       - urgent
       - important
       - critical
   ```

3. **Pipe separator**: `bug|issue|defect`
   ```yaml
   has:
     any:
       - bug
       - issue
       - defect
   ```

### NOT Patterns (`not` operator)

Gmail uses the minus prefix for negation:

1. **Simple negation**: `-unsubscribe`
   ```yaml
   has:
     not: unsubscribe
   ```

2. **Negated OR group**: `-{spam promotions ads}`
   ```yaml
   has:
     not:
       any:
         - spam
         - promotions
         - ads
   ```

3. **Negated parenthetical**: `-(error OR warning OR failure)`
   ```yaml
   subject:
     not:
       any:
         - error
         - warning
         - failure
   ```

### AND Patterns (`all` operator)

Gmail supports explicit AND operations:

1. **Explicit AND**: `invoice AND paid AND 2024`
   ```yaml
   has:
     all:
       - invoice
       - paid
       - '2024'
   ```

2. **Parentheses with implicit AND**: `(term1 term2 term3)`
   ```yaml
   has:
     all:
       - term1
       - term2
       - term3
   ```

### Complex Patterns

The inference engine handles nested combinations:

1. **Mixed OR and AND**: `(bug OR issue) AND fixed`
   ```yaml
   has:
     all:
       - any:
           - bug
           - issue
       - fixed
   ```

2. **Negated complex patterns**: `-(error OR warning) AND critical`
   ```yaml
   has:
     all:
       - not:
           any:
             - error
             - warning
       - critical
   ```

## Benefits

1. **Readability**: YAML operators are more readable than Gmail's search syntax
2. **Maintainability**: Easier to understand and modify filter logic
3. **Type Safety**: Clear structure makes it easier to validate filters
4. **Consistency**: Uniform representation of logical operations

## Examples

### Before (Gmail XML export):
```xml
<apps:property name='from' value='alice@example.com OR bob@example.com OR charlie@example.com'/>
<apps:property name='hasTheWord' value='invoice AND paid AND -cancelled'/>
<apps:property name='subject' value='{urgent important critical}'/>
```

### After (with operator inference):
```yaml
from:
  any:
    - alice@example.com
    - bob@example.com
    - charlie@example.com

has:
  all:
    - invoice
    - paid
    - not: cancelled

subject:
  any:
    - urgent
    - important
    - critical
```

## Limitations

1. **Context Sensitivity**: The inference is pattern-based and may occasionally misinterpret text that happens to contain words like "OR" or "AND"
2. **Quoted Strings**: Currently doesn't handle quoted strings within patterns
3. **Field Lists**: Gmail's `list:` field has special semantics that aren't converted

## Combining with Other Features

Operator inference works well with other conversion features:

```bash
# Combine all inference features
gmail-yaml-filters convert mailFilters.xml \
  --merge-filters \
  --infer-more \
  --infer-operators \
  --infer-strategy interactive \
  -o filters.yaml
```

This will:
1. Merge filters that differ only in labels
2. Infer hierarchical "more" structures
3. Convert OR/AND/NOT patterns to operators
4. Prompt for confirmation on ambiguous merges