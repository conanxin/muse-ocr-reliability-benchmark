#!/usr/bin/env python3
"""P17 evaluation — dual track, kept strictly separate:

A) MECHANICAL (region-based): reuses p16/evaluate.py's evaluate_page
   unchanged — a flag counts as TP iff its base span intersects a
   punctuation-containing base<->gold error region.
B) ADJUDICATED (image-based): verdicts from p17/adjudications.jsonl,
   each flag judged against the page image; FN = punctuation error
   sites found by an independent full-page census of punctuation
   diffs (base vs gold) that no flag covers.

CER before/after uses the protocol definition: normalize BOTH sides,
then Levenshtein. (P16 erratum fix: the corrected string is
re-normalized before scoring; a regression test below fails loudly
if a fix leaves a double space that changes the score silently —
the raw and normalized scores are both reported.)

Usage: evaluate.py CONFIG_JSON
Config keys: pages, gold_dir, base_dir, flags_dir, adj_path,
             corrected_dir, out_path
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "p16"))
from p14 import normalize, levenshtein  # noqa: E402
import evaluate as p16ev  # noqa: E402  p16/evaluate.py (mechanical parts reused)


def main(argv) -> int:
    cfg = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    pages = cfg["pages"]
    adj = {}
    if Path(cfg["adj_path"]).exists():
        for line in Path(cfg["adj_path"]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                adj[a["flag_id"]] = a
    result = {"pages": {}, "totals": {}}
    tot = dict(flags=0, mech_tp=0, mech_fp=0, mech_regions=0, mech_covered=0,
               adj_tp=0, adj_fp=0, fixes=0, edits_before=0, edits_after=0,
               edits_after_raw=0, gold_chars=0)
    for p in pages:
        name = f"p{p:04d}"
        gold = normalize(Path(cfg["gold_dir"], name + ".txt").read_text(encoding="utf-8"))
        base = normalize(Path(cfg["base_dir"], name + ".txt").read_text(encoding="utf-8"))
        flags = [json.loads(l) for l in
                 Path(cfg["flags_dir"], name + ".jsonl").read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        mech = p16ev.evaluate_page(gold, base, flags)
        fixes, adj_tp, adj_fp = [], 0, 0
        for fl in flags:
            a = adj.get(fl["flag_id"])
            if a is None:
                continue
            if a["verdict"] == "fix":
                adj_tp += 1
                fixes.append({"base_span": a.get("base_span", fl["base_span"]),
                              "replacement": a["replacement"]})
            elif a["verdict"] == "no-fix":
                adj_fp += 1
        before = levenshtein(base, gold)
        corrected = p16ev.apply_fixes(base, fixes)
        after = levenshtein(normalize(corrected), gold)
        after_raw = levenshtein(corrected, gold)
        Path(cfg["corrected_dir"]).mkdir(parents=True, exist_ok=True)
        Path(cfg["corrected_dir"], name + ".txt").write_text(corrected, encoding="utf-8")
        result["pages"][str(p)] = {
            "gold_chars": len(gold), "flags": len(flags),
            "mechanical": mech,
            "adjudicated": {"tp": adj_tp, "fp": adj_fp, "fixes": len(fixes)},
            "char_edits_before": before, "char_edits_after": after,
            "char_edits_after_raw_scoring": after_raw,
            "cer_before": before / len(gold), "cer_after": after / len(gold),
        }
        tot["flags"] += len(flags); tot["mech_tp"] += mech["tp_flags"]
        tot["mech_fp"] += mech["fp_flags"]; tot["mech_regions"] += mech["error_regions"]
        tot["mech_covered"] += mech["covered_regions"]
        tot["adj_tp"] += adj_tp; tot["adj_fp"] += adj_fp; tot["fixes"] += len(fixes)
        tot["edits_before"] += before; tot["edits_after"] += after
        tot["edits_after_raw"] += after_raw; tot["gold_chars"] += len(gold)
    t = result["totals"]
    t.update(tot)
    t["mechanical"] = {
        "precision": tot["mech_tp"] / tot["flags"] if tot["flags"] else None,
        "recall_region": tot["mech_covered"] / tot["mech_regions"] if tot["mech_regions"] else None,
        "fn_regions": tot["mech_regions"] - tot["mech_covered"]}
    t["adjudicated"] = {
        "precision": tot["adj_tp"] / (tot["adj_tp"] + tot["adj_fp"]) if (tot["adj_tp"] + tot["adj_fp"]) else None}
    t["cer_before"] = tot["edits_before"] / tot["gold_chars"]
    t["cer_after"] = tot["edits_after"] / tot["gold_chars"]
    t["review_load_total"] = tot["flags"]
    t["reviews_per_confirmed_fix"] = (tot["flags"] / tot["fixes"]) if tot["fixes"] else None
    Path(cfg["out_path"]).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(json.dumps(t, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
