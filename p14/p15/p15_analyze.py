#!/usr/bin/env python3
"""P15: DPI paired ablation on the P14 gold pages (The Chinese Recorder, 1896).

Compares Tesseract OCR of the SAME 5 blind-gold pages rendered at 200/300/360 DPI.
All OCR parameters held constant (eng, PSM 3); only the pdftoppm -r value changes.
Scoring reuses p14.py's normalize/levenshtein/words so numbers are commensurable
with the P14 baseline (strict CER 76/13435, WER 33/2356 at 200 DPI).

Confusion analysis uses difflib.SequenceMatcher opcodes on the normalized
strings (deterministic alignment; an alignment method, not the Levenshtein
optimum). Error "sites" are gold character indices touched by a delete/replace
opcode, plus insertion points keyed separately. Fixed = sites erroneous at
200 DPI but clean at the comparison DPI; New = the converse. Sites erroneous
at both are "persistent" (a changed-but-still-wrong substitution at the same
gold index counts as persistent, not fixed+new).

Outputs: results.json (this directory), diffs/*.txt (per page/DPI opcode lists).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
P14 = HERE.parent
sys.path.insert(0, str(P14))
from p14 import levenshtein, normalize, words  # noqa: E402

PAGES = [32, 119, 284, 286, 501]
DPIS = [200, 300, 360]
P14_BASELINE = {"char_edits": 76, "gold_chars": 13435, "word_edits": 33, "gold_words": 2356}

CLASSES = {
    "period_comma": set(".,"),
    "curly_double_quotes": set("“”„«»"),
    "single_quotes_apostrophe": set("‘’'’‚"),
    "hyphen": set("-‐−"),
    "letters": set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def opcodes(gold: str, pred: str):
    sm = difflib.SequenceMatcher(None, gold, pred, autojunk=False)
    return [op for op in sm.get_opcodes() if op[0] != "equal"]


def class_counts(ops, gold: str, pred: str) -> dict:
    """Count error opcodes touching each character class (classes may overlap)."""
    counts = {name: {"ops": 0, "gold_chars": 0, "pred_chars": 0} for name in CLASSES}
    other = {"ops": 0}
    for tag, i1, i2, j1, j2 in ops:
        g, p = gold[i1:i2], pred[j1:j2]
        hit = False
        for name, charset in CLASSES.items():
            if (set(g) | set(p)) & charset:
                counts[name]["ops"] += 1
                counts[name]["gold_chars"] += sum(1 for c in g if c in charset)
                counts[name]["pred_chars"] += sum(1 for c in p if c in charset)
                hit = True
        if not hit:
            other["ops"] += 1
    counts["other"] = other
    return counts


def substitution_pairs(ops, gold: str, pred: str) -> dict:
    """1:1 replace pairs only (equal-length replace opcodes), e.g. '.->,' ."""
    pairs: dict[str, int] = {}
    for tag, i1, i2, j1, j2 in ops:
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for g, p in zip(gold[i1:i2], pred[j1:j2]):
                if g != p:
                    pairs[f"{g}->{p}"] = pairs.get(f"{g}->{p}", 0) + 1
    return pairs


def error_sites(ops) -> set:
    sites = set()
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("delete", "replace"):
            sites.update(range(i1, i2))
        elif tag == "insert":
            sites.add(("ins", i1))
    return sites


def main() -> int:
    gold = {p: normalize((P14 / "work" / "gold" / f"p{p:04d}.txt").read_text(encoding="utf-8")) for p in PAGES}
    results: dict = {"pages": PAGES, "dpis": DPIS, "per_dpi": {}, "fixed_new": {}}
    all_ops: dict[int, dict[int, list]] = {d: {} for d in DPIS}
    diffs_dir = HERE / "diffs"
    diffs_dir.mkdir(exist_ok=True)

    for dpi in DPIS:
        tot = {"char_edits": 0, "gold_chars": 0, "word_edits": 0, "gold_words": 0}
        per_page = {}
        merged_classes = {name: {"ops": 0, "gold_chars": 0, "pred_chars": 0} for name in CLASSES}
        merged_classes["other"] = {"ops": 0}
        merged_pairs: dict[str, int] = {}
        for p in PAGES:
            pred = normalize((HERE / f"ocr{dpi}" / f"p{p:04d}.txt").read_text(encoding="utf-8"))
            g = gold[p]
            ce = levenshtein(pred, g)
            gw, pw = words(g), words(pred)
            we = levenshtein(pw, gw)
            per_page[p] = {
                "char_edits": ce, "gold_chars": len(g), "CER": ce / len(g),
                "word_edits": we, "gold_words": len(gw), "WER": we / len(gw),
            }
            tot["char_edits"] += ce; tot["gold_chars"] += len(g)
            tot["word_edits"] += we; tot["gold_words"] += len(gw)
            ops = opcodes(g, pred)
            all_ops[dpi][p] = ops
            cc = class_counts(ops, g, pred)
            for name in merged_classes:
                for k in merged_classes[name]:
                    merged_classes[name][k] += cc[name].get(k, 0)
            for k, v in substitution_pairs(ops, g, pred).items():
                merged_pairs[k] = merged_pairs.get(k, 0) + v
            lines = [f"page {p} dpi {dpi}"]
            for tag, i1, i2, j1, j2 in ops:
                lines.append(f"{tag}: gold={g[i1:i2]!r} -> ocr={pred[j1:j2]!r}")
            (diffs_dir / f"p{p:04d}_{dpi}dpi.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        tot["CER"] = tot["char_edits"] / tot["gold_chars"]
        tot["WER"] = tot["word_edits"] / tot["gold_words"]
        results["per_dpi"][dpi] = {
            "totals": tot, "per_page": per_page,
            "confusion_classes": merged_classes,
            "substitution_pairs_top": dict(sorted(merged_pairs.items(), key=lambda kv: -kv[1])[:15]),
        }

    base = results["per_dpi"][200]["totals"]
    results["baseline_reproduced"] = (
        base["char_edits"] == P14_BASELINE["char_edits"]
        and base["gold_chars"] == P14_BASELINE["gold_chars"]
        and base["word_edits"] == P14_BASELINE["word_edits"]
        and base["gold_words"] == P14_BASELINE["gold_words"]
    )

    for dpi in (300, 360):
        fixed = new = persistent = 0
        per_page = {}
        for p in PAGES:
            s200 = error_sites(all_ops[200][p])
            snew = error_sites(all_ops[dpi][p])
            f, n, per = len(s200 - snew), len(snew - s200), len(s200 & snew)
            fixed += f; new += n; persistent += per
            per_page[p] = {"fixed": f, "new": n, "persistent": per,
                           "sites_200": len(s200), "sites_dpi": len(snew)}
        results["fixed_new"][dpi] = {"fixed": fixed, "new": new, "persistent": persistent,
                                     "per_page": per_page}

    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
