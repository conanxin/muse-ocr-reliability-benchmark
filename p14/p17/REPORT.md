# P17 — P16 reconciliation + independent validation on a second book (2026-10-23)

## Part 1 — P16 score reconciliation (ChatGPT cross-check)

- ChatGPT's independent recount (23 / **15** / 24 / 9 = **71**) is CORRECT;
  the P16 report's 72 (p120 = 16) was wrong by one edit, on p120 only.
- Root cause: `p16/evaluate.py` scored the raw in-memory corrected string;
  the p0120-007 fix (delete a spurious ':') leaves a double space that the
  protocol scoring (normalize, then Levenshtein) collapses. Isolated rerun
  reproduced the original outputs bit-identically — definitional defect,
  not environment drift.
- Disposition: `p16/ERRATUM.md` + `p16/eval_results_v2.json` issued;
  original `eval_results.json` preserved. **P16 final CER_after =
  71/10,936 = 0.6492%** (CER_before 0.8687%, P/R, TP/FP/FN unchanged).
- Gold apostrophe recheck: all 10 v1→v2 sites re-inspected on 360-DPI
  crops — **10/10 typographic apostrophes**, v2 upheld
  (`p16/gold_apostrophe_recheck.json`, crops in `p16/apos_recheck/`).
  Both gold seal versions retained.

## Part 2 — P17 independent validation (new book)

Source: Arthur Henderson Smith, *Chinese Characteristics* (Fleming H.
Revell, 1894), IA `chinesecharacter00smitiala`, PDF SHA-256
`9bc540a0d8f26dac0c297ec14d6213f2fc75bb2668202650a7f97e91328bee72`,
388 pp. Public domain (1894 publication). A genuinely different book,
author, publisher and scan from the P14–P16 Recorder volume.

Design (preregistered in `PREREGISTRATION.json` before any OCR):
6 pages (PDF 52, 100, 148, 197, 244, 292; PDF 196 was a full-page plate
and was replaced by 197 under the preregistered plate rule). Gold
transcribed blind from page images and sealed BEFORE OCR; the P16
detector was reused byte-identically (SHA fd3142bb… verified at run
time) with no parameter changes; 200 DPI = text of record, 300/360 =
flag discovery only. Gold v2 (3 transcriber apostrophe slips of the
same U+0027 failure mode as P16, each verified on 360-DPI crops) is the
scoring gold; v1 seals retained.

### Results — adjudicated track (each flag judged on the page image)

- Flags: **25** (p52: 8, p100: 7, p148: 2, p197: 8, p244: 0, p292: 0)
- TP 7 / FP 18 → **Precision 28.0%**
- Independent punctuation census vs gold v2: 8 true error sites,
  7 covered, **FN 1** (spurious apostrophe in "cite'a", p197, from a
  print speck — no tier disagreed there) → **Recall 87.5%**
- Review load: 25 flags / 6 pages ≈ 4.2 per page;
  **3.57 reviews per confirmed fix** (7 fixes)
- CER (strict, protocol scoring): **0.3638% → 0.2391%**
  (35 → 23 edits over 9,620 gold chars; relative −34.3%)

### Results — mechanical track (p16 evaluate_page, region-based; reported separately, never mixed)

- Precision 5/25 = 20.0%; region recall 5/8 = 62.5%; FN regions 3.
- The mechanical rule undercounts exactly where P16 showed it would:
  speck-promoted punctuation and regions whose gold-side span carries
  no punctuation character.

### Reading of the result

- Recall transferred (87.5% vs P16's 85.2%): cross-DPI disagreement
  still finds most real punctuation errors on an unseen book.
- Precision fell (28.0% vs 53.5%) while flags per page also fell
  (4.2 vs 10.8): on this cleaner Revell typesetting the 200-DPI base
  makes fewer punctuation errors (base CER 0.36% vs 0.87%), so a
  larger share of tier disagreements are high-DPI quote garbling
  (“ ” read as ‘, *, ¥ at 300/360) rather than base errors. This is a
  base-rate effect, not a detector change — the detector was frozen.
- Two pages (244, 292) had zero flags and (essentially) zero errors:
  the gate is quiet when the base is clean.
- The P16 gold failure mode repeated in miniature: 3 ASCII-apostrophe
  transcription slips in P17 gold v1, caught by the census and fixed
  as a versioned gold v2 before scoring. Transcription tooling should
  auto-flag U+0027 in gold for curly-quote books.

## Files

`PREREGISTRATION.json` · `gold/` (v1) · `gold_v2/` + `gold_v2_seal.json`
· `run_pipeline.py` · `evaluate.py` (erratum-fixed scorer; reports raw
and normalized CER-after side by side) · `flags/` · `adjudications.jsonl`
· `census_v2.json` · `corrected/` · `eval_results.json` · this report.
Renders and OCR tiers are local-only (hashes reproducible from the
sealed PDF via run_pipeline.py).
