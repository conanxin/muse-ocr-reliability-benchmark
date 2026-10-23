# P16 Independent Artifact Check — 2026-10-23

**Status:** MEASURED, WITH ONE PUBLIC-ARTIFACT CONSISTENCY DISCREPANCY TO RECONCILE.

This audit reads only files already published on the P14/P16 experimental branch. It **does not** re-review the local source scan or assume the manually adjudicated labels are proven from the public artifacts alone.

## Verified directly from the GitHub experiment branch

- 43 flags across PDF pages 33/120/287/503: 19, 11, 7, 6 respectively.
- `adjudications.jsonl`: 43 unique flag IDs, each present among the flagged IDs; 23 `fix`, 20 `keep`.
- Reported manual-adjudication score: precision `23/43 = 53.49%`; recall `23/27 = 85.19%` (4 manual false negatives, from Muse's source-image adjudication and Notion notes).
- Frozen mechanical scorer `eval_results.json`: precision `17/43 = 39.53%`; region recall `17/29 = 58.62%`. These use strict mapped-span intersection against *mixed letter/punctuation error regions*, so they are not the same unit or scoring rubric as the manual source-image judgements.
- Reported CER before review: `95/10,936 = 0.8687%`. The public branch does **not** contain the four `work/ocr/pNNNN.txt` originals, so this baseline cannot be recomputed independently from public GitHub files alone.
- Reported CER after: `72/10,936 = 0.6584%` (`eval_results.json`).

## One-edit discrepancy requiring reconciliation

Using the current committed `p14/p16/gold_eval/pNNNN.txt` and `p14/p16/corrected/pNNNN.txt` files, `p14.normalize()` (Unicode NFC, collapse whitespace, trim) and an independently implemented Levenshtein distance:

| Page | Committed corrected vs gold, independent char edits | eval_results.json char_edits_after |
|---|---:|---:|
| 33 | 23 | 23 |
| 120 | **15** | **16** |
| 287 | 24 | 24 |
| 503 | 9 | 9 |
| **Total** | **71** | **72** |

Thus the committed final corrected texts yield `71 / 10,936 = 0.6492%`, while the published score JSON claims `72 / 10,936 = 0.6584%`.

**The page 120 value of 15 was independently recomputed with Python using the exact p14.normalize() and the same standard Levenshtein recurrence.** This is a real artifact-accounting inconsistency, not a rounding difference. The cause (evaluation order, local file revisions, scorer run inputs, or another source) is **not yet established**. Do not quietly overwrite either source or claim the issue is resolved.

## Gold-label provenance caveat

The blind-gold v1 seal precedes candidate generation. After flag/false-negative review, v2 changed ten ASCII apostrophes to curly apostrophes where the original print was reportedly verified. Both seal records and the detector freeze record are published; the v1 full transcripts and original source-image crops are not independently reviewed here. Such a source-backed gold correction is legitimate *if independently confirmed*, but the final held-out metrics depend on v2 and must explicitly disclose that post-hoc adjudication and the original blind-seal history.

## Next actions (scoped)

1. In Muse's environment (where the P14 baseline OCR, source scans and v1/v2 gold are actually present), re-run the frozen evaluator **on a temporary copy**, capturing file hashes of gold, input baseline, correction output and results before/after.
2. Reconcile the page 120 `15 vs 16` discrepancy; determine which committed file/score was produced from which input snapshot. If correcting artifacts, retain the old score and a transparent amendment.
3. Reconfirm 10 apostrophe changes against scan-only crops without using OCR candidate characters as ground-truth. Keep both seals.
4. Only then treat a selected follow-up as a fresh evaluation. Do not change the original PDF, P9/P10 Notion texts, GitHub main, or the v0.1.0 release.
5. Continue measuring **human review yield and cost**, not automatic punctuation replacements; any new detector rules need unexamined held-out pages from a different volume/source.

**Conclusion:** P16's conservative human review mechanism is promising within four same-volume pages, but the public scorer/corrected text discrepancy must be resolved before presenting a single definitive post-correction CER as reproducible.
