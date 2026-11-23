"""Tests for the constants module."""

from andalus.constants import MT_TRANSLATION, REACTION_LABELS, get_mt_number


def test_mt_translation_dict():
    """Test that MT_TRANSLATION dictionary is properly defined."""
    assert isinstance(MT_TRANSLATION, dict)
    assert len(MT_TRANSLATION) > 0
    # Test some known values
    assert MT_TRANSLATION["total xs"] == 1
    assert MT_TRANSLATION["mt 18 xs"] == 18
    assert MT_TRANSLATION["mt 102 xs"] == 102
    assert MT_TRANSLATION["nubar total"] == 452


def test_reaction_labels_cover_mt_translation():
    """Every MT that Serpent sensitivities can produce has a reaction label."""
    assert set(MT_TRANSLATION.values()) <= set(REACTION_LABELS)
    for plain, latex in REACTION_LABELS.values():
        assert isinstance(plain, str) and isinstance(latex, str)


def test_get_mt_number_known_label():
    """Test get_mt_number with known labels."""
    assert get_mt_number("total xs") == 1
    assert get_mt_number("mt 18 xs") == 18
    assert get_mt_number("mt 102 xs") == 102
    assert get_mt_number("nubar total") == 452


def test_get_mt_number_case_insensitive():
    """Test that get_mt_number is case insensitive."""
    assert get_mt_number("TOTAL XS") == 1
    assert get_mt_number("Total Xs") == 1
    assert get_mt_number("MT 18 XS") == 18


def test_get_mt_number_unknown_label():
    """Test get_mt_number with unknown label returns 999."""
    assert get_mt_number("unknown_reaction") == 999
    assert get_mt_number("non_existent") == 999
    assert get_mt_number("") == 999
