#!/usr/bin/env python3
"""P17 pipeline: render 300/360 DPI, OCR all three tiers, run the FROZEN
P16 detector (imported byte-identically, SHA verified), emit flags.
Gold is never touched here."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # p14/
P17 = ROOT / "p17"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "p16"))
from p14 import normalize  # noqa: E402
import detector  # noqa: E402  (p16/detector.py, frozen)

TESS = str(Path.home() / "tess-local/bin/tesseract")


def ocr_page(img: Path) -> str:
    out = subprocess.run([TESS, str(img), "stdout", "-l", "eng", "--psm", "3"],
                         check=True, capture_output=True, text=True)
    return out.stdout

PAGES = [52, 100, 148, 197, 244, 292]
PDF = P17 / "source/chinese_characteristics_1894_smith.pdf"
FROZEN_SHA = "fd3142bb77a42a5598aa13ce7646ed97f1ab2de996005114fe2c082e335fe478"


def main() -> int:
    det_bytes = (ROOT / "p16/detector.py").read_bytes()
    sha = hashlib.sha256(det_bytes).hexdigest()
    assert sha == FROZEN_SHA, f"detector.py hash drift: {sha}"
    print("detector.py SHA verified:", sha[:16], "...")

    for dpi, sub in [(200, "work/ocr"), (300, "work/ocr300"), (360, "work/ocr360")]:
        outdir = P17 / sub
        outdir.mkdir(parents=True, exist_ok=True)
        scandir = P17 / f"work/scans{dpi if dpi != 200 else ''}"
        scandir.mkdir(parents=True, exist_ok=True)
        for p in PAGES:
            img = scandir / f"p{p:04d}.png"
            if not img.exists():
                subprocess.run(
                    ["pdftoppm", "-f", str(p), "-l", str(p), "-r", str(dpi),
                     "-gray", "-png", "-singlefile", str(PDF),
                     str(scandir / f"p{p:04d}")],
                    check=True)
            txt = outdir / f"p{p:04d}.txt"
            if not txt.exists():
                txt.write_text(ocr_page(img), encoding="utf-8")
            print(f"dpi{dpi} p{p}: ocr {txt.stat().st_size}B")

    flags_dir = P17 / "flags"
    flags_dir.mkdir(exist_ok=True)
    total = 0
    for p in PAGES:
        b = normalize((P17 / f"work/ocr/p{p:04d}.txt").read_text(encoding="utf-8"))
        o3 = normalize((P17 / f"work/ocr300/p{p:04d}.txt").read_text(encoding="utf-8"))
        o6 = normalize((P17 / f"work/ocr360/p{p:04d}.txt").read_text(encoding="utf-8"))
        flags = detector.detect(b, o3, o6)
        with open(flags_dir / f"p{p:04d}.jsonl", "w", encoding="utf-8") as fh:
            for i, fl in enumerate(flags, 1):
                fl["flag_id"] = f"p{p:04d}-{i:03d}"
                fh.write(json.dumps(fl, ensure_ascii=False) + "\n")
        total += len(flags)
        print(f"p{p}: {len(flags)} flags")
    print("TOTAL FLAGS:", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
