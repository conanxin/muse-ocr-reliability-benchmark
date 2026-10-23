#!/usr/bin/env python3
"""P16 evaluation: score detector flags against sealed gold.

Definitions (frozen with the detector):
  * Scope punctuation (gold side): . , “ ” ‘ ’ ' - —   (period, comma, curly
    quotes, apostrophe, hyphen/em-dash — the five P16 classes).
  * A gold<->baseline error REGION is a difflib opcode block (delete/replace/
    insert) where the gold substring contains a scope char, or the baseline
    substring contains a detector PUNCT_SET char, or an inserted baseline
    string contains a PUNCT_SET char. Insert regions are points [i, i+1).
  * A flag's baseline span is mapped to gold coordinates through the same
    opcodes (monotone block mapping). A flag is TP when its gold span
    intersects an error region; an error region is covered when >=1 flag
    intersects it. Precision is flag-level, Recall is region-level.
  * CER before = strict CER of the untouched 200-DPI baseline vs gold.
    CER after = CER of an experiment copy where ONLY human-confirmed fixes
    (adjudications.jsonl: verdict 'fix' with replacement text per flag span)
    are applied to the baseline.
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from p14 import levenshtein, normalize  # noqa: E402
from detector import PUNCT_SET  # noqa: E402

SCOPE_GOLD = set(".,") | set("“”‘’'") | set("-—")


def opcodes(gold: str, base: str):
    return difflib.SequenceMatcher(None, gold, base, autojunk=False).get_opcodes()


def error_regions(ops, gold: str, base: str) -> list[list[int]]:
    regions = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        g, b = gold[i1:i2], base[j1:j2]
        if tag == "insert":
            if any(c in PUNCT_SET for c in b):
                regions.append([i1, i1 + 1])
        elif any(c in SCOPE_GOLD for c in g) or any(c in PUNCT_SET for c in b):
            regions.append([i1, max(i2, i1 + 1)])
    return regions


def base_to_gold_span(ops, s: int, e: int) -> tuple[int, int]:
    """Map a baseline span [s,e) to gold coordinates via opcode blocks."""
    def map_index(j: int, is_end: bool) -> int:
        for tag, i1, i2, j1, j2 in ops:
            if tag == "insert":
                if j == j1:
                    return i1
                continue
            if j1 <= j < j2 or (is_end and j == j2 and j > j1):
                if tag == "equal":
                    return i1 + (j - j1)
                # replace/delete: proportional position inside the block
                if j2 == j1:
                    return i1
                frac = (j - j1) / max(1, (j2 - j1))
                return i1 + min(i2 - i1, int(frac * (i2 - i1)))
        return ops[-1][2] if ops else 0
    gs = map_index(s, False)
    ge = map_index(max(s, e - 1), True) + (1 if e > s else 0)
    return gs, max(ge, gs + 1)


def intersects(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def evaluate_page(gold: str, base: str, flags: list[dict]) -> dict:
    ops = opcodes(gold, base)
    regions = error_regions(ops, gold, base)
    covered = set()
    tp = 0
    flag_rows = []
    for fl in flags:
        gs, ge = base_to_gold_span(ops, fl["base_span"][0], fl["base_span"][1])
        hit = [k for k, r in enumerate(regions) if intersects((gs, ge), r)]
        if hit:
            tp += 1
            covered.update(hit)
        flag_rows.append({"flag_id": fl["flag_id"], "gold_span": [gs, ge],
                          "hit_regions": hit, "tp": bool(hit)})
    fn = len(regions) - len(covered)
    return {"error_regions": len(regions), "flags": len(flags), "tp_flags": tp,
            "fp_flags": len(flags) - tp, "covered_regions": len(covered),
            "fn_regions": fn, "flag_rows": flag_rows}


def apply_fixes(base: str, fixes: list[dict]) -> str:
    """fixes: [{base_span:[s,e], replacement:str}] applied right-to-left."""
    out = base
    for fx in sorted(fixes, key=lambda f: -f["base_span"][0]):
        s, e = fx["base_span"]
        out = out[:s] + fx["replacement"] + out[e:]
    return out


def main(argv) -> int:
    # evaluate.py CONFIG.json  (see config schema in README/p16 notes)
    cfg = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = {"pages": {}, "totals": {}}
    tot = {"flags": 0, "tp": 0, "fp": 0, "regions": 0, "covered": 0, "fn": 0,
           "char_edits_before": 0, "char_edits_after": 0, "gold_chars": 0}
    for spec in cfg["pages"]:
        page = spec["page"]
        gold = normalize(Path(spec["gold"]).read_text(encoding="utf-8"))
        base = normalize(Path(spec["base200"]).read_text(encoding="utf-8"))
        flags = [json.loads(l) for l in Path(spec["flags"]).read_text(encoding="utf-8").splitlines() if l.strip()]
        ev = evaluate_page(gold, base, flags)
        before = levenshtein(base, gold)
        after = None
        if spec.get("adjudications"):
            adj = [json.loads(l) for l in Path(spec["adjudications"]).read_text(encoding="utf-8").splitlines() if l.strip()]
            by_id = {f["flag_id"]: f for f in flags}
            fixes = [{"base_span": a.get("base_span", by_id[a["flag_id"]]["base_span"]),
                      "replacement": a["replacement"]}
                     for a in adj if a.get("verdict") == "fix" and a["flag_id"] in by_id]
            corrected = apply_fixes(base, fixes)
            Path(spec["corrected_out"]).write_text(corrected, encoding="utf-8")
            after = levenshtein(corrected, gold)
            ev["fixes_applied"] = len(fixes)
        ev["cer_before"] = before / len(gold)
        ev["char_edits_before"] = before
        if after is not None:
            ev["cer_after"] = after / len(gold)
            ev["char_edits_after"] = after
        result["pages"][page] = ev
        tot["flags"] += ev["flags"]; tot["tp"] += ev["tp_flags"]; tot["fp"] += ev["fp_flags"]
        tot["regions"] += ev["error_regions"]; tot["covered"] += ev["covered_regions"]; tot["fn"] += ev["fn_regions"]
        tot["char_edits_before"] += before; tot["gold_chars"] += len(gold)
        if after is not None:
            tot["char_edits_after"] += after
    tot["precision"] = tot["tp"] / tot["flags"] if tot["flags"] else None
    tot["recall"] = tot["covered"] / tot["regions"] if tot["regions"] else None
    tot["cer_before"] = tot["char_edits_before"] / tot["gold_chars"]
    if tot["char_edits_after"]:
        tot["cer_after"] = tot["char_edits_after"] / tot["gold_chars"]
    result["totals"] = tot
    Path(cfg["out"]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(tot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
