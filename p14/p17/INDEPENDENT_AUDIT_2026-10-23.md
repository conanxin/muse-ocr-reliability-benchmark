# P17 independent readback audit — 2026-10-23

**Status:** P17 measured and independently arithmetic/file verified within the public experiment-branch scope. **No automatic correction or new GitHub release authorized.**

## Evidence inspected
- [P17 reported outcome](REPORT.md), `PREREGISTRATION.json`, `eval_results.json`, `census_v2.json`, `adjudications.jsonl`, `gold_v2_seal.json`.
- Every PDF page's **committed** `gold_v2/pNNNN.txt`, `work/ocr/pNNNN.txt` and `corrected/pNNNN.txt` (six of each, all files accessible via GitHub).
- P16 [versioned erratum](../p16/ERRATUM.md), [corrected results](../p16/eval_results_v2.json) and apostrophe review log.

Using Unicode NFC, whitespace collapse and Levenshtein distance as in `p14.normalize` / the official scorer, a **separate implementation** gives:

| PDF page | Gold chars | Baseline edit count | After human-approved edits |
|---:|---:|---:|---:|
| 52 | 2,026 | 10 | 8 |
| 100 | 1,529 | 6 | 3 |
| 148 | 1,994 | 2 | 0 |
| 197 | 1,609 | 16 | 11 |
| 244 | 455 | 0 | 0 |
| 292 | 2,007 | 1 | 1 |
| **Total** | **9,620** | **35** | **23** |

- **CER:** 35/9620 = **0.3638%** before; 23/9620 = **0.2391%** after; absolute reduction 12 edits, relative reduction **34.29%**.
- `adjudications.jsonl`: 25 unique flags, exactly 7 `fix` and 18 `no-fix` decisions. Human/image adjudication (per Muse log): **Precision 7/25 = 28.0%**, **Recall 7/8 = 87.5%** (one missed punctuation error on p197). `census_v2.json` lists 8 site records, 7 covered and 1 uncovered.
- Frozen mechanical-region evaluator: precision 5/25 = 20%; region recall 5/8 = 62.5%. This is a different unit/definition than human-reviewed punctuation-site scores; **do not combine the numerators and denominators**.
- Seven confirmed flags can reduce 12 *character edits* because a flag may cover multi-character deletion/replacement. One example is p0197-002, which replaces a baseline comma span with `. To`. Flags/edits/regions are distinct counting units.

## P16 reconciliation
- The reported original P16 72-edit after-score had one extra whitespace edit in p120; `ERRATUM.md` correctly explains the post-edit normalization difference. The correct recorded score is **71/10,936 = 0.6492%**; baseline 95/10,936 = 0.8687%; improvement **25.26%**. Historical `eval_results.json` remains preserved and `eval_results_v2.json` is canonical.

## Sensitivity to the post-blind gold revision
- P17 originally blind-sealed gold v1 before OCR. Later image-review-driven gold v2 changed **exactly three ASCII apostrophes to typographic apostrophes**, across p52 (two) and p197 (one). Six committed v1/v2 gold pairs were fetched and compared: edit distance v1→v2 = 2,0,0,1,0,0 for pages 52,100,148,197,244,292.
- Holding all OCR and corrected outputs fixed, **v1** would yield **38 → 26** edits and **v2** yields **35 → 23** edits. **Both versions reduce the Levenshtein count by exactly 12**. Thus the direction and absolute improvement are robust to these three character-level gold amendments; the *percentages* depend on the declared gold version.
- The claimed source-image glyph verifications for the apostrophes and the page-196 photograph plate are documented by Muse, **not independently visually checked here**. The temporal pre-OCR blind-seal assertion is supported by task records, not independently established by Git commit timestamps alone.

## Interpretation and boundaries
- The P16 detector SHA `fd3142bb77a42a5598aa13ce7646ed97f1ab2de996005114fe2c082e335fe478` is recorded unchanged in P17 preregistration; the new source, gold and output comprise a distinct English historical book.
- P17 has **8 adjudicated positive punctuation sites on six pages**. 7/8 vs P16 23/27 is **descriptively similar, not proof of statistically equivalent recall**; uncertainty is wide for eight positives (simple Wilson 95% interval approximately 52.9–97.8%, which does not incorporate page clustering).
- The precision decline from 53.5% to 28.0% **may be consistent with lower base error prevalence**, but page layout/typography and high-DPI false-positive mechanisms also differ; the experiment alone does not isolate the sole cause.
- `35→23` is **human-confirmed repair**, not an automated punctuation rewrite. The per-flag correction unit can span letters and spacing, so the CER benefit should not be advertised as solely single-character punctuation fixes.
- A different English historical book is an encouraging out-of-source replication but is not evidence for traditional Chinese, other OCR engines, or current printing.

## Publication discipline / suggested next stage
Keep `main`, `v0.1.0`, P9/P10 and the original gold histories unchanged. **P18 proposal (not executed)**: convert the human review workflow into a strict, read-only candidate queue with source crops, reviewer adjudication, immutable v1/v2 gold and baseline hashes, and an explicit normalized scoring contract. Measure candidate-review time and **net edits removed per review** on a new, preregistered source, alongside precision/recall; avoid training/evaluating candidate ranking on the P17 test pages.

This report is an **independent audit summary**, not a new benchmark run on the original PDF images.
