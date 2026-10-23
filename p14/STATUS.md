## P15 measured follow-up (2026-10-23)

**P15_STATUS: MEASURED / COMPLETE.** The original P14 selected five gold pages (32,119,284,286,501), source PDF SHA and Tesseract 5.3.4 / eng tessdata 4.1.0 / PSM 3 were held constant. P14 200 DPI image and OCR SHA values were reproduced exactly.

| Render DPI | CER (char edits / 13,435) | WER (word edits / 2,356) |
|---:|---:|---:|
| **200** | **0.5657% (76)** | **1.4007% (33)** |
| 300 | 0.7890% (106) | 3.4805% (82) |
| 360 | 0.6848% (92) | 2.6316% (62) |

- 300 DPI adds 30 Levenshtein character edits and 49 word edits relative to 200 DPI; 360 adds 16 character edits and 29 word edits.
- 300 and 360 DPI reduce some period-as-comma substitutions, but letter-class error operations rise from 30 to 61/49, notably `i` becoming `1` or other letters.
- The supplementary `fixed/new` columns (300: 44/77, 360: 41/57) count **SequenceMatcher alignment sites**, not necessarily minimum Levenshtein edit operations. Their arithmetic must not be presented as exact CER delta.
- For these five pages and this OCR configuration, **retain 200 DPI**. This does not establish a universally optimal DPI, nor that P11's quality gates improved accuracy.
- Punctuation, single quotes, curly quotes and hyphen categories in `results.json` can overlap when an operation touches multiple classes. Do not add all class subtotals as if they partition CER.
- P15 artifacts: `p14/p15/manifest_p15.json`, `results.json`, `p15_analyze.py`, `ocr200/`, `ocr300/`, `ocr360/`, `diffs/`. Original PDF, gold transcripts and rendered PNG images remain local; public branch alone does not give a third party full source-to-gold reproducibility.

**Suggested next question (not yet tested):** Could disagreement among OCR resolutions flag questionable punctuation for manual verification without changing the 200 DPI output? This must be tested on **separate gold pages** before publishing any correction precision/recall numbers. No global punctuation rewrite or release changes.

---

# P14 · Independent Book Pilot / Current Status

**Status (2026-10-23): MEASURED / COMPLETE (Muse execution report).**  
This GitHub branch documents one independently selected English historical journal. It is **not** merged to `main`, and `v0.1.0` remains frozen.

## Source integrity and frozen sampling

- Book: *The Chinese Recorder and Missionary Journal*, vol. 27 (1896), IA item `s3039id1390153`.
- SOURCE_SHA256: `98342b582bbe86b35cfe68bfdabf749c8e3813c2b5a07e74f4ce3c8d658c3b9e`
- File size: 60,674,637 bytes; PDF: 636 pages.
- Download: direct IA PDF, no Wikimedia fallback.
- Preregistered pages: 32–36, 118–122, 284–288, 500–504 (20 of 20 OCR processed).
- Manual blind-gold pages: 32, 119, 284, 286, 501 (5 of 5, sealed before Tesseract OCR according to Muse's log).
- Environment: Tesseract 5.3.4, `eng` tessdata 4.1.0, PSM 3, `pdftoppm` grayscale render 200 DPI, native embedded main-image scan reported at 360 PPI.
- An apt package-index lock caused installation delay; official distribution .deb binaries were locally extracted without writing system dpkg state. Full hashes and details are in the Notion P14 report.

## Reported independent-book results

| PDF page | Char edits | Gold chars | CER |
|---|---:|---:|---:|
| 32 | 26 | 2,495 | 1.0421% |
| 119 | 14 | 2,969 | 0.4715% |
| 284 | 9 | 2,359 | 0.3815% |
| 286 | 13 | 2,777 | 0.4681% |
| 501 | 14 | 2,835 | 0.4938% |
| **Total** | **76** | **13,435** | **0.5657%** |

- Strict CER: `76 / 13435 = 0.5657%`
- Strict WER: `33 / 2356 = 1.4007%`
- Historical P14 unit tests: 6/6 PASS; OCR pages: 20/20; blind gold: 5/5.
- OMISSION_RECALL: **NOT_MEASURED**, no independent omission-line labels.
- AI_MISCORRECTION: **NOT_MEASURED**, no AI-correction arm.
- Notion original results: https://app.notion.com/p/40234a28189a81efbb3fd83acd8f42cd

## Most important residual errors

- Punctuation is disproportionately represented: period read as comma ~10 times; curly quotes read as other glyphs (¢, «, ¥, *).
- PDF p32 contains nested quotations and has the highest measured page CER (1.0421%); the other measured pages are ~0.38%–0.49%.
- Gold transcription conventions (line-end hyphens, historical punctuation spacing, printer typos) were fixed before OCR and should remain frozen.

## Evidence boundary

The aggregate arithmetic and five per-page CER ratios have been checked independently against the reported counts. The **raw PDF, OCR outputs, full gold transcripts and scoring artifacts are not included on this public experiment branch**, so the reported 5-page gold is **not independently re-audited at the character level** from this repository alone.

The 0.5657% score is a **selected five-page sample for one historical periodical**, not a general English OCR accuracy figure. Approximate character-level binomial 95% intervals assume independence and are not a substitute for page-clustered inference; with only five pages, avoid strong confidence claims.

This is a baseline measurement for one OCR engine. **It does not measure whether P11's quality gates improve OCR**, because no treatment-vs-baseline arm was run.

## Follow-up recommendation (not yet executed)

P15: same frozen five-page gold, paired 200 DPI vs 300/360 DPI OCR at fixed engine and PSM; report page-by-page total, punctuation-only and non-punctuation edit deltas and regression count. No global punctuation normalization. If rule-based punctuation correction is later studied, use separately held-out pages to avoid tuning on this already-examined gold.

---

## Historical pre-run state (preserved)

# P14 Gate / Status

As of 2026-10-23:

- SOURCE_IDENTIFIED: YES; Commons PD-marked archive volume 27 (1896), IA `s3039id1390153`
- PDF_ACQUIRED: NO (archive.org/Wikimedia access timeout in current environment)
- PAGES_PRE_REGISTERED: YES, 20; blind-gold subset 5
- PILOT_SCRIPT_READY: YES
- UNIT_TESTS: 6/6 PASS (code-only)
- SYNTHETIC_METRIC_SMOKE: PASS (code-only, not a real OCR score)
- ACTUAL_OCR_PAGES: 0/20
- MANUALLY_VERIFIED_GOLD: 0/5
- STRICT_CER: NOT_MEASURED
- WER: NOT_MEASURED
- OMISSION_RECALL: NOT_MEASURED
- AI_MISCORRECTION: NOT_MEASURED

GitHub v0.1.0 remains frozen. Files here are a development experiment and do not supersede the released benchmark.
