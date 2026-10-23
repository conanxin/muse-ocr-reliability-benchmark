#!/usr/bin/env python3
"""pipeline.py — render + OCR a book PDF at three DPI tiers (v0.2.0).

Parameterized replacement for the hard-coded research script: PDF path,
page selection, work directory and tool locations are all arguments or
environment variables — nothing is tied to one book or one machine.

Environment:
  TESSERACT_BIN   tesseract binary (default: "tesseract" from PATH)
  TESSDATA_DIR    directory containing eng.traineddata (default: tesseract's own)
  PDFTOPPM_BIN    pdftoppm binary (default: "pdftoppm" from PATH)

Background flattening: photo-style grey scans (e.g. Google Books) can make
Tesseract SILENTLY return empty text (exit 0, no warning) because the grey
page margins dominate binarization. With --flatten (default), each render
is background-flattened before OCR: a heavily blurred copy estimates the
page background and every pixel is rescaled by it. The flattening applies
to the OCR input only, uniformly across tiers.

FAIL-CLOSED (R1): if any requested page not declared via --blank-pages
produces an empty OCR file at any tier, the run reports the exact pages
and exits 3. A page may be skipped only by naming it in --blank-pages,
which the caller must have verified against the source.

Exit codes: 0 ok; 2 missing tool/input; 3 empty OCR output.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TIERS = (200, 300, 360)


def flatten(src: Path, dst: Path) -> None:
    import numpy as np
    from PIL import Image, ImageFilter
    im = Image.open(src).convert("L")
    small = im.resize((max(1, im.width // 8), max(1, im.height // 8)))
    bg = small.resize(im.size).filter(ImageFilter.GaussianBlur(30))
    a = np.asarray(im).astype(np.float32)
    b = np.asarray(bg).astype(np.float32)
    out = np.clip(a / np.maximum(b, 1.0) * 255.0, 0, 255).astype("uint8")
    Image.fromarray(out).save(dst)


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"COMMAND FAILED: {' '.join(cmd)}\n{r.stderr[:400]}", file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True, help="comma-separated PDF page numbers")
    ap.add_argument("--work-dir", required=True, help="book work directory (ocr_*, scans* written under it)")
    ap.add_argument("--blank-pages", default="", help="comma-separated pages verified blank (plate pages)")
    ap.add_argument("--flatten", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--tesseract", default=os.environ.get("TESSERACT_BIN", "tesseract"))
    ap.add_argument("--tessdata-dir", default=os.environ.get("TESSDATA_DIR", ""))
    ap.add_argument("--pdftoppm", default=os.environ.get("PDFTOPPM_BIN", "pdftoppm"))
    a = ap.parse_args()
    pdf, work = Path(a.pdf), Path(a.work_dir)
    if not pdf.exists():
        print(f"INPUT_ERROR: PDF not found: {pdf}", file=sys.stderr)
        return 2
    pages = [int(x) for x in a.pages.split(",") if x.strip()]
    blanks = {int(x) for x in a.blank_pages.split(",") if x.strip()}
    for d in ("scans", "scans_300", "scans_360", "flat_200", "flat_300", "flat_360",
              "ocr_200", "ocr_300", "ocr_360", "tsv"):
        (work / d).mkdir(parents=True, exist_ok=True)
    tess = [a.tesseract] + (["--tessdata-dir", a.tessdata_dir] if a.tessdata_dir else [])
    manifest = {"pdf": str(pdf), "pages": pages, "blank_pages": sorted(blanks),
                "tesseract": a.tesseract, "flatten": a.flatten, "outputs": {}}
    for pg in pages:
        first = last = str(pg)
        for tier in TIERS:
            scan_dir = "scans" if tier == 200 else f"scans_{tier}"
            scan = work / scan_dir / f"p{pg:04d}.png"
            if not scan.exists():
                run([a.pdftoppm, "-f", first, "-l", last, "-r", str(tier), "-png",
                     "-singlefile", str(pdf), str(work / scan_dir / f"p{pg:04d}")])
            src = scan
            if a.flatten:
                flat = work / f"flat_{tier}" / f"p{pg:04d}.png"
                if not flat.exists():
                    flatten(scan, flat)
                src = flat
            out_base = work / f"ocr_{tier}" / f"p{pg:04d}"
            out_txt = Path(str(out_base) + ".txt")
            if not out_txt.exists():
                run(tess + [str(src), str(out_base), "-l", "eng", "--psm", "3"])
            manifest["outputs"].setdefault(str(pg), {})[str(tier)] = out_txt.stat().st_size
        tsv = work / f"tsv/p{pg:04d}.tsv"
        if not tsv.exists():
            # NOTE: some tessdata installs lack configs/; the 'tsv' config name is
            # then silently ignored and plain text comes out. The -c flag is the
            # reliable switch (research finding, P18).
            r = subprocess.run(tess + [str(work / f"flat_200/p{pg:04d}.png" if a.flatten else work / f"scans/p{pg:04d}.png"),
                                        str(work / f"tsv/p{pg:04d}"), "-l", "eng", "--psm", "3",
                                        "-c", "tessedit_create_tsv=1"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"TSV FAILED page {pg}: {r.stderr[:300]}", file=sys.stderr)
                return 2
    empty = [(pg, tier) for pg in pages if pg not in blanks
             for tier in TIERS
             if manifest["outputs"].get(str(pg), {}).get(str(tier), 0) == 0]
    (work / "pipeline_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    total = sum(v for per in manifest["outputs"].values() for v in per.values())
    print(f"pipeline done: {len(pages)} pages x {len(TIERS)} tiers, {total} OCR bytes; "
          f"blank-declared: {sorted(blanks)}")
    if empty:
        print(f"EMPTY_OCR_GATE_FAILED (fail-closed): empty OCR output at {empty} — "
              f"pages not declared blank; investigate the scan (background flattening?) "
              f"instead of proceeding.", file=sys.stderr)
        return 3
    print("PIPELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
