# P16 ERRATUM (2026-10-23, issued during P17 Phase 1 reconciliation)

## What changes

- `eval_results.json` reported total char_edits_after = **72** (CER_after 0.6584%),
  with p120 char_edits_after = 16.
- Correct figures: total char_edits_after = **71** (CER_after **0.6492%**),
  p120 char_edits_after = **15**. Per-page: p33 23, p120 15, p287 24, p503 9.
- Corrected machine-readable record: `eval_results_v2.json`.
  `eval_results.json` is preserved unchanged as the historical report.

## Root cause (verified, not conjectured)

`evaluate.py` computed CER_after as Levenshtein(apply_fixes(normalized_base), gold)
on the **raw in-memory corrected string**, without re-applying `p14.normalize`.
The p0120-007 fix deletes one spurious ':' from "topic. : : 2.", leaving two
consecutive spaces ("topic. :  2."). The raw string therefore carries one extra
space versus its normalized form, inflating the distance by exactly 1.
The project scoring definition (P14 `score`: normalize both sides, then
Levenshtein) applied to the written `corrected/` files yields 15 for p120.

## Verification performed

1. Isolated-copy rerun of the frozen `evaluate.py` + `eval_config_final.json`
   reproduced `eval_results.json` and all `corrected/` files **bit-identically**
   (SHA-256 match) — the pipeline is deterministic; the discrepancy is definitional,
   not an input or environment drift.
2. Two independent Levenshtein implementations (p14.py two-row DP and a
   full-matrix DP) computed on the preserved `corrected/` files against
   `gold_eval/` (v2 seals) both give 23 / 15 / 24 / 9 = 71.
3. The single differing position was localized: the double space at
   "important topic. :  2. Advantages" in the raw corrected p120 string.
4. Only p120 is affected; p33/p287/p503 agree under both scorings.

## What does NOT change

- CER_before: 95 / 10,936 = 0.8687% (that path normalized both sides).
- Flags (43), adjudications (TP 23 / FP 20), FN census (4), Precision 53.5%,
  Recall 85.2%, review load — all unaffected (they do not depend on the
  corrected-string distance).
- Gold files and seals (v1 and v2) are untouched by this erratum.

## Disposition

Historical report preserved; this erratum + `eval_results_v2.json` are the
versioned correction. P17's evaluator applies normalize-before-score and
carries a regression check for this defect.
