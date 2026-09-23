"""Writer for ASCII ACE files.

See ``andalus.ace.reader`` for the format references this module builds on
(the ACE format specification and the ``endf-python`` reader used for
cross-checking).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from andalus.ace.reader import _XSS_START_LINE

if TYPE_CHECKING:
    from andalus.ace.core import ACE

#: XSS entries are packed 4 per 80-character line (20 characters/field),
#: independent of record boundaries (e.g. the MTR block can start
#: mid-line right after the ESZ block ends) — confirmed by comparing
#: JXS pointers to their actual line/column position in a sample file.
_VALUES_PER_LINE = 4
_FIELD_WIDTH = 20
_FIELD_PRECISION = 11


def write_ace(ace: ACE, filepath: str) -> None:
    """Write an :class:`~andalus.ace.core.ACE` instance to an ASCII ACE file.

    Parameters
    ----------
    ace : ACE
        The (possibly perturbed) ACE instance to write.
    filepath : str
        Output path.
    """
    lines = list(ace._raw_lines[:_XSS_START_LINE])  # header/IZAW/NXS/JXS, untouched
    lines.extend(_format_xss_lines(ace))

    with open(filepath, "w") as f:
        f.writelines(lines)


def _format_xss_lines(ace: ACE) -> list[str]:
    """Re-serialize the XSS array, reusing original text for unchanged entries."""
    xss = ace.xss
    original = ace._original_xss
    tokens = ace._xss_tokens

    fields = [
        tokens[i].rjust(_FIELD_WIDTH) if xss[i] == original[i] else f"{xss[i]:{_FIELD_WIDTH}.{_FIELD_PRECISION}E}"
        for i in range(len(xss))
    ]

    lines = []
    for start in range(0, len(fields), _VALUES_PER_LINE):
        chunk = fields[start : start + _VALUES_PER_LINE]
        lines.append("".join(chunk) + "\n")
    return lines
