from io import StringIO
import sys

import pytest

from gmail_yaml_filters.main import load_yaml_filters
from gmail_yaml_filters.ruleset import RuleSet


@pytest.fixture
def tmpconfig(tmp_path):
    fpath = tmp_path / "tmp.yaml"
    fpath.write_text(
        """
        - has: attachment
          archive: true
        - to: alice
          label: foo
        """
    )
    return fpath


def test_load_yaml_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", StringIO("- has: attachment\n  archive: true"))
    ruleset = load_yaml_filters("-")
    assert isinstance(ruleset, RuleSet)
    assert len(ruleset.rules) == 1


def test_load_yaml_from_filename(tmpconfig):
    ruleset = load_yaml_filters(str(tmpconfig))
    assert isinstance(ruleset, RuleSet)
    assert len(ruleset.rules) == 2


def test_load_yaml_handles_single_rule(tmp_path):
    fpath = tmp_path / "single.yaml"
    fpath.write_text("has: attachment\narchive: true")
    ruleset = load_yaml_filters(str(fpath))
    assert isinstance(ruleset, RuleSet)
    assert len(ruleset.rules) == 1


def test_load_yaml_ignores_rules_with_ignore_flag(tmp_path):
    fpath = tmp_path / "ignored.yaml"
    fpath.write_text(
        """
        - has: attachment
          archive: true
        - to: alice
          label: foo
          ignore: true
        """
    )
    ruleset = load_yaml_filters(str(fpath))
    assert len(ruleset.rules) == 1  # Only one rule, the ignored one is filtered out
