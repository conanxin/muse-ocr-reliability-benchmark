#!/usr/bin/env python3
"""P16 punctuation-disagreement detector (FROZEN at freeze time; see FREEZE.json).

Idea: the 200-DPI OCR is the sole baseline text. The 300/360-DPI OCRs of the
same page are used ONLY to locate positions where the three readings disagree
about punctuation identity. A human then checks each flagged position against
the page image. The detector never modifies any text.

Method (deterministic):
  1. Normalize all three OCR texts with p14.normalize (NFC + whitespace fold).
  2. Align the 300 and 360 texts to the 200 baseline with
     difflib.SequenceMatcher opcodes. For every baseline character index and
     every baseline insertion point, collect the aligned reading of each DPI
     (a string: the aligned substring, or ABSENT for a deletion).
  3. Punctuation identity of a reading:
       - single char in PUNCT_SET            -> that char
       - multi-char containing a PUNCT_SET  -> 'PUNCT+'
       - ABSENT                             -> 'ABSENT'
       - anything else (letter/digit/space) -> 'OTHER'
  4. Flag a position when the three identities are NOT all equal AND at
     least one reading has a punctuation identity (a PUNCT_SET char or
     PUNCT+). Pure letter/digit disagreements (the typical high-DPI noise,
     e.g. i->1) never flag, because no reading is punctuation.
  5. Merge flagged positions whose baseline indices are <=2 apart into one
     flag item spanning the union; attach the three readings over the span
     and +/-30 chars of baseline context.

Inputs: three OCR text files. Output: JSONL flags (no gold is ever read).
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from p14 import normalize  # noqa: E402

PUNCT_SET = set(".,;:!?") | set("“”„«»¢¥") | set("‘’'\"") | set("-—–=") | set("*")
MERGE_GAP = 2
CONTEXT = 30


def identity(reading: str | None) -> str:
    if reading is None:
        return "ABSENT"
    if len(reading) == 1 and reading in PUNCT_SET:
        return reading
    if any(c in PUNCT_SET for c in reading):
        return "PUNCT+"
    return "OTHER"


def aligned_readings(base: str, other: str):
    """Return (per-index readings, per-point insertions) of `other` vs `base`."""
    sm = difflib.SequenceMatcher(None, base, other, autojunk=False)
    per_index: dict[int, str | None] = {}
    per_point: dict[int, str] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                per_index[i1 + k] = other[j1 + k]
        elif tag == "replace":
            for k in range(i2 - i1):
                per_index[i1 + k] = other[j1:j2] if k == 0 else None
            # first index carries the whole replacement string; rest ABSENT
            for k in range(1, i2 - i1):
                per_index[i1 + k] = None
        elif tag == "delete":
            for k in range(i1, i2):
                per_index[k] = None
        elif tag == "insert":
            per_point[i1] = other[j1:j2]
    return per_index, per_point


def detect(base: str, o300: str, o360: str) -> list[dict]:
    idx300, pt300 = aligned_readings(base, o300)
    idx360, pt360 = aligned_readings(base, o360)
    # items: (sort_pos, end_pos, kind, key, reading200, reading300, reading360)
    items: list[tuple] = []

    def consider(kind, key, sort_pos, end_pos, r_base, r_300, r_360):
        ids = (identity(r_base), identity(r_300), identity(r_360))
        punct_involved = any(i in PUNCT_SET or i == "PUNCT+" for i in ids)
        if len(set(ids)) > 1 and punct_involved:
            items.append((sort_pos, end_pos, kind, key, r_base, r_300, r_360))

    # opcode coverage guarantees every baseline index has an aligned reading
    for i, ch in enumerate(base):
        consider("char", i, i, i + 1, ch, idx300[i], idx360[i])
    for pt in sorted(set(pt300) | set(pt360)):
        consider("ins", pt, pt, pt, "", pt300.get(pt), pt360.get(pt))

    items.sort(key=lambda t: (t[0], 0 if t[2] == "ins" else 1))
    groups: list[list[tuple]] = []
    for it in items:
        if groups and it[0] - max(x[1] for x in groups[-1]) <= MERGE_GAP:
            groups[-1].append(it)
        else:
            groups.append([it])
    flags: list[dict] = []
    for g in groups:
        s = min(x[0] for x in g)
        e = max(x[1] for x in g)
        flags.append({
            "base_span": [s, e],
            "base_text": base[s:e],
            "context": base[max(0, s - CONTEXT):e + CONTEXT],
            "positions": [
                {"kind": x[2], "base_index": x[3],
                 "reading_200": x[4], "reading_300": x[5], "reading_360": x[6]}
                for x in g
            ],
        })
    return flags


def main(argv: list[str]) -> int:
    # usage: detector.py PAGE BASE200 OCR300 OCR360 OUT.jsonl
    page, f200, f300, f360, out = argv[1], Path(argv[2]), Path(argv[3]), Path(argv[4]), Path(argv[5])
    base = normalize(f200.read_text(encoding="utf-8"))
    o300 = normalize(f300.read_text(encoding="utf-8"))
    o360 = normalize(f360.read_text(encoding="utf-8"))
    flags = detect(base, o300, o360)
    with out.open("w", encoding="utf-8") as fh:
        for i, fl in enumerate(flags):
            fh.write(json.dumps({"page": int(page), "flag_id": f"p{int(page):04d}-{i:03d}", **fl},
                                ensure_ascii=False) + "\n")
    print(f"page {page}: {len(flags)} flags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
