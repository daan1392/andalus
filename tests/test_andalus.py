"""Tests for `andalus` package."""

import andalus
from andalus.utils import add


def test_import():
    """Verify the package can be imported."""
    assert andalus


def test_add():
    assert add(1, 2) == 3
