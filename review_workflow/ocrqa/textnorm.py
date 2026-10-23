"""Text normalization and edit distance (extracted from the research codebase).

normalize: NFC + collapse all whitespace runs to single spaces + strip.
This exact normalization is part of the measurement: gold and OCR are always
compared AFTER normalization, and any corrected string is re-normalized
before scoring (the P16 erratum: deleting punctuation can leave a double
space that otherwise inflates the edit count).
"""
from __future__ import annotations

import re
import unicodedata


def normalize(s: str) -> str:
    """NFC + collapse whitespace only; preserve punctuation and case."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def levenshtein(a: str, b: str) -> int:
    """Classic DP edit distance over Unicode code points."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,                # deletion
                current[j - 1] + 1,             # insertion
                previous[j - 1] + (ca != cb),   # substitution
            ))
        previous = current
    return previous[len(b)]
