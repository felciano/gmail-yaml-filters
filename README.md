# gmail-yaml-filters

[![Build Status](https://github.com/mesozoic/gmail-yaml-filters/workflows/Tests/badge.svg?branch=master)](https://github.com/mesozoic/gmail-yaml-filters/actions?workflow=Tests)

A quick tool for generating Gmail filters from YAML rules.

Interested in helping? See [CONTRIBUTING.md](CONTRIBUTING.md) for a few guidelines.

## Getting Started

It's strongly recommended to use a tool like [pipx](https://pypa.github.io/pipx/)
to install this package in an isolated environment:

```bash
$ pipx install gmail-yaml-filters
```

## Generating XML

By default, the command line script will generate XML to stdout, which
you can then upload to Gmail yourself:

```bash
# Original behavior (still works for backward compatibility)
$ gmail-yaml-filters my-filters.yaml > my-filters.xml

# Explicit export command (recommended)
$ gmail-yaml-filters export my-filters.yaml -o my-filters.xml
```

## Converting Between XML and YAML

The tool supports bidirectional conversion between Gmail's XML export format and YAML.
All Gmail-specific properties are preserved to ensure perfect round-trip conversion.

```bash
# Convert Gmail XML export to YAML (auto-detects format)
$ gmail-yaml-filters convert mailFilters.xml -o my-filters.yaml

# Convert YAML back to Gmail XML for re-import
$ gmail-yaml-filters convert my-filters.yaml -o filters.xml

# Force output format if needed
$ gmail-yaml-filters convert filters.xml --to yaml -o output.yaml

# Clean up output by removing Gmail's default values
$ gmail-yaml-filters convert mailFilters.xml --smart-clean -o clean.yaml

# Show detailed conversion information
$ gmail-yaml-filters convert mailFilters.xml --verbose -o my-filters.yaml

# Fail if unsupported Gmail properties are encountered
$ gmail-yaml-filters convert mailFilters.xml --fail-on-unsupported-properties
```

## Validating Round-trip Conversion

Validate that your filters can be converted from XML to YAML and back without data loss:

```bash
# Validate round-trip conversion (XML → YAML → XML)
$ gmail-yaml-filters validate mailFilters.xml

# Show detailed validation information
$ gmail-yaml-filters validate mailFilters.xml --verbose
```

## Synchronization via Gmail API

You can authorize the script to manage your Gmail filters via the API.
Before using these commands, you will need to create
[`client_secret.json`](https://developers.google.com/identity/protocols/oauth2/web-server#creatingcred)
and store it in the same directory as your YAML file.

```bash
# Upload all filters (and create new labels) from the configuration file
$ gmail-yaml-filters upload my-filters.yaml

# Delete any filters that aren't defined in the configuration file
$ gmail-yaml-filters prune my-filters.yaml

# Do both of these steps at once (upload + prune)
$ gmail-yaml-filters sync my-filters.yaml

# See what would happen but don't apply any changes
$ gmail-yaml-filters sync --dry-run my-filters.yaml

# Also remove unused labels when pruning
$ gmail-yaml-filters prune --prune-labels my-filters.yaml
$ gmail-yaml-filters sync --prune-labels my-filters.yaml
```

If you need to pipe configuration from somewhere else, you can do that
by passing a single dash as the filename.

```sh
# (but why would you need to do this?)
$ cat filters.yaml | gmail-yaml-filters --sync -
```

## Sample Configuration

```yaml
# Simple example
-
  from: googlealerts-noreply@google.com
  label: news
  not_important: true

# Boolean conditions
-
  from:
    any:
      - alice
      - bob
      - carol
  to:
    all: [me, -MyBoss]
  label: conspiracy

# Nested conditions
-
  from: lever.co
  label: hiring
  more:
    -
      has: 'completed feedback'
      archive: true
    -
      has: 'what is your feedback'
      star: true
      important: true

# Foreach loops
-
  for_each:
    - list1
    - list2
    - list3
  rule:
    to: "{item}@mycompany.com"
    label: "{item}"

# Foreach loops with complex structures
-
  for_each:
    - [mailing-list-1a, list1]
    - [mailing-list-1b, list1]
    - [mailing-list-1c, list1]
    - [mailing-list-2a, list2]
    - [mailing-list-2b, list2]
  rule:
    to: "{item[0]}@mycompany.com"
    label: "{item[1]}"
-
  for_each:
    - {list: list1, domain: example.com}
    - {list: list2, domain: whatever.com}
  rule:
    to: "{list}@{domain}"
    label: "{list}"
```

## Configuration

Supported conditions:

* `has` (also `match`)
* `does_not_have` (also `missing`, `no_match`)
* `subject`
* `list`
* `labeled`
* `from`, `to`, `cc`, and `bcc`
* `category`
* `deliveredto`
* `filename`
* `larger`
* `smaller`
* `size`
* `rfc822msgid`
* `is` and `has` work like [Gmail's search operators](https://support.google.com/mail/answer/7190?hl=en), for example:
  * `has: attachment` is translated to `match: "has:attachment"`
  * `is: -snoozed` is translated to `no_match: "is:snoozed"`

Supported actions:

* `archive`
* `forward`
* `important` (also `mark_as_important`)
* `label`, including support for Gmail's [category tabs](https://developers.google.com/gmail/api/guides/labels):
  * `CATEGORY_PERSONAL`
  * `CATEGORY_SOCIAL`
  * `CATEGORY_PROMOTIONS`
  * `CATEGORY_UPDATES`
  * `CATEGORY_FORUMS`
* `not_important` (also `never_mark_as_important`)
* `not_spam`
* `read` (also `mark_as_read`)
* `star`
* `trash` (also `delete`)

Any set of rules with `ignore: true` will be ignored and not written to XML.

## Similar Projects

* [gmail-britta](https://github.com/antifuchs/gmail-britta) is written in Ruby and lets you express rules with a DSL.
* [gmail-filters](https://github.com/dimagi/gmail-filters) is written in Python and has a web frontend.
* [google-mail-filter](https://hackage.haskell.org/package/google-mail-filters) is written in Haskell and lets you express rules with a DSL.
* [Gefilte Fish](https://github.com/nedbat/gefilte) is written in Python and lets you express rules with a DSL.
