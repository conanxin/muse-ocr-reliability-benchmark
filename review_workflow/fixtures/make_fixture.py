#!/usr/bin/env python3
"""Regenerate the tiny synthetic book fixture (fixtures/synthetic_book/).

The fixture is fully synthetic: both "pages" are short invented English
passages written for this repository, the page images are drawn with PIL,
and the three OCR tiers are derived from the baseline by scripted
punctuation changes. No scanned book, no copyrighted text, no external
data. It exists so a clean clone can run the whole review workflow:

    lint -> queue -> decide -> apply -> score

Designed detector flags (baseline 200 vs 300/360):
  p101 F1 ':' read as ';' by 300/360   -> gold has ':'  (KEEP)
  p101 F2 ASCII ' read as ’ by 300/360 -> gold has ’    (CONFIRM_FIX ’)
  p101 F3 missing '.' supplied by 300/360 after "all"   (CONFIRM_FIX .)
  p102 F4 ':' read as ';' by 300/360   -> gold has ':'  (KEEP)
  p102 F5 ASCII ' read as ’ by 300/360 -> gold has ’    (CONFIRM_FIX ’)
p102 also contains the literal text "a<b and c>d" near F5: it exercises
HTML escaping in queue.html (must appear as a&lt;b, never as markup).

Run:  python3 make_fixture.py            (writes ./synthetic_book/)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOK = HERE / "synthetic_book"
SCALE = 360 / 200  # TSV boxes are written in 200-DPI space; scan is 360 DPI

BASE = {
    101: ("The harbour at dawn was quiet, and the ferries moved slowly across the water. "
          "Mr. Alden, the editor's assistant, counted the crates twice: forty one boxes "
          "in all A note in the margin said see plate in pencil."),
    102: ("By noon the rain: the road to the ferry was empty. Outside the mayor's office, "
          "he wrote a<b and c>d on the slate. The clerk nodded, filed the letter, "
          "and locked the drawer."),
}
GOLD = {
    101: BASE[101].replace("editor's", "editor’s").replace("in all A note", "in all. A note"),
    102: BASE[102].replace("mayor's", "mayor’s"),
}
# 300 and 360 tiers agree with each other and differ from the baseline at the loci.
ALT = {
    101: (BASE[101].replace("twice:", "twice;").replace("editor's", "editor’s")
          .replace("in all A note", "in all. A note")),
    102: BASE[102].replace("rain:", "rain;").replace("mayor's", "mayor’s"),
}


def wrap(words, per_line=9):
    return [words[i:i + per_line] for i in range(0, len(words), per_line)]


def draw_page(pg: int):
    """Draw the baseline text on a 360-DPI canvas; return TSV rows (200-DPI space)."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    W, H = 1240, 520
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    words = BASE[pg].split(" ")
    rows, x, y = [], 60, 50
    for line in wrap(words):
        x = 60
        for w in line:
            tw = dr.textlength(w, font=font)
            dr.text((x, y), w, fill="black", font=font)
            rows.append((w, x / SCALE, y / SCALE, tw / SCALE, 30 / SCALE))
            x += tw + 16
        y += 52
    out = BOOK / f"work/scans_360/p{pg:04d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return rows


def main() -> None:
    for d in ("gold", "work/ocr_200", "work/ocr_300", "work/ocr_360", "work/tsv", "work/scans_360"):
        (BOOK / d).mkdir(parents=True, exist_ok=True)
    for pg in (101, 102):
        (BOOK / f"work/ocr_200/p{pg:04d}.txt").write_text(BASE[pg] + "\n")
        for tier in (300, 360):
            (BOOK / f"work/ocr_{tier}/p{pg:04d}.txt").write_text(ALT[pg] + "\n")
        (BOOK / f"gold/p{pg:04d}.txt").write_text(GOLD[pg] + "\n")
        rows = draw_page(pg)
        with (BOOK / f"work/tsv/p{pg:04d}.tsv").open("w") as fh:
            fh.write("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
            for i, (w, l, t, wd, ht) in enumerate(rows):
                fh.write(f"5\t1\t1\t1\t1\t{i}\t{int(l)}\t{int(t)}\t{int(wd)}\t{int(ht)}\t95\t{w}\n")
    seal = {f"p{pg:04d}.txt": hashlib.sha256((BOOK / f"gold/p{pg:04d}.txt").read_bytes()).hexdigest()
            for pg in (101, 102)}
    (BOOK / "gold_seal.json").write_text(json.dumps({"files": seal}, indent=1) + "\n")
    (BOOK / "book.json").write_text(json.dumps({
        "title": "Synthetic fixture book (invented text, not a real publication)",
        "pages": [101, 102], "blank_pages": [],
        "gold_dir": "gold", "seal": "gold_seal.json",
        "tiers": [200, 300, 360], "baseline_tier": 200, "crop_tier": 360,
        "control_seed": 7}, indent=1) + "\n")
    print(f"fixture written to {BOOK}")


if __name__ == "__main__":
    main()
