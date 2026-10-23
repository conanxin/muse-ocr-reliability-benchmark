#!/usr/bin/env python3
"""P18 pipeline: render 300/360 DPI, background-flatten ALL tier images,
OCR all tiers (200 DPI body baseline). Gold was sealed before this runs.

AMENDMENT (2026-10-23): raw Google Books photographic scans return SILENT
EMPTY OCR from Tesseract 5.3.4 PSM 3 (exit 0, no warning) on 7 of 10 pages
(grey page surround defeats its binarization). A uniform background-
flattening step (grey -> divide by heavily blurred background -> 255) is
therefore applied to every tier image before OCR. This conditions the OCR
input only; page selection, the frozen detector and the protocol are
unchanged. P14-P17 Internet Archive scans did not need this step.
"""
import hashlib, json, subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
PAGES = [72, 153, 233, 314, 395, 475, 556, 637, 718, 798]
PDF = HERE / "source/middle_kingdom_1883_williams_v1.pdf"
TESS = Path.home() / "tess-local/bin/tesseract"
TD = Path.home() / "tess-local/tessdata"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def flatten(src: Path, dst: Path):
    im = Image.open(src).convert("L")
    bg = (im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
            .resize(im.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(30)))
    a = np.asarray(im).astype(np.float32)
    b = np.asarray(bg).astype(np.float32)
    norm = np.clip(a / np.maximum(b, 1) * 255, 0, 255).astype(np.uint8)
    Image.fromarray(norm).save(dst)


def nonempty(p: Path):
    return p.exists() and p.stat().st_size > 0


def main():
    man = {"pdf_sha256": sha(PDF),
           "tesseract": subprocess.run([str(TESS), "--version"], capture_output=True, text=True).stdout.splitlines()[0],
           "tessdata_sha256": sha(TD / "eng.traineddata"), "psm": 3,
           "preprocessing": "background_flatten (uniform, all tiers): grayscale; background = 1/8 downscale + upscale + GaussianBlur(30); pixel = clip(px/bg*255). Reason: silent empty OCR on raw photographic scans (see docstring).",
           "tiers": {}}
    for dpi in (200, 300, 360):
        (HERE / f"work/ocr_{dpi}").mkdir(parents=True, exist_ok=True)
        (HERE / "work/tsv").mkdir(parents=True, exist_ok=True)
        (HERE / f"work/flat_{dpi}").mkdir(parents=True, exist_ok=True)
        man["tiers"][str(dpi)] = {}
        for pg in PAGES:
            tag = f"p{pg:04d}"
            img = HERE / f"work/scans/{tag}.png" if dpi == 200 else HERE / f"work/scans_{dpi}/{tag}.png"
            if dpi != 200 and not img.exists():
                subprocess.run(["pdftoppm", "-f", str(pg), "-l", str(pg), "-r", str(dpi),
                                "-gray", "-png", "-singlefile", str(PDF), str(img.with_suffix(""))], check=True)
            flat = HERE / f"work/flat_{dpi}/{tag}.png"
            if not nonempty(flat):
                flatten(img, flat)
            out = HERE / f"work/ocr_{dpi}/{tag}.txt"
            if not nonempty(out):
                subprocess.run([str(TESS), str(flat), str(out.with_suffix("")), "-l", "eng", "--psm", "3",
                                "--tessdata-dir", str(TD)], check=True, capture_output=True)
            if dpi == 200:
                tsv = HERE / f"work/tsv/{tag}.tsv"
                if not nonempty(tsv):
                    subprocess.run([str(TESS), str(flat), str(HERE / f"work/tsv/{tag}"), "-l", "eng", "--psm", "3",
                                    "--tessdata-dir", str(TD), "-c", "tessedit_create_tsv=1"], check=True, capture_output=True)
            man["tiers"][str(dpi)][tag] = {"image": str(img.relative_to(HERE)), "image_sha256": sha(img),
                                           "flat_sha256": sha(flat), "ocr_sha256": sha(out),
                                           "ocr_bytes": out.stat().st_size}
    (HERE / "work/pipeline_manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    empties = [f"{d}/{t}" for d, pages in man["tiers"].items() for t, v in pages.items() if v["ocr_bytes"] == 0]
    print("pipeline done; empty OCR outputs:", empties if empties else "none")


if __name__ == "__main__":
    main()
