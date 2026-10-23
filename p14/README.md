# P14 · Cross-book Independent OCR Pilot (Unreleased Experiment)

**Status (2026-10-23): protocol and scripts ready; independent-book OCR NOT RUN.**

P14 checks whether selected quality methods learned from the Chinese book *访美观感* carry over to a separate **English historical periodical**. It is deliberately isolated from the 433-case same-book dataset.

## Source and preregistered pages

- *The Chinese Recorder and Missionary Journal*, vol. 27 (1896), IA item `s3039id1390153`.
- [Wikimedia Commons public-domain scan record](https://commons.wikimedia.org/wiki/File:The_Chinese_recorder_and_missionary_journal_(IA_s3039id1390153).pdf).
- [Internet Archive file](https://archive.org/download/s3039id1390153/s3039id1390153.pdf).
- Registered 20 PDF pages (1-based): **32–36, 118–122, 284–288, 500–504**.
- Blind human-gold sample: **32, 119, 284, 286, 501**.

The source PDF has **not** yet been downloaded or page-inspected in this experiment. Selection was fixed before viewing OCR predictions. Do not silently replace excluded/difficult pages.

## Run

Requires Poppler tools (`pdfinfo`, `pdftoppm`, `pdfimages`), Tesseract with `eng` and Python standard library:

```bash
cd p14
mkdir -p source
# Download verified PDF to source/the_chinese_recorder_1896_v27.pdf
python3 p14.py prepare --pdf source/the_chinese_recorder_1896_v27.pdf --out work
# Independently transcribe work/scans/p0032.png, p0119.png, p0284.png, p0286.png, p0501.png
# as work/gold/p0032.txt, ... BEFORE revealing work/ocr/ predictions.
python3 p14.py ocr --out work
python3 p14.py score --out work
python3 -m unittest discover -s tests -v
```

The runner locks input PDF SHA-256 and the selection manifest, preserves native embedded-image DPI inventories separately from 200 DPI rendering, seals blind-gold files, and only computes strict CER/WER on pages with ground truth.

### Reporting constraints

- Missing gold is **NOT_MEASURED**, never zero CER.
- Omission recall needs independently source-verified labeled omissions.
- AI miscorrection needs reviewed applied edits; rejected bad proposals are recorded separately.
- Prior 33/35 history and 39.25% error-sample CER **are not P14 results**.
- Do not change P9/P10 source texts, GitHub `v0.1.0` tag or the original research data.
- Full protocol notes and progress are maintained in the project's Notion P14 research page.

## Validation status

Local code-only checks: 6/6 unit tests and one synthetic scoring smoke test passed before uploading to this branch. **20-page OCR, 5-page blind-gold transcriptions and independent CER/WER remain pending.**

This is an experimental branch, not a release; do not merge performance claims without source files and inspectable measured evidence.
